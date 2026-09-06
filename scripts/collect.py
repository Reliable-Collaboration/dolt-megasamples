#!/usr/bin/env python3
"""Fold the timed run into build/results.json.

  python3 scripts/collect.py

`run_all.py` records what it did in `build/progress.json`: for every database and every load, how
long it took and how much disk it produced. This copies those into the results file the report and
the charts read, under the mode keys they already use, and adds the timings that had no home before.

MySQL's sizes now come from the timed run too — a fresh, empty server loaded from the same dump —
rather than from the megasamples image. That matters: the image was built by a `mysqlsh` dump and
restore with deferred index builds, and it is measurably more compact than the same data loaded from
SQL. Comparing Dolt against the image was comparing against a differently-built MySQL.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human, load_results, save_results  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")
# progress key -> where it lands in results.json
MODE_OF = {"dolt_oneshot": "oneshot", "dolt_rowinsert": "rowinsert", "dolt_rowcommit": "rowcommit"}


def main():
    if not os.path.exists(PROGRESS):
        sys.exit("no build/progress.json; `make run` produces it")
    p = json.load(open(PROGRESS, encoding="utf-8"))
    r = load_results()

    counted = 0
    for key, u in p["units"].items():
        if u.get("status") != "done":
            continue
        # `dolt_rowcommit/chinook/inline` is one unit of one database, not a database called
        # "chinook/inline". The index policy is a suffix on the key, so split it off first.
        parts = key.split("/")
        phase, db = parts[0], parts[1]
        suffix = "_inline" if parts[2:] == ["inline"] else ""
        entry = r.setdefault(db, {})
        counted += 1
        spread = {k: u[k] for k in ("seconds_all", "bytes_all", "repeats") if k in u}
        if phase == "mysql":
            entry[f"mysql_disk_bytes{suffix}"] = u.get("bytes")
            entry[f"mysql_load_seconds{suffix}"] = u.get("seconds")
            entry[f"mysql_spread{suffix}"] = spread
        elif phase == "mysql_rowwise":
            entry[f"mysql_rowwise_bytes{suffix}"] = u.get("bytes")
            entry[f"mysql_rowwise_seconds{suffix}"] = u.get("seconds")
            entry[f"mysql_rowwise_spread{suffix}"] = spread
        elif phase in MODE_OF:
            m = entry.setdefault("modes", {}).setdefault(MODE_OF[phase] + suffix, {})
            m["disk_bytes"] = u.get("bytes")
            m["stats_bytes"] = u.get("stats_bytes", 0)
            m["load_seconds"] = u.get("seconds")
            m["settle_seconds"] = u.get("settle_seconds")
            m["total_seconds"] = round((u.get("seconds") or 0) + (u.get("settle_seconds") or 0), 1)
            m["indexes_deferred"] = suffix == ""
            m.update(spread)

    save_results(r)
    dbs = sorted(d for d in r if r[d].get("mysql_disk_bytes"))
    my = sum(r[d]["mysql_disk_bytes"] for d in dbs)
    mt = sum(r[d].get("mysql_load_seconds") or 0 for d in dbs)
    print(f"  . folded {counted} completed units into build/results.json")
    print(f"  . MySQL: {len(dbs)} databases, {human(my)}, {mt:,.0f}s to load")
    for mode in ("oneshot", "rowinsert", "rowcommit",
                 "rowinsert_inline", "rowcommit_inline"):
        have = [d for d in dbs if (r[d].get("modes", {}).get(mode) or {}).get("disk_bytes")]
        if not have:
            continue
        b = sum(r[d]["modes"][mode]["disk_bytes"] for d in have)
        t = sum(r[d]["modes"][mode].get("total_seconds") or 0 for d in have)
        print(f"  . Dolt {mode:<10}: {len(have):>2} databases, {human(b):>10}, {t:>8,.0f}s "
              f"({b / sum(r[d]['mysql_disk_bytes'] for d in have):.2f}× MySQL size, "
              f"{t / max(1, sum(r[d].get('mysql_load_seconds') or 0 for d in have)):.1f}× MySQL time)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
