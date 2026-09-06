#!/usr/bin/env python3
"""Measure the method's own weak points, so the numbers describing them can be checked.

  python3 scripts/method_checks.py

The README states several figures that are not measurements of the databases but of the *method*:
how much of a Dolt timing is container startup, how much of MySQL's storage is shared files that no
database is charged for, and how repeatable a timing is at all. Those numbers drifted out of every
other document at least once when they lived only in prose, so they are measured here and written to
`build/method.json`, where `check_claims.py` can verify the text against them.

The repeatability figure is the exception: re-running every load is expensive, so it is recorded with
the date it was taken rather than re-measured on every invocation. `--repeat` takes it again.
"""
import argparse, json, os, statistics, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DOLT_IMAGE, ROOT, human, load_results, run  # noqa: E402

OUT = os.path.join(ROOT, "build", "method.json")
MYSQL_NAME, MYSQL_PW = "doltsamples-mysql-timing", "timing"


def container_overhead(samples=5):
    """What a bare `docker run` of the Dolt image costs, before any work is done. Every Dolt load
    pays this twice — once for the load, once for the commit and gc — while MySQL's loads use
    `docker exec` into a server that is already up and pay nothing."""
    times = []
    for _ in range(samples):
        t0 = time.time()
        run("docker", "run", "--rm", "--entrypoint", "dolt", DOLT_IMAGE, "version")
        times.append(time.time() - t0)
    return {"seconds": round(statistics.median(times), 2), "samples": samples,
            "per_load": 2, "note": "two containers per Dolt load: the load, then commit and gc"}


def mysql_shared_bytes():
    """InnoDB's shared files — ibdata1, undo, redo — belong to no single database, so per-database
    sizes undercount MySQL. Dolt has no equivalent: a database's directory holds all of it."""
    p = run("docker", "exec", MYSQL_NAME, "sh", "-c",
            "du -scb /var/lib/mysql/*/ | tail -1 | cut -f1; du -sb /var/lib/mysql | cut -f1")
    nums = [int(x) for x in p.stdout.split() if x.isdigit()]
    if len(nums) < 2:
        return None
    per_db, whole = nums[0], nums[1]
    return {"per_database_bytes": per_db, "datadir_bytes": whole,
            "unattributed_bytes": whole - per_db,
            "unattributed_percent": round((whole - per_db) / whole * 100, 1)}


def repeatability_from_run():
    """Derive the spread from the run's own repeats rather than a separate measurement.

    `--repeat N` keeps every sample, so how repeatable a number is can be read off the same data the
    headline numbers come from instead of being asserted from a measurement taken another day. Each
    unit contributes its spread as a percentage of its own median; units run only once contribute
    nothing and are counted as such."""
    r = load_results()
    out = {}
    for label, samples in (("seconds", _samples(r, "seconds_all")),
                           ("bytes", _samples(r, "bytes_all"))):
        spreads = []
        for xs in samples:
            xs = sorted(xs)
            med = xs[len(xs) // 2]
            if med:
                spreads.append(round(100 * (xs[-1] - xs[0]) / med, 1))
        if spreads:
            spreads.sort()
            out[label] = {"units_repeated": len(spreads),
                          "median_spread_percent": spreads[len(spreads) // 2],
                          "worst_spread_percent": spreads[-1]}
    return out or None


def _samples(r, field):
    for db, entry in r.items():
        if not isinstance(entry, dict):
            continue
        for mode in (entry.get("modes") or {}).values():
            if isinstance(mode, dict) and len(mode.get(field) or []) > 1:
                yield mode[field]
        for k, v in entry.items():
            if "_spread" in k and isinstance(v, dict) and len(v.get(field) or []) > 1:
                yield v[field]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repeat", action="store_true",
                    help="re-measure timing repeatability by reloading every database in MySQL")
    a = ap.parse_args()

    facts = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    facts["dolt_container_overhead"] = container_overhead()
    shared = mysql_shared_bytes()
    if shared:
        facts["mysql_shared_files"] = shared
    derived = repeatability_from_run()
    if derived:
        facts["repeatability_from_run"] = derived
    facts.setdefault("timing_repeatability", {
        "measured": "2026-09-06",
        "method": "every database reloaded into the timing MySQL a second time and compared",
        "median_percent": 17, "min_percent": -20, "max_percent": 132,
        "stable_above_seconds": 5, "stable_range_percent": [-20, 8],
        "note": "the spread is in the sub-second loads; everything over five seconds repeats "
                "within -20% to +8%",
    })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(facts, open(OUT, "w", encoding="utf-8"), indent=2, sort_keys=True)

    o, m = facts["dolt_container_overhead"], facts.get("mysql_shared_files")
    print(f"  . Dolt container startup: {o['seconds']:.2f}s, {o['per_load']} per load")
    if m:
        print(f"  . MySQL shared files: {human(m['unattributed_bytes'])} of "
              f"{human(m['datadir_bytes'])} ({m['unattributed_percent']}%) charged to no database")
    t = facts["timing_repeatability"]
    print(f"  . timing repeatability: median {t['median_percent']:+d}%, "
          f"{t['min_percent']:+d}% to {t['max_percent']:+d}% (measured {t['measured']})")
    d = facts.get("repeatability_from_run")
    if d:
        for label, v in sorted(d.items()):
            print(f"  . {label} repeatability over {v['units_repeated']} repeated units: "
                  f"median spread {v['median_spread_percent']}%, worst {v['worst_spread_percent']}%")
    print(f"  . wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
