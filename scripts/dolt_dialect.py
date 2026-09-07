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
# Two clauses, stripped independently, because mysqldump puts DEFINER between them:
# `CREATE ALGORITHM=UNDEFINED DEFINER=`x`@`y` SQL SECURITY DEFINER VIEW ...`. A single pattern
# expecting SQL SECURITY to follow ALGORITHM only removed the first, and once DEFINER went too the
# statement read `CREATE  SQL SECURITY DEFINER VIEW`, which Dolt rejects -- so oracle_co's three
# views failed the load outright while MySQL, which accepts the clause, kept all three.
VIEW_ALGORITHM = re.compile(rb"CREATE\s+ALGORITHM\s*=\s*\w+\s*", re.I)
VIEW_SECURITY = re.compile(rb"\s*SQL\s+SECURITY\s+(DEFINER|INVOKER)\s*", re.I)
# `DROP FUNCTION IF EXISTS x` is Dolt-unsupported, and mysqldump emits one before every routine.
# The failure aborts the rest of the routine section, which is why one rejected DROP costs sakila
# all 6 of its routines and employees all 7.
DROP_ROUTINE = re.compile(rb"^\s*DROP\s+(FUNCTION|PROCEDURE|TRIGGER)\s+IF\s+EXISTS\s+[^;]+;\s*$",
                          re.I | re.M)

CROSS_FK = re.compile(
    rb"^\s*CONSTRAINT\s+`[^`]+`\s+FOREIGN KEY\s*\([^)]*\)\s*REFERENCES\s+`([^`]+)`\.`[^`]+`.*?,?\s*$",
    re.I)
# After the version-gated comments are unwrapped, mysqldump's view lands as `CREATE ... DEFINER ...`
# on one line and `VIEW `name` AS select ...` on the next, so both openings have to be recognised.
VIEW_LINE = re.compile(rb"^\s*(?:CREATE\b[^`]*?)?\bVIEW\s+`([^`]+)`", re.I)
CREATE_LEAD = re.compile(rb"^\s*CREATE\b", re.I)
QUALIFIED = re.compile(rb"`([A-Za-z0-9_$]+)`\s*\.\s*`")


def drop_cross_database_views(text, database, known=()):
    """Remove views that read from another database, and say which.

    `oracle_oe.account_managers` selects from `oracle_hr`.`countries`. Each engine here is given one
    database at a time -- MySQL a fresh empty server, Dolt a repository per database -- so that view
    has nothing to resolve against in either. What made it worth catching is that the two engines
    disagreed about it: MySQL refused the statement outright with `ERROR 1049: Unknown database`,
    while Dolt accepted the view and stored it. Left alone, the comparison would have had MySQL
    loading 6 views and Dolt 7 out of the same file, which is not the same file being loaded.

    `known` is the set of sibling database names, and it is what makes this safe. A view body is
    full of `alias`.`column` references that look identical to `database`.`table` -- matching the
    shape alone drops every view in the corpus, sakila's seven included, because `c`.`account_mgr_id`
    parses the same way as `oracle_hr`.`countries`. Only a qualifier that names a database that
    actually exists counts, and with no list supplied nothing is dropped.

    Same reasoning as the cross-database foreign keys above, and the same disclosure.
    """
    known = {k.encode() if isinstance(k, str) else k for k in known} - {database}
    if not known:
        return text, []
    out, dropped = [], []
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        m = VIEW_LINE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        # the statement may open on the previous line, which holds only `CREATE ...`
        block = []
        if not CREATE_LEAD.match(lines[i]):
            while out and not out[-1].strip():
                block.insert(0, out.pop())
            if out and CREATE_LEAD.match(out[-1]):
                block.insert(0, out.pop())
        while i < len(lines):
            block.append(lines[i])
            done = lines[i].rstrip().endswith(b";")
            i += 1
            if done:
                break
        body = b"".join(block)
        others = {d for d in QUALIFIED.findall(body) if d in known}
        if others:
            dropped.append(m.group(1).decode() + " -> "
                           + ", ".join(sorted(d.decode() for d in others)))
        else:
            out.extend(block)
    return b"".join(out), dropped


def transform(text, database, known_databases=()):
    """Return (sql, notes) as bytes. `database` is the schema the dump belongs to.

    `known_databases` is every database in the corpus; it is what lets a cross-database view be told
    apart from an ordinary table alias."""
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
    text, n = VIEW_ALGORITHM.subn(b"CREATE ", text)
    text, n2 = VIEW_SECURITY.subn(b" ", text)
    if n or n2:
        notes.append(f"removed ALGORITHM from {n} and SQL SECURITY from {n2} view definition(s)")
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

    # 4. drop views that read from another database, for the same reason and with the same notice
    text, views = drop_cross_database_views(b"".join(out), database, known_databases)
    if views:
        notes.append(f"dropped {len(views)} cross-database view(s): " + "; ".join(views))
    return text, notes


SECONDARY = re.compile(rb"^\s*(UNIQUE\s+KEY|FULLTEXT\s+KEY|SPATIAL\s+KEY|KEY|CONSTRAINT)\s", re.I)
AUTO_COL = re.compile(rb"^\s*`([^`]+)`.*\bAUTO_INCREMENT\b", re.I)
PRIMARY = re.compile(rb"^\s*PRIMARY\s+KEY\s*\(\s*`([^`]+)`", re.I)
FIRST_COL = re.compile(rb"\(\s*`([^`]+)`")
CREATE_TABLE = re.compile(rb"^CREATE TABLE\s+`([^`]+)`", re.I)


def defer_indexes(sql):
    """Take secondary indexes and foreign keys out of `CREATE TABLE` and add them back at the end.

    This is what anyone loading a large table actually does, and it is the standard advice for both
    engines: an index maintained row by row is rebuilt on every insert, while an index built once
    over finished data is built once. Removing it from the load isolates how much of the row-by-row
    cost is index maintenance rather than the writing itself.

    The primary key stays inline. It is not an optimisation to defer it — it is the row's identity,
    Dolt stores tables as a prolly tree keyed by it, and a table loaded without one is a different
    table. Everything else — `KEY`, `UNIQUE KEY`, `FULLTEXT KEY`, `SPATIAL KEY`, and the foreign key
    constraints — is deferred and re-added by `ALTER TABLE` after the last row, so the final state is
    the same schema either way. For Dolt that means the indexes land in the last commit, which is
    what makes the commit history comparable: the rows arrive one at a time, the indexes once.

    `UNIQUE_CHECKS` and `FOREIGN_KEY_CHECKS` are turned off for the load and restored afterwards,
    which is the other half of the same technique.
    """
    out, deferred, table, in_create = [], [], None, False
    kept = []
    auto_cols, pk_first = set(), None
    for line in sql.splitlines(keepends=True):
        m = CREATE_TABLE.match(line)
        if m:
            table, in_create = m.group(1), True
            auto_cols, pk_first = set(), None
            out.append(line)
            continue
        if in_create:
            a = AUTO_COL.match(line)
            if a:
                auto_cols.add(a.group(1))
            pk = PRIMARY.match(line)
            if pk:
                pk_first = pk.group(1)
            if line.lstrip().startswith(b")"):
                in_create = False
                # the last kept line must not end with a comma now that lines have been removed
                for i in range(len(out) - 1, -1, -1):
                    if out[i].strip():
                        if out[i].rstrip().endswith(b","):
                            out[i] = out[i].rstrip()[:-1] + b"\n"
                        break
                out.append(line)
                continue
            if SECONDARY.match(line):
                if _must_stay(line, auto_cols, pk_first):
                    kept.append(table)
                else:
                    deferred.append((table, line.strip().rstrip(b",")))
                    continue
        out.append(line)

    if not deferred:
        return b"".join(out), []
    note = [note_text(deferred, kept)]
    head = (b"SET UNIQUE_CHECKS=0;\nSET FOREIGN_KEY_CHECKS=0;\n")
    tail = [b"\n-- indexes and constraints deferred to the end of the load\n"]
    for t, clause in deferred:
        tail.append(b"ALTER TABLE `" + t + b"` ADD " + clause + b";\n")
    tail.append(b"SET UNIQUE_CHECKS=1;\nSET FOREIGN_KEY_CHECKS=1;\n")

    # After the rows, but *before* the routines. Dolt rejects `CREATE FUNCTION` and one rejected
    # statement aborts the rest of the file, so indexes appended to the very end were silently never
    # built: sakila finished with 16 of its 42. Placed after the rows they are always built, and for
    # a per-row-commit load they still land in the final commit, which is the point.
    #
    # "After the rows" means after the `UNLOCK TABLES` that closes the last table, not merely after
    # the last INSERT. mysqldump wraps each table's inserts in `LOCK TABLES <that table> WRITE`, and
    # MySQL refuses to touch any other table while a lock is held: dropping the block straight after
    # the last INSERT produced `ERROR 1100: Table 'album' was not locked with LOCK TABLES`. Dolt does
    # not enforce it and loaded the same file happily, which is exactly the kind of difference that
    # would have made the two engines run different SQL without anyone noticing.
    body = b"".join(out)
    cut = _end_of_rows(body)
    if cut is None:
        return head + body + b"".join(tail), note
    return head + body[:cut] + b"".join(tail) + body[cut:], note


def _end_of_rows(body):
    """Byte offset just past the last row-loading statement, outside any LOCK TABLES block."""
    last_insert = body.rfind(b"\nINSERT INTO ")
    if last_insert == -1:
        return None
    unlock = body.find(b"\nUNLOCK TABLES", last_insert)
    if unlock != -1:
        end = body.find(b"\n", unlock + 1)
        return end + 1 if end != -1 else len(body)
    # no LOCK TABLES in this dump: end of the last INSERT statement instead
    end = body.find(b"\n", last_insert + 1)
    while end != -1 and not body[last_insert + 1:end].rstrip().endswith(b";"):
        last_insert = end
        end = body.find(b"\n", last_insert + 1)
    return end + 1 if end != -1 else len(body)


def _must_stay(line, auto_cols, pk_first):
    """True for a key MySQL will not let the table exist without.

    An AUTO_INCREMENT column has to be the first column of some key. Where it is also the first
    column of the primary key that is already satisfied, but `adventureworks_lt.salesorderdetail`
    has `PRIMARY KEY (salesorderid, salesorderdetailid)` with the auto column second, and the only
    thing meeting the rule is the plain `KEY (salesorderdetailid)` beside it. Deferring that one
    made the table illegal: `ERROR 1075: Incorrect table definition; there can be only one auto
    column and it must be defined as a key`.

    Dolt accepted the same file, so this would have been another difference between the engines
    rather than an error in both."""
    if not auto_cols:
        return False
    first = FIRST_COL.search(line)
    return bool(first and first.group(1) in auto_cols and first.group(1) != pk_first)


def note_text(deferred, kept):
    text = (f"deferred {len(deferred)} secondary index/constraint definition(s) to ALTER TABLE "
            f"after the last row, with UNIQUE_CHECKS and FOREIGN_KEY_CHECKS off during the load")
    if kept:
        text += (f"; {len(kept)} key(s) kept inline because an AUTO_INCREMENT column leads them and "
                 "not the primary key, which MySQL requires: "
                 + ", ".join(sorted({t.decode() for t in kept})))
    return text



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
