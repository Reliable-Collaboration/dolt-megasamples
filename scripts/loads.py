#!/usr/bin/env python3
"""The three pairs and how to read one measurement of any of them out of build/results.json --
shared by the figures (scripts/charts.py) and the tables (scripts/report_pairs.py), so a number
drawn and a number tabulated come from the same place.

Every pair has the same five loads in the same order: the baseline in bulk, the baseline one row
at a time, and the Dolt engine one commit per database, one INSERT per row, one commit per row.
"""

TESTS = ["mysql", "mysql_rowwise", "dolt_oneshot", "dolt_rowinsert", "dolt_rowcommit"]
PAIR_TESTS = {"pg": ["postgres", "postgres_rowwise", "doltgres_oneshot", "doltgres_rowinsert", "doltgres_rowcommit"],
              "lite": ["sqlite", "sqlite_rowwise", "doltlite_oneshot", "doltlite_rowinsert", "doltlite_rowcommit"]}
SHAPES = ["bulk", "rowwise", "oneshot", "rowinsert", "rowcommit"]      # the five, by position
SHAPE_LABELS = {"bulk": "the baseline in bulk", "rowwise": "the baseline, one INSERT per row",
                "oneshot": "one commit per database", "rowinsert": "one INSERT per row, one commit",
                "rowcommit": "one commit per row"}
PAIRS = {
    "dolt": {"title": "MySQL and Dolt", "baseline": "MySQL", "engine": "Dolt", "tests": TESTS,
             "labels": {"mysql": "MySQL — extended INSERTs", "mysql_rowwise": "MySQL — one INSERT per row",
                        "dolt_oneshot": "Dolt — one commit per database",
                        "dolt_rowinsert": "Dolt — one INSERT per row, one commit", "dolt_rowcommit": "Dolt — one commit per row"},
             "short": {"mysql": "MySQL\nextended", "mysql_rowwise": "MySQL\n1 INSERT/row", "dolt_oneshot": "Dolt\n1 commit/db",
                       "dolt_rowinsert": "Dolt\n1 INSERT/row", "dolt_rowcommit": "Dolt\n1 commit/row"}},
    "pg": {"title": "PostgreSQL and DoltgreSQL", "baseline": "PostgreSQL", "engine": "DoltgreSQL", "tests": PAIR_TESTS["pg"],
           "labels": {"postgres": "PostgreSQL — COPY", "postgres_rowwise": "PostgreSQL — one INSERT per row",
                      "doltgres_oneshot": "DoltgreSQL — one commit per database",
                      "doltgres_rowinsert": "DoltgreSQL — one INSERT per row, one commit",
                      "doltgres_rowcommit": "DoltgreSQL — one commit per row"},
           "short": {"postgres": "PostgreSQL\nCOPY", "postgres_rowwise": "PostgreSQL\n1 INSERT/row",
                     "doltgres_oneshot": "DoltgreSQL\n1 commit/db", "doltgres_rowinsert": "DoltgreSQL\n1 INSERT/row",
                     "doltgres_rowcommit": "DoltgreSQL\n1 commit/row"}},
    "lite": {"title": "SQLite and DoltLite", "baseline": "SQLite", "engine": "DoltLite", "tests": PAIR_TESTS["lite"],
             "labels": {"sqlite": "SQLite — one transaction", "sqlite_rowwise": "SQLite — one INSERT per row",
                        "doltlite_oneshot": "DoltLite — one commit per database",
                        "doltlite_rowinsert": "DoltLite — one INSERT per row, one commit",
                        "doltlite_rowcommit": "DoltLite — one commit per row"},
             "short": {"sqlite": "SQLite\none transaction", "sqlite_rowwise": "SQLite\n1 INSERT/row",
                       "doltlite_oneshot": "DoltLite\n1 commit/db", "doltlite_rowinsert": "DoltLite\n1 INSERT/row",
                       "doltlite_rowcommit": "DoltLite\n1 commit/row"}},
}
PAIR_ORDER = ["dolt", "pg", "lite"]
for _p in PAIRS.values():
    _p["baseline_test"] = _p["tests"][0]


def test_of(pair, shape):
    """The test name of a shape in a pair: shape 'rowcommit' of 'pg' is 'doltgres_rowcommit'."""
    return PAIRS[pair]["tests"][SHAPES.index(shape)]


def rows_of(r, pair="dolt"):
    """The rows the pair's source holds for a database (the pairs' ports differ from MySQL's by a few)."""
    if pair != "dolt":
        n = ((r.get("pairs") or {}).get("source_rows") or {}).get(pair)
        if n:
            return n
    return r.get("rows_mysql") or 0


def value(r, test, axis, policy="deferred"):
    """One MySQL/Dolt measurement, or None. `axis` is 'bytes' or 'seconds'; `policy` picks the
    row-by-row load that dropped its secondary indexes or the one that kept them."""
    sfx = "_inline" if policy == "inline" else ""
    if test == "mysql":
        return r.get("mysql_disk_bytes") if axis == "bytes" else r.get("mysql_load_seconds")
    if test == "mysql_rowwise":
        return r.get(f"mysql_rowwise_bytes{sfx}") if axis == "bytes" else r.get(f"mysql_rowwise_seconds{sfx}")
    m = (r.get("modes", {}) or {}).get(test.replace("dolt_", "") + sfx, {}) or {}
    return m.get("disk_bytes") if axis == "bytes" else m.get("total_seconds")


def samples(r, test, axis, policy="deferred"):
    """Every repeat of a MySQL/Dolt measurement, or None when it was measured once."""
    sfx = "_inline" if policy == "inline" else ""
    key = "bytes_all" if axis == "bytes" else "seconds_all"
    if test.startswith("dolt_"):
        got = ((r.get("modes", {}) or {}).get(test.replace("dolt_", "") + sfx, {}) or {}).get(key)
    else:
        got = (r.get("mysql_spread" if test == "mysql" else f"mysql_rowwise_spread{sfx}") or {}).get(key)
    return got if got and len(got) > 1 else None


def measure(r, pair, test, axis, policy="deferred"):
    """One measurement of any pair, or None: the settled size, or the load plus its settle step."""
    if pair == "dolt":
        return value(r, test, axis, policy)
    per_row = test != PAIRS[pair]["baseline_test"] and "oneshot" not in test
    key = test + ("_inline" if policy == "inline" and per_row else "")
    u = ((r.get("pairs") or {}).get(pair) or {}).get(key)
    if not u:
        return None
    if axis == "bytes":
        return u.get("disk_bytes")
    return u.get("load_seconds") if test in ("postgres", "sqlite") else u.get("total_seconds")


def spread(r, pair, test, axis, policy="deferred"):
    """Every repeat, or None; the pairs' units are single samples."""
    return samples(r, test, axis, policy) if pair == "dolt" else None


def complete(results, pair, axis="bytes"):
    """The databases where every load of the pair has a result, so totals stand for one population."""
    return [d for d, r in results.items()
            if all(measure(r, pair, t, "bytes") and measure(r, pair, t, "seconds") is not None
                   for t in PAIRS[pair]["tests"])]
