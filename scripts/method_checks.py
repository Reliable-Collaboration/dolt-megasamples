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
    """What a bare `docker run` of the Dolt image costs, before any work is done.

    Kept because it is the size of an asymmetry this experiment used to have and no longer does.
    Dolt loads once paid this twice -- one container for the load, another for the commit and gc --
    while MySQL loaded by `docker exec` into a server already up and paid nothing, which was under
    1% of the large Dolt loads but most of the smallest. Both engines now load by `docker exec`
    into a long-lived container, so no load pays it and the current answer is zero per load. The
    measurement stays so the claim about how big it was can be checked."""
    times = []
    for _ in range(samples):
        t0 = time.time()
        run("docker", "run", "--rm", "--entrypoint", "dolt", DOLT_IMAGE, "version")
        times.append(time.time() - t0)
    return {"seconds": round(statistics.median(times), 2), "samples": samples,
            "per_load": 0,
            "note": "zero per load: both engines now load by `docker exec` into a long-lived "
                    "container. Dolt used to pay this twice per load and MySQL not at all"}


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


def empty_footprint():
    """What each engine costs before it holds any data.

    The timed run records the size of the empty MySQL data directory it starts every load from, so
    this reads that rather than starting another server and competing with a run in progress. It is
    worth knowing because of what the per-database numbers do *not* include: with a fresh server per
    database, the InnoDB shared files do not grow during a load at all -- the bytes charged to a
    database equal its own directory, exactly, for every database measured -- so the whole of that
    baseline sits outside every MySQL figure in this report.

    Dolt's equivalent is an empty database directory, measured post-run by
    `--measure-empty-dolt` so it does not perturb a run either.
    """
    prog = os.path.join(ROOT, "build", "progress.json")
    if not os.path.exists(prog):
        return None
    p = json.load(open(prog, encoding="utf-8"))
    seen = [u for u in p.get("units", {}).values()
            if u.get("phase") == "mysql" and u.get("baseline_bytes")]
    if not seen:
        return None
    baselines = sorted(u["baseline_bytes"] for u in seen)
    attributed = [u for u in seen
                  if u.get("bytes") is not None and u.get("database_dir_bytes") is not None]
    unattributed = [u["bytes"] - u["database_dir_bytes"] for u in attributed]
    return {
        "mysql_empty_datadir_bytes": baselines[len(baselines) // 2],
        "mysql_empty_datadir_samples": len(baselines),
        "mysql_empty_datadir_spread_bytes": baselines[-1] - baselines[0],
        "mysql_shared_growth_bytes": max(unattributed) if unattributed else None,
        "databases_checked": len(attributed),
        "note": "every MySQL figure in this report excludes the empty-server baseline: it is a "
                "per-server cost, not a per-database one, and it does not grow as data is loaded",
    }


def dolt_empty_bytes():
    """An empty Dolt database directory, for the same comparison. Starts one short-lived
    container, so it is opt-in rather than run on every report."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o777)
        run("docker", "run", "--rm", "-v", f"{tmp}:/var/lib/dolt", "-w", "/var/lib/dolt",
            "--entrypoint", "sh", DOLT_IMAGE, "-c",
            "dolt --data-dir /var/lib/dolt sql -q 'CREATE DATABASE empty_probe' "
            "&& cd empty_probe && dolt gc")
        p = run("docker", "run", "--rm", "-v", f"{tmp}:/d", "--entrypoint", "sh", DOLT_IMAGE,
                "-c", "du -sb /d/empty_probe 2>/dev/null || echo 0")
        parts = p.stdout.split()
        return int(parts[0]) if parts and parts[0].isdigit() else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repeat", action="store_true",
                    help="re-measure timing repeatability by reloading every database in MySQL")
    ap.add_argument("--remeasure-overhead", action="store_true",
                    help="re-time a bare Dolt container start; normally kept from the first "
                         "measurement so the prose that cites it does not drift")
    ap.add_argument("--measure-empty-dolt", action="store_true",
                    help="also create and measure an empty Dolt database; starts a container, so "
                         "it is left out of the default report to avoid perturbing a timed run")
    a = ap.parse_args()

    facts = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    # Measured once and kept. It is historical context -- the size of an asymmetry that no longer
    # exists -- and re-measuring it on every report made the prose that cites it drift between 0.32
    # and 0.36 seconds, failing its own check for no reason anyone should care about.
    if "dolt_container_overhead" not in facts or a.remeasure_overhead:
        facts["dolt_container_overhead"] = container_overhead()
    # mysql_shared_bytes() used to live here: it measured the timing server's data directory and
    # reported whatever was not inside a database folder as "unattributed". That was the right
    # question when one server held all 21 databases. It is a fresh server per database now, so the
    # figure it produced was the empty-server baseline being re-reported as a 49.4% shortfall.
    # empty_footprint() below answers the question properly, and measures rather than infers that
    # the shared files do not grow during a load.
    facts.pop("mysql_shared_files", None)
    empty = empty_footprint()
    if empty:
        facts["empty_footprint"] = empty
    if a.measure_empty_dolt:
        got = dolt_empty_bytes()
        if got:
            facts.setdefault("empty_footprint", {})["dolt_empty_database_bytes"] = got
    derived = repeatability_from_run()
    if derived:
        facts["repeatability_from_run"] = derived
    # A hard-coded timing_repeatability lived here, from a day when every unit was a single
    # sample and the only way to know the spread was to re-run the whole thing and diff it. The run
    # records its own repeats now, so that number is both superseded and contradicted by better
    # data -- it said a median of +17% where the repeats say 0.0% -- and keeping both would only
    # invite a reader to pick one.
    facts.pop("timing_repeatability", None)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(facts, open(OUT, "w", encoding="utf-8"), indent=2, sort_keys=True)

    o = facts["dolt_container_overhead"]
    print(f"  . a Dolt container start costs {o['seconds']:.2f}s; "
          f"{o['per_load']} of them per load now")
    d = facts.get("repeatability_from_run")
    if d:
        for label, v in sorted(d.items()):
            print(f"  . {label} repeatability over {v['units_repeated']} repeated units: "
                  f"median spread {v['median_spread_percent']}%, worst {v['worst_spread_percent']}%")
    e = facts.get("empty_footprint")
    if e:
        print(f"  . MySQL costs {human(e['mysql_empty_datadir_bytes'])} before it holds any data "
              f"({e['mysql_empty_datadir_samples']} samples, spread "
              f"{e['mysql_empty_datadir_spread_bytes']} bytes); shared files grew "
              f"{human(e['mysql_shared_growth_bytes'] or 0)} across "
              f"{e['databases_checked']} loads")
        if e.get("dolt_empty_database_bytes") is not None:
            print(f"  . an empty Dolt database is {human(e['dolt_empty_database_bytes'])}")
    print(f"  . wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
