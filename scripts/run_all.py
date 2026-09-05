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
from dolt_dialect import transform  # noqa: E402
from load_dolt import per_row_commits  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")
MYSQL_IMAGE = os.environ.get("MYSQL_TIMING_IMAGE", "mysql:9.7.2")
MYSQL_NAME = "doltsamples-mysql-timing"
MYSQL_DATA = os.path.join(ROOT, "data", "mysql")
MYSQL_PW = "timing"

# cheapest first, so the table fills in early and an interrupted run still says something
PHASES = ["mysql", "dolt_oneshot", "mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"]
ENGINE = {"mysql": "MySQL", "mysql_rowwise": "MySQL", "dolt_oneshot": "Dolt",
          "dolt_rowinsert": "Dolt", "dolt_rowcommit": "Dolt"}
PER_ROW = {"mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"}


# ---------------------------------------------------------------- progress ---
def load_progress():
    if os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as fh:
            return json.load(fh)
    return {"started": time.time(), "units": {}}


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


def mysql_load(db, per_row):
    """Drop and reload one database, timing only the load itself."""
    mysql_up()
    run("docker", "exec", MYSQL_NAME, "mysql", f"-p{MYSQL_PW}", "-uroot",
        "-e", f"DROP DATABASE IF EXISTS `{db}`")
    inside = f"/dumps/{'rowwise/' if per_row else ''}{db}.sql"
    started = time.time()
    p = run("docker", "exec", MYSQL_NAME, "sh", "-c",
            f"mysql -p{MYSQL_PW} -uroot --force < {inside}")
    seconds = time.time() - started
    if p.returncode != 0 and "ERROR" in (p.stderr or ""):
        return {"error": p.stderr.strip()[:300], "seconds": round(seconds, 1)}
    run("docker", "exec", MYSQL_NAME, "mysql", f"-p{MYSQL_PW}", "-uroot", "-e", "FLUSH TABLES")
    size = run("docker", "exec", MYSQL_NAME, "du", "-sb", f"/var/lib/mysql/{db}")
    return {"seconds": round(seconds, 1),
            "bytes": int(size.stdout.split()[0]) if size.stdout.split() else None}


# ------------------------------------------------------------------- Dolt ---
def dolt_prepare(db, mode):
    src = os.path.join(dumps_dir(mode in PER_ROW), f"{db}.sql")
    out_dir = os.path.join(DUMPS, "dolt", mode)
    os.makedirs(out_dir, exist_ok=True)
    sql, notes = transform(open(src, "rb").read(), db)
    if mode == "dolt_rowcommit":
        sql, n = per_row_commits(sql)
        notes.append(f"a DOLT_COMMIT after each of {n:,} INSERT statements")
    open(os.path.join(out_dir, f"{db}.sql"), "wb").write(sql)
    return f"/dumps/dolt/{mode}/{db}.sql", notes


def dolt_load(db, mode):
    target = os.path.join(data_dir(mode), db)
    if os.path.isdir(target):
        run("docker", "run", "--rm", "-v", f"{data_dir(mode)}:/var/lib/dolt", "--entrypoint", "sh",
            DOLT_IMAGE, "-c", f"rm -rf /var/lib/dolt/{db}")
    os.makedirs(data_dir(mode), exist_ok=True)
    inside, notes = dolt_prepare(db, mode)

    started = time.time()
    p = run("docker", "run", "--rm", "--label", "doltsamples.transient=true",
            "-v", f"{data_dir(mode)}:/var/lib/dolt", "-v", f"{DUMPS}:/dumps",
            "-w", "/var/lib/dolt", "--entrypoint", "dolt", DOLT_IMAGE,
            "--data-dir", "/var/lib/dolt", "sql", "--file", inside)
    load_s = time.time() - started
    if not os.path.isdir(target):
        return {"error": (p.stderr or p.stdout).strip()[:300], "seconds": round(load_s, 1)}

    final = ("dolt gc" if mode == "dolt_rowcommit" else
             'dolt add -A && dolt commit -m "import from mysql-megasamples" '
             '--author "megasamples <megasamples@localhost>" ; dolt gc')
    started = time.time()
    run("docker", "run", "--rm", "-v", f"{data_dir(mode)}:/var/lib/dolt",
        "-w", f"/var/lib/dolt/{db}", "--entrypoint", "sh", DOLT_IMAGE, "-c", final)
    settle_s = time.time() - started

    size = run("docker", "run", "--rm", "-v", f"{data_dir(mode)}:/d", "--entrypoint", "sh",
               DOLT_IMAGE, "-c",
               f"du -sb /d/{db}; du -sb /d/{db}/.dolt/stats 2>/dev/null || echo 0")
    lines = [l.split()[0] for l in size.stdout.splitlines() if l.split()]
    total = int(lines[0]) if lines else None
    stats = int(lines[1]) if len(lines) > 1 else 0
    return {"seconds": round(load_s, 1), "settle_seconds": round(settle_s, 1),
            "bytes": (total - stats) if total else None, "stats_bytes": stats,
            "notes": notes}


# ------------------------------------------------------------------- run ---
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append")
    ap.add_argument("--phase", action="append", choices=PHASES)
    ap.add_argument("--restart", action="store_true", help="forget previous progress and redo all")
    a = ap.parse_args()

    dbs = a.only or databases()
    phases = a.phase or PHASES
    p = {"started": time.time(), "units": {}} if a.restart else load_progress()
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
        key = f"{phase}/{db}"
        note(p, key, status="running", started=time.time(), phase=phase, database=db)
        started = time.time()
        try:
            if phase.startswith("mysql"):
                res = mysql_load(db, phase in PER_ROW)
            else:
                res = dolt_load(db, phase)
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
