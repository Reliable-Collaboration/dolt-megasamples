#!/usr/bin/env python3
"""What pg_dump's output needs changed before DoltgreSQL -- and PostgreSQL -- load it.

Every rule is named, counted and reported per database, and none touches a row. Both engines of
the pair load the same transformed file (the discipline `dolt_dialect.py` set for MySQL and
Dolt), so the comparison is between engines, not between inputs. The rules were found by refusal
on the quick subset (2026-09-10, DoltgreSQL 1.3.1, pg_dump 18.6), not assumed.

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
    blocks, n = hoist(kept, lambda b: b.type == "CONSTRAINT" and PK.search(b.text))
    if n:
        notes.append(f"G2 moved {n} PRIMARY KEY constraint(s) ahead of the rows")
    return join(preamble, blocks, trailer), notes, dropped


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
        for line in b.text.splitlines(keepends=True):
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
