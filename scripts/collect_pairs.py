#!/usr/bin/env python3
"""Fold the two further pairs' timed runs into build/results.json.

  python3 scripts/collect_pairs.py

`run_pairs.py` records every unit in build/progress.json with a `pair` field. This copies the
completed ones under `results[db]["pairs"][pair][phase(_inline)]`, beside the MySQL/Dolt numbers
`collect.py` folds, so the documents and the landing page read one file. Nothing is computed
here: sizes, times, memory peaks, the refusals and the index report are carried as recorded.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human, load_results, save_results  # noqa: E402
from pairs import ENGINE, PHASES, reference  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")


def settle_failed(u):
    """Whether a unit's garbage collection failed, judged from the errors every unit records.

    The `settled` flag is newer than some of the units, and one of those (DoltLite, dvdstore, per-row
    commits with the indexes inline) carries the very out-of-memory error the flag was made for, so
    the flag alone let its uncollected footprint through as a size."""
    if u.get("settled") is False:
        return True
    return any(e.get("object") == "settle" or str(e.get("message", "")).startswith("settle:")
               for e in u.get("errors") or [])


def refusals(u):
    """The schema objects the engine would not take, one line each, deduplicated by object."""
    seen, out = set(), []
    for e in u.get("errors") or []:
        obj = e.get("object") or f"line {e.get('line')}"
        if obj.startswith("TABLE DATA") or obj in seen:
            continue
        seen.add(obj)
        out.append(f"{obj}: {e.get('message', '')[:120]}")
    return out


def main():
    if not os.path.exists(PROGRESS):
        sys.exit("no build/progress.json; `make run-pg` or `make run-lite` produces it")
    p = json.load(open(PROGRESS, encoding="utf-8"))
    r = load_results()
    # the pair entries are a function of the recorded units, rebuilt on every fold, so a unit that was
    # superseded or cleaned cannot leave its old numbers in the documents
    for entry in r.values():
        if isinstance(entry, dict):
            entry.pop("pairs", None)
    counted = shared = 0
    for key, u in p["units"].items():
        pair = u.get("pair")
        if not pair or u.get("status") != "done":
            continue
        parts = key.split("/")
        phase, db = parts[0], parts[1]
        suffix = "_inline" if parts[2:] == ["inline"] else ""
        # the method requires a DoltgreSQL load in a server of its own; a unit measured on the first
        # runner's shared server is not reported, and the chain measures it again
        if ENGINE[phase] == "doltgres" and u.get("isolation") != "one server per unit":
            shared += 1
            continue
        entry = r.setdefault(db, {}).setdefault("pairs", {})
        entry.setdefault("source_rows", {})[pair] = u.get("source_rows")
        # the rows a per-row load writes: a virtual table's rows are its content table's, counted
        # again, and no INSERT ever names it, so they are left out of what a commit-per-row load
        # is expected to commit
        try:
            ref = reference(pair, db)
            virtual = set(ref.get("virtual_tables") or [])
            entry.setdefault("source_rows_committed", {})[pair] = sum(
                v or 0 for t, v in ref["rows"].items() if t not in virtual)
        except RuntimeError:
            pass
        settled = not settle_failed(u)
        m = entry.setdefault(pair, {})
        m[phase + suffix] = {
            "engine": ENGINE[phase],
            # a store that could not be collected has a footprint, not a settled size: every consumer
            # of disk_bytes -- tables, totals, figures, facts, the audit -- then leaves it out alike
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
            "memory_anon_peak_bytes": u.get("memory_anon_peak_bytes"),
            "memory_total_peak_bytes": u.get("memory_total_peak_bytes"),
            "error_count": u.get("error_count", 0),
            "refused_objects": refusals(u),
            "indexes_checked": (u.get("index_parity") or {}).get("checked"),
            "indexes_refused": sorted(i.split("|")[1] for i in (u.get("index_parity") or {}).get("refused", {})),
            "indexes_dropped": (u.get("index_parity") or {}).get("dropped_by_dialect", []),
            "indexes_extra": (u.get("index_parity") or {}).get("extra", []),
            "notes": u.get("notes", []),
            "indexes_deferred": suffix == "",
            "finished": u.get("finished"),
        }
        counted += 1
    save_results(r)
    print(f"  . folded {counted} completed pair units into build/results.json")
    if shared:
        print(f"  . left out {shared} DoltgreSQL unit(s) measured on a shared server; they are measured again")
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
