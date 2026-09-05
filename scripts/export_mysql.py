#!/usr/bin/env python3
"""Dump every sample database out of a running mysql-megasamples image.

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
from common import DUMPS, MYSQL_CONTAINER, databases, human, run  # noqa: E402

DUMP_ARGS = ["--no-tablespaces", "--skip-comments", "--routines", "--events", "--triggers",
             "--single-transaction", "--default-character-set=utf8mb4"]


def export(db, force):
    out = os.path.join(DUMPS, f"{db}.sql")
    if os.path.exists(out) and not force:
        print(f"  = {db:<24} {human(os.path.getsize(out)):>12}  (already dumped)")
        return os.path.getsize(out)
    tmp = out + ".part"
    with open(tmp, "wb") as fh:
        p = run("docker", "exec", MYSQL_CONTAINER, "mysqldump", "-uroot", "-proot",
                *DUMP_ARGS, "--databases", db, capture_output=False, stdout=fh,
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
    a = ap.parse_args()

    os.makedirs(DUMPS, exist_ok=True)
    names = a.only or databases()
    print(f"exporting {len(names)} database(s) from {MYSQL_CONTAINER}")
    total = sum(export(db, a.force) for db in names)
    print(f"\n{len(names)} dumps, {human(total)} of SQL in {os.path.relpath(DUMPS, os.getcwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
