#!/usr/bin/env python3
"""Verify the hand-written numbers in the prose against build/results.json.

  python3 scripts/check_claims.py

`REPORT.md`, the README's results table and the figures are generated, so they cannot drift. The
prose around them is written by a person and it *did* drift: after a re-measurement, three claims
were wrong at once -- an `adventureworks` statistics figure from a superseded run, "six of the nine"
where seven was right, and "ten of the eleven" where nine was.

So every load-bearing number in `README.md` and `JOURNAL.md` is listed here with the query that
produces it, and `make check` fails if the document no longer says what the measurements say. The
point is not to police wording; it is that a number in a sentence should be as checkable as a number
in a table.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, load_results  # noqa: E402

MB = 1024 * 1024
DOCS = ("README.md", "JOURNAL.md")


def facts(r):
    def one(db):
        return (r[db].get("modes", {}).get("oneshot") or {})

    def mode(db, m):
        return (r[db].get("modes", {}).get(m) or {})

    cov = [d for d in r if r[d].get("mysql_disk_bytes") and one(d).get("disk_bytes")]
    my = sum(r[d]["mysql_disk_bytes"] for d in cov)
    do = sum(one(d)["disk_bytes"] for d in cov)
    ratios = sorted((one(d)["disk_bytes"] / r[d]["mysql_disk_bytes"], d) for d in cov)
    rc = [d for d in r if mode(d, "rowcommit").get("disk_bytes")]
    ri = [d for d in r if mode(d, "rowinsert").get("disk_bytes")]
    mult = sorted(mode(d, "rowcommit")["disk_bytes"] / one(d)["disk_bytes"] for d in rc)
    deltas = [abs(mode(d, "rowinsert")["disk_bytes"] - one(d)["disk_bytes"]) / one(d)["disk_bytes"]
              for d in ri]
    return {
        "databases": len(cov),
        "rows": sum(r[d].get("rows_mysql") or 0 for d in cov),
        "ratio": f"{do / my:.2f}×",
        "ratio_low": f"{ratios[0][0]:.2f}×",
        "ratio_high": f"{ratios[-1][0]:.2f}×",
        "indexes": sum(r[d].get("indexes_mysql") or 0 for d in cov),
        "stats_total": f"{sum(one(d).get('stats_bytes') or 0 for d in cov) / MB:.1f} MB",

        "rowcommit_dbs": len(rc),
        "rowinsert_dbs": len(ri),
        "mult_low": f"{mult[0]:.0f}×",
        "mult_high": f"{mult[-1]:.0f}×",
        "rowcommit_worse": sum(1 for d in rc if mode(d, "rowcommit")["disk_bytes"]
                               > r[d]["mysql_disk_bytes"]),
        "within_05": sum(1 for x in deltas if x <= 0.005),
        "identical": sum(1 for x in deltas if x <= 0.0001),
        "widest": f"{max(deltas) * 100:.1f}%",
        "aw_data": f"{one('adventureworks')['disk_bytes'] / MB:.1f} MB",
    }


# Each claim is a sentence fragment that must appear verbatim in the named documents, with the value
# filled in from the measurements. If a fragment is reworded the check fails loudly rather than
# silently passing, which is the intended trade: prose about numbers should be pinned to them.
CLAIMS = [
    # `adventureworks`'s statistics figure is deliberately not pinned: it was observed during
    # console use and a controlled probe does not reproduce it, so it is prose, not a measurement.
    ("more than the {aw_data} of data they describe", DOCS),
    ("for {rowcommit_worse} of the {rowcommit_dbs} databases", DOCS),
    ("within 0.5% for {within_05} of the {rowinsert_dbs} databases", DOCS),
    ("{mult_low} to {mult_high} the single-commit load", DOCS),
    ("{indexes} in MySQL, {indexes} in Dolt", DOCS),
]


WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def variants(template, f):
    """Every spelling the prose is allowed to use: "7 of the 9" and "seven of the nine" are the
    same claim, and a check that insisted on one would be about style rather than accuracy."""
    out = {template.format(**f)}
    worded = dict(f)
    for k, v in f.items():
        if isinstance(v, int) and v in WORDS:
            worded[k] = WORDS[v]
    out.add(template.format(**worded))
    return out


def main():
    r = load_results()
    if not r:
        sys.exit("no measurements; run `make measure` first")
    f = facts(r)
    text = {d: open(os.path.join(ROOT, d), encoding="utf-8").read() for d in DOCS}

    failures = []
    for template, docs in CLAIMS:
        wants = variants(template, f)
        where = [d for d in docs if any(w in text[d] for w in wants)]
        if not where:
            failures.append("no document says " + " or ".join(f'"{w}"' for w in sorted(wants)))
        else:
            found = next(w for w in sorted(wants) if any(w in text[d] for d in where))
            print(f'  . "{found}" — in {", ".join(where)}')

    for d in failures:
        print(f"  x {d}")
    print(f"claims: {len(failures)} stale or missing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
