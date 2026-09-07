#!/usr/bin/env python3
"""Run the whole experiment, timing every load, and record progress as it goes.

  python3 scripts/run_all.py [--only sakila] [--phase dolt_rowcommit] [--restart]

The first version of this experiment measured only size. Time is the other half of the answer — a
storage format that is a fifth the size but takes twenty times as long to load is a different
proposition — so every load here is timed on a wall clock, in both engines, from the same dumps.

**Five loads of every database:**

| key | engine | how the rows are written |
|---|---|---|
| `mysql` | MySQL 9.7.2 | mysqldump's extended `INSERT`s |
| `mysql_rowwise` | MySQL 9.7.2 | one `INSERT` per row |
| `dolt_oneshot` | Dolt 2.3.2 | extended `INSERT`s, one commit for the database |
| `dolt_rowinsert` | Dolt 2.3.2 | one `INSERT` per row, one commit for the database |
| `dolt_rowcommit` | Dolt 2.3.2 | one `INSERT` per row, one commit **per row** |

MySQL is loaded into a **fresh, empty server** rather than read from the megasamples image, so both
engines are timed and sized from the same input under the same conditions. `mysql_rowwise` is the
honest counterpart to Dolt's per-row loads: MySQL commits every autocommitted statement, so one
`INSERT` per row is one durable transaction per row, which is the closest thing MySQL has to what
Dolt does with a commit per row.

**Designed to be watched.** Every unit of work writes `build/progress.json` the moment it finishes,
so `python3 scripts/progress.py` says what is done, what is running, how long it has taken and what
is left. The run is resumable: a unit already recorded is skipped, so it can be stopped and picked
up. Units run cheapest-first and smallest-first within a phase, so the results table fills in from
the top rather than arriving all at once at the end.
"""
import argparse, json, os, re, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DOLT_IMAGE, DUMPS, MEM_HELPER, MEM_WORKER, MYSQL_CONTAINER, RESULTS,
                    ROOT, data_dir, databases, mem,  # noqa: E402
                    dumps_dir, human, run)
from dolt_dialect import defer_indexes, transform  # noqa: E402
from load_dolt import per_row_commits  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")
MYSQL_IMAGE = os.environ.get("MYSQL_TIMING_IMAGE", "mysql:9.7.2")
MYSQL_NAME = "doltsamples-mysql-timing"
MYSQL_DATA = os.path.join(ROOT, "data", "mysql")
MYSQL_PW = "timing"
# One Dolt container, not one per mode. There used to be five, because each mounted a different
# data directory -- but `--data-dir` is an argument, not a mount. Mounting the parent `data/` once
# and passing the mode's subdirectory does the same work in a single container, which is five fewer
# things holding memory and five fewer things to leak, rebuild or find stale.
DOLT_HOST = "doltsamples-dolt-runner"
DATA_ROOT = os.path.join(ROOT, "data")


def inside_data(mode):
    """Where a mode's directory appears inside the Dolt container."""
    return "/data/" + os.path.basename(data_dir(mode))


def dolt_root(mode, db):
    """The `--data-dir` for one database: a directory holding that database and nothing else.

    Dolt opens every database under its data directory when it starts. Giving all 21 a shared
    directory therefore made each load pay to open everything loaded before it -- and by the end of
    the per-row-commit phase that was 128 GB across 20 databases, which is what exhausted a 15.5 GB
    host. With the directory that size, even `CREATE DATABASE` is killed for memory; against an
    empty one it returns immediately.

    It also quietly contaminated the timings. A database loaded twentieth paid a startup cost that
    the one loaded first did not, so the per-row-commit figures were partly a measure of load order.
    One directory per database removes both problems: constant memory, and a load that costs the
    same wherever it comes in the phase.
    """
    return f"{inside_data(mode)}/{db}"


def dolt_repo(mode, db):
    """The repository itself, one level inside its own data directory."""
    return f"{dolt_root(mode, db)}/{db}"

# cheapest first, so the table fills in early and an interrupted run still says something
PHASES = ["mysql", "dolt_oneshot", "mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"]
ENGINE = {"mysql": "MySQL", "mysql_rowwise": "MySQL", "dolt_oneshot": "Dolt",
          "dolt_rowinsert": "Dolt", "dolt_rowcommit": "Dolt"}
PER_ROW = {"mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"}
# How much of a per-row-commit dump one `dolt sql` process is asked to hold. This is the number that
# decides whether the load fits in memory: the process keeps the commit history it is building, so
# the peak scales with the chunk and not with the database. It was 150,000 and `employees` -- 3.9
# million rows, one commit each -- still exhausted a 15.5 GB host. Set by --chunk-statements.
CHUNK_STATEMENTS = 50_000
# The phase name is not the mode name. `data_dir()` prefixes anything that is not "oneshot" with
# "dolt-", so passing the phase produced data/dolt-dolt_oneshot and the measurement pass, which
# looks in data/dolt, found nothing at all.
MODE = {"dolt_oneshot": "oneshot", "dolt_rowinsert": "rowinsert", "dolt_rowcommit": "rowcommit"}


# ---------------------------------------------------------------- progress ---
def fingerprint():
    """Enough of the machine to tell one host's run from another's."""
    import platform
    return f"{platform.node()}|{platform.machine()}|{os.cpu_count()}"


def load_progress():
    """Resume a run — but never silently resume *someone else's*.

    `build/progress.json` is committed, because it is the record of how long each load took and is
    part of the evidence. That creates a trap for anyone reproducing this: a fresh clone already
    contains 105 completed units, so `make run` would skip every one of them and produce a report
    of measurements taken on a different machine. If the fingerprint does not match, the run starts
    clean rather than inheriting results it did not produce.
    """
    if not os.path.exists(PROGRESS):
        return {"started": time.time(), "units": {}, "host": fingerprint()}
    with open(PROGRESS, encoding="utf-8") as fh:
        p = json.load(fh)
    if p.get("host") and p["host"] != fingerprint():
        print(f"build/progress.json was recorded on another machine ({p['host']});\n"
              f"starting a fresh run on this one ({fingerprint()}).\n"
              f"Pass --resume to continue the recorded run anyway.\n", flush=True)
        return {"started": time.time(), "units": {}, "host": fingerprint()}
    p["host"] = fingerprint()
    return p


def save_progress(p):
    os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(p, fh, indent=2, sort_keys=True)
    os.replace(tmp, PROGRESS)


def note(p, key, replace=False, **fields):
    """Record a unit. `replace=True` writes a fresh record instead of merging into the old one.

    Merging left the `error` of a failed attempt sitting on the record of the retry that succeeded:
    `status: done` and an error message in the same unit, which is worse than either alone."""
    if replace:
        p["units"][key] = fields
    else:
        p["units"].setdefault(key, {}).update(fields)
    p["updated"] = time.time()
    save_progress(p)


# ------------------------------------------------------------------ MySQL ---
def ensure_data_root(*paths):
    """Make the data directories exist as the invoking user, before Docker can make them as root."""
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    for p in paths:
        os.makedirs(p, exist_ok=True)


def only_worker(keep):
    """Leave exactly one worker container running beside the source server.

    The loads used to create a container per mode and never remove it, so by the last phase seven
    were alive at once -- two MySQL servers and five Dolt runners -- each holding memory that the
    phase actually running had no use for. This stops everything except the one worker the current
    phase needs, which is what keeps the budget to source + one worker."""
    alive = [l for l in run("docker", "ps", "--format", "{{.Names}}").stdout.splitlines()
             if l.startswith(("doltsamples-dolt-runner", "doltsamples-mysql-timing"))
             and l != keep]
    if alive:
        run("docker", "stop", "-t", "30", *alive)


def helper(*args, volumes=(), workdir=None, entrypoint="sh"):
    """A short-lived container for `du` and `rm -rf`, capped so it cannot compete for memory."""
    cmd = ["docker", "run", "--rm", *mem(MEM_HELPER)]
    for v in volumes:
        cmd += ["-v", v]
    if workdir:
        cmd += ["-w", workdir]
    return run(*cmd, "--entrypoint", entrypoint, DOLT_IMAGE, *args)


def mysql_up():
    state = run("docker", "inspect", "-f", "{{.State.Status}}", MYSQL_NAME).stdout.strip()
    if state == "running":
        return
    run("docker", "rm", "-f", MYSQL_NAME)
    os.makedirs(MYSQL_DATA, exist_ok=True)
    # The buffer pool is set explicitly rather than left to MySQL's default sizing, which reads the
    # host's memory and not the container's: on a 15.5 GB host inside a 5 GB container it will
    # happily plan for more than it is allowed to have and be killed for it.
    p = run("docker", "run", "-d", "--name", MYSQL_NAME, *mem(MEM_WORKER),
            "--label", "doltsamples.transient=true", "--label", "doltsamples.role=mysql-timing",
            "-e", f"MYSQL_ROOT_PASSWORD={MYSQL_PW}",
            "-v", f"{MYSQL_DATA}:/var/lib/mysql", "-v", f"{DUMPS}:/dumps:ro",
            MYSQL_IMAGE, "mysqld", "--local-infile=1", "--skip-log-bin",
            "--innodb-buffer-pool-size=2G", "--innodb-redo-log-capacity=512M")
    if p.returncode != 0:
        sys.exit(f"could not start {MYSQL_IMAGE}: {p.stderr.strip()[:200]}")
    # Probe over TCP, not the socket. On a fresh data directory the MySQL entrypoint initialises the
    # database using a *temporary* server started with --skip-networking, then shuts it down and
    # starts the real one. A socket probe connects to that temporary server, so readiness was
    # declared during initialisation and the load that followed hit "ERROR 2002: Can't connect to
    # local MySQL server through socket". The temporary server refuses TCP, so this waits for the
    # real one. Two consecutive successes, because the moment between the two servers also passes a
    # single check.
    good = 0
    for _ in range(600):
        if run("docker", "exec", MYSQL_NAME, "mysql", f"-p{MYSQL_PW}", "-uroot",
               "--protocol=TCP", "-h", "127.0.0.1", "-e", "SELECT 1").returncode == 0:
            good += 1
            if good >= 2:
                return
        else:
            good = 0
        time.sleep(1)
    sys.exit("the timing MySQL never became ready")


def mysql_load(db, per_row, indexes="deferred"):
    """Drop and reload one database, timing only the load itself.

    Three things here are deliberate:

    * **the same SQL Dolt gets.** MySQL used to load mysqldump's original while Dolt loaded a
      transformed copy, so the engines were not given the same input. Both now load the transformed
      file, which is still valid MySQL — it only has clauses removed that Dolt cannot parse.
    * **no `--force`.** Continuing past errors is what let loads look successful while being short.
    * **the whole data directory is measured**, not the database's folder. InnoDB keeps shared files
      — ibdata1, undo, redo — that belong to no database and came to 5.4% of the total; measuring one
      database at a time against an empty-server baseline charges them to the database that caused
      them, which is what Dolt's per-database directory already does.
    """
    # MySQL now loads the same transformed file Dolt does, so it has to exist before the MySQL
    # phase runs — and the MySQL phases run first.
    phase = "dolt_rowinsert" if per_row else "dolt_oneshot"
    inside, _ = dolt_prepare(db, phase, indexes)
    only_worker(MYSQL_NAME)
    mysql_fresh()
    baseline = mysql_datadir_bytes()
    started = time.time()
    p = run("docker", "exec", MYSQL_NAME, "sh", "-c", f"mysql -p{MYSQL_PW} -uroot < {inside}")
    seconds = time.time() - started
    if p.returncode != 0:
        return {"error": mysql_error(p), "seconds": round(seconds, 1)}
    run("docker", "exec", MYSQL_NAME, "mysql", f"-p{MYSQL_PW}", "-uroot", "-e", "FLUSH TABLES")
    return {"seconds": round(seconds, 1),
            "bytes": mysql_datadir_bytes() - baseline,
            "database_dir_bytes": mysql_dir_bytes(db),
            "baseline_bytes": baseline}


def mysql_error(p):
    """The real message, not the password warning.

    `mysql` writes "[Warning] Using a password on the command line interface can be insecure" to
    stderr on every single invocation. Truncating stderr to a few hundred characters therefore
    recorded the warning and threw the actual error away."""
    lines = [l for l in ((p.stderr or "") + "\n" + (p.stdout or "")).splitlines()
             if l.strip() and "Using a password on the command line" not in l]
    return " / ".join(lines).strip()[:300] or f"exit {p.returncode} with no message"


def du_bytes(container, path):
    """Size of a path, or an exception. Never a zero standing in for a failed measurement.

    This returned 0 when `du` failed, and it is the source of every MySQL size in the report:
    `bytes = mysql_datadir_bytes() - baseline`. A failed baseline therefore charged the database
    the whole ~205 MB of an empty server, and a failed second reading made the size negative.
    Neither raised, and the first looks entirely plausible in a table.
    """
    p = run("docker", "exec", container, "du", "-sb", path)
    first = p.stdout.split()[0] if p.stdout.split() else ""
    if p.returncode != 0 or not first.isdigit():
        raise RuntimeError(f"could not measure {path} in {container}: "
                           f"exit {p.returncode} {(p.stderr or '').strip()[:120]}")
    return int(first)


def mysql_datadir_bytes():
    return du_bytes(MYSQL_NAME, "/var/lib/mysql")


def mysql_dir_bytes(db):
    try:
        return du_bytes(MYSQL_NAME, f"/var/lib/mysql/{db}")
    except RuntimeError:
        return None   # a database directory need not exist; the datadir total must


def mysql_fresh():
    """A brand-new empty server for every database, so shared files are attributable."""
    # Create the directory as this user before anything bind-mounts it. Docker creates a missing
    # bind-mount source itself, as root -- and the cleanup container below mounts data/mysql, so on
    # the first run after `make clean-data` it created data/ root-owned. Every later
    # `os.makedirs(data/dolt-...)` then failed with EACCES and the entire Dolt phase errored out,
    # 21 units in a row, with the load never attempted.
    ensure_data_root(MYSQL_DATA)
    run("docker", "rm", "-f", MYSQL_NAME)
    helper("-c", "rm -rf /d/* /d/.[!.]* 2>/dev/null || true", volumes=[f"{MYSQL_DATA}:/d"])
    mysql_up()


# ------------------------------------------------------------------- Dolt ---
def dolt_host_up():
    """One long-lived Dolt container per data directory, so loads are `docker exec` like MySQL's.

    One container serves every mode, because the mode is a `--data-dir` argument rather than a
    mount."""
    want = DOLT_HOST
    only_worker(want)
    state = run("docker", "inspect", "-f", "{{.State.Status}}", want).stdout.strip()
    # "running" is not the same as usable. These containers outlive the directories they mount: if
    # data/ is deleted and recreated between runs, the container keeps a mount on the old inode,
    # `docker inspect` still reports it running, and every `docker exec` into it fails with "OCI
    # runtime exec failed". Ask it to do something trivial rather than trusting its status.
    if state == "running" and run("docker", "exec", want, "true").returncode != 0:
        state = "stale"
    if state == "running":
        # Stopping the harness kills the Python process, not the `dolt sql` it started inside this
        # container. That orphan keeps writing while the next load clears the directory underneath
        # it, which produced a half-written repository and an exit 1 that looked like a data bug.
        run("docker", "exec", want, "sh", "-c",
            "pkill -x dolt 2>/dev/null; sleep 1; pkill -9 -x dolt 2>/dev/null; true")
    if state != "running":
        run("docker", "rm", "-f", want)
        run("docker", "run", "-d", "--name", want, *mem(MEM_WORKER),
            "--label", "doltsamples.transient=true",
            "-v", f"{DATA_ROOT}:/data", "-v", f"{DUMPS}:/dumps",
            "--entrypoint", "sh", DOLT_IMAGE, "-c", "sleep infinity")

def dolt_prepare(db, phase, indexes="deferred"):
    mode = MODE[phase] + ("" if indexes == "deferred" or phase not in PER_ROW else "_inline")
    src = os.path.join(dumps_dir(phase in PER_ROW), f"{db}.sql")
    out_dir = os.path.join(DUMPS, "dolt", mode)
    os.makedirs(out_dir, exist_ok=True)
    sql, notes = transform(open(src, "rb").read(), db, databases())
    # Deferring the indexes only means anything for a row-by-row load: with extended INSERTs the
    # index is built over batches anyway, and the point of the variant is to separate the cost of
    # writing rows one at a time from the cost of maintaining an index while doing it.
    if indexes == "deferred" and phase in PER_ROW:
        sql, more = defer_indexes(sql)
        notes += more
    if phase == "dolt_rowcommit":
        sql, n = per_row_commits(sql)
        notes.append(f"a DOLT_COMMIT after each of {n:,} INSERT statements")
    open(os.path.join(out_dir, f"{db}.sql"), "wb").write(sql)
    return f"/dumps/dolt/{mode}/{db}.sql", notes


def chunk_sql(path, statements_per_chunk=50_000):
    """Split a prepared dump into files of at most N statements.

    The per-row-commit loads were killed by the kernel — exit 137 — on the three largest databases,
    every time, because one `dolt sql` process builds the whole commit history in memory and this
    host has 15.5 GB. `oracle_sh` died at 262,915 of 918,843 rows on the retry, at the same kind of
    point as the first attempt. Splitting the file lets each process exit and give its memory back;
    the data directory is the only thing carried between them, and Dolt picks up where it left off.

    It changes the timing slightly — a process start per chunk — and that is disclosed rather than
    hidden: the alternative is a measurement that cannot be taken at all on this machine.
    """
    # Every chunk is a separate `dolt sql` process with its own session, so each one needs the
    # preamble: the character set, the checks, and above all `USE <db>` — the INSERTs are
    # unqualified. Blank lines are skipped rather than ending the preamble; when they ended it, a
    # `SET` added at the very top of the file cut `USE` out of every chunk after the first.
    out, chunk, count = [], [], 0
    head, in_head = [], True
    with open(path, "rb") as fh:
        for line in fh:
            if in_head:
                if not line.strip():
                    continue
                if (line.startswith(b"/*") or line.startswith(b"--") or line.startswith(b"SET ")
                        or line.startswith(b"CREATE DATABASE") or line.startswith(b"USE ")):
                    head.append(line)
                    continue
                in_head = False
            chunk.append(line)
            if line.rstrip().endswith(b";"):
                count += 1
            if count >= statements_per_chunk:
                out.append(head + chunk)
                chunk, count = [], 0
    if chunk:
        out.append(head + chunk)
    paths = []
    for i, body in enumerate(out):
        q = f"{path}.part{i:03d}"
        with open(q, "wb") as fh:
            fh.writelines(body)
        paths.append(q)
    return paths


def dolt_load(db, phase, indexes="deferred"):
    mode = MODE[phase] + ("" if indexes == "deferred" or phase not in PER_ROW else "_inline")
    # `target` is this database's own data directory; the repository lands one level inside it.
    target = os.path.join(data_dir(mode), db)
    repo = os.path.join(target, db)
    if os.path.isdir(target):
        helper("-c", f"rm -rf {dolt_root(mode, db)}", volumes=[f"{DATA_ROOT}:/data"])
    # created as this user, before Docker can create it as root
    os.makedirs(target, exist_ok=True)
    inside, notes = dolt_prepare(db, phase, indexes)
    host_path = os.path.join(DUMPS, "dolt", mode, f"{db}.sql")
    parts = ([os.path.join("/dumps/dolt", mode, os.path.basename(q))
              for q in chunk_sql(host_path, CHUNK_STATEMENTS)]
             if phase == "dolt_rowcommit" else [inside])
    if len(parts) > 1:
        notes.append(f"loaded in {len(parts)} chunks so no single process is OOM-killed")

    # `docker exec` into a container that is already up, exactly as the MySQL loads do. Creating a
    # container per load cost a measured 0.36s twice over, which was most of the smallest Dolt
    # timings and nothing of MySQL's.
    dolt_host_up()
    started = time.time()
    for part in parts:
        p = run("docker", "exec", "-w", dolt_root(mode, db), DOLT_HOST,
                "dolt", "--data-dir", dolt_root(mode, db), "sql", "--file", part)
        if p.returncode != 0:
            break
    load_s = time.time() - started
    # The repository, not its parent: the parent is created before the load runs, so its existence
    # proves nothing about whether Dolt wrote anything.
    if not os.path.isdir(repo):
        return {"error": (dolt_error_tail(p) or (p.stderr or p.stdout).strip())[:300],
                "seconds": round(load_s, 1)}
    # A directory is not proof of a load. Three per-row-commit loads truncated mid-table and were
    # recorded as successful because the directory existed: `employees` stopped at 1,854,812 of
    # 3.9M rows with `titles` never created. The exit status and the tail of the output are kept for
    # every load now, and the row count is checked below.
    outcome = {"exit_code": p.returncode,
               "output_tail": dolt_error_tail(p)}

    final_started = time.time()
    # Every mode ends committed. The per-row-commit mode used to end with `dolt gc` alone, on the
    # reasoning that each row had already been committed -- but deferring the indexes leaves the
    # `ALTER TABLE ... ADD` rebuild in the working set, so the repository was measured with seven
    # tables modified and uncommitted. The rebuild belongs in the last commit, and a repository with
    # an uncommitted working set is not the thing being measured. `--allow-empty` covers the case
    # where there is nothing outstanding, which is what happens with the indexes left inline.
    commit = ('dolt add -A && dolt commit --allow-empty --author '
              '"megasamples <megasamples@localhost>" -m ')
    final = (commit + '"rebuild deferred indexes" ; dolt gc' if phase == "dolt_rowcommit" else
             commit + '"import from mysql-megasamples" ; dolt gc')
    started = time.time()
    run("docker", "exec", "-w", dolt_repo(mode, db), DOLT_HOST, "sh", "-c", final)
    settle_s = time.time() - started

    size = helper("-c", f"du -sb {dolt_repo(mode, db)}; "
                        f"du -sb {dolt_repo(mode, db)}/.dolt/stats 2>/dev/null || echo 0",
                  volumes=[f"{DATA_ROOT}:/data"])
    lines = [l.split()[0] for l in size.stdout.splitlines() if l.split()]
    total = int(lines[0]) if lines else None
    stats = int(lines[1]) if len(lines) > 1 else 0
    outcome.update({"seconds": round(load_s, 1), "settle_seconds": round(settle_s, 1),
                    "bytes": (total - stats) if total else None, "stats_bytes": stats,
                    "notes": notes})
    # A nonzero exit is not automatically a failed load, and Dolt's message cannot be used to tell
    # the difference: it names the statement it choked on only when writing to a TTY, so under
    # `docker exec` all that arrives is "syntax error at position 383 near 'character'".
    #
    # The row check is the arbiter instead, and it is a better one. `truncated()` walks MySQL's
    # table list and counts every table on both sides, so a load that dropped a table or stopped
    # early fails it. If every table is present and complete, the load delivered the data, and
    # whatever Dolt refused was a schema object after the rows -- stored routines, which it does not
    # implement, or a view whose body it cannot parse: `oracle_co.product_reviews` selects through a
    # JSON_TABLE whose column carries a `character set`, and Dolt stops at that word. That shortfall
    # is real and is counted in the report's "Schema objects Dolt would not take", not hidden.
    if outcome["bytes"] is None:
        outcome["error"] = "the loaded directory could not be measured"
        return outcome
    short = truncated(db, mode)
    if short:
        outcome["error"] = ("the load did not finish: " + short
                            + (f" (exit {p.returncode})" if p.returncode else ""))
    elif p.returncode != 0:
        notes.append("Dolt refused something after the rows and exited "
                     f"{p.returncode}; every table matches MySQL, so the shortfall is in the "
                     "schema objects the report counts separately. It said: "
                     + outcome["output_tail"][:200])
        outcome["schema_object_error"] = outcome["output_tail"][:300]
    return outcome


def dolt_output(p):
    """Everything Dolt said, with the noise removed.

    `dolt sql --file` writes "Processed N% of the file" thousands of times and a result table for
    every `CALL DOLT_COMMIT`, so a failed per-row-commit load's raw tail is progress bars and
    `+------+` and nothing about what went wrong."""
    text = ((p.stderr or "") + "\n" + (p.stdout or "")).replace("\r", "\n")
    return [l.strip() for l in text.splitlines()
            if l.strip() and not set(l.strip()) <= set("+-| ") and "of the file" not in l]


def dolt_error_tail(p):
    """The error and the statement that caused it.

    Keeping only lines that contain the word "error" threw away the statement on the next line --
    which is the half that says *what* Dolt would not take, and the half the caller needs to tell a
    rejected stored routine from a real failure. The tail now runs from the last error line to the
    end of the output."""
    lines = dolt_output(p)
    starts = [i for i, l in enumerate(lines)
              if any(w in l.lower() for w in ("error", "cannot", "unsupported", "not found"))]
    chosen = lines[starts[-1]:] if starts else lines[-6:]
    return " / ".join(chosen)[-600:]


def truncated(db, mode):
    """Compare the row count in Dolt against MySQL, table by table, and say what is short.

    Counted one table at a time with a generous timeout: a single UNION over every table of a
    repository with millions of commits does not return, which is how the truncation was first
    mistaken for a measuring problem."""
    tables = [r[0] for r in mysql_rows_query(
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema='{db}' AND table_type='BASE TABLE' ORDER BY table_name")]
    # No tables means the reference server did not answer, not that the load is clean. Returning
    # None here once let a load that never ran at all be recorded as successful.
    if not tables:
        raise RuntimeError(f"cannot verify {db}: the reference MySQL returned no table list")
    for t in tables:
        want = int(mysql_rows_query(f"SELECT COUNT(*) FROM `{db}`.`{t}`")[0][0])
        # Counted through the one long-lived container, not a new one per table: 248 tables meant
        # 248 container creations, and each carried the same ceiling anyway.
        dolt_host_up()
        p = run("docker", "exec", "-w", dolt_root(mode, db), DOLT_HOST, "dolt",
                "--data-dir", dolt_root(mode, db), "--use-db", db,
                "sql", "-r", "csv", "-q", f"SELECT COUNT(*) FROM `{t}`")
        got = next((int(l.strip()) for l in p.stdout.splitlines() if l.strip().isdigit()), None)
        if got is None and p.returncode != 0 and not p.stdout.strip():
            raise RuntimeError(f"cannot verify {db}.{t}: {(p.stderr or '').strip()[:200]}")
        if got != want:
            return f"{db}.{t} has {got if got is not None else 'no'} rows, expected {want:,}"
    return None


def mysql_rows_query(sql):
    p = run("docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot", "-proot", "-N", "--batch",
            "-e", sql)
    return [l.split("\t") for l in p.stdout.splitlines() if l.strip()]


# ------------------------------------------------------------------- run ---
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append")
    ap.add_argument("--phase", action="append", choices=PHASES)
    ap.add_argument("--restart", action="store_true", help="forget previous progress and redo all")
    ap.add_argument("--indexes", choices=["deferred", "inline"], default="deferred",
                    help="deferred (default): for the row-by-row loads, drop secondary indexes and "
                         "foreign keys during the load and rebuild them afterwards, with unique and "
                         "foreign-key checks off — the way anyone actually bulk-loads. inline: "
                         "maintain every index on every row, which is the slow way and the one the "
                         "first runs measured")
    ap.add_argument("--allow-busy", action="store_true",
                    help="time the loads even with other stacks running (they will compete)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each unit up to N times and keep the median of every sample")
    ap.add_argument("--repeat-budget", type=float, default=180.0,
                    help="stop repeating a unit once it has spent this many seconds, so a cheap "
                         "load gets its spread and an expensive one is a single honest sample")
    ap.add_argument("--chunk-statements", type=int, default=CHUNK_STATEMENTS,
                    help="statements per chunk for the per-row-commit loads. Lower it if a load is "
                         "killed for memory (exit 137); it costs a process start per chunk")
    ap.add_argument("--floor-gb", type=float, default=8.0,
                    help="stop before starting a unit if less than this many GB are free. The "
                         "per-row-commit phase is the one that can fill a disk: it wrote 160 GB "
                         "across the corpus, most of it in the last few databases")
    ap.add_argument("--resume", action="store_true",
                    help="continue a run recorded on another machine (normally refused)")
    a = ap.parse_args()
    globals()["CHUNK_STATEMENTS"] = a.chunk_statements

    busy = [l for l in run("docker", "ps", "--format", "{{.Names}}").stdout.splitlines()
            if l.startswith(("megasamples-", "doltsamples-")) and "mysql-timing" not in l
            and "dolt-runner" not in l and l != "megasamples-mysql"]
    if busy and not a.allow_busy:
        sys.exit("These containers are running and will compete with the measurements:\n  "
                 + "\n  ".join(busy)
                 + "\n\nStop them first — `make down` here and in ../mysql-megasamples, keeping\n"
                   "megasamples-mysql, which is the source of the dumps. --allow-busy overrides.")

    ensure_data_root()
    dbs = a.only or databases()
    phases = a.phase or PHASES
    if a.indexes == "inline" and not a.phase:
        # Deferral only applies to the row-by-row loads: the one-shot loads use mysqldump's extended
        # INSERTs and build their indexes over batches either way, so running them again under
        # `--indexes inline` would spend the time to reproduce byte-identical numbers under a second
        # set of keys. Ask for them explicitly with --phase if you want the duplicate measurement.
        phases = [ph for ph in phases if ph in PER_ROW]
        print("--indexes inline: running the row-by-row phases only "
              f"({', '.join(phases)}); the one-shot loads are unaffected by index deferral\n",
              flush=True)
    if a.restart:
        p = {"started": time.time(), "units": {}, "host": fingerprint()}
        # A restart replaces these measurements, so the file the report reads has to go with them.
        # collect.py merges each finished unit into build/results.json, which means a restart that
        # left the old file in place would keep every value for every unit the new run does not
        # reach -- a report blending two runs, with nothing on its face to say so. Only a full
        # restart does this: `--only` and `--phase` are deliberate partial re-measurements.
        if not a.only and not a.phase and os.path.exists(RESULTS):
            os.replace(RESULTS, RESULTS + ".superseded")
            print(f"  . --restart: moved {os.path.relpath(RESULTS, ROOT)} aside to "
                  f"{os.path.basename(RESULTS)}.superseded; these runs replace it\n", flush=True)
    elif a.resume and os.path.exists(PROGRESS):
        p = json.load(open(PROGRESS, encoding="utf-8"))
    else:
        p = load_progress()
    p["databases"] = dbs
    p["phases"] = phases
    save_progress(p)

    # smallest first inside each phase, so the slow phases still produce results early
    rows = {}
    for db in dbs:
        out = run("docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot", "-proot", "-N", "--batch",
                  "-e", f"SELECT COALESCE(SUM(table_rows),0) FROM information_schema.tables "
                        f"WHERE table_schema='{db}'")
        rows[db] = int(out.stdout.strip() or 0)
    order = sorted(dbs, key=lambda d: rows[d])

    # The results key carries the index policy, and so must the "already done" test: without it an
    # `--indexes inline` run skipped every unit the deferred run had already recorded.
    def key_of(phase, db):
        return f"{phase}/{db}" + ("" if a.indexes == "deferred" else "/inline")

    units = [(phase, db) for phase in phases for db in order]
    todo = [(ph, db) for ph, db in units
            if p["units"].get(key_of(ph, db), {}).get("status") != "done"]
    print(f"{len(units)} units, {len(todo)} to do "
          f"({len(units) - len(todo)} already recorded)\n", flush=True)

    for i, (phase, db) in enumerate(todo, 1):
        # A run outlives most things, including the Docker daemon. A restart mid-run once left a
        # unit recorded `done` with no size and no verification, so stop at the first unit that
        # cannot reach the daemon rather than recording 100 more of the same.
        free_gb = shutil.disk_usage(ROOT).free / 1e9
        if free_gb < a.floor_gb:
            print(f"\n{free_gb:.1f} GB free, below the {a.floor_gb:.0f} GB floor; stopping with "
                  f"{len(todo) - i + 1} units left. Recorded progress is kept: free space and run "
                  f"the same command again, or raise --floor-gb.", flush=True)
            return 3
        if run("docker", "version", "-f", "{{.Server.Version}}").returncode != 0:
            print("\ndocker is not answering; stopping so no unit is recorded unverified. "
                  "restart it and run the same command again; recorded progress is kept.",
                  flush=True)
            return 2
        key = key_of(phase, db)
        note(p, key, replace=True, status="running", started=time.time(),
             phase=phase, database=db, indexes=a.indexes)
        started = time.time()
        runs = []
        try:
            # Repeats are what turn a number into a number with a spread, but repeating a load that
            # takes three hours would put the run past a week. So `--repeat` is a maximum, and a
            # unit stops repeating once it has spent `--repeat-budget` seconds: the cheap loads get
            # their spread, the expensive ones are honestly reported as single samples, and which
            # is which is recorded per unit rather than decided by hand.
            spent = 0.0
            for _ in range(max(1, a.repeat)):
                began = time.time()
                runs.append(mysql_load(db, phase in PER_ROW, a.indexes)
                            if phase.startswith("mysql") else dolt_load(db, phase, a.indexes))
                spent += time.time() - began
                if "error" in runs[-1] or spent > a.repeat_budget:
                    break
            res = dict(runs[-1])
            if len(runs) > 1 and all("error" not in x for x in runs):
                times = sorted(x["seconds"] for x in runs)
                res["seconds"] = times[len(times) // 2]
                res["seconds_all"] = times
                res["repeats"] = len(times)
                # Disk is the headline number, so it gets the same treatment time does: the median
                # of every repeat, with all of them kept. Recording only the last repeat hid how
                # repeatable a size is, and for the per-row-commit loads it is the least repeatable
                # number in the experiment.
                sizes = sorted(x["bytes"] for x in runs if x.get("bytes") is not None)
                if len(sizes) == len(runs):
                    res["bytes"] = sizes[len(sizes) // 2]
                    res["bytes_all"] = sizes
        except Exception as exc:                                   # noqa: BLE001
            res = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        res["status"] = "error" if "error" in res else "done"
        res["samples"] = len(runs)
        res["finished"] = time.time()
        res["wall_seconds"] = round(time.time() - started, 1)
        note(p, key, **res)

        mark = "x" if res["status"] == "error" else "."
        size = human(res["bytes"]) if res.get("bytes") else "—"
        print(f"  {mark} [{i}/{len(todo)}] {phase:<15} {db:<22} "
              f"{res.get('seconds', 0):>8.1f}s  {size:>10}"
              + (f"   {res['error'][:70]}" if "error" in res else ""), flush=True)

    print("\nall requested units complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
