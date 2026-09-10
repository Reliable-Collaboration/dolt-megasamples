---
type: Decision
title: What the dialects change before a load, and what is recorded as refused instead
description: The nine named rules of scripts/doltgres_dialect.py and scripts/doltlite_dialect.py, each found by refusal; the objects each engine still refuses, which the report counts; and the preflight table of the quick subset.
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
  at: "2026-09-10T06:50:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T06:50:00Z"
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
| adventureworks_lt | 86 | 14: the `xpath` view; 8 indexes and 5 foreign keys on the two tables with generated columns (now dropped by G4) | G2, G4 | 46 | 0 | |
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
| pubs | 47 | 0 (its 4 `regexp_like` checks refuse rows, found by the loads) | G2, G3 | 23 | 0 | |
| sakila | 147 | 0 | G1 (1), G2, G6 (15) | 75 | 0 | L2 (1) |
| smallsets | 12 | 0 | G2 | 4 | 0 | |
| stackexchange_beer | 35 | 0 | G1 (1), G2 | 31 | 0 | L2 (1) |

| adventureworks | 426 | 25 before G5: 3 tables with named NOT NULL constraints and the 20 views and constraints that depend on them; 2 `xpath` views after it (and, found by the rows, every row of `production_product` before G7) | G3 (1), G4 (5 tables), G5 (6), G7 (8) | 212 | 0 | |
| chicago_crimes | 11 | 0 | G2 | 8 | 0 | |
| enron | 18 | 0 | G1 (1), G2 | 20 | 0 | L2 (1) |
| lahman | 55 | 0 | G2 | 37 | 0 | |
| oracle_sh | 46 | 0 | G1 (1), G2 | 36 | 0 | L2 (1) |
| wikipedia_simple | 42 | 4 views over `convert_from` | G1 (1), G2 | 36 | 0 | L2 (1) |

(The six rows below the quick subset were preflighted the same night, once the quick subset's loads were sound. L1 fires on every dump with rows and is not shown; the preflight loads schemas, so a refusal that only shows at row time -- G3's, and G4's second-alteration failure -- was found by the first loads and the rules added before the units were rerun.)

# Outcome

**DoltgreSQL** (`scripts/doltgres_dialect.py`, working on pg_dump's object blocks, never on the rows inside `TABLE DATA`; since method 2 the files are also read and written byte for byte, after a text-mode read was found to turn the carriage returns inside row values into line feeds -- the rules never touched a row, the read did):

* **G1 gin-index**: `CREATE INDEX ... USING gin` dropped on both sides; DoltgreSQL 1.3.1 answers "index method gin is not yet supported" and has no `@@` to serve it. The index-parity check expects it absent.
* **G2 primary-keys-first**: pg_dump's `ALTER TABLE ... ADD CONSTRAINT ... PRIMARY KEY` blocks moved ahead of the first `TABLE DATA` block in every shape, where the MySQL/Dolt pair had them.
* **G3 regexp-check**: a `CHECK` constraint calling `regexp_like` is removed from `CREATE TABLE` on both sides; DoltgreSQL 1.3.1 accepts it and then refuses every `INSERT` and `COPY` into the table ("at or near "as": syntax error"). pubs: `authors_chk_1`, `authors_chk_2`, `employee_chk_1`, `publishers_chk_1`. Found by the first loads, not by the preflight, which loads no rows.
* **G4 generated-column-table**: for a table with a `STORED` generated column, the primary key is written inside `CREATE TABLE` and the table's other indexes, unique constraints and foreign keys are dropped and named; DoltgreSQL 1.3.1 accepts one alteration of such a table and then refuses every row. adventureworks_lt: `salesorderdetail` and `salesorderheader`, 8 indexes and 5 foreign keys. The rows and the generated values are carried (the sum of `linetotal` matches the source).
* **G5 named-not-null**: `col type CONSTRAINT name NOT NULL` loses its name on both sides (the constraint stays); DoltgreSQL 1.3.1 refuses the whole table otherwise ("non-foreign key column constraint names are not yet supported"). pg_dump 18 writes the name for a NOT NULL constraint whose name is not the generated one. adventureworks: six columns in three tables. Found by the preflight of the six databases outside the quick subset (2026-09-10).
* **G6 row-comparison-in-when**: a trigger's `WHEN ((old.* IS DISTINCT FROM new.*))` -- the port's "only when the row changed" guard on every ON UPDATE trigger -- becomes the same test column by column (`old.a IS DISTINCT FROM new.a OR ...`), from the table's own CREATE TABLE block. DoltgreSQL 1.3.1 creates the trigger with the whole-row form and then refuses every UPDATE of the table at run time (`record "old" has no field "*"`); PostgreSQL evaluates both forms identically (proved on sakila, 2026-09-10: an unchanged row leaves `last_update` alone, a changed one moves it, on both engines). sakila: 15 triggers. Found by bisecting the run-time failure the tool record had recorded as an open question, after the quick subset's per-row units had been measured; those units loaded the whole-row form, which is created after the rows in every shape and never fires during a load, so no recorded size or time depends on the rule. The one-commit loads were run again with it, since they are what the stack serves.
* **G7 padded-char-in-check**: in a CHECK constraint, a `character(n)` column's cast to text is wrapped in `rtrim()`. PostgreSQL strips the blank padding when it casts bpchar to text, so nothing changes there (proved: the same file loads on both, `production_product` 504 rows on each); DoltgreSQL 1.3.1 keeps it, and `upper((class)::text) = ANY (ARRAY['L','M','H'])` refuses every padded value the dump carries (`L ` for a `character(2)`), by INSERT and by COPY, on which the first load of adventureworks failed with `Check constraint "ck_product_class" violated` for all 504 rows. adventureworks: 8 casts in `production_product`'s four checks; no other database has a checked `character(n)` column. Found by the first adventureworks load (2026-09-10), since the preflight loads no rows.
* Shapes, not rules: `inline_indexes` (INDEX blocks and UNIQUE constraints ahead of the rows), `per_row_commits` (a `SELECT dolt_commit('-Am', 'row N')` after every complete `INSERT`, quotes balanced across lines).
* **Recorded, not transformed**: the `xpath` views (adventureworks_lt: 1, adventureworks: 2), the `JSON_TABLE` view (oracle_co), the `convert_from` views (wikipedia_simple: 4). psql runs with `ON_ERROR_STOP=0`; every `ERROR` line is read back into the block (type and name) it fell in and kept on the unit; a refused index is a schema object not taken, a missing index nobody refused is a failed load. The trigger bodies that fail at run time are created without complaint and do not affect the loads.

**DoltLite** (`scripts/doltlite_dialect.py`, working on statements split the way the sqlite3 shell splits them):

* **L1 schema-first**: every `CREATE TABLE` and `CREATE VIRTUAL TABLE` ahead of the first `INSERT`, in the dump's order; DoltLite will not commit a table whose foreign key names a table that does not exist yet.
* **L2 virtual-tables-created**: the dump's `sqlite_schema` registration of a virtual table becomes the `CREATE VIRTUAL TABLE` it carries, placed with the tables; the shadow tables' statements are dropped; the index is rebuilt after the last row (`INSERT INTO v(v) VALUES('rebuild')`), or, under the inline policy, kept in step by the port's sync triggers moved ahead of the rows. Both engines refuse the registration as its own statement and refuse shadow rows once the virtual table exists.
* Shapes: `strip_transaction` (the dump's `BEGIN`/`COMMIT` removed), `inline_indexes`, `per_row_commits` (not after the rebuild).

# Status

accepted (2026-09-10); to be revisited whenever a database outside the quick subset makes an engine refuse something new -- the preflight runs before its rows do.
