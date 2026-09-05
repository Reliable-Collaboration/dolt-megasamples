#!/usr/bin/env python3
"""What the run has done so far, what it is doing, and what is left.

  python3 scripts/progress.py [--watch]

Reads `build/progress.json`, which `run_all.py` rewrites after every unit of work. Safe to run at
any time, including while the run is going: it only reads.

The estimate is deliberately crude — measured seconds per row in each phase, applied to the rows
still to do. It is honest about being an estimate, because the per-row commit phase costs an order
of magnitude more per row than the others and an average across phases would be meaningless.
"""
import argparse, json, os, sys, time

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
        done = [u for u in units.values() if u.get("status") == "done"]
        err = [u for u in units.values() if u.get("status") == "error"]
        running = [u for u in units.values() if u.get("status") == "running"]

        print(f"\n  elapsed {clock(elapsed)}   {len(done)} done, {len(err)} failed, "
              f"{len(running)} running, of {len(dbs) * len(p.get('phases', []))} units\n")
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

        if running:
            for u in running:
                print(f"\n  running: {u.get('phase')} / {u.get('database')} — "
                      f"{clock(time.time() - u.get('started', time.time()))} so far")
        recent = sorted((u for u in done if u.get("finished")),
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
