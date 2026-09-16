#!/usr/bin/env python3
"""Dump every sample database out of a running sql-megasamples MySQL image.

  python3 scripts/export_mysql.py [--only sakila] [--force]

One `mysqldump` per database, written to `build/dumps/<db>.sql`. The dumps are the interchange
format for the whole experiment: Dolt speaks the MySQL dialect, so the same file that describes the
data in MySQL creates it in Dolt, and neither side gets a schema the other did not.

`--routines --events --triggers` are included so the comparison is of the whole database and not
just its rows. `--no-tablespaces` avoids needing PROCESS privileges; `--skip-comments` keeps the
dumps byte-stable between runs so re-exporting does not churn the checksums.
"""
import argparse, hashlib, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MYSQL_CONTAINER, databases, dumps_dir, human, run  # noqa: E402

DUMP_ARGS = ["--no-tablespaces", "--skip-comments", "--routines", "--events", "--triggers",
             "--single-transaction", "--default-character-set=utf8mb4"]
# `--skip-extended-insert` writes one INSERT per row instead of packing thousands into each
# statement. The rows are identical; only the statement count changes -- 312 statements for
# jaffle_shop instead of 3. This is the input for the rowinsert and rowcommit experiments.
PER_ROW_ARGS = DUMP_ARGS + ["--skip-extended-insert"]


def export(db, force, per_row=False):
    out = os.path.join(dumps_dir(per_row), f"{db}.sql")
    if os.path.exists(out) and not force:
        print(f"  = {db:<24} {human(os.path.getsize(out)):>12}  (already dumped)")
        return os.path.getsize(out)
    tmp = out + ".part"
    with open(tmp, "wb") as fh:
        p = run("docker", "exec", MYSQL_CONTAINER, "mysqldump", "-uroot", "-proot",
                *(PER_ROW_ARGS if per_row else DUMP_ARGS), "--databases", db,
                capture_output=False, stdout=fh,
                stderr=__import__("subprocess").PIPE, text=False)
    if p.returncode != 0:
        os.remove(tmp)
        sys.exit(f"{db}: mysqldump failed: {p.stderr.decode('utf-8', 'replace')[:300]}")
    os.replace(tmp, out)
    size = os.path.getsize(out)
    print(f"  . {db:<24} {human(size):>12}")
    return size


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append", help="one database, repeatable")
    ap.add_argument("--force", action="store_true", help="re-dump even if the file exists")
    ap.add_argument("--per-row", action="store_true",
                    help="one INSERT per row (build/dumps/rowwise/), for the rowinsert experiments")
    a = ap.parse_args()

    out_dir = dumps_dir(a.per_row)
    os.makedirs(out_dir, exist_ok=True)
    names = a.only or databases()
    kind = "one INSERT per row" if a.per_row else "extended INSERTs"
    print(f"exporting {len(names)} database(s) from {MYSQL_CONTAINER} ({kind})")
    total = sum(export(db, a.force, a.per_row) for db in names)
    print(f"\n{len(names)} dumps, {human(total)} of SQL in {os.path.relpath(out_dir, os.getcwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
