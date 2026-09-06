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
from common import ROOT, human, load_results  # noqa: E402

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
        "ri_ratio": f"{sum((r[d]['modes']['rowinsert']['disk_bytes']) for d in ri) / sum(r[d]['mysql_disk_bytes'] for d in ri):.2f}×",
        "rc_ratio": f"{sum((r[d]['modes']['rowcommit']['disk_bytes']) for d in rc) / sum(r[d]['mysql_disk_bytes'] for d in rc):.1f}×",
        "rc_one_ratio": f"{sum((r[d]['modes']['oneshot']['disk_bytes']) for d in rc) / sum(r[d]['mysql_disk_bytes'] for d in rc):.2f}×",
        "identical": sum(1 for x in deltas if x <= 0.0001),
        "widest": f"{max(deltas) * 100:.1f}%",
        "aw_data": f"{one('adventureworks')['disk_bytes'] / MB:.1f} MB",
        **spread_facts(r),
    }


def spread_facts(r):
    """The repeatability claim, taken from the run's own repeats.

    The README says the per-row-commit size is the one number here that does not repeat. That is a
    claim about the measurements, so it is pinned to them: the widest spread any repeated
    per-row-commit load actually showed, and the database it belongs to."""
    worst, where = 0.0, None
    for db, entry in r.items():
        xs = ((entry.get("modes", {}) or {}).get("rowcommit") or {}).get("bytes_all") or []
        if len(xs) > 1:
            xs = sorted(xs)
            med = xs[len(xs) // 2]
            if med and (xs[-1] - xs[0]) / med > worst:
                worst, where = (xs[-1] - xs[0]) / med, db
    if not where:
        return {"rc_spread": "n/a", "rc_spread_db": "n/a"}
    return {"rc_spread": f"{worst * 100:.0f}%", "rc_spread_db": where}


# Each claim is a sentence fragment that must appear verbatim in the named documents, with the value
# filled in from the measurements. If a fragment is reworded the check fails loudly rather than
# silently passing, which is the intended trade: prose about numbers should be pinned to them.
METHOD_CLAIMS = [
    # measured by scripts/method_checks.py into build/method.json
    ("a measured {overhead} s per container", ["README.md"]),
    ("data directory is **{empty_mysql}** — measured {empty_samples} times during this run, with "
     "{empty_spread} bytes between the largest and the smallest", ["README.md"]),
    ("InnoDB shared files grew by **{shared_growth}**", ["README.md"]),
]

CLAIMS = [
    # `adventureworks`'s statistics figure is deliberately not pinned: it was observed during
    # console use and a controlled probe does not reproduce it, so it is prose, not a measurement.
    # the comparison word varies with the measurement, so only the figure is pinned
    ("{aw_data} of data they describe", DOCS),
    ("for {rowcommit_worse} of the {rowcommit_dbs} databases", DOCS),
    ("within 0.5% for {within_05} of the {rowinsert_dbs} databases", DOCS),
    ("{mult_low} to {mult_high} the single-commit load", DOCS),
    ("{indexes} in MySQL, {indexes} in Dolt", DOCS),
]


WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def normalise(text):
    """A minus sign is a minus sign. The README renders ranges with U+2212 and the templates emit
    ASCII, which is a typographic difference, not a disagreement about a number."""
    return text.replace("\u2212", "-").replace("\u00a0", " ")


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
    method_path = os.path.join(ROOT, "build", "method.json")
    if os.path.exists(method_path):
        m = json.load(open(method_path, encoding="utf-8"))
        e = m.get("empty_footprint") or {}
        f.update({
            "overhead": f"{m['dolt_container_overhead']['seconds']:.2f}",
            "empty_mysql": human(e["mysql_empty_datadir_bytes"]) if e else "n/a",
            "empty_samples": e.get("mysql_empty_datadir_samples", 0),
            "empty_spread": e.get("mysql_empty_datadir_spread_bytes", 0),
            "shared_growth": human(e["mysql_shared_growth_bytes"]) if e.get(
                "mysql_shared_growth_bytes") else "0 bytes",
        })
        globals()["CLAIMS"] = CLAIMS + METHOD_CLAIMS
    text = {d: open(os.path.join(ROOT, d), encoding="utf-8").read() for d in DOCS}

    failures = []
    for template, docs in CLAIMS:
        wants = variants(template, f)
        where = [d for d in docs if any(normalise(w) in normalise(text[d]) for w in wants)]
        if not where:
            failures.append("no document says " + " or ".join(f'"{w}"' for w in sorted(wants)))
        else:
            found = next(w for w in sorted(wants)
                         if any(normalise(w) in normalise(text[d]) for d in where))
            print(f'  . "{found}" — in {", ".join(where)}')

    for d in failures:
        print(f"  x {d}")
    print(f"claims: {len(failures)} stale or missing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
