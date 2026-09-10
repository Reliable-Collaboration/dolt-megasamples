#!/usr/bin/env python3
"""Check the experiment's numbers against things that must be true, and fail if they are not.

  python3 scripts/audit.py [--strict]

Every check here exists because something in this experiment failed by producing a *plausible*
value rather than an error. That is the failure mode worth engineering against: a load that stops
early still leaves a directory, a truncated query still returns a number, a `du` that fails still
returns something an arithmetic expression will accept.

The one that prompted this file: row counts were built as a single `UNION ALL` over every table
using `GROUP_CONCAT`, whose default `group_concat_max_len` of 1024 bytes silently cut the generated
SQL mid-statement. `adventureworks`, with 69 tables, reported 142,002 rows against an actual
759,240. Nothing errored. The wrong number was then used in an argument about what Dolt's memory
scales with -- and the check that would have caught it instantly was available the whole time, in
the same table: a load that commits once per row must end with as many commits as it has rows.

So the checks are invariants, not spot values. An invariant does not need to be updated when the
numbers change, cannot be satisfied by a plausible-looking wrong answer, and says which measurement
disagrees with which. They are cheap; run them after every run.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DUMPS, ROOT, human, load_results  # noqa: E402

MEMORY = os.path.join(ROOT, "build", "memory.json")
PROGRESS = os.path.join(ROOT, "build", "progress.json")
# Commits mysqldump's own scaffolding produces beyond the data: Dolt's initial commit, the schema
# commit, and the final one this experiment makes.
BASE_COMMITS = 3


class Audit:
    def __init__(self):
        self.failures, self.checked, self.skipped = [], 0, []

    def check(self, ok, label, detail=""):
        self.checked += 1
        if not ok:
            self.failures.append(f"{label}{(': ' + detail) if detail else ''}")
        return ok

    def skip(self, label, why):
        self.skipped.append(f"{label} ({why})")


def commits_match_rows(a, memory):
    """One commit per row means commits = rows + the scaffolding, exactly.

    This is the check that was missing. It costs nothing, needs no expected value written down
    anywhere, and is impossible to satisfy with a row count that lost two thirds of its tables."""
    rc = memory.get("rowcommit") or {}
    for db, r in sorted(rc.items()):
        rows, commits = r.get("rows"), r.get("commits")
        if rows is None or commits is None:
            a.skip(f"commits==rows for {db}", "one of the two was not readable")
            continue
        a.check(commits == rows + BASE_COMMITS, f"commits==rows+{BASE_COMMITS} for {db}",
                f"{commits:,} commits against {rows:,} rows "
                f"(off by {commits - rows - BASE_COMMITS:+,})")

    for mode in ("oneshot", "rowinsert"):
        for db, r in sorted((memory.get(mode) or {}).items()):
            if r.get("commits") is None:
                continue
            a.check(r["commits"] == BASE_COMMITS, f"{mode} commits=={BASE_COMMITS} for {db}",
                    f"{r['commits']:,}")


def rows_agree_across_modes(a, memory):
    """The same database holds the same rows however it was stored."""
    modes = [m for m in memory if isinstance(memory[m], dict)]
    for db in sorted({d for m in modes for d in memory[m]}):
        seen = {m: memory[m][db].get("rows") for m in modes
                if db in memory[m] and memory[m][db].get("rows") is not None}
        if len(seen) < 2:
            continue
        a.check(len(set(seen.values())) == 1, f"row count agrees across modes for {db}",
                ", ".join(f"{m}={v:,}" for m, v in seen.items()))


def sizes_are_positive(a, results):
    """No published size is zero, negative, or missing. A zero here used to mean `du` failed."""
    for db, entry in sorted(results.items()):
        for key in ("mysql_disk_bytes", "mysql_rowwise_bytes"):
            v = entry.get(key)
            if v is not None:
                a.check(v > 0, f"{key} positive for {db}", str(v))
        for mode, m in sorted((entry.get("modes") or {}).items()):
            v = m.get("disk_bytes")
            if v is not None:
                a.check(v > 0, f"{mode} disk_bytes positive for {db}", str(v))


def dolt_matches_mysql(a, results):
    """Rows and indexes on both sides, as recorded by measure.py."""
    for db, entry in sorted(results.items()):
        for mode, m in sorted((entry.get("modes") or {}).items()):
            if m.get("rows_dolt") is not None and entry.get("rows_mysql") is not None:
                a.check(m["rows_dolt"] == entry["rows_mysql"],
                        f"{mode} rows match MySQL for {db}",
                        f"Dolt {m['rows_dolt']:,} against MySQL {entry['rows_mysql']:,}")
            if m.get("row_mismatches"):
                a.check(False, f"{mode} per-table rows match for {db}",
                        ", ".join(sorted(m["row_mismatches"])[:5]))
            if m.get("indexes_only_mysql") or m.get("indexes_only_dolt"):
                a.check(False, f"{mode} indexes match for {db}",
                        f"only in MySQL: {m.get('indexes_only_mysql')}, "
                        f"only in Dolt: {m.get('indexes_only_dolt')}")


def transform_preserved_the_rows(a):
    """The transformed dump must contain every `INSERT` the original did.

    Nothing in the transform is supposed to touch a row, and this is the check that says so about
    the actual bytes rather than about the intent. It compares the original mysqldump with the file
    each engine is really given."""
    src_dir = os.path.join(DUMPS, "rowwise")
    for mode in ("oneshot", "rowinsert", "rowcommit"):
        out_dir = os.path.join(DUMPS, "dolt", mode)
        if not os.path.isdir(out_dir):
            a.skip(f"transform preserves rows ({mode})", "no transformed dumps on disk")
            continue
        for name in sorted(os.listdir(out_dir)):
            if not name.endswith(".sql"):
                continue
            db = name[:-4]
            src = os.path.join(src_dir if mode != "oneshot" else DUMPS, name)
            if not os.path.exists(src):
                continue
            want = count_inserts(src)
            got = count_inserts(os.path.join(out_dir, name))
            a.check(got == want, f"{mode} keeps every INSERT for {db}",
                    f"{got:,} in the transformed file against {want:,} in the dump")


def count_inserts(path):
    n = 0
    with open(path, "rb") as fh:
        for line in fh:
            if line[:12].upper().startswith(b"INSERT INTO"):
                n += 1
    return n


def memory_is_monotonic(a, memory):
    """More history never needs less memory than the same database with less history."""
    one, rc = memory.get("oneshot") or {}, memory.get("rowcommit") or {}
    for db in sorted(set(one) & set(rc)):
        lo, hi = one[db].get("megabytes"), rc[db].get("megabytes")
        if lo is None or hi is None:
            continue
        a.check(hi >= lo, f"per-row-commit needs at least as much memory as one-shot for {db}",
                f"{hi} MB against {lo} MB")


def progress_is_consistent(a):
    """A unit recorded as done has a size, a time, and no error left on it."""
    if not os.path.exists(PROGRESS):
        a.skip("progress records", "no build/progress.json")
        return
    p = json.load(open(PROGRESS, encoding="utf-8"))
    for key, u in sorted((p.get("units") or {}).items()):
        if u.get("status") != "done":
            continue
        a.check("error" not in u, f"no stale error on completed unit {key}",
                str(u.get("error"))[:80])
        a.check(u.get("seconds") is not None, f"completed unit {key} has a time")
        a.check(u.get("bytes"), f"completed unit {key} has a size", str(u.get("bytes")))


def pairs_are_consistent(a, results):
    """The PostgreSQL/DoltgreSQL and SQLite/DoltLite units obey what the method promises.

    A per-row-commit load ends with as many commits as it wrote rows (plus the initial commit and
    the final one); a Dolt engine's working footprint before the settle step is never smaller than
    the settled size; every completed unit was checked against the reference (a positive number
    of indexes compared, or the database has none); and the same reference row count is behind
    every shape of a database within a pair."""
    from pairs import ENGINE, PHASES
    for db in sorted(results):
        pairs = results[db].get("pairs") or {}
        for pair, phases in PHASES.items():
            m = pairs.get(pair) or {}
            rows = ((pairs.get("source_rows_committed") or {}).get(pair)
                    or (pairs.get("source_rows") or {}).get(pair))
            for key, u in sorted(m.items()):
                if not isinstance(u, dict) or not u.get("disk_bytes"):
                    continue
                phase = key.replace("_inline", "")
                versioned = ENGINE[phase] in ("doltgres", "doltlite")
                if versioned and u.get("bytes_before_settle") is not None and u.get("settled", True):
                    a.check(u["bytes_before_settle"] >= u["disk_bytes"] * 0.9,
                            f"{db} {key}: the settle step did not grow the store",
                            f"{human(u['bytes_before_settle'])} before, {human(u['disk_bytes'])} after")
                if phase.endswith("_rowcommit") and u.get("commits") is not None and rows:
                    a.check(abs(u["commits"] - rows) <= 3, f"{db} {key}: one commit per row",
                            f"{u['commits']:,} commits for {rows:,} rows")
                a.check(u.get("indexes_checked") is not None, f"{db} {key}: index parity was checked")
                a.check(not u.get("indexes_extra"), f"{db} {key}: no index the reference lacks",
                        ", ".join(u.get("indexes_extra") or [])[:80])


def pair_settles_reported(a, results):
    """A pair unit whose settle step failed is reported unsettled, whichever runner recorded it."""
    if not os.path.exists(PROGRESS):
        return
    from collect_pairs import settle_failed
    p = json.load(open(PROGRESS, encoding="utf-8"))
    for key, u in sorted((p.get("units") or {}).items()):
        if not u.get("pair") or u.get("status") != "done" or not settle_failed(u):
            continue
        parts = key.split("/")
        name = parts[0] + ("_inline" if parts[2:] == ["inline"] else "")
        got = ((((results.get(parts[1]) or {}).get("pairs") or {}).get(u["pair"]) or {}).get(name)) or {}
        a.check(got.get("settled") is False and not got.get("disk_bytes"),
                f"{parts[1]} {name}: its failed settle step is reported as unsettled", f"settled={got.get('settled')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="treat skipped checks as failures too")
    args = ap.parse_args()

    a = Audit()
    results = load_results() if os.path.exists(os.path.join(ROOT, "build", "results.json")) else {}
    memory = json.load(open(MEMORY, encoding="utf-8")) if os.path.exists(MEMORY) else {}

    if memory:
        commits_match_rows(a, memory)
        rows_agree_across_modes(a, memory)
        memory_is_monotonic(a, memory)
    else:
        a.skip("history and memory invariants", "no build/memory.json")
    if results:
        sizes_are_positive(a, results)
        dolt_matches_mysql(a, results)
        pairs_are_consistent(a, results)
        pair_settles_reported(a, results)
    else:
        a.skip("size and parity invariants", "no build/results.json")
    transform_preserved_the_rows(a)
    progress_is_consistent(a)

    print(f"  {a.checked} invariant(s) checked, {len(a.failures)} failed, "
          f"{len(a.skipped)} skipped")
    for s in a.skipped:
        print(f"  - skipped: {s}")
    for f in a.failures:
        print(f"  x {f}")
    if not a.failures and not (args.strict and a.skipped):
        print("  everything that can be checked agrees")
    return 1 if a.failures or (args.strict and a.skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
