# Plan: DoltgreSQL and DoltLite beside Dolt, and instances that stay up

This file is written by hand (it is the one document here that is not generated) and describes
what is being built next; `README.md`, `REPORT.md` and `JOURNAL.md` describe what exists and what
was measured. Written 2026-09-10 against Dolt 2.3.x, DoltgreSQL 1.3.1 and DoltLite v0.50.9.

## What is being asked

Two things, in the order they can be done:

1. **The same experiment for two more pairs.** Today the five tests compare MySQL with Dolt. The
   corpus now exists on PostgreSQL and SQLite too (`sql-megasamples` release 2, ports verified
   against the MySQL hub by content digest, view digest, routine and trigger output), and DoltHub
   ships a versioned engine for each: DoltgreSQL speaks the PostgreSQL wire protocol; DoltLite is
   a SQLite fork with a versioned storage engine. The question stays the same -- for the same data,
   what does versioning cost in disk, time and memory -- asked three times.
2. **Instances that stay up.** `make up` already leaves Dolt and its consoles running on ports one
   range above `sql-megasamples`. The same for DoltgreSQL and DoltLite: the sample databases,
   loaded once, served with the same two accounts, browsable where a console can, with a landing
   page that says how to connect a tool of one's own -- the same shape `sql-megasamples` has.

## What is known, and what must be measured before anything is promised

| | DoltgreSQL | DoltLite |
|---|---|---|
| version, date | 1.3.1, 2026-09-02; "1.0, ready for production" per its README | v0.50.9, 2026-09-10; a beta with near-daily releases; storage format 12 is frozen for the beta |
| licence | Apache-2.0 | Apache-2.0 for the DoltLite extensions; the SQLite it forks is public domain |
| how it ships | `dolthub/doltgresql` on Docker Hub (tags `1.3.1`, `latest`), release tarballs per platform | no image: `.deb` packages (`libdoltlite0`, `doltlite`) and per-platform library zips on GitHub releases; `bin/doltlite` is the CLI shell |
| how data goes in | "import your existing Postgres database with `pg_dump` and `psql`" (its README); version control is SQL only: `select dolt_commit('-m', ...)`, no CLI | the `doltlite` shell runs SQL; a stock SQLite file opens on SQLite's own B-tree engine **without** version control; a versioned database is one DoltLite creates, filled by SQL (`INSERT INTO ... SELECT` from an `ATTACH`ed stock file, or a dump replayed); `dolt_commit('-Am', ...)`; `VACUUM` is garbage collection; one durable writer per file |
| stated gaps | "some Postgres syntax, types, functions and features are not yet implemented"; limited extensions; sqllogictest 99.3 % on 1.0.0; sysbench 2.7× PostgreSQL's latency on 1.0.0 (their numbers, not ours) | storage-coupled behaviour differs from SQLite: no journal or WAL, non-integer primary keys clustered and `NOT NULL`, rowids from a counter shared by branches; what of FTS5, triggers and views survives is not stated and will be measured |
| source in `sql-megasamples` | `sql-megasamples-postgres:dev` (PostgreSQL 18.6): `pg_dump` per database, default `COPY` form and `--inserts` for one statement per row | `build/sqlite/<database>/<database>.sqlite` (also `/data` in `sql-megasamples-sqlite:dev`); `sqlite3 .dump` gives one `INSERT` per row |

Nothing above the line "how data goes in" has been tried here yet. The first phase exists to find
out what each engine refuses, the way the current preflight found what Dolt and MySQL disagreed on.

## Phase 1 -- sources and preflight (days)

* **Export.** `scripts/export_postgres.py`: `pg_dump --no-owner --no-privileges` of every database
  from the running `sql-megasamples` PostgreSQL, twice (`COPY` form; `--inserts` form), into
  `build/dumps/postgres/`. `scripts/export_sqlite.py`: copy each `.sqlite` file and write its
  `.dump` (one `INSERT` per row) into `build/dumps/sqlite/`.
* **Dialects.** `scripts/doltgres_dialect.py` and `scripts/doltlite_dialect.py`, each rule named
  and reported per database, none touching a row -- the discipline `dolt_dialect.py` set. Expected
  candidates, to be confirmed by refusal rather than assumed: `pg_dump`'s `SET` preamble, stored
  generated columns, GIN indexes over `to_tsvector`, PL/pgSQL routines and triggers, `regexp_like`
  checks, identity sequences (Doltgres); FTS5 tables and their sync triggers, views, triggers,
  `GLOB` checks (DoltLite). What an engine refuses is dropped with its reason, listed per
  database, and the row comparison stays exact.
* **Preflight**, extended: every schema (no rows) into PostgreSQL and DoltgreSQL, and into SQLite
  and DoltLite; what only one side refuses is the finding, as it was for MySQL and Dolt.
* **Fairness facts to establish**: DoltgreSQL's garbage collection (`dolt_gc()`) and what a served
  data directory adds (the `.dolt/stats` question again); DoltLite's file size after `VACUUM`;
  where each engine's indexes can be read back for parity (`pg_indexes` on Doltgres; DoltLite's
  `sqlite_schema` projection); that both accept the two accounts.
* **Gate**: the preflight table for both pairs, with every refusal named, before a row is loaded.

## Phase 2 -- the loads and the numbers (a run of days; per-row commits dominate)

The same five shapes per pair, under the same two index policies, measured the same way
(disk after settling, wall clock inside an already-running container, cgroup memory, counts and
index parity before any size is recorded), resumable, cheapest-first, with the disk floor:

| # | PostgreSQL / DoltgreSQL | SQLite / DoltLite |
|---|---|---|
| 1 | `postgres`: `pg_dump` `COPY` into a fresh `postgres:18.6` | `sqlite`: the dump replayed by `sqlite3` into a fresh file |
| 2 | `postgres_rowwise`: `--inserts` | `sqlite_rowwise`: `.dump`, one `INSERT` per row |
| 3 | `doltgres_oneshot`: `COPY` form through `psql`, one commit | `doltlite_oneshot`: the dump through `doltlite` into a DoltLite-format file, one commit |
| 4 | `doltgres_rowinsert`: one `INSERT` per row, one commit | `doltlite_rowinsert` |
| 5 | `doltgres_rowcommit`: `select dolt_commit('-Am', ...)` after every row | `doltlite_rowcommit`: `dolt_commit('-Am', ...)` after every row |

* Index policies: deferred (indexes and foreign keys out of `CREATE TABLE`, rebuilt after the last
  row; for SQLite and DoltLite, where a foreign key cannot be added later, the deferred policy is
  `PRAGMA foreign_keys=OFF` for the load and `CREATE INDEX` after -- a difference the report states)
  and inline.
* Memory: DoltgreSQL as a server under a ceiling, like Dolt; DoltLite is in-process, so the ceiling
  and the trace apply to the container running the shell.
* Budget: the Dolt per-row-commit loads needed the better part of a day and disk that could not be
  projected; DoltgreSQL shares Dolt's storage engine and should behave like it, DoltLite is a
  different implementation and is unknown. Both run cheapest-first and stop at the floor, so results
  accrue from the top. If the budget is the problem, the per-row-commit shape can be run on the
  quick subset first and the report says which databases it covers.
* **Gate**: `make audit` invariants extended to the new pairs; every unit has counts and index
  parity on both sides before its size counts.

## Phase 3 -- instances that stay up (days, in parallel with the loads)

* **Stack.** `compose.yaml` gains `doltgres` (`dolthub/doltgresql` pinned by digest, data directory
  from the one-shot load, port `5433`, `DOLTGRES_PASSWORD`, an init step that creates `demo` and
  `admin` with `psql` from the `sql-megasamples-postgres` image) and `doltlite` (a small image built
  here from `debian:12-slim` plus the `.deb`, holding `data/doltlite/<database>.doltlite` and the
  `doltlite` shell, sleeping so `docker exec doltsamples-doltlite doltlite /data/sakila.doltlite` is
  the client). Every service keeps a memory limit; ports stay one range above `sql-megasamples`.
* **Consoles.** Adminer, DbGate and CloudBeaver get a PostgreSQL connection to DoltgreSQL for each
  account, and Dolt Workbench a Postgres connection (it shows branches and commits for Doltgres as
  it does for Dolt). Whether each console's catalog queries survive Doltgres's gaps is measured
  by a `test-console` step, not assumed; a console that cannot open it is marked so, as
  phpMyAdmin is marked MySQL-only in `sql-megasamples`. DoltLite files are not SQLite pages, so no
  web console opens them: the landing page says so and gives the shell command and the
  `docker cp` path.
* **Landing page.** `scripts/console_page.py` gains the "connect with your own tool" section from
  `sql-megasamples` (address, accounts, client, URL and JDBC per engine; the file paths for
  DoltLite), the same ordering of consoles by coverage, and a column per engine in the database
  table with rows, size and what was not carried.
* **Gate**: `make up` then a `make test-console` that proves each engine answers with both
  accounts, each console opens what it claims, and the page names every database.

## Phase 4 -- the documents

`docs/templates/README.md`, `JOURNAL.md` and `REPORT.md` gain the two pairs, `scripts/facts.py`
every new number, `scripts/charts.py` the figures, and `make check` fails on a stale one, as now.
The human note stays on every document. A record of what DoltgreSQL and DoltLite are and where
each fact came from belongs beside the experiment; this repository has no knowledge bundle, and
adding one in the `sql-megasamples` form (tool records for the two engines, decision records for
the dialects and the stack) is the recommended way to keep the evidence reviewable.

## Decisions taken before starting (2026-09-10)

1. **Scope of the per-row-commit shape**: the quick subset first (`make -C ../sql-megasamples
   list-quick`, 15 databases), the remaining databases once the quick subset is sound.
2. **The pins**: DoltgreSQL 1.3.1 by image digest, marked PINNED in `scripts/pairs.py` and
   `compose.yaml` with the undo path beside it ([decision](knowledge/decisions/doltgresql-version-pin.md));
   DoltLite v0.50.9 from its checksummed `.deb` packages, built into an image here
   (`make lite-image`), never pushed. Both stay pinned unless the maintainer explicitly asks for a pin to be
   removed, and every document marks them as pinned (decided 2026-09-10).
3. **A knowledge bundle here**, in the sql-megasamples form: `knowledge/` (tool, source, decision
   and question records; `make okf-check`).
4. **What "the same file" means for DoltLite**: the dump replayed into a DoltLite-format database
   ([decision](knowledge/decisions/doltlite-same-file.md)).

## Decisions taken during the work (2026-09-10)

5. **Employees' row-by-row loads come last.** Its four row-by-row shapes, about 29 hours of machine
   time under both index policies, run once every other result is in (`--skip-row-by-row employees`
   until then; [running the pairs](knowledge/runbooks/pairs-run.md)).
6. **DoltgreSQL's accounts follow Dolt's**: `admin`/`admin` reads and writes, `demo`/`demo` only reads.
   DoltgreSQL 1.3.1 enforces table privileges but not database privileges, so `demo` can still create
   and drop databases until a way to stop it is found and recorded in
   [stood-up instances](knowledge/decisions/stood-up-instances.md).
What the first phase found, and how the loads are shaped and measured, is recorded in
[knowledge/decisions/pair-dialect-rules.md](knowledge/decisions/pair-dialect-rules.md) and
[knowledge/decisions/pair-load-shapes-and-measurement.md](knowledge/decisions/pair-load-shapes-and-measurement.md);
the plan above is kept as written, and the decisions say where the work departed from it.
