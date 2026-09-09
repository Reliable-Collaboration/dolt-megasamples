#!/usr/bin/env python3
"""Shared settings and helpers for the MySQL-to-Dolt comparison.

The experiment has one question: for the same data, how much disk does Dolt use compared with
MySQL? Everything here exists to make that comparison honest -- the same rows, loaded the same way,
measured the same way, with the engines' own storage left to do whatever it does.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMPS = os.path.join(ROOT, "build", "dumps")
DATA = os.path.join(ROOT, "data", "dolt")

# The three ways the same rows are put into Dolt. They differ only in how the load is written, never
# in what ends up being stored logically -- same tables, same rows, same indexes -- which is what
# makes the sizes comparable.
MODES = {
    "oneshot":   "mysqldump's extended INSERTs; one Dolt commit for the whole database",
    "rowinsert": "one INSERT statement per row; still one Dolt commit for the whole database",
    "rowcommit": "one INSERT statement per row, and one Dolt commit after every row",
    # The same two loads with every secondary index and constraint left in place for the whole
    # load, which is what the row-by-row phases used to do. Kept as their own modes so both
    # policies can be measured and reported side by side rather than one replacing the other.
    "rowinsert_inline": "one INSERT statement per row, indexes maintained during the load",
    "rowcommit_inline": "one commit per row, indexes maintained during the load",
}


def data_dir(mode="oneshot"):
    return DATA if mode == "oneshot" else f"{DATA}-{mode}"


def dumps_dir(per_row=False):
    return os.path.join(DUMPS, "rowwise") if per_row else DUMPS
# An override so the report and the figures can be rendered from a results file other than the live
# one -- checking a new table or a new figure against full coverage without waiting hours for a run,
# and without writing over the run's own evidence while it is still being collected.
RESULTS = os.environ.get("DOLTSAMPLES_RESULTS") or os.path.join(ROOT, "build", "results.json")

MYSQL_CONTAINER = os.environ.get("MEGASAMPLES_CONTAINER", "megasamples-mysql")
MYSQL_IMAGE = os.environ.get("MEGASAMPLES_IMAGE", "mysql-megasamples:dev")
DOLT_IMAGE = os.environ.get(
    "DOLT_IMAGE",
    "dolthub/dolt-sql-server@sha256:38d5e900583267f35e36ad738e13f202e62860b351aa4c088dceaf7dbaed7ab6")

# ---------------------------------------------------------------------- memory ---
# WSL2 gave this host 15.5 GB and ran out of it. Nothing here was bounded: the loads created a
# container per mode and never removed them, so up to seven were alive at once, and a `dolt sql`
# building a multi-million-commit history will take whatever it can reach -- which under WSL2 means
# the whole VM, not just the container.
#
# Every container this repository starts now carries an explicit ceiling, and the run keeps at most
# one worker alive beside the source server. The budget totals 9.25 GB, which is what this host can
# give up without the rest of it suffering.
#
#   source MySQL   1 GB   only needed to answer the row checks; it is *stopped* during a Dolt load
#   one worker    the rest, sized from this host: MemTotal less 2.5 GB for the host and the helper
#   helper       256 MB   the short-lived `du` and `rm -rf` containers
#
# The worker's share is computed rather than written down, because the right number is a property of
# the machine. On this host WSL2 takes its default half of 31.7 GB, and raising that in .wslconfig
# raises the worker with it without touching any code.
#
# The worker gets 12 GB because nothing else is running while it works. The dumps are a bind mount
# and the source server is not consulted between the first statement and the last, so it is stopped
# for the duration of a Dolt load and started again for the row-count verification that follows.
# That is not a saving of 1 GB but of everything the source server holds -- and it costs only the
# twenty seconds it takes to come back, which falls outside the timed section.
#
# --memory-swap set equal to --memory turns swap off for the container. That matters more than the
# ceiling on WSL2: a process allowed to swap does not fail, it drags the whole VM down with it.
def _host_memory_gb():
    """What this machine actually has, so the budget is not a constant written for one host."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 8.0


HOST_GB = _host_memory_gb()
# The worker gets what is left after the host keeps 2.5 GB for itself, Docker and page cache, and
# after the 256 MB helper. The source server is stopped during a Dolt load, so it is not subtracted.
# Floors and ceilings keep it sane on very small and very large machines.
_worker_gb = max(2, min(48, int(HOST_GB - 2.5 - 0.25)))

MEM_SOURCE = os.environ.get("DOLTSAMPLES_MEM_SOURCE", "1g")
MEM_WORKER = os.environ.get("DOLTSAMPLES_MEM_WORKER", f"{_worker_gb}g")
MEM_HELPER = os.environ.get("DOLTSAMPLES_MEM_HELPER", "256m")


def mem(limit):
    """Docker arguments capping a container's memory, with swap disabled."""
    return ["--memory", limit, "--memory-swap", limit]


# schemas that are not sample data: MySQL's own, and the provenance registry the image carries
SKIP = {"mysql", "information_schema", "performance_schema", "sys", "megasamples"}


def run(*args, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(list(args), **kw)


def mysql(sql, container=None):
    p = run("docker", "exec", container or MYSQL_CONTAINER, "mysql", "-uroot", "-proot",
            "-N", "--batch", "-e", sql)
    if p.returncode != 0:
        sys.exit(f"could not query {container or MYSQL_CONTAINER}: {p.stderr.strip()[:200]}\n"
                 f"Is mysql-megasamples running? `cd ../mysql-megasamples && make up`")
    return [line.split("\t") for line in p.stdout.splitlines() if line.strip()]


def databases(container=None):
    rows = mysql("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name",
                 container)
    return [r[0] for r in rows if r[0] not in SKIP]


def dolt(*args, mounts=(), workdir=None, mode="oneshot", db=None):
    """Run a dolt CLI command in a throwaway container over one database's data directory.

    Each database has its own `--data-dir` -- `data/dolt-<mode>/<db>`, holding the repository at
    `data/dolt-<mode>/<db>/<db>` -- because Dolt opens every database under its data directory when
    it starts, so a shared directory made each command pay for all 21. Passing `db` mounts that
    database's directory; without it the mode's whole tree is mounted, which is the old behaviour
    and is wrong for anything that names a database.
    """
    root = os.path.join(data_dir(mode), db) if db else data_dir(mode)
    cmd = ["docker", "run", "--rm", *mem(MEM_WORKER),
           "--label", "doltsamples.transient=true",
           "-v", f"{root}:/var/lib/dolt",
           "-v", f"{DUMPS}:/dumps"]
    for host, inside in mounts:
        cmd += ["-v", f"{host}:{inside}"]
    cmd += ["-w", workdir or "/var/lib/dolt", "--entrypoint", "dolt", DOLT_IMAGE, *args]
    return run(*cmd)


def load_results():
    return json.load(open(RESULTS, encoding="utf-8")) if os.path.exists(RESULTS) else {}


def save_results(data):
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    json.dump(data, open(RESULTS, "w", encoding="utf-8"), indent=2, sort_keys=True)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
