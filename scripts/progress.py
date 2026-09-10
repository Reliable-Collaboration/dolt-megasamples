#!/usr/bin/env python3
"""What the run has done so far, what it is doing, and what is left.

  python3 scripts/progress.py [--watch]

Reads `build/progress.json`, which `run_all.py` rewrites after every unit of work. Safe to run at
any time, including while the run is going: it only reads.

The estimate is deliberately crude — measured seconds per row in each phase, applied to the rows
still to do. It is honest about being an estimate, because the per-row commit phase costs an order
of magnitude more per row than the others and an average across phases would be meaningless.
"""
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human, load_results  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")
LABEL = {"mysql": "MySQL, extended INSERTs",
         "mysql_rowwise": "MySQL, one INSERT per row",
         "dolt_oneshot": "Dolt, one commit per database",
         "dolt_rowinsert": "Dolt, one INSERT per row",
         "dolt_rowcommit": "Dolt, one commit per row"}


def clock(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    return f"{seconds / 3600:.1f}h"


TITLE = {"pg": "PostgreSQL / DoltgreSQL", "lite": "SQLite / DoltLite"}
ISOLATED = "one server per unit"


def runner_alive(u):
    """Whether a runner of the unit's kind is working, so a unit left `running` by an interrupted run
    is not shown as if it were still going."""
    pattern = f"run_pair[s].py --pair {u['pair']}" if u.get("pair") else "run_al[l].py"
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


def pairs_section(p):
    """The two further pairs, by index policy: what is measured, what is left, and a rough estimate
    from the seconds per row of the units measured so far (or of the superseded ones, before any)."""
    try:
        from pairs import LABEL as PAIR_LABEL, PER_ROW, PHASES, exported, reference
    except Exception as exc:                                        # noqa: BLE001
        print(f"\n  (the pairs cannot be shown: {exc})")
        return
    units, sup = p["units"], p.get("superseded") or {}
    for pair in ("pg", "lite"):
        dbs = exported(pair)
        if not dbs:
            continue
        rows = {}
        for db in dbs:
            try:
                rows[db] = sum(v or 0 for v in reference(pair, db)["rows"].values())
            except Exception:                                       # noqa: BLE001
                rows[db] = 0
        for policy, suffix in (("deferred", ""), ("inline", "/inline")):
            phases = PHASES[pair] if not suffix else [ph for ph in PHASES[pair] if ph in PER_ROW]
            print(f"\n  {TITLE[pair]}, indexes {policy}")
            print(f"  {'phase':<40}{'done':>7}{'left':>7}{'time so far':>13}{'est. left':>12}")
            total = 0.0
            for ph in phases:
                recs = {db: units.get(f"{ph}/{db}{suffix}", {}) for db in dbs}
                fin = [db for db, u in recs.items() if u.get("status") == "done"
                       and (not ph.startswith("doltgres") or u.get("isolation") == ISOLATED)]
                left = [db for db in dbs if db not in fin]
                spent = sum(recs[db].get("wall_seconds") or 0 for db in fin)
                basis = []
                for db in dbs:
                    for u in (recs[db], sup.get(f"{ph}/{db}{suffix}") or {}):
                        if u.get("status") == "done" and u.get("wall_seconds"):
                            basis.append((u["wall_seconds"], rows[db]))
                            break
                secs, done_rows = sum(b[0] for b in basis), sum(b[1] for b in basis)
                est = secs / done_rows * sum(rows[db] for db in left) if done_rows else 0.0
                total += est
                print(f"  {PAIR_LABEL.get(ph, ph):<40}{len(fin):>7}{len(left):>7}{clock(spent):>13}"
                      f"{(clock(est) if left else '—'):>12}")
            print(f"  {'':<40}{'':>7}{'':>7}{'':>13}{clock(total):>12}  (rough)")
    stale = [k for k, u in units.items() if k.startswith("doltgres_") and u.get("status") == "done"
             and u.get("isolation") != ISOLATED]
    if stale or sup:
        print(f"\n  DoltgreSQL units measured on a shared server: {len(stale)} still recorded, {len(sup)} superseded; "
              f"each is measured again with one server per unit")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--watch", action="store_true", help="redraw every 60 seconds")
    a = ap.parse_args()

    while True:
        if not os.path.exists(PROGRESS):
            sys.exit("no run recorded yet; `make run` starts one")
        with open(PROGRESS, encoding="utf-8") as fh:
            p = json.load(fh)
        results = load_results()
        rows = {d: (results.get(d, {}) or {}).get("rows_mysql") or 0 for d in p.get("databases", [])}

        units, dbs = p["units"], p.get("databases", [])
        elapsed = time.time() - p.get("started", time.time())
        mine = {k: u for k, u in units.items() if not u.get("pair")}      # the MySQL/Dolt run
        done = [u for u in mine.values() if u.get("status") == "done"]
        err = [u for u in units.values() if u.get("status") == "error"]
        running = [u for u in units.values() if u.get("status") == "running"]

        print(f"\n  MySQL and Dolt: elapsed {clock(elapsed)}   {len(done)} done, "
              f"{sum(1 for u in mine.values() if u.get('status') == 'error')} failed, "
              f"of {len(dbs) * len(p.get('phases', []))} units\n")
        print(f"  {'phase':<32}{'done':>7}{'left':>7}{'time so far':>13}{'est. left':>12}")
        total_left = 0
        for phase in p.get("phases", []):
            ph = [units.get(f"{phase}/{d}", {}) for d in dbs]
            fin = [u for u in ph if u.get("status") == "done"]
            left_dbs = [d for d in dbs if units.get(f"{phase}/{d}", {}).get("status") != "done"]
            spent = sum(u.get("wall_seconds") or 0 for u in ph)
            rate = (spent / max(1, sum(rows[u["database"]] for u in fin if u.get("database")))
                    if fin else 0)
            est = rate * sum(rows[d] for d in left_dbs)
            total_left += est
            print(f"  {LABEL.get(phase, phase):<32}{len(fin):>7}{len(left_dbs):>7}"
                  f"{clock(spent):>13}{(clock(est) if left_dbs else '—'):>12}")
        print(f"  {'':<32}{'':>7}{'':>7}{clock(elapsed):>13}{clock(total_left):>12}  (rough)")

        pairs_section(p)
        if running:
            for u in running:
                state = "running" if runner_alive(u) else "interrupted, no runner is working on it"
                print(f"\n  {state}: {u.get('phase')} / {u.get('database')}"
                      f"{' (indexes inline)' if u.get('indexes') == 'inline' else ''} — "
                      f"started {clock(time.time() - u.get('started', time.time()))} ago")
        recent = sorted((u for u in units.values() if u.get("status") == "done" and u.get("finished")),
                        key=lambda u: u["finished"], reverse=True)[:5]
        if recent:
            print("\n  last finished:")
            for u in recent:
                print(f"    {u.get('phase',''):<15} {u.get('database',''):<22} "
                      f"{u.get('seconds', 0):>8.1f}s  "
                      f"{human(u['bytes']) if u.get('bytes') else '—':>10}")
        if err:
            print("\n  failures:")
            for u in err:
                print(f"    {u.get('phase',''):<15} {u.get('database',''):<22} "
                      f"{str(u.get('error'))[:70]}")
        if not a.watch:
            return 0
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
