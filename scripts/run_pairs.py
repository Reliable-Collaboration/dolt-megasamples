#!/usr/bin/env python3
"""Run the PostgreSQL/DoltgreSQL or the SQLite/DoltLite experiment, timing every load, recording
progress as it goes -- the counterpart of run_all.py for the two further pairs.

  python3 scripts/run_pairs.py --pair pg  [--only sakila] [--phase doltgres_rowcommit] [--indexes inline]
  python3 scripts/run_pairs.py --pair lite

Units are recorded in the same build/progress.json as the MySQL/Dolt run, under the same key
shape (`<phase>/<database>[/inline]`), with the same fields plus what the pairs add (memory
peaks for every unit, the size before the settle step, the index-parity report, every refusal,
and the measurement method). A unit recorded `done` with the current method is skipped, so the run
can be stopped and resumed; a unit recorded with an older method is measured again, and its first
record is kept under `superseded`. Units run cheapest-first: phases in the order given, and within
a phase the databases with the fewest rows first, so the tables fill in from the top.

One runner at a time: every runner holds build/run.lock for as long as it runs (common.run_lock),
so two can never stop each other's workers or write over each other's records.

The loads themselves, the settle steps and the checks are in pairs.py.
"""
import argparse, json, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human, run, run_lock  # noqa: E402
from pairs import (ENGINE, LABEL, METHOD, PER_ROW, PHASES, WORKERS, committed_rows, exported,  # noqa: E402
                   load)
from run_all import PROGRESS, fingerprint, note, save_progress  # noqa: E402


def current(u):
    """Measured, with the method the collector reports."""
    return u.get("status") == "done" and u.get("method") == METHOD


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pair", choices=["pg", "lite"], required=True)
    ap.add_argument("--only", action="append")
    ap.add_argument("--phase", action="append", choices=sorted(ENGINE))
    ap.add_argument("--indexes", choices=["deferred", "inline"], default="deferred",
                    help="deferred (default): pg_dump's and .dump's own order, indexes after the rows; "
                         "inline: indexes and unique constraints ahead of the rows (row-by-row phases only)")
    ap.add_argument("--redo", action="store_true", help="run the selected units again even if recorded done")
    ap.add_argument("--allow-busy", action="store_true", help="time the loads even with other stacks running")
    ap.add_argument("--max-rows", type=int, default=None, metavar="N",
                    help="skip databases with more than N rows (the report says which were not run)")
    ap.add_argument("--floor-gb", type=float, default=8.0, help="stop before a unit if less than this is free")
    ap.add_argument("--resume", action="store_true", help="add to a run recorded on another machine")
    a = ap.parse_args()

    lock, holder = run_lock(f"run_pairs.py --pair {a.pair}")
    if lock is None:
        sys.exit(f"build/run.lock is held by {holder}: one runner at a time, so that no two can stop "
                 f"each other's workers or write over each other's records")
    # a worker container left by an interrupted run is this experiment's own, and with the lock held
    # nothing is using it
    stale = [n for n in run("docker", "ps", "-a", "--format", "{{.Names}}").stdout.split() if n in WORKERS]
    if stale:
        run("docker", "rm", "-f", *stale)
        print(f"removed worker container(s) left by an interrupted run: {', '.join(stale)}\n", flush=True)
    busy = [n for n in run("docker", "ps", "--format", "{{.Names}}").stdout.split()
            if n.startswith(("megasamples-", "doltsamples-"))]
    if busy and not a.allow_busy:
        sys.exit("These containers are running and will compete with the measurements:\n  " + "\n  ".join(busy)
                 + "\n\nStop them first (`make down` here and in the sql-megasamples checkout; the exports are "
                   "already on disk). --allow-busy overrides.")

    phases = a.phase or PHASES[a.pair]
    if any(ph not in PHASES[a.pair] for ph in phases):
        sys.exit(f"--phase must name phases of the {a.pair} pair: {', '.join(PHASES[a.pair])}")
    if a.indexes == "inline" and not a.phase:
        phases = [ph for ph in phases if ph in PER_ROW]
        print(f"--indexes inline: the row-by-row phases only ({', '.join(phases)})\n", flush=True)
    dbs = a.only or exported(a.pair)
    if not dbs:
        sys.exit(f"nothing exported for the {a.pair} pair: run scripts/export_"
                 f"{'postgres' if a.pair == 'pg' else 'sqlite'}.py first")
    rows = {db: committed_rows(a.pair, db) for db in dbs}
    skipped = [db for db in dbs if a.max_rows is not None and rows[db] > a.max_rows]
    order = sorted((db for db in dbs if db not in skipped), key=lambda d: rows[d])
    if skipped:
        print(f"--max-rows {a.max_rows:,}: not running {', '.join(skipped)}\n", flush=True)

    if os.path.exists(PROGRESS):
        p = json.load(open(PROGRESS, encoding="utf-8"))
        if p.get("host") and p["host"] != fingerprint() and not a.resume:
            # refused before anything is written: this file is the only record of every unit
            sys.exit(f"build/progress.json was recorded on another machine ({p['host']}; this one is "
                     f"{fingerprint()}). Nothing was changed. Pass --resume to add to it, or move it aside.")
        p["host"] = fingerprint()
    else:
        p = {"started": time.time(), "units": {}, "host": fingerprint()}
    p.setdefault("pairs", {})[a.pair] = {"databases": dbs, "phases": phases, "indexes": a.indexes}
    save_progress(p)

    def key_of(phase, db):
        return f"{phase}/{db}" + ("" if a.indexes == "deferred" else "/inline")

    units = [(ph, db) for ph in phases for db in order]
    todo = [(ph, db) for ph, db in units if a.redo or not current(p["units"].get(key_of(ph, db), {}))]
    print(f"{len(units)} units, {len(todo)} to do ({len(units) - len(todo)} already measured with method "
          f"{METHOD})\n", flush=True)

    for i, (phase, db) in enumerate(todo, 1):
        free_gb = shutil.disk_usage(ROOT).free / 1e9
        if free_gb < a.floor_gb:
            print(f"\n{free_gb:.1f} GB free, below the {a.floor_gb:.0f} GB floor; stopping with "
                  f"{len(todo) - i + 1} units left. Recorded progress is kept.", flush=True)
            return 3
        if run("docker", "version", "-f", "{{.Server.Version}}").returncode != 0:
            print("\ndocker is not answering; stopping so no unit is recorded unverified.", flush=True)
            return 2
        key = key_of(phase, db)
        old = p["units"].get(key) or {}
        if old.get("status") == "done" and old.get("method") != METHOD:
            # the first measurement is kept, not the last one before this: a unit interrupted while being
            # measured again must not replace it
            p.setdefault("superseded", {}).setdefault(
                key, dict(old, superseded=f"measured with method {old.get('method', 1)}; measured again "
                                          f"with method {METHOD}"))
        note(p, key, replace=True, status="running", started=time.time(), phase=phase, database=db,
             indexes=a.indexes, pair=a.pair, engine=ENGINE[phase], label=LABEL[phase], source_rows=rows[db],
             method=METHOD)
        started = time.time()
        try:
            res = load(db, phase, a.indexes)
        except Exception as exc:                                   # noqa: BLE001
            res = {"error": f"{type(exc).__name__}: {exc}"[:300], "method": METHOD}
        res["status"] = "error" if "error" in res else "done"
        res["samples"] = 1
        res["finished"] = time.time()
        res["wall_seconds"] = round(time.time() - started, 1)
        note(p, key, **res)
        mark = "x" if res["status"] == "error" else "."
        size = human(res["bytes"]) if res.get("bytes") else "—"
        print(f"  {mark} [{i}/{len(todo)}] {phase:<19} {db:<22} {res.get('seconds', 0):>8.1f}s  {size:>10}"
              + (f"   {res['error'][:80]}" if "error" in res else
                 (f"   {res['error_count']} refusal(s)" if res.get("error_count") else "")), flush=True)

    print("\nall requested units complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
