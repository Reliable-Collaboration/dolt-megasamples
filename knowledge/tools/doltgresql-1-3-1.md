---
type: Tool
title: DoltgreSQL 1.3.1
description: The PostgreSQL-compatible Dolt server the PostgreSQL pair measures, pinned by image digest, with what was verified by loading sakila into it before the experiment ran.
resource: https://github.com/dolthub/doltgresql
tags:
- engine
- doltgresql
- pin
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T07:20:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T07:20:00Z"
sources:
- resource: /sources/doltgresql-readme.md
  title: DoltgreSQL README
  accessed: "2026-09-10"
- resource: /sources/doltgresql-release-v1-3-1.md
  title: DoltgreSQL release v1.3.1 and its Docker image
  accessed: "2026-09-10"
stale_after: "2027-03-01"
---

# Facts

Everything below was observed on 2026-09-10 against `dolthub/doltgresql@sha256:6c85cb1f35beabf47f094336a420255130b841b1645f36d79ef046276af36851` (tag `1.3.1`, published 2026-09-02), started with `DOLTGRES_PASSWORD` set, and driven with `psql` from `postgres:18.6-bookworm` over the wire and with the image's own `psql` 17.11. Licence Apache-2.0.

* **Identity.** `SELECT version()` answers `PostgreSQL 15.5`; the wire protocol and `psql` work as with PostgreSQL. Data lives under `/var/lib/doltgres` (the image's declared volume): one directory per database, each a Dolt repository (`<db>/.dolt/noms`, `.dolt/noms/oldgen`), plus `auth.db`, `config.yaml` and a `postgres` database of its own. `CREATE DATABASE`, `DROP DATABASE IF EXISTS` work and create or remove that directory.
* **Version control is SQL.** `SELECT dolt_commit('-Am', 'msg')` and `SELECT dolt_commit('-A', '--allow-empty', '-m', 'msg')` return the hash; `SELECT COUNT(*) FROM dolt_log` counts commits (a fresh database starts with one); `SELECT dolt_gc()` returns `0` and packs the store. The README states there is no CLI; none was needed.
* **The pg_dump path works.** sakila's `pg_dump` COPY form (3,115,627 bytes: 16 tables, 27 PL/pgSQL functions, 21 triggers, 7 views, 13 identity sequences, 25 indexes, 22 foreign keys) loaded through `psql -v ON_ERROR_STOP=0` with exactly one error: `index method gin is not yet supported` (the FULLTEXT port's GIN index). Row counts matched (film 1,000; payment 16,044; rental 16,044). `pg_dump 18`'s `\restrict` / `\unrestrict` lines are accepted by both psql versions. The `--inserts` form loaded the same way (one error, the same GIN index). `pg_trigger` held 21 triggers, `pg_proc` 15 `*_last_update*` functions, `pg_views` 7 views, `pg_indexes` 40 indexes, `information_schema.table_constraints` 22 foreign keys; identity columns take explicit values from the dump and go on generating (`INSERT INTO language(name) VALUES ('Klingon') RETURNING language_id` gave 7).
* **Views work.** `SELECT COUNT(*) FROM film_list` gave 1,000; `sales_by_store` 2.
* **Garbage collection is the difference between a working directory and a database.** sakila after the COPY load: 66,722,714 bytes (`du -sb` of `/var/lib/doltgres/sakila`, `.dolt/noms` nearly all of it); after `dolt_commit` and `dolt_gc()`: 2,001,856 bytes. A second copy loaded with `--inserts` plus `SELECT dolt_commit('-Am', ...)` after each of the first 3,000 rows: 428,139,392 bytes before, 20,773,812 bytes after `dolt_gc()`. No `.dolt/stats` directory appeared during these loads (the served-statistics directory `run_all.py` excludes for Dolt); the loads exclude it if it does.
* **Per-statement cost, one sample.** sakila's `--inserts` form (47,268 single-row INSERTs, no commits) took 109.6 s through `psql -f` over the Docker network (about 2.3 ms per statement); the same file with a `dolt_commit` after each of the first 3,000 rows took 126.1 s. One sample each, on the shared machine, not a measurement of the experiment -- the timed runs are.
* **The image carries `psql`** (`/usr/bin/psql`, PostgreSQL 17.11) and `pg_dump`, so loads can be run inside the server's container the way the Dolt loads are.

# Limits

Found by refusal, on the quick subset's schemas (`scripts/preflight_pairs.py`, 2026-09-10) and on sakila's rows; each is either a dialect rule (dropped before the load, on both engines of the pair) or a recorded refusal the report counts:

* **Accounts.** `CREATE ROLE demo LOGIN PASSWORD 'demo'`, `CREATE ROLE admin LOGIN PASSWORD 'admin' SUPERUSER`, `GRANT USAGE ON SCHEMA public TO demo` and `GRANT SELECT ON ALL TABLES IN SCHEMA public TO demo` are accepted. With only those, `demo` is refused an `INSERT` (`permission denied for table discounts`) but also `SELECT COUNT(*)` (`permission denied for routine count`): unlike PostgreSQL, EXECUTE on functions is not granted to everyone by default. `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pg_catalog TO demo` (and `... IN SCHEMA public`) makes the read-only account usable; the stack's init step applies all four ([stood-up instances](/decisions/stood-up-instances.md), verified by `scripts/stack_check.py` on 2026-09-10).
* **`USING gin` indexes** are refused ("index method gin is not yet supported"); the `@@` text-search operator too ("@@ is not yet supported"). Dialect rule G1 drops the index on both sides: [dialect rules](/decisions/pair-dialect-rules.md).
* **`xpath()`** is not implemented ("function: 'xpath' not found"): `adventureworks_lt.vproductmodelcatalogdescription` is refused. **`JSON_TABLE`** is not parsed ("at or near "columns": syntax error"): `oracle_co.product_reviews` is refused (Dolt refused the same view). Both are recorded per unit as schema objects not taken.
* **A table with a `STORED` generated column takes exactly one alteration.** The `CREATE TABLE` is accepted and the column is computed on INSERT (`linetotal` 10.000000 for 2.5 × 4; `SUM(linetotal)` over adventureworks_lt's 542 detail rows 207,482.4327, the source's value). The first `ALTER TABLE ... ADD CONSTRAINT ... PRIMARY KEY` or `CREATE INDEX` after it succeeds; after that the server has re-serialised the generated expression into text it cannot parse back (`Invalid default value for '(coalesce("a" * "b" as a * b,0.0))': at or near "as": syntax error` -- with or without a cast in the expression), and every later alteration, `INSERT` and `COPY` fails with it; adding a foreign key answers `receiveMessage recovered panic: ...` and the server carries on. Dialect rule G4 writes the primary key inside `CREATE TABLE` for such a table and drops its other indexes, unique constraints and foreign keys out loud; with that, both forms of adventureworks_lt load (2026-09-10). Open question: [generated column alteration](/questions/doltgresql-generated-column-alteration.md).
* **A `CHECK` constraint calling `regexp_like` refuses every row.** `CONSTRAINT c CHECK (regexp_like((z)::text, '^[0-9]+$'::text))` is accepted at `CREATE TABLE`, and then `INSERT` and `COPY` into the table both answer `at or near "as": syntax error` (the `CAST(... AS text)` spelling too). Checks of other forms work and are enforced -- `= ANY (ARRAY[...])`, `(q)::integer > 0`, `upper((r)::text) = 'G'`, and `regexp_like(z, '^[0-9]+$')` without casts (which the port does not write) -- on `INSERT` and on `COPY` alike (`Check constraint "c2_chk" violated`). Dialect rule G3 drops the `regexp_like` checks (pubs: 4, on `authors`, `employee`, `publishers`); with that pubs loads in both forms. The preflight loads no rows, so this class of refusal shows only in the loads.
* **A trigger whose `WHEN` clause compares whole rows refuses every UPDATE.** The port's ON UPDATE triggers carry `WHEN ((old.* IS DISTINCT FROM new.*))`; DoltgreSQL creates them without complaint and then answers `ERROR: record "old" has no field "*"` to any `UPDATE` of the table. The body was not the cause: the same body under a per-column `WHEN` (`old.a IS DISTINCT FROM new.a OR ...`) works, an unchanged row leaves `last_update` alone (`UPDATE 0`, MySQL-style affected rows) and a changed row moves it, and `film`'s two triggers keep `film_text` in step (bisected on 2026-09-10 through the function body, the creation order, `check_function_bodies`, the search path, the identity column, COPY versus INSERT and pg_dump's comment headers, none of which mattered). Dialect rule G6 expands the clause on both sides. Still refused at run time: a `BEFORE INSERT` trigger that fills a NOT NULL column (sakila's `rental_date`, `payment_date`): `INSERT INTO rental (inventory_id, customer_id, staff_id) VALUES (...)` answers `Field 'rental_date' doesn't have a default value` where PostgreSQL lets the trigger supply it -- the NOT NULL check runs before the trigger.
* **A `character(n)` value keeps its padding through a text cast.** `SELECT '[' || (class)::text || ']'` on a `character(2)` holding `L ` answers `[L ]` where PostgreSQL answers `[L]`, so `upper((class)::text) = ANY (ARRAY['L'::text, ...])` is false for every padded value and the CHECK refuses the row -- by INSERT and by COPY -- while an unpadded `l` passes. `rtrim((class)::text)` answers `[L]` on both engines; dialect rule G7 wraps such casts inside CHECK constraints (probed 2026-09-10; adventureworks' `production_product` then loads all 504 rows).
* **A named NOT NULL column constraint refuses the table.** `businessentityid integer CONSTRAINT humanresources_employeedepartmenthist_businessentityid_not_null NOT NULL` (pg_dump 18's form for a NOT NULL constraint with a non-generated name) answers "non-foreign key column constraint names are not yet supported" and the table is not created, so every view and constraint over it fails too (adventureworks: 3 tables, 23 refusals). Dialect rule G5 drops the name and keeps the constraint; with it all 69 tables of adventureworks are created and only its two `xpath` views are refused (probed 2026-09-10). **`convert_from()`** is not implemented either (wikipedia_simple: 4 views refused).
* **`dolt_gc()` can fail after many DROP/CREATE cycles on one server.** The 21st one-commit reload of the night (sakila, after 20 `DROP DATABASE` / `CREATE DATABASE` cycles on the same server) answered `Error in SaveHashes call: dangling references requested during GC. GC not successful.` and left the store at 7.7 MB instead of 2.0 MB; the same load into the same server a minute later collected normally (2026-09-10). A unit whose collection fails is kept with `settled: false` and its size marked.
* **`::regnamespace`** casts are not resolved ("unable to resolve type `regnamespace`"); `information_schema.triggers` answers 0 while `pg_trigger` holds the triggers. The parity queries use `pg_trigger`, `pg_views`, `pg_indexes` and `information_schema.tables`/`table_constraints`, which all answer.
* **`show session_replication_role`** is not needed and was not tested further; foreign keys stay after the rows in both index policies for a different reason ([load shapes](/decisions/pair-load-shapes-and-measurement.md)).

# Decision

Pinned by digest for the whole experiment; undo path recorded: [DoltgreSQL version pin](/decisions/doltgresql-version-pin.md).
