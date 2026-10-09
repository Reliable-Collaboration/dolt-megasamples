#!/usr/bin/env python3
"""What pg_dump's output needs changed before DoltgreSQL -- and PostgreSQL -- load it.

Every rule is named, counted and reported per database, and none touches a row. Both engines of
the pair load the same transformed file (the discipline `dolt_dialect.py` set for MySQL and
Dolt), so the comparison is between engines, not between inputs. The rules were found by refusal
on the quick subset (2026-09-10, DoltgreSQL 1.3.1, pg_dump 18.6), not assumed. DoltgreSQL 1.3.1 is
pinned (scripts/pairs.py): the rules describe that version and no other.

pg_dump writes one block per object under a header of the form
    --
    -- Name: film_actor film_actor_pkey; Type: CONSTRAINT; Schema: public; Owner: -
    --
which is what this module works on: blocks are classified by their `Type`, dropped or moved
whole, and the rows inside `TABLE DATA` blocks are never edited.

Rules (each returns a note when it fired):

  G1 gin-index. `CREATE INDEX ... USING gin` is dropped: DoltgreSQL 1.3.1 answers "index method
     gin is not yet supported". These are the full-text indexes the PostgreSQL port carries for
     MySQL's FULLTEXT keys; the table and its rows are unaffected, and the index parity check
     expects them to be absent on both sides. The `@@` text-search operator is also unsupported,
     so the index would have had nothing to serve.
  G2 primary-keys-first. pg_dump adds every PRIMARY KEY after the rows (`ALTER TABLE ... ADD
     CONSTRAINT ... PRIMARY KEY`). They are moved ahead of the first `TABLE DATA` block in every
     shape, which is where the MySQL/Dolt pair had them (mysqldump keeps the primary key inside
     CREATE TABLE and `defer_indexes` left it there). Without it every Dolt table is keyless while
     the rows arrive and rewritten when the key is added, which is not the load the other pair got.

  G3 regexp-check. A CHECK constraint that calls `regexp_like` is dropped from CREATE TABLE.
     DoltgreSQL 1.3.1 stores the expression in a form it cannot parse back, and every INSERT and
     COPY into the table then fails with "at or near "as": syntax error" (pubs: authors, employee,
     publishers). Checks of other forms -- `= ANY (ARRAY[...])`, comparisons with casts, `upper()`
     -- work and stay. The check is lost on both engines and the report says so.
  G4 generated-column-table. A table with a STORED generated column takes exactly one alteration
     on DoltgreSQL 1.3.1: after it, the server re-serialises the generated expression into text
     it cannot parse, and every later alteration, INSERT and COPY fails ("Invalid default value
     ... syntax error at 'as'"). So for such a table the PRIMARY KEY goes inside CREATE TABLE
     instead of the ALTER pg_dump writes, and the table's other indexes, unique constraints and
     foreign keys are dropped and recorded: the rows and the key are carried, the rest is refused
     out loud rather than lost by accident (adventureworks_lt: salesorderdetail, salesorderheader).

  G5 named-not-null. `col type CONSTRAINT name NOT NULL` -- the name pg_dump 18 writes for a NOT
     NULL constraint whose name is not the generated one -- loses its name: DoltgreSQL 1.3.1
     refuses the table ("non-foreign key column constraint names are not yet supported"). The
     constraint stays. adventureworks: six columns in three tables.

  G6 row-comparison-in-when. A trigger's `WHEN ((old.* IS DISTINCT FROM new.*))` -- the port's
     "only when the row changed" guard on every ON UPDATE trigger -- is expanded to the same test
     column by column (`old.a IS DISTINCT FROM new.a OR old.b IS DISTINCT FROM new.b ...`), which
     PostgreSQL evaluates identically. DoltgreSQL 1.3.1 creates the trigger with the whole-row
     form and then refuses every UPDATE of the table at run time (`record "old" has no field
     "*"`); with the expansion an unchanged row leaves `last_update` alone and a changed one
     moves it, on both engines. The columns come from the table's own CREATE TABLE block.

  G7 padded-char-in-check. In a CHECK constraint, a `character(n)` column cast to text --
     `(col)::text` -- is wrapped in `rtrim(...)`. PostgreSQL strips the blank padding when it
     casts bpchar to text, so the wrap changes nothing there; DoltgreSQL 1.3.1 keeps it, and a
     check such as `upper((class)::text) = ANY (ARRAY['L','M','H'])` then refuses every padded
     value the dump carries (`L ` for a `character(2)`), row by row and by COPY alike
     (adventureworks: `production_product`, four checks).

Shapes (applied per phase by pairs.py):

  inline_indexes     every INDEX block and every UNIQUE constraint moved ahead of the first
                     TABLE DATA block; pg_dump's own order -- indexes and constraints after the
                     rows -- is the deferred policy already. Foreign keys and triggers stay after
                     the rows in both policies: the data is written in table-creation order, not
                     dependency order, so a foreign key in force during the load would refuse
                     rows, and neither engine offers a checks-off switch both accept.
  per_row_commits    `SELECT dolt_commit('-Am', 'row N');` after every INSERT of the --inserts form
"""
import re

HEADER = re.compile(r"^--\n-- (?:Data for )?Name: (?P<name>.*?); Type: (?P<type>[A-Z ]+?); Schema: (?P<schema>.*?); "
                    r"Owner: (?P<owner>.*?)\n--\n", re.M)
TRAILER = "--\n-- PostgreSQL database dump complete\n--\n"


class Block:
    __slots__ = ("type", "name", "schema", "text")

    def __init__(self, type_, name, schema, text):
        self.type, self.name, self.schema, self.text = type_, name, schema, text

    def __repr__(self):
        return f"<{self.type}: {self.name}>"


def split(text):
    """(preamble, blocks, trailer) -- joining them back gives the input."""
    heads = list(HEADER.finditer(text))
    if not heads:
        return text, [], ""
    preamble = text[:heads[0].start()]
    blocks = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        blocks.append(Block(h.group("type"), h.group("name"), h.group("schema"), text[h.start():end]))
    trailer = ""
    last = blocks[-1].text
    at = last.find(TRAILER)
    if at >= 0:
        trailer, blocks[-1].text = last[at:], last[:at]
    return preamble, blocks, trailer


def join(preamble, blocks, trailer):
    return preamble + "".join(b.text for b in blocks) + trailer


def first_data(blocks):
    return next((i for i, b in enumerate(blocks) if b.type == "TABLE DATA"), len(blocks))


def hoist(blocks, pick):
    """Move the blocks `pick` selects ahead of the first TABLE DATA block, keeping their order."""
    cut = first_data(blocks)
    head, rest = blocks[:cut], blocks[cut:]
    chosen = [b for b in rest if pick(b)]
    return head + chosen + [b for b in rest if not pick(b)], len(chosen)


GIN = re.compile(r"\bUSING\s+gin\b", re.I)
PK = re.compile(r"\bPRIMARY\s+KEY\b", re.I)
UNIQUE = re.compile(r"\bADD\s+CONSTRAINT\s+\S+\s+UNIQUE\b", re.I)


def transform(text, database):
    """The dump as both engines should load it; returns (text, notes, dropped_indexes)."""
    preamble, blocks, trailer = split(text)
    notes, dropped = [], []
    kept = []
    for b in blocks:
        if b.type == "INDEX" and GIN.search(b.text):
            dropped.append(b.name)
            continue
        kept.append(b)
    if dropped:
        notes.append(f"G1 dropped {len(dropped)} GIN index(es) DoltgreSQL 1.3.1 refuses "
                     f"(\"index method gin is not yet supported\"): {', '.join(dropped)}")
    # G3
    removed = []
    for b in kept:
        if b.type == "TABLE":
            b.text, names = drop_check_lines(b.text, REGEXP_CHECK)
            removed += names
    if removed:
        notes.append(f"G3 dropped {len(removed)} CHECK constraint(s) calling regexp_like, which DoltgreSQL "
                     f"1.3.1 cannot evaluate on INSERT or COPY: {', '.join(removed)}")
    # G5
    unnamed = 0
    for b in kept:
        if b.type == "TABLE" and NAMED_NOT_NULL.search(b.text):
            b.text, n = NAMED_NOT_NULL.subn("NOT NULL", b.text)
            unnamed += n
    if unnamed:
        notes.append(f"G5 dropped the names of {unnamed} NOT NULL column constraint(s), which DoltgreSQL 1.3.1 "
                     f"refuses (\"non-foreign key column constraint names are not yet supported\")")
    # G7
    padded = 0
    for b in kept:
        if b.type == "TABLE":
            chars = [c for c, t in table_column_types(b.text).items() if BPCHAR.match(t)]
            if chars and "CHECK" in b.text:
                b.text, n = wrap_char_casts(b.text, chars)
                padded += n
    if padded:
        notes.append(f"G7 wrapped {padded} cast(s) of character(n) columns inside CHECK constraints in rtrim(); "
                     f"DoltgreSQL 1.3.1 keeps the blank padding a text cast strips in PostgreSQL")
    # G6
    columns = {qualified_table(b): table_columns(b.text) for b in kept if b.type == "TABLE"}
    expanded, unexpanded = 0, []
    for b in kept:
        if b.type == "TRIGGER" and ROW_WHEN.search(b.text):
            m = TRIGGER_ON.search(b.text)
            cols = columns.get(m.group("table")) if m else None
            if cols:
                b.text = ROW_WHEN.sub(lambda mm: row_when(mm, cols), b.text)
                expanded += 1
            else:
                unexpanded.append(b.name)
    if unexpanded:
        notes.append(f"G6 could NOT expand the whole-row WHEN of {len(unexpanded)} trigger(s), because the table's "
                     f"columns were not found; DoltgreSQL will refuse every UPDATE of their tables: {', '.join(unexpanded)}")
    if expanded:
        notes.append(f"G6 expanded the whole-row WHEN comparison of {expanded} trigger(s) column by column; "
                     f"DoltgreSQL 1.3.1 refuses every UPDATE of the table otherwise (record \"old\" has no field \"*\")")
    # G4
    generated = {qualified_table(b) for b in kept if b.type == "TABLE" and GENERATED.search(b.text)}
    if generated:
        kept, moved, lost = inline_primary_keys(kept, generated)
        dropped += [n for n, kind in lost if kind in ("INDEX", "UNIQUE")]
        notes.append(f"G4 {len(generated)} table(s) with a STORED generated column ({', '.join(sorted(generated))}): "
                     f"{moved} PRIMARY KEY(s) written inside CREATE TABLE; {len(lost)} other index/constraint "
                     f"block(s) dropped because DoltgreSQL 1.3.1 accepts one alteration of such a table and then "
                     f"refuses every INSERT: {', '.join(n for n, _ in lost)}")
    blocks, n = hoist(kept, lambda b: b.type == "CONSTRAINT" and PK.search(b.text))
    if n:
        notes.append(f"G2 moved {n} PRIMARY KEY constraint(s) ahead of the rows")
    return join(preamble, blocks, trailer), notes, dropped


NAMED_NOT_NULL = re.compile(r"\bCONSTRAINT\s+\S+\s+NOT\s+NULL\b")
REGEXP_CHECK = re.compile(r"^\s*CONSTRAINT\s+(?P<name>\S+)\s+CHECK\s+\(.*\bregexp_like\s*\(", re.I)
GENERATED = re.compile(r"\bGENERATED\s+ALWAYS\s+AS\b", re.I)
CREATE_TABLE = re.compile(r"^CREATE TABLE (?P<name>\S+) \($", re.M)
ADD_PK = re.compile(r"^ALTER TABLE ONLY (?P<table>\S+)\n\s+ADD CONSTRAINT (?P<name>\S+) PRIMARY KEY \((?P<cols>[^)]*)\);", re.M)
ALTER_TABLE = re.compile(r"^ALTER TABLE ONLY (?P<table>\S+)\n\s+ADD CONSTRAINT (?P<name>\S+) (?P<kind>UNIQUE|FOREIGN KEY|CHECK)\b", re.M)
INDEX_ON = re.compile(r"^CREATE (?:UNIQUE )?INDEX (?P<name>\S+) ON (?P<table>\S+) ", re.M)


ROW_WHEN = re.compile(r"\b(?P<a>old|new)\.\*\s+IS\s+(?P<not>NOT\s+)?DISTINCT\s+FROM\s+(?P<b>old|new)\.\*", re.I)
TRIGGER_ON = re.compile(r"\bON\s+(?P<table>\S+)\s+(?:FOR\s+EACH|NOT\s+DEFERRABLE|DEFERRABLE|REFERENCING)", re.I)
COLUMN_LINE = re.compile(r'^\s{4}(?P<name>"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)\s')
NOT_A_COLUMN = ("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "EXCLUDE", "LIKE")


def table_columns(text):
    """The column names of a CREATE TABLE block, in order (the one walker is table_column_types)."""
    return list(table_column_types(text))


BPCHAR = re.compile(r"^(character|char|bpchar)\b(?!\s+varying)", re.I)
CHECK_LINE = re.compile(r"^\s*CONSTRAINT\s+\S+\s+CHECK\s+\(", re.I)


def table_column_types(text):
    """{column: type text} of a CREATE TABLE block."""
    inside, out = False, {}
    for line in text.split("\n"):
        if CREATE_TABLE.match(line):
            inside = True
            continue
        if inside and line.startswith(");"):
            break
        m = COLUMN_LINE.match(line) if inside else None
        if m and m.group("name").upper() not in NOT_A_COLUMN:
            out[m.group("name")] = line.strip()[len(m.group("name")):].strip()
    return out


def wrap_char_casts(text, chars):
    """rtrim() around `(col)::text` for the named columns, on CHECK constraint lines only."""
    n, out = 0, []
    names = "|".join(re.escape(c) for c in chars)
    cast = re.compile(r"\((?P<col>" + names + r")\)::text\b")
    for line in text.split("\n"):
        if CHECK_LINE.match(line):
            line, k = cast.subn(lambda m: f"rtrim(({m.group('col')})::text)", line)
            n += k
        out.append(line)
    return "\n".join(out), n


def row_when(m, cols):
    a, b, negated = m.group("a").lower(), m.group("b").lower(), bool(m.group("not"))
    op, glue = ("IS NOT DISTINCT FROM", " AND ") if negated else ("IS DISTINCT FROM", " OR ")
    return "(" + glue.join(f"{a}.{c} {op} {b}.{c}" for c in cols) + ")"


def qualified_table(block):
    m = CREATE_TABLE.search(block.text)
    return m.group("name") if m else None


def drop_check_lines(text, pattern):
    """Remove the constraint lines `pattern` matches from a CREATE TABLE block, keeping the
    column list well-formed (the last line of the list carries no comma)."""
    lines = text.split("\n")
    names, out = [], []
    for line in lines:
        m = pattern.match(line)
        if m:
            names.append(m.group("name"))
            continue
        out.append(line)
    if names:
        # the line before ");" must not end with a comma
        ends = [i for i, line in enumerate(out) if line.strip() == ");"]
        if not ends:
            raise ValueError(f"G3: a CREATE TABLE without ');' on its own line lost CHECK constraint(s) "
                             f"{', '.join(names)}, and its column list cannot be repaired")
        for i in ends:
            if i > 0 and out[i - 1].rstrip().endswith(","):
                out[i - 1] = out[i - 1].rstrip()[:-1]
    return "\n".join(out), names


def inline_primary_keys(blocks, tables):
    """For the named tables: the PRIMARY KEY constraint written inside CREATE TABLE, every other
    index, unique constraint and foreign key of the table dropped. Returns (blocks, moved, lost)."""
    by_name = {qualified_table(b): b for b in blocks if b.type == "TABLE"}
    keep, moved, lost = [], 0, []
    for b in blocks:
        if b.type == "CONSTRAINT":
            m = ADD_PK.search(b.text)
            if m and m.group("table") in tables:
                t = by_name[m.group("table")]
                written = t.text.replace("\n);", f",\n    CONSTRAINT {m.group('name')} PRIMARY KEY ({m.group('cols')})\n);", 1)
                if written == t.text:
                    # a CREATE TABLE that does not end in ");" on its own line (WITH, PARTITION BY,
                    # INHERITS ...) would otherwise be counted as keyed and loaded keyless
                    raise ValueError(f"G4: the CREATE TABLE of {m.group('table')} does not end with ');' on its own "
                                     f"line, so its PRIMARY KEY {m.group('name')} cannot be written inside it")
                t.text = written
                moved += 1
                continue
            m = ALTER_TABLE.search(b.text)
            if m and m.group("table") in tables:
                lost.append((m.group("name"), m.group("kind")))
                continue
        if b.type == "FK CONSTRAINT":
            m = ALTER_TABLE.search(b.text)
            if m and m.group("table") in tables:
                lost.append((m.group("name"), "FOREIGN KEY"))
                continue
        if b.type == "INDEX":
            m = INDEX_ON.search(b.text)
            if m and m.group("table") in tables:
                lost.append((m.group("name"), "INDEX"))
                continue
        keep.append(b)
    return keep, moved, lost


def inline_indexes(text):
    preamble, blocks, trailer = split(text)
    blocks, n = hoist(blocks, lambda b: b.type == "INDEX"
                      or (b.type == "CONSTRAINT" and UNIQUE.search(b.text)))
    return join(preamble, blocks, trailer), n


def per_row_commits(text):
    """A dolt_commit after every complete INSERT statement of a --inserts dump.

    An INSERT can span lines when a value holds a newline (pg_dump writes the newline as itself
    under standard_conforming_strings), so a statement ends only where the line ends in `;` with
    every quote closed."""
    preamble, blocks, trailer = split(text)
    n = 0
    for b in blocks:
        if b.type != "TABLE DATA":
            continue
        out, open_quotes, inside = [], 0, False
        # pieces ending at a line feed only: str.splitlines also breaks at a carriage return and at
        # other Unicode separators, which occur inside row values
        for line in re.split(r"(?<=\n)", b.text):
            out.append(line)
            if not inside and not line.startswith("INSERT INTO "):
                continue
            inside = True
            open_quotes = (open_quotes + line.count("'")) % 2
            if open_quotes == 0 and line.rstrip("\r\n").endswith(";"):
                n += 1
                out.append(f"SELECT dolt_commit('-Am', 'row {n}');\n")
                inside = False
        b.text = "".join(out)
    return join(preamble, blocks, trailer), n


def kinds(text):
    """How many blocks of each pg_dump type a dump holds."""
    _, blocks, _ = split(text)
    counts = {}
    for b in blocks:
        counts[b.type] = counts.get(b.type, 0) + 1
    return counts


def block_at_line(text, line_no):
    """Which block (type, name) a 1-based line number of the dump falls in -- for reading
    psql's `psql:file:LINE: ERROR:` back into the object that was refused."""
    pos, current = 0, None
    _, blocks, _ = split(text)
    preamble_len = text.find(blocks[0].text) if blocks else len(text)
    line = text.count("\n", 0, preamble_len) + 1
    for b in blocks:
        n = b.text.count("\n")
        if line <= line_no < line + n:
            return b.type, b.name
        line += n
    return None, None


def block_index(text):
    """(first lines, [(type, name)]) of every block, so that many psql line numbers map to blocks
    with one pass over the file instead of one per error."""
    preamble, blocks, _ = split(text)
    line = preamble.count("\n") + 1
    starts, names = [], []
    for b in blocks:
        starts.append(line)
        names.append((b.type, b.name))
        line += b.text.count("\n")
    return starts, names


def block_at(index, line_no):
    """The (type, name) of the block a 1-based line number of the file falls in."""
    import bisect
    starts, names = index
    i = bisect.bisect_right(starts, line_no) - 1
    return names[i] if i >= 0 else (None, None)
