#!/usr/bin/env python3
"""What sqlite3's `.dump` needs changed before DoltLite -- and stock SQLite -- replay it.

Every rule is named, counted and reported per database, and none touches a row. Both engines of
the pair load the same transformed file, so a rule that changes the load for one changes it for
the other and the comparison stays between engines, not between inputs. The rules were found by
refusal on sakila (2026-09-10, DoltLite v0.50.9, sqlite3 3.46.1), not assumed.

Rules (each returns a note when it fired):

  L1 schema-first. `.dump` writes each table's CREATE TABLE immediately before its rows. Every
     CREATE TABLE and CREATE VIRTUAL TABLE is moved ahead of the first INSERT instead, in the
     dump's order. DoltLite will not *commit* a table whose foreign key names a table that does
     not exist yet ("foreign key on table `staff` requires the referenced table `store`"), so a
     per-row-commit load in creation order loses every commit between a child's first row and its
     parent's CREATE. Stock SQLite does not care and gets the same order.
  L2 virtual-tables-created. `.dump` writes a virtual table's shadow tables as ordinary tables
     with their rows -- the serialised index -- and registers the virtual table last by writing
     its CREATE text into sqlite_schema under `PRAGMA writable_schema=ON`. Both engines accept
     that only inside the single transaction `.dump` opens; as its own statement both refuse it
     ("table sqlite_master may not be modified"), and once the virtual table exists first both
     refuse the shadow rows ("object name reserved for internal use"). So the registration
     becomes the CREATE VIRTUAL TABLE statement itself, placed with the other tables; the shadow
     tables' CREATE and INSERT statements are dropped; and under the deferred policy the index is
     rebuilt from its content table after the last row (`INSERT INTO v(v) VALUES('rebuild')`),
     which is what the MySQL/Dolt pair did with a deferred FULLTEXT key. Under the inline policy
     the triggers that keep the index in step (the ones whose body names the virtual table) are
     moved ahead of the rows instead, so the index is maintained row by row on both engines.

Shapes (applied per phase by pairs.py; they define the loads, not the dialect):

  strip_transaction  the dump's BEGIN TRANSACTION / COMMIT removed, so every statement is its own
                     durable transaction: one INSERT per row, autocommitted (mysql_rowwise's shape)
  inline_indexes     every CREATE INDEX moved ahead of the first INSERT; `.dump` writes them after
                     the last row, which is the deferred policy already
  per_row_commits    `SELECT dolt_commit('-Am', 'row N');` after every INSERT
"""
import re, sqlite3

IDENT = r'(?:"(?P<dq>[^"]+)"|\'(?P<sq>[^\']+)\'|`(?P<bq>[^`]+)`|\[(?P<br>[^\]]+)\]|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*))'
CREATE_TABLE = re.compile(r'^\s*CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?' + IDENT, re.I)
VIRTUAL = re.compile(r'^\s*CREATE\s+VIRTUAL\s+TABLE\b', re.I)
INSERT = re.compile(r'^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+' + IDENT, re.I)
INDEX = re.compile(r'^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b', re.I)
REGISTRATION = re.compile(
    r"^\s*INSERT\s+INTO\s+sqlite_(?:schema|master)\s*\(.*?\)\s*VALUES\s*\('table','(?P<name>(?:[^']|'')*)',"
    r"'(?:[^']|'')*',\s*0,\s*'(?P<sql>(?:[^']|'')*)'\)\s*;?\s*$", re.I | re.S)
WRITABLE = re.compile(r'^\s*PRAGMA\s+writable_schema\s*=\s*(ON|OFF|1|0|TRUE|FALSE)\s*;?\s*$', re.I)
BEGIN = re.compile(r'^\s*BEGIN(\s+TRANSACTION)?\s*;?\s*$', re.I)
COMMIT = re.compile(r'^\s*(COMMIT|END)(\s+TRANSACTION)?\s*;?\s*$', re.I)


def ident(m):
    return m.group("dq") or m.group("sq") or m.group("bq") or m.group("br") or m.group("bare")


def statements(text):
    """The dump split into complete statements, the way the sqlite3 shell splits its input."""
    out, buf = [], []
    for line in text.splitlines(keepends=True):
        buf.append(line)
        if sqlite3.complete_statement("".join(buf)):
            out.append("".join(buf).strip("\n"))
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def table_of(stmt):
    m = CREATE_TABLE.match(stmt)
    return ident(m) if m else None


def insert_table(stmt):
    m = INSERT.match(stmt)
    return ident(m) if m else None


def is_table(stmt):
    return CREATE_TABLE.match(stmt) is not None


def first_insert(stmts):
    return next((i for i, s in enumerate(stmts) if INSERT.match(s)), len(stmts))


def transform(text, database):
    """The dump text as both engines should replay it; returns (text, notes)."""
    stmts = statements(text)
    notes = []

    # L2 -- the writable_schema registration becomes the CREATE VIRTUAL TABLE it carries; the
    # shadow tables go; the index is rebuilt after the rows (inline_indexes undoes the rebuild)
    created, out, dropped_pragmas = [], [], 0
    for s in stmts:
        if WRITABLE.match(s):
            dropped_pragmas += 1
            continue
        m = REGISTRATION.match(s)
        if m:
            name = m.group("name").replace("''", "'")
            created.append((name, m.group("sql").replace("''", "'").rstrip(";") + ";"))
            continue
        out.append(s)
    stmts = out
    # `.schema` output (the preflight's input) carries CREATE VIRTUAL TABLE directly, with the
    # shadow tables' CREATE TABLE IF NOT EXISTS beside it; those get the same treatment
    direct = [table_of(s) for s in stmts if VIRTUAL.match(s)]
    virtual = [n for n, _ in created] + [n for n in direct if n]
    if virtual:
        shadows = {t for t in (table_of(s) for s in stmts if is_table(s) and not VIRTUAL.match(s)) if t
                   and any(t.startswith(name + "_") for name in virtual)}
        kept, dropped_shadow = [], 0
        for s in stmts:
            if (table_of(s) or insert_table(s)) in shadows:
                dropped_shadow += 1
                continue
            kept.append(s)
        stmts = kept
        last = max((i for i, s in enumerate(stmts) if INSERT.match(s)), default=-1)
        if last >= 0:
            stmts[last + 1:last + 1] = [f"INSERT INTO {q(name)}({q(name)}) VALUES('rebuild');" for name in virtual]
        first = next((i for i, s in enumerate(stmts) if is_table(s)), 0)
        stmts[first:first] = [create for _, create in created]
        notes.append(f"L2 created {len(virtual)} virtual table(s) with CREATE VIRTUAL TABLE"
                     + (" instead of the dump's sqlite_schema registration" if created else "")
                     + f", dropped {dropped_shadow} shadow-table statement(s)"
                     + (" and rebuilt the index after the rows" if last >= 0 else "")
                     + f" ({', '.join(virtual)})")

    # L1 -- every table ahead of the first row
    cut = first_insert(stmts)
    head, rest = stmts[:cut], stmts[cut:]
    tables = [s for s in rest if is_table(s)]
    if tables:
        stmts = head + tables + [s for s in rest if not is_table(s)]
        notes.append(f"L1 moved {len(tables)} CREATE TABLE statement(s) ahead of the first INSERT")
    return "\n".join(stmts) + "\n", notes


def strip_transaction(text):
    stmts = [s for s in statements(text) if not BEGIN.match(s) and not COMMIT.match(s)]
    return "\n".join(stmts) + "\n"


REBUILD = re.compile(r"^\s*INSERT\s+INTO\s+" + IDENT + r"\s*\(\s*" + IDENT.replace("?P<", "?P<x") +
                     r"\s*\)\s*VALUES\s*\(\s*'rebuild'\s*\)\s*;?\s*$", re.I)
TRIGGER = re.compile(r"^\s*CREATE\s+TRIGGER\b", re.I)


def inline_indexes(text):
    """Every CREATE INDEX ahead of the first row; for a virtual table, its sync triggers too, and
    no rebuild afterwards -- the index is then maintained row by row, as an inline key is."""
    stmts = statements(text)
    virtual = [table_of(s) for s in stmts if VIRTUAL.match(s)]
    cut = first_insert(stmts)
    head, rest = stmts[:cut], stmts[cut:]

    def early(s):
        if INDEX.match(s):
            return True
        return TRIGGER.match(s) is not None and any(q(v) in s or v in s for v in virtual)

    moved = [s for s in rest if early(s)]
    rest = [s for s in rest if not early(s) and not REBUILD.match(s)]
    return "\n".join(head + moved + rest) + "\n", len(moved)


def q(name):
    return '"' + name.replace('"', '""') + '"'


def per_row_commits(text):
    out, n = [], 0
    for s in statements(text):
        out.append(s)
        if INSERT.match(s) and not REBUILD.match(s):
            n += 1
            out.append(f"SELECT dolt_commit('-Am', 'row {n}');")
    return "\n".join(out) + "\n", n


def kinds(text):
    """How many statements of each kind a dump holds -- what the preflight table reports."""
    counts = {}
    for s in statements(text):
        head = " ".join(s.split()[:3]).upper()
        if VIRTUAL.match(s):
            k = "virtual table"
        elif is_table(s):
            k = "table"
        elif INSERT.match(s):
            k = "insert"
        elif INDEX.match(s):
            k = "index"
        elif head.startswith("CREATE TRIGGER"):
            k = "trigger"
        elif head.startswith("CREATE VIEW"):
            k = "view"
        else:
            k = s.split()[0].lower() if s.split() else "?"
        counts[k] = counts.get(k, 0) + 1
    return counts
