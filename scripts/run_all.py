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
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DOLT_IMAGE, DUMPS, MYSQL_CONTAINER, ROOT, data_dir, databases,  # noqa: E402
                    dumps_dir, human, run)
from dolt_dialect import defer_indexes, transform  # noqa: E402
from load_dolt import per_row_commits  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")
MYSQL_IMAGE = os.environ.get("MYSQL_TIMING_IMAGE", "mysql:9.7.2")
MYSQL_NAME = "doltsamples-mysql-timing"
MYSQL_DATA = os.path.join(ROOT, "data", "mysql")
MYSQL_PW = "timing"
DOLT_HOST_BASE = "doltsamples-dolt-runner"
DOLT_HOST = DOLT_HOST_BASE

# cheapest first, so the table fills in early and an interrupted run still says something
PHASES = ["mysql", "dolt_oneshot", "mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"]
ENGINE = {"mysql": "MySQL", "mysql_rowwise": "MySQL", "dolt_oneshot": "Dolt",
          "dolt_rowinsert": "Dolt", "dolt_rowcommit": "Dolt"}
PER_ROW = {"mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"}
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


def note(p, key, **fields):
    p["units"].setdefault(key, {}).update(fields)
    p["updated"] = time.time()
    save_progress(p)


# ------------------------------------------------------------------ MySQL ---
def mysql_up():
    state = run("docker", "inspect", "-f", "{{.State.Status}}", MYSQL_NAME).stdout.strip()
    if state == "running":
        return
    run("docker", "rm", "-f", MYSQL_NAME)
    os.makedirs(MYSQL_DATA, exist_ok=True)
    p = run("docker", "run", "-d", "--name", MYSQL_NAME,
            "--label", "doltsamples.transient=true", "--label", "doltsamples.role=mysql-timing",
            "-e", f"MYSQL_ROOT_PASSWORD={MYSQL_PW}",
            "-v", f"{MYSQL_DATA}:/var/lib/mysql", "-v", f"{DUMPS}:/dumps:ro",
            MYSQL_IMAGE, "mysqld", "--local-infile=1", "--skip-log-bin")
    if p.returncode != 0:
        sys.exit(f"could not start {MYSQL_IMAGE}: {p.stderr.strip()[:200]}")
    for _ in range(300):
        if run("docker", "exec", MYSQL_NAME, "mysql", f"-p{MYSQL_PW}", "-uroot",
               "-e", "SELECT 1").returncode == 0:
            return
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


def mysql_datadir_bytes():
    p = run("docker", "exec", MYSQL_NAME, "du", "-sb", "/var/lib/mysql")
    return int(p.stdout.split()[0]) if p.stdout.split() else 0


def mysql_dir_bytes(db):
    p = run("docker", "exec", MYSQL_NAME, "du", "-sb", f"/var/lib/mysql/{db}")
    return int(p.stdout.split()[0]) if p.stdout.split() else None


def mysql_fresh():
    """A brand-new empty server for every database, so shared files are attributable."""
    run("docker", "rm", "-f", MYSQL_NAME)
    run("docker", "run", "--rm", "-v", f"{MYSQL_DATA}:/d", "--entrypoint", "sh", DOLT_IMAGE,
        "-c", "rm -rf /d/* /d/.[!.]* 2>/dev/null || true")
    mysql_up()


# ------------------------------------------------------------------- Dolt ---
def dolt_host_up(mode):
    """One long-lived Dolt container per data directory, so loads are `docker exec` like MySQL's.

    The name is always built from the constant, never from the current value of DOLT_HOST: doing the
    latter appended the mode once per call and left a trail of containers named
    `doltsamples-dolt-runner-oneshot-oneshot-rowinsert-...`, one leaked per mode change."""
    want = f"{DOLT_HOST_BASE}-{mode}"
    state = run("docker", "inspect", "-f", "{{.State.Status}}", want).stdout.strip()
    if state != "running":
        run("docker", "rm", "-f", want)
        run("docker", "run", "-d", "--name", want, "--label", "doltsamples.transient=true",
            "-v", f"{data_dir(mode)}:/var/lib/dolt", "-v", f"{DUMPS}:/dumps",
            "--entrypoint", "sh", DOLT_IMAGE, "-c", "sleep infinity")
    globals()["DOLT_HOST"] = want

def dolt_prepare(db, phase, indexes="deferred"):
    mode = MODE[phase] + ("" if indexes == "deferred" or phase not in PER_ROW else "_inline")
    src = os.path.join(dumps_dir(phase in PER_ROW), f"{db}.sql")
    out_dir = os.path.join(DUMPS, "dolt", mode)
    os.makedirs(out_dir, exist_ok=True)
    sql, notes = transform(open(src, "rb").read(), db)
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


def chunk_sql(path, statements_per_chunk=150_000):
    """Split a prepared dump into files of at most N statements.

    The per-row-commit loads were killed by the kernel — exit 137 — on the three largest databases,
    every time, because one `dolt sql` process builds the whole commit history in memory and this
    host has 15.5 GB. `oracle_sh` died at 262,915 of 918,843 rows on the retry, at the same kind of
    point as the first attempt. Splitting the file lets each process exit and give its memory back;
    the data directory is the only thing carried between them, and Dolt picks up where it left off.

    It changes the timing slightly — a process start per chunk — and that is disclosed rather than
    hidden: the alternative is a measurement that cannot be taken at all on this machine.
    """
    out, chunk, n, count = [], [], 0, 0
    head = []
    with open(path, "rb") as fh:
        for line in fh:
            if not out and not chunk and (line.startswith(b"/*") or line.startswith(b"SET ")
                                          or line.startswith(b"CREATE DATABASE")
                                          or line.startswith(b"USE ")):
                head.append(line)
                continue
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
    target = os.path.join(data_dir(mode), db)
    if os.path.isdir(target):
        run("docker", "run", "--rm", "-v", f"{data_dir(mode)}:/var/lib/dolt", "--entrypoint", "sh",
            DOLT_IMAGE, "-c", f"rm -rf /var/lib/dolt/{db}")
    os.makedirs(data_dir(mode), exist_ok=True)
    inside, notes = dolt_prepare(db, phase, indexes)
    host_path = os.path.join(DUMPS, "dolt", mode, f"{db}.sql")
    parts = ([os.path.join("/dumps/dolt", mode, os.path.basename(q))
              for q in chunk_sql(host_path)] if phase == "dolt_rowcommit" else [inside])
    if len(parts) > 1:
        notes.append(f"loaded in {len(parts)} chunks so no single process is OOM-killed")

    # `docker exec` into a container that is already up, exactly as the MySQL loads do. Creating a
    # container per load cost a measured 0.36s twice over, which was most of the smallest Dolt
    # timings and nothing of MySQL's.
    dolt_host_up(mode)
    started = time.time()
    for part in parts:
        p = run("docker", "exec", "-w", "/var/lib/dolt", DOLT_HOST,
                "dolt", "--data-dir", "/var/lib/dolt", "sql", "--file", part)
        if p.returncode != 0:
            break
    load_s = time.time() - started
    if not os.path.isdir(target):
        return {"error": (p.stderr or p.stdout).strip()[:300], "seconds": round(load_s, 1)}
    # A directory is not proof of a load. Three per-row-commit loads truncated mid-table and were
    # recorded as successful because the directory existed: `employees` stopped at 1,854,812 of
    # 3.9M rows with `titles` never created. The exit status and the tail of the output are kept for
    # every load now, and the row count is checked below.
    outcome = {"exit_code": p.returncode,
               "output_tail": ((p.stderr or "") + (p.stdout or "")).strip()[-400:]}

    final_started = time.time()
    final = ("dolt gc" if phase == "dolt_rowcommit" else
             'dolt add -A && dolt commit -m "import from mysql-megasamples" '
             '--author "megasamples <megasamples@localhost>" ; dolt gc')
    started = time.time()
    run("docker", "exec", "-w", f"/var/lib/dolt/{db}", DOLT_HOST, "sh", "-c", final)
    settle_s = time.time() - started

    size = run("docker", "run", "--rm", "-v", f"{data_dir(mode)}:/d", "--entrypoint", "sh",
               DOLT_IMAGE, "-c",
               f"du -sb /d/{db}; du -sb /d/{db}/.dolt/stats 2>/dev/null || echo 0")
    lines = [l.split()[0] for l in size.stdout.splitlines() if l.split()]
    total = int(lines[0]) if lines else None
    stats = int(lines[1]) if len(lines) > 1 else 0
    outcome.update({"seconds": round(load_s, 1), "settle_seconds": round(settle_s, 1),
                    "bytes": (total - stats) if total else None, "stats_bytes": stats,
                    "notes": notes})
    if p.returncode != 0:
        outcome["error"] = f"load exited {p.returncode}: {outcome['output_tail'][-200:]}"
        return outcome
    if outcome["bytes"] is None:
        outcome["error"] = "the loaded directory could not be measured"
        return outcome
    short = truncated(db, mode)
    if short:
        outcome["error"] = "the load did not finish: " + short
    return outcome


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
        p = run("docker", "run", "--rm", "-v", f"{data_dir(mode)}:/var/lib/dolt",
                "-w", "/var/lib/dolt", "--entrypoint", "dolt", DOLT_IMAGE,
                "--use-db", db, "sql", "-r", "csv", "-q", f"SELECT COUNT(*) FROM `{t}`")
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
                    help="run each unit N times and keep the median, for the cheap phases")
    ap.add_argument("--resume", action="store_true",
                    help="continue a run recorded on another machine (normally refused)")
    a = ap.parse_args()

    busy = [l for l in run("docker", "ps", "--format", "{{.Names}}").stdout.splitlines()
            if l.startswith(("megasamples-", "doltsamples-")) and "mysql-timing" not in l
            and "dolt-runner" not in l and l != "megasamples-mysql"]
    if busy and not a.allow_busy:
        sys.exit("These containers are running and will compete with the measurements:\n  "
                 + "\n  ".join(busy)
                 + "\n\nStop them first — `make down` here and in ../mysql-megasamples, keeping\n"
                   "megasamples-mysql, which is the source of the dumps. --allow-busy overrides.")

    dbs = a.only or databases()
    phases = a.phase or PHASES
    if a.restart:
        p = {"started": time.time(), "units": {}, "host": fingerprint()}
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

    units = [(phase, db) for phase in phases for db in order]
    todo = [(ph, db) for ph, db in units if p["units"].get(f"{ph}/{db}", {}).get("status") != "done"]
    print(f"{len(units)} units, {len(todo)} to do "
          f"({len(units) - len(todo)} already recorded)\n", flush=True)

    for i, (phase, db) in enumerate(todo, 1):
        # A run outlives most things, including the Docker daemon. A restart mid-run once left a
        # unit recorded `done` with no size and no verification, so stop at the first unit that
        # cannot reach the daemon rather than recording 100 more of the same.
        if run("docker", "version", "-f", "{{.Server.Version}}").returncode != 0:
            print("\ndocker is not answering; stopping so no unit is recorded unverified. "
                  "restart it and run the same command again; recorded progress is kept.",
                  flush=True)
            return 2
        key = f"{phase}/{db}" + ("" if a.indexes == "deferred" else "/inline")
        note(p, key, status="running", started=time.time(), phase=phase, database=db)
        started = time.time()
        runs = []
        try:
            for _ in range(max(1, a.repeat)):
                runs.append(mysql_load(db, phase in PER_ROW, a.indexes)
                            if phase.startswith("mysql") else dolt_load(db, phase, a.indexes))
                if "error" in runs[-1]:
                    break
            res = dict(runs[-1])
            if len(runs) > 1 and all("error" not in x for x in runs):
                times = sorted(x["seconds"] for x in runs)
                res["seconds"] = times[len(times) // 2]
                res["seconds_all"] = times
                res["repeats"] = len(times)
        except Exception as exc:                                   # noqa: BLE001
            res = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        res["status"] = "error" if "error" in res else "done"
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
