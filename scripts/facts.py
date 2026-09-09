#!/usr/bin/env python3
"""Every number the documents can contain, derived from the evidence files and nothing else.

  python3 scripts/facts.py            # list every fact, its value, and where it came from
  python3 scripts/facts.py --missing  # only the ones no measurement supports yet

This exists because a document that contains a typed number is a document that can be wrong, and
this experiment proved it twice: prose quoting a superseded run, and a row count that was silently
truncated and then reasoned from. Both were invisible because nothing connected the sentence to the
measurement.

So no document holds a number. Documents are templates of prose with `{{name}}` placeholders, and
every `name` resolves here, from a file written by a script that measured something:

  build/results.json      what each load produced -- sizes, times, row and index parity
  build/memory.json       what each database needs to open, against rows, disk and commits
  build/method.json       the method's own measurements: empty footprint, repeatability
  build/environment.json  the machine
  build/progress.json     what the run did, unit by unit

A fact with no measurement behind it is not blank and is not a guess: it renders as a visible
marker and `--missing` lists it. That way an unfinished run produces a document that says which
numbers it is waiting for, rather than one that looks complete.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human  # noqa: E402

BUILD = os.path.join(ROOT, "build")
SOURCES = {
    "results": "results.json",
    "memory": "memory.json",
    "method": "method.json",
    "environment": "environment.json",
    "progress": "progress.json",
}
MISSING = "[not measured]"

# The Dolt commits that are not data: the initial commit, the schema commit, and the final one.
BASE_COMMITS = 3
MODE_ORDER = ["oneshot", "rowinsert", "rowcommit", "rowinsert_inline", "rowcommit_inline"]


def load(name):
    path = os.path.join(BUILD, SOURCES[name])
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Facts(dict):
    """A name -> (formatted value, source) mapping that refuses to invent anything."""

    def __init__(self):
        super().__init__()
        self.sources = {}

    def put(self, name, value, source, fmt=str):
        if value is None:
            self[name] = MISSING
            self.sources[name] = f"{source} (absent)"
        else:
            self[name] = fmt(value)
            self.sources[name] = source

    def missing(self):
        return sorted(k for k, v in self.items() if v == MISSING)


def pct(x):
    return f"{x:.0f}%"


def one(x):
    return f"{x:.1f}"


def commas(x):
    return f"{int(x):,}"


def ratio(x):
    return f"{x:.2f}×"


def build():                                                    # noqa: C901 - a flat catalogue
    f = Facts()
    results, memory = load("results"), load("memory")
    method, env = load("method"), load("environment")
    progress = load("progress")

    # ----------------------------------------------------------------- the machine ---
    host = (env or {}).get("host") or {}
    docker = (env or {}).get("docker") or {}
    engines = (env or {}).get("engines") or {}
    f.put("env.cpu", host.get("cpu"), "environment.json:host.cpu")
    # The keys are `cpu_threads` and `memory`, not `threads` and `memory_gb`. Guessing them rather
    # than reading environment.json is why both rendered as [not measured] -- which is the marker
    # doing its job: a wrong key surfaced as a visible gap instead of a blank or a stale value.
    f.put("env.threads", host.get("cpu_threads"), "environment.json:host.cpu_threads", commas)
    f.put("env.memory", host.get("memory"), "environment.json:host.memory")
    f.put("env.disk", host.get("disk_total"), "environment.json:host.disk_total")
    f.put("env.filesystem", host.get("filesystem"), "environment.json:host.filesystem")
    f.put("env.kernel", host.get("kernel"), "environment.json:host.kernel")
    f.put("env.docker", docker.get("version"), "environment.json:docker.version")
    f.put("env.mysql_image", engines.get("mysql_image"), "environment.json:engines.mysql_image")
    f.put("env.dolt_version", engines.get("dolt_version"), "environment.json:engines.dolt_version")
    f.put("env.mysql_flags", ", ".join(f"`{x}`" for x in engines.get("mysql_flags") or []) or None,
          "environment.json:engines.mysql_flags")

    # ------------------------------------------------------------------- the corpus ---
    # The corpus is knowable from any file that enumerates the databases, so it falls back to the
    # memory study rather than reporting "not measured" for something two files can answer.
    if results:
        dbs = sorted(results)
        f.put("corpus.databases", len(dbs), "results.json: number of databases", commas)
        f.put("corpus.rows", sum((results[d].get("rows_mysql") or 0) for d in dbs) or None,
              "results.json:*.rows_mysql", commas)
        f.put("corpus.tables", sum((results[d].get("tables") or 0) for d in dbs) or None,
              "results.json:*.tables", commas)
    else:
        per_db = {}
        for mode in (memory or {}).values():
            for db, r in mode.items():
                if r.get("rows") is not None:
                    per_db[db] = r["rows"]
        f.put("corpus.databases", len(per_db) or None,
              "memory.json: number of databases (results.json absent)", commas)
        f.put("corpus.rows", sum(per_db.values()) or None,
              "memory.json:*.rows (results.json absent)", commas)
        f.put("corpus.tables", None, "results.json:*.tables")

    _size_facts(f, results)
    _memory_facts(f, memory)
    _method_facts(f, method)
    _run_facts(f, progress)
    return f


def _size_facts(f, results):
    """Totals and ratios per mode, over the databases where both engines have a figure."""
    for mode in MODE_ORDER:
        have = [] if not results else [
            d for d, e in results.items()
            if e.get("mysql_disk_bytes") and ((e.get("modes") or {}).get(mode) or {}).get(
                "disk_bytes")]
        if not have:
            for suffix in ("databases", "bytes", "ratio", "seconds"):
                f.put(f"{mode}.{suffix}", None, f"results.json:*.modes.{mode}")
            continue
        my = sum(results[d]["mysql_disk_bytes"] for d in have)
        do = sum(results[d]["modes"][mode]["disk_bytes"] for d in have)
        secs = sum((results[d]["modes"][mode].get("total_seconds") or 0) for d in have)
        f.put(f"{mode}.databases", len(have), f"results.json:*.modes.{mode}", commas)
        f.put(f"{mode}.bytes", do, f"results.json:*.modes.{mode}.disk_bytes", human)
        f.put(f"{mode}.ratio", do / my, f"results.json: {mode} bytes / mysql bytes", ratio)
        f.put(f"{mode}.seconds", secs or None,
              f"results.json:*.modes.{mode}.total_seconds", one)

    have = [d for d, e in (results or {}).items() if e.get("mysql_disk_bytes")]
    f.put("mysql.databases", len(have) or None, "results.json:*.mysql_disk_bytes", commas)
    f.put("mysql.bytes", sum(results[d]["mysql_disk_bytes"] for d in have) if have else None,
          "results.json:*.mysql_disk_bytes", human)
    f.put("mysql.seconds",
          sum((results[d].get("mysql_load_seconds") or 0) for d in have) or None if have else None,
          "results.json:*.mysql_load_seconds", one)


def _memory_facts(f, memory):
    """What Dolt needs to open a database, and what that scales with."""
    if not memory:
        for k in ("memory.floor_mb", "memory.commits_per_mb", "memory.largest_commits",
                  "memory.largest_db", "memory.ladder_top_gb", "memory.oneshot_max_mb",
                  "memory.oneshot_max_rows", "memory.disk_pair"):
            f.put(k, None, "memory.json")
        return
    one_shot, rc = memory.get("oneshot") or {}, memory.get("rowcommit") or {}

    measured = [r["megabytes"] for r in list(one_shot.values()) + list(rc.values())
                if r.get("megabytes")]
    f.put("memory.floor_mb", min(measured) if measured else None,
          "memory.json: smallest ceiling any database needed", commas)

    # the linear region: databases above the floor, with a commit count
    floor = min(measured) if measured else None
    above = [(r["commits"], r["megabytes"]) for r in rc.values()
             if r.get("megabytes") and r.get("commits") and r["megabytes"] > (floor or 0)]
    if above:
        rates = [c / m for c, m in above]
        f.put("memory.commits_per_mb", sum(rates) / len(rates),
              "memory.json: mean commits per MB above the floor",
              lambda x: f"{round(x, -2):,.0f}")
        f.put("memory.linear_from", min(c for c, _ in above),
              "memory.json: smallest commit count above the floor", commas)
        f.put("memory.linear_to", max(c for c, _ in above),
              "memory.json: largest commit count still measurable", commas)
    else:
        for k in ("memory.commits_per_mb", "memory.linear_from", "memory.linear_to"):
            f.put(k, None, "memory.json")

    # the one that would not open at all
    over = [(db, r) for db, r in rc.items() if r.get("megabytes") is None]
    f.put("memory.over_budget_db", f"`{over[0][0]}`" if over else None,
          "memory.json: killed at the top of the ladder")
    f.put("memory.ladder_top_gb",
          (over[0][1].get("ladder_top_mb") or 0) / 1024 if over else None,
          "memory.json:ladder_top_mb", lambda x: f"{x:.0f}")
    f.put("memory.over_budget_rows", over[0][1].get("rows") if over else None,
          "memory.json: rows of the database that would not open", commas)

    biggest = max(one_shot.values(), key=lambda r: r.get("rows") or 0, default=None)
    f.put("memory.oneshot_max_mb", max((r.get("megabytes") or 0 for r in one_shot.values()),
                                       default=None) or None,
          "memory.json: largest ceiling any one-shot database needed", commas)
    f.put("memory.oneshot_max_rows", (biggest or {}).get("rows"),
          "memory.json: rows in the largest one-shot database", commas)

    # the pair that separates disk from history: more disk, fewer commits, less memory
    pairs = [(a, b) for a in rc.values() for b in rc.values()
             if a.get("disk_bytes") and b.get("disk_bytes") and a.get("megabytes")
             and b.get("megabytes") and a["disk_bytes"] > b["disk_bytes"]
             and a["commits"] and b["commits"] and a["commits"] < b["commits"]
             and a["megabytes"] < b["megabytes"]]
    if pairs:
        a, b = max(pairs, key=lambda p: p[0]["disk_bytes"] - p[1]["disk_bytes"])
        names = {id(v): k for k, v in rc.items()}
        f.put("memory.disk_pair",
              f"`{names[id(a)]}` holds {human(a['disk_bytes'])} across {a['commits']:,} commits and "
              f"opens in {a['megabytes']} MB, while `{names[id(b)]}` holds "
              f"{human(b['disk_bytes'])} across {b['commits']:,} commits and needs "
              f"{b['megabytes']} MB",
              "memory.json: the widest disk-against-commits inversion")
    else:
        f.put("memory.disk_pair", None, "memory.json")


def _method_facts(f, method):
    m = method or {}
    empty = m.get("empty_footprint") or {}
    f.put("method.mysql_empty", empty.get("mysql_empty_datadir_bytes"),
          "method.json:empty_footprint.mysql_empty_datadir_bytes", human)
    f.put("method.mysql_empty_samples", empty.get("mysql_empty_datadir_samples"),
          "method.json:empty_footprint.mysql_empty_datadir_samples", commas)
    f.put("method.mysql_empty_spread", empty.get("mysql_empty_datadir_spread_bytes"),
          "method.json:empty_footprint.mysql_empty_datadir_spread_bytes", commas)
    f.put("method.shared_growth", empty.get("mysql_shared_growth_bytes"),
          "method.json:empty_footprint.mysql_shared_growth_bytes", human)
    f.put("method.container_overhead",
          (m.get("dolt_container_overhead") or {}).get("seconds"),
          "method.json:dolt_container_overhead.seconds", lambda x: f"{x:.2f}")
    rep = m.get("repeatability_from_run") or {}
    for label in ("bytes", "seconds"):
        d = rep.get(label) or {}
        f.put(f"method.repeat_{label}_median", d.get("median_spread_percent"),
              f"method.json:repeatability_from_run.{label}.median_spread_percent", one)
        f.put(f"method.repeat_{label}_worst", d.get("worst_spread_percent"),
              f"method.json:repeatability_from_run.{label}.worst_spread_percent", one)
        f.put(f"method.repeat_{label}_units", d.get("units_repeated"),
              f"method.json:repeatability_from_run.{label}.units_repeated", commas)


def _run_facts(f, progress):
    units = (progress or {}).get("units") or {}
    done = [u for u in units.values() if u.get("status") == "done"]
    f.put("run.units_done", len(done) or None, "progress.json: units with status done", commas)
    f.put("run.units_total", len(units) or None, "progress.json: units recorded", commas)
    f.put("run.hours", sum((u.get("wall_seconds") or 0) for u in done) / 3600 or None,
          "progress.json:*.wall_seconds", one)
    singles = [u for u in done if (u.get("samples") or 1) == 1]
    f.put("run.single_sample_units", len(singles) or None,
          "progress.json: units measured once", commas)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--missing", action="store_true", help="only facts with no measurement")
    a = ap.parse_args()
    f = build()
    names = f.missing() if a.missing else sorted(f)
    width = max((len(n) for n in names), default=0)
    for n in names:
        print(f"  {n:<{width}}  {f[n]:<28}  {f.sources[n]}")
    print(f"\n  {len(f)} fact(s), {len(f.missing())} without a measurement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
