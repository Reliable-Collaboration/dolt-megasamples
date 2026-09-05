#!/usr/bin/env python3
"""Make a mysqldump loadable by Dolt, and say exactly what had to change.

  python3 scripts/dolt_dialect.py build/dumps/sakila.sql out.sql

Three transformations, each for a measured reason. Nothing here touches a row: every `INSERT` is
passed through untouched, which is what keeps the size comparison honest.

**The dump is handled as bytes, never as text.** `adventureworks` alone carries 20,156 `_binary`
literals of spatial data; decoding the file as UTF-8 with `errors="replace"` turns every byte that
is not valid UTF-8 into U+FFFD and grows the file by 267,588 bytes -- silently corrupting the rows
before Dolt ever sees them. The first version of this script did exactly that, and Dolt caught it by
rejecting the first corrupted `INSERT`.

0. **Statements that are mysqldump's scaffolding, not the database, are removed**: the
   `ALGORITHM=`/`SQL SECURITY` clauses on `CREATE VIEW`, and the `DROP ... IF EXISTS` lines emitted
   before every routine. Dolt parses neither, and because one rejected statement aborts the rest of
   the routine section, a single `DROP FUNCTION IF EXISTS` costs sakila all 6 of its routines.

1. **Version-gated comments are unwrapped.** mysqldump writes views and stored routines inside
   MySQL's conditional-execution syntax, `/*!50001 CREATE VIEW ... */`. Real MySQL executes what is
   inside when its version is high enough; Dolt does not parse the form at all, so views and
   routines silently never arrive -- sakila lost all 6, pubs 3, oracle_oe 6. Unwrapping is what
   MySQL itself would do.
2. **`DEFINER=` clauses are dropped.** They name a user that does not exist in a fresh Dolt server,
   and nothing in this comparison depends on who owns a view.
3. **Cross-database foreign keys are dropped**, with the constraint named in the report. Dolt keeps
   each database as its own repository and says so plainly: "only foreign keys on the same database
   are currently supported". `oracle_oe.customers` has one, into `oracle_hr.employees`; without this
   the whole database fails to load, which is why it first measured 56 KB against MySQL's 19.7 MB.
"""
import argparse, re, sys

VERSIONED = re.compile(rb"/\*!\d{5}\s?(.*?)\*/", re.S)
DEFINER = re.compile(rb"\s*DEFINER\s*=\s*[^\s]+@[^\s]+", re.I)
# mysqldump writes `CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW ...`; Dolt parses neither
# clause. Both are MySQL execution hints, not part of what the view computes.
VIEW_CLAUSES = re.compile(rb"CREATE\s+ALGORITHM\s*=\s*\w+\s*(SQL SECURITY\s+\w+\s*)?", re.I)
# `DROP FUNCTION IF EXISTS x` is Dolt-unsupported, and mysqldump emits one before every routine.
# The failure aborts the rest of the routine section, which is why one rejected DROP costs sakila
# all 6 of its routines and employees all 7.
DROP_ROUTINE = re.compile(rb"^\s*DROP\s+(FUNCTION|PROCEDURE|TRIGGER)\s+IF\s+EXISTS\s+[^;]+;\s*$",
                          re.I | re.M)

CROSS_FK = re.compile(
    rb"^\s*CONSTRAINT\s+`[^`]+`\s+FOREIGN KEY\s*\([^)]*\)\s*REFERENCES\s+`([^`]+)`\.`[^`]+`.*?,?\s*$",
    re.I)


def transform(text, database):
    """Return (sql, notes) as bytes. `database` is the schema the dump belongs to."""
    if isinstance(text, str):
        raise TypeError("pass the dump as bytes: decoding it corrupts _binary literals")
    if isinstance(database, str):
        database = database.encode()
    notes = []

    # 1. unwrap the executable comments mysqldump uses for views and routines
    before = len(VERSIONED.findall(text))
    text = VERSIONED.sub(lambda m: m.group(1), text)
    if before:
        notes.append(f"unwrapped {before} version-gated comment block(s)")

    # 1b. drop the view clauses Dolt cannot parse, and the DROP ... IF EXISTS lines it rejects
    text, n = VIEW_CLAUSES.subn(b"CREATE ", text)
    if n:
        notes.append(f"removed ALGORITHM/SQL SECURITY from {n} view definition(s)")
    text, n = DROP_ROUTINE.subn(b"", text)
    if n:
        notes.append(f"removed {n} `DROP ... IF EXISTS` statement(s) Dolt rejects")

    # 2. drop DEFINER clauses
    text, n = DEFINER.subn(b"", text)
    if n:
        notes.append(f"dropped {n} DEFINER clause(s)")

    # 3. drop foreign keys that point at another database, and any comma they leave dangling
    out, dropped = [], []
    for line in text.splitlines(keepends=True):
        m = CROSS_FK.match(line)
        if m and m.group(1) != database:
            dropped.append(line.strip().rstrip(b",").decode("utf-8", "replace"))
            # if this was the last item in the CREATE TABLE list, the previous line's comma must go
            for i in range(len(out) - 1, -1, -1):
                if out[i].strip():
                    break
            continue
        if dropped and line.lstrip().startswith(b")") and out:
            for i in range(len(out) - 1, -1, -1):
                stripped = out[i].rstrip()
                if stripped:
                    if stripped.endswith(b","):
                        out[i] = stripped[:-1] + b"\n"
                    break
        out.append(line)
    if dropped:
        notes.append(f"dropped {len(dropped)} cross-database foreign key(s): "
                     + "; ".join(d[:80] for d in dropped))
    return b"".join(out), notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--database", help="the schema this dump belongs to (default: file stem)")
    a = ap.parse_args()
    import os
    db = a.database or os.path.basename(a.source).rsplit(".", 1)[0]
    sql, notes = transform(open(a.source, "rb").read(), db)
    open(a.out, "wb").write(sql)
    for n in notes:
        print(f"  . {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
