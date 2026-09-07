#!/usr/bin/env python3
"""Project how long a full run will take, from rates that were measured rather than guessed.

  python3 scripts/estimate.py [--repeat 3] [--repeat-budget 180]

Every rate here comes from a load this project actually performed, and each is named with the
database it was measured on so it can be checked or replaced. Two things make the projection
trustworthy enough to plan with, and one makes it a projection rather than a forecast:

  * the per-row-commit rate is the important one, because that phase is most of the run, and it is
    also the steadiest thing measured: `employees` held 300 rows a second across 350,000 rows with
    the window rate drifting only from 308 to 297.
  * the row-by-row rates agree across databases of very different shapes -- one-INSERT-per-row came
    to 844 rows/s on `chinook` and 819 on `dvdstore`, and MySQL row-wise to 2,198 and 2,044 on
    `chinook` and `adventureworks`.
  * the one-shot loads are dominated by fixed cost, not by rows, so their rate is the least
    meaningful number here. They are also a rounding error in the total.

The fixed cost per unit is real and is counted: every MySQL load starts a brand-new server and waits
for it, and every repeat pays that again.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT  # noqa: E402

# rows per second, and where each was measured
RATES = {
    "mysql":          (50_000, "adventureworks 759,240 rows in 7.8 s; chinook 15,607 in 0.4 s"),
    "dolt_oneshot":   (50_000, "chinook 15,607 rows in 0.3 s"),
    "mysql_rowwise":  (2_100,  "chinook 2,198 rows/s; adventureworks 2,044 rows/s"),
    "dolt_rowinsert": (830,    "chinook 844 rows/s; dvdstore 819 rows/s"),
    "dolt_rowcommit": (300,    "employees, 350,000 rows at 297-308 rows/s in-window"),
}
# seconds of fixed cost per unit, paid again on every repeat
FIXED = {
    "mysql":          32,   # a fresh empty server, started and waited for
    "mysql_rowwise":  32,
    "dolt_oneshot":   2,
    "dolt_rowinsert": 2,
    "dolt_rowcommit": 6,    # plus a gc over a large store
}
PER_ROW_PHASES = ["mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"]
ALL_PHASES = ["mysql", "dolt_oneshot"] + PER_ROW_PHASES


def rows_per_database():
    """Row counts from the measurements, not from a list typed here."""
    path = os.path.join(ROOT, "build", "memory.json")
    if not os.path.exists(path):
        sys.exit("no build/memory.json; it is where the row counts come from")
    data = json.load(open(path, encoding="utf-8"))
    rows = {}
    for mode in data.values():
        for db, r in mode.items():
            if r.get("rows"):
                rows[db] = r["rows"]
    return rows


def unit_seconds(phase, rows, repeat, budget):
    """One unit, including however many repeats fit inside the budget."""
    rate, _ = RATES[phase]
    once = rows / rate + FIXED[phase]
    runs, spent = 0, 0.0
    for _ in range(max(1, repeat)):
        runs += 1
        spent += once
        if spent > budget:
            break
    return spent, runs


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--repeat-budget", type=float, default=180.0)
    a = ap.parse_args()

    rows = rows_per_database()
    print(f"  {len(rows)} databases, {sum(rows.values()):,} rows\n")
    print(f"  {'phase':<16} {'units':>6} {'runs':>6} {'hours':>8}   rate used")
    grand = 0.0
    for phase in ALL_PHASES:
        total, runs = 0.0, 0
        for db, n in rows.items():
            s, r = unit_seconds(phase, n, a.repeat, a.repeat_budget)
            total += s
            runs += r
        grand += total
        rate, where = RATES[phase]
        print(f"  {phase:<16} {len(rows):>6} {runs:>6} {total / 3600:>8.1f}   "
              f"{rate:,}/s — {where[:52]}")
    print(f"  {'':<16} {'':>6} {'':>6} {grand / 3600:>8.1f}   deferred pass, all five tests")

    inline = 0.0
    for phase in PER_ROW_PHASES:
        for db, n in rows.items():
            s, _ = unit_seconds(phase, n, a.repeat, a.repeat_budget)
            inline += s
    print(f"  {'':<16} {'':>6} {'':>6} {inline / 3600:>8.1f}   inline pass, the three row-by-row "
          f"tests")
    print(f"  {'':<16} {'':>6} {'':>6} {(grand + inline) / 3600:>8.1f}   both passes\n")
    print("  These are projections from measured rates, not a schedule. What would move them most:\n"
          "  a per-row-commit rate that falls as a store grows (it has held flat so far), and the\n"
          "  gc after each load, which is timed but not modelled per database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
