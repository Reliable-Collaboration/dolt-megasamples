---
type: Decision
title: What the dialects change before a load, and what is recorded as refused instead
description: The four named rules of scripts/doltgres_dialect.py and scripts/doltlite_dialect.py, each found by refusal; the objects each engine still refuses, which the report counts; and the preflight table of the quick subset.
resource: /decisions/pair-dialect-rules.md
tags:
- method
- decision
- doltgresql
- doltlite
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: /tools/doltgresql-1-3-1.md
  title: DoltgreSQL 1.3.1
  accessed: "2026-09-10"
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9
  accessed: "2026-09-10"
---

# Question

What must change in `pg_dump`'s and `sqlite3 .dump`'s output before DoltgreSQL and DoltLite load it, what is the smallest change, and what is better left refused and counted than worked around?

# Options considered

* **Hand-edit the dumps per database.** Lost: not reproducible and not the discipline `dolt_dialect.py` set (every rule named and reported, none touching a row).
* **Named rules, found by refusal, applied to both engines of a pair; everything else refused and recorded with its reason.** Chosen.
* **Work around every refusal** (rewrite views without `xpath`, split generated columns into plain columns). Lost: each would carry different objects or different values than the source, and the report would be comparing a different database.

# Evidence

The refusals were found on sakila's rows (2026-09-10) and on the quick subset's schemas by `scripts/preflight_pairs.py` (2026-09-10, `build/preflight/pairs.json`). PostgreSQL and `sqlite3` refused nothing; after the rules, DoltLite refused nothing; DoltgreSQL refused what is listed below.

| database | objects (pg_dump blocks) | DoltgreSQL refused | rules | objects (.schema) | DoltLite refused | rules |
|---|---|---|---|---|---|---|
| adventureworks_lt | 86 | 14: the `xpath` view; 8 indexes and 5 foreign keys on the two tables with generated columns | G2 | 46 | 0 | |
| chinook | 44 | 0 | G2 | 22 | 0 | |
| contoso | 30 | 0 | G2 | 15 | 0 | |
| dvdstore | 36 | 0 | G1 (2), G2 | 35 | 0 | L2 (2) |
| employees | 32 | 0 | G2 | 11 | 0 | |
| jaffle_shop | 10 | 0 | G2 | 5 | 0 | |
| northwind | 97 | 0 | G2 | 59 | 0 | |
| nyc_taxi | 14 | 0 | G2 | 9 | 0 | |
| oracle_co | 43 | 1: the `JSON_TABLE` view | G2 | 21 | 0 | |
| oracle_hr | 45 | 0 | G2 | 28 | 0 | |
| oracle_oe | 50 | 0 | G1 (1), G2 | 39 | 0 | L2 (1) |
| pubs | 47 | 0 | G2 | 23 | 0 | |
| sakila | 147 | 0 | G1 (1), G2 | 75 | 0 | L2 (1) |
| smallsets | 12 | 0 | G2 | 4 | 0 | |
| stackexchange_beer | 35 | 0 | G1 (1), G2 | 31 | 0 | L2 (1) |

(L1 fires on every dump with rows and is not shown; the preflight loads schemas.)

# Outcome

**DoltgreSQL** (`scripts/doltgres_dialect.py`, working on pg_dump's object blocks, never on the rows inside `TABLE DATA`):

* **G1 gin-index**: `CREATE INDEX ... USING gin` dropped on both sides; DoltgreSQL 1.3.1 answers "index method gin is not yet supported" and has no `@@` to serve it. The index-parity check expects it absent.
* **G2 primary-keys-first**: pg_dump's `ALTER TABLE ... ADD CONSTRAINT ... PRIMARY KEY` blocks moved ahead of the first `TABLE DATA` block in every shape, where the MySQL/Dolt pair had them.
* Shapes, not rules: `inline_indexes` (INDEX blocks and UNIQUE constraints ahead of the rows), `per_row_commits` (a `SELECT dolt_commit('-Am', 'row N')` after every complete `INSERT`, quotes balanced across lines).
* **Recorded, not transformed**: the `xpath` view, the `JSON_TABLE` view, and every second alteration of a table with a `STORED` generated column (its secondary indexes and foreign keys). psql runs with `ON_ERROR_STOP=0`; every `ERROR` line is read back into the block (type and name) it fell in and kept on the unit; a refused index is a schema object not taken, a missing index nobody refused is a failed load. The trigger bodies that fail at run time are created without complaint and do not affect the loads.

**DoltLite** (`scripts/doltlite_dialect.py`, working on statements split the way the sqlite3 shell splits them):

* **L1 schema-first**: every `CREATE TABLE` and `CREATE VIRTUAL TABLE` ahead of the first `INSERT`, in the dump's order; DoltLite will not commit a table whose foreign key names a table that does not exist yet.
* **L2 virtual-tables-created**: the dump's `sqlite_schema` registration of a virtual table becomes the `CREATE VIRTUAL TABLE` it carries, placed with the tables; the shadow tables' statements are dropped; the index is rebuilt after the last row (`INSERT INTO v(v) VALUES('rebuild')`), or, under the inline policy, kept in step by the port's sync triggers moved ahead of the rows. Both engines refuse the registration as its own statement and refuse shadow rows once the virtual table exists.
* Shapes: `strip_transaction` (the dump's `BEGIN`/`COMMIT` removed), `inline_indexes`, `per_row_commits` (not after the rebuild).

# Status

accepted (2026-09-10); to be revisited whenever a database outside the quick subset makes an engine refuse something new -- the preflight runs before its rows do.
