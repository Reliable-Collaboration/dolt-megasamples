#!/usr/bin/env python3
"""Fold the two further pairs' timed runs into build/results.json.

  python3 scripts/collect_pairs.py

`run_pairs.py` records every unit in build/progress.json with a `pair` field. This copies the units
measured with the current method (pairs.METHOD) under `results[db]["pairs"][pair][phase(_inline)]`,
beside the MySQL/Dolt numbers `collect.py` folds, so the documents and the landing page read one
file. Nothing is computed here: sizes, times, memory peaks, the refusals and the index report are
carried as recorded.

build/results.json is committed and build/progress.json is not, so a pair entry is withdrawn only
when this machine's progress.json holds a record of that unit which is not a current measurement --
one taken with an older method, or one being measured again. A fresh clone, whose progress.json has
no pair units, keeps every committed pair result; `make clean-pairs` removes them on purpose. (The
first version rebuilt the pair entries from progress.json alone, so a fresh clone's `make report`
deleted every committed pair result: 2026-09-10 review.)
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human, load_results, save_results  # noqa: E402
from pairs import ENGINE, METHOD, PAIR_OF, PHASES, committed_rows, settle_error  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")


def settle_failed(u):
    """Whether a unit's garbage collection failed, judged from the errors every unit records, so an
    older record without the `settled` flag cannot pass an uncollected footprint off as a size."""
    if u.get("settled") is False:
        return True
    return any(settle_error(e) for e in u.get("errors") or [])


def refusals(u):
    """The schema objects the engine would not take, one line each, deduplicated by object. A failed
    settle step is recorded on the unit but is not a refusal."""
    seen, out = set(), []
    for e in u.get("errors") or []:
        if settle_error(e):
            continue
        obj = e.get("object") or f"line {e.get('line')}"
        if obj.startswith("TABLE DATA") or obj in seen:
            continue
        seen.add(obj)
        out.append(f"{obj}: {e.get('message', '')[:120]}")
    return out


def folded(phase, u, suffix):
    settled = not settle_failed(u)
    parity = u.get("index_parity") or {}
    return {
        "engine": ENGINE[phase],
        # a store that could not be collected has a footprint, not a settled size: every consumer of
        # disk_bytes -- tables, totals, figures, facts, the audit -- then leaves it out alike
        "disk_bytes": u.get("bytes") if settled else None,
        "footprint_bytes": None if settled else u.get("bytes"),
        "bytes_before_settle": u.get("bytes_before_settle"),
        "database_bytes": u.get("database_bytes"),
        "empty_database_bytes": u.get("empty_database_bytes"),
        "load_seconds": u.get("seconds"),
        "settle_seconds": u.get("settle_seconds"),
        "total_seconds": round((u.get("seconds") or 0) + (u.get("settle_seconds") or 0), 1),
        "commits": u.get("commits"),
        "settled": settled,
        "memory_peak_bytes": u.get("memory_peak_bytes"),
        "memory_load_peak_bytes": u.get("memory_load_peak_bytes"),
        "memory_settle_peak_bytes": u.get("memory_settle_peak_bytes"),
        "memory_anon_peak_bytes": u.get("memory_anon_peak_bytes"),
        "memory_cgroup_peak_bytes": u.get("memory_cgroup_peak_bytes"),
        "error_count": u.get("error_count", 0),
        "refused_objects": refusals(u),
        "indexes_checked": parity.get("checked"),
        "indexes_refused": sorted(i.split("|")[1] for i in parity.get("refused", {})),
        "indexes_dropped": parity.get("dropped_by_dialect", []),
        "indexes_extra": parity.get("extra", []),
        "notes": u.get("notes", []),
        "indexes_deferred": suffix == "",
        "method": u.get("method"),
        "finished": u.get("finished"),
    }


def main():
    if not os.path.exists(PROGRESS):
        sys.exit("no build/progress.json; `make run-pg` or `make run-lite` produces it")
    p = json.load(open(PROGRESS, encoding="utf-8"))
    r = load_results()
    units = p.get("units") or {}
    keys = set(units) | set(p.get("superseded") or {})
    counted = withdrawn = 0
    for key in sorted(keys):
        parts = key.split("/")
        phase = parts[0]
        if phase not in ENGINE or len(parts) < 2:
            continue
        pair, db = PAIR_OF[phase], parts[1]
        suffix = "_inline" if parts[2:] == ["inline"] else ""
        name = phase + suffix
        live = units.get(key) or {}
        if not (live.get("status") == "done" and live.get("method") == METHOD):
            entry = ((r.get(db) or {}).get("pairs") or {}).get(pair)
            if entry and name in entry:
                del entry[name]
                withdrawn += 1
            continue
        pairs = r.setdefault(db, {}).setdefault("pairs", {})
        try:
            rows = committed_rows(pair, db)
        except RuntimeError:
            rows = live.get("source_rows")
        # the rows a load writes: a virtual table's rows are its content table's counted again
        pairs.setdefault("source_rows", {})[pair] = rows
        pairs.setdefault("source_rows_committed", {})[pair] = rows
        pairs.setdefault(pair, {})[name] = folded(phase, live, suffix)
        counted += 1
    save_results(r)
    print(f"  . folded {counted} pair unit(s) measured with method {METHOD} into build/results.json"
          + (f"; withdrew {withdrawn} taken with an older method or being measured again" if withdrawn else ""))
    for pair in PHASES:
        base = PHASES[pair][0]
        dbs = sorted(d for d in r if (r[d].get("pairs", {}).get(pair) or {}).get(base, {}).get("disk_bytes"))
        if not dbs:
            continue
        b0 = sum(r[d]["pairs"][pair][base]["disk_bytes"] for d in dbs)
        t0 = sum(r[d]["pairs"][pair][base].get("load_seconds") or 0 for d in dbs)
        print(f"  . {base:<9}: {len(dbs):>2} databases, {human(b0):>10}, {t0:>8,.0f}s")
        for ph in PHASES[pair][1:] + [x + "_inline" for x in PHASES[pair][1:]]:
            have = [d for d in dbs if (r[d]["pairs"][pair].get(ph) or {}).get("disk_bytes")]
            if not have:
                continue
            b = sum(r[d]["pairs"][pair][ph]["disk_bytes"] for d in have)
            t = sum(r[d]["pairs"][pair][ph].get("total_seconds") or 0 for d in have)
            b_base = sum(r[d]["pairs"][pair][base]["disk_bytes"] for d in have)
            t_base = sum(r[d]["pairs"][pair][base].get("load_seconds") or 0 for d in have)
            print(f"  . {ph:<26}: {len(have):>2} databases, {human(b):>10}, {t:>8,.0f}s "
                  f"({b / b_base:.2f}× the baseline's size, {t / max(1, t_base):.1f}× its time)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
