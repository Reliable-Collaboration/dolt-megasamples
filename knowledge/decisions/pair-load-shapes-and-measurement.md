---
type: Decision
title: The load shapes, index policies and measurement rules of the two further pairs
description: The five shapes per pair, what the deferred and inline index policies mean for pg_dump and .dump output, and how disk, time and memory are read -- and where each departs from the MySQL/Dolt pair and why.
resource: /decisions/pair-load-shapes-and-measurement.md
tags:
- method
- decision
- doltgresql
- doltlite
status: stable
trust: verified
generated:
  by: claude-code/claude-opus-5
  at: "2026-09-10T18:20:00Z"
verified:
- by: claude-code/claude-opus-5
  at: "2026-09-10T18:20:00Z"
sources:
- resource: /tools/doltgresql-1-3-1.md
  title: DoltgreSQL 1.3.1
  accessed: "2026-09-10"
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9
  accessed: "2026-09-10"
- resource: /tools/postgresql-18-6-baseline.md
  title: PostgreSQL 18.6 as the baseline
  accessed: "2026-09-10"
- resource: /tools/sqlite3-shell-3-46-1.md
  title: The sqlite3 shell 3.46.1 as the baseline
  accessed: "2026-09-10"
---

# Question

How are the PostgreSQL/DoltgreSQL and SQLite/DoltLite loads shaped, ordered and measured so that they answer the same question the MySQL/Dolt pair answered -- for the same data, what does versioning cost in disk, time and memory -- with the same discipline, given that `pg_dump` and `sqlite3 .dump` write files of a different shape from `mysqldump`?

# Options considered

* **Load the engines' native files as they come** (pg_dump's COPY form into DoltgreSQL, the stock `.sqlite` into DoltLite). Lost: the stock file is not versioned by DoltLite ([same file](/decisions/doltlite-same-file.md)), and a single shape says nothing about the cost of history.
* **The five shapes of `run_all.py`, per pair, with the same two index policies, from one transformed file per shape that both engines load.** Chosen.
* **A single shared client container for both servers of the PostgreSQL pair.** Lost to simplicity: each server's container carries `psql` (18.6 in PostgreSQL's, 17.11 in DoltgreSQL's), and running the client inside the server's container is the shape the Dolt loads have; the client version does not touch the server's work.

# Evidence

The dump layouts, the refusals, and the sizes before and after the settle steps: the four tool records under `sources`. The preflight table: [dialect rules](/decisions/pair-dialect-rules.md).

# Outcome

**Both engines are pinned.** Every measurement belongs to DoltgreSQL 1.3.1 and DoltLite v0.50.9 exactly, beside PostgreSQL 18.6 and Debian 13's sqlite3 3.46.1, each pinned too; none moves to a newer release unless the maintainer explicitly asks ([the DoltgreSQL pin](/decisions/doltgresql-version-pin.md), [the DoltLite pin](/decisions/doltlite-version-pin.md)).

**Shapes** (keys in `build/progress.json`, definitions in `scripts/pairs.py`):

| PostgreSQL pair | SQLite pair | what the rows are |
|---|---|---|
| `postgres` | `sqlite` | COPY form into a fresh PostgreSQL / the dump replayed inside its one transaction into a fresh file |
| `postgres_rowwise` | `sqlite_rowwise` | one `INSERT` per row, each its own durable transaction (`--inserts` through `psql`; the dump without its `BEGIN`/`COMMIT`) |
| `doltgres_oneshot` | `doltlite_oneshot` | the one-shot file, one `dolt_commit` at the end |
| `doltgres_rowinsert` | `doltlite_rowinsert` | the per-row file, one `dolt_commit` at the end |
| `doltgres_rowcommit` | `doltlite_rowcommit` | the per-row file with `SELECT dolt_commit('-Am', 'row N')` after every `INSERT` |

The baseline of a per-row shape loads the same file its versioned counterpart loads without the commit calls, as `mysql_rowwise` loaded `dolt_rowinsert`'s file.

**Index policies.** Deferred is each dump's own order: pg_dump and `.dump` both write indexes and constraints after the rows. Inline moves every `CREATE INDEX` (and, for pg_dump, every `UNIQUE` constraint) ahead of the first row; for a virtual table under DoltLite, its sync triggers move with them and the rebuild is dropped. Three departures from the MySQL/Dolt pair, each because of what the dumps allow: (1) **primary keys are always ahead of the rows** on the PostgreSQL side (rule G2 moves pg_dump's `ADD CONSTRAINT ... PRIMARY KEY` up), which is where mysqldump has them and where `defer_indexes` left them, so no Dolt table is keyless during a load; on the SQLite side they are inside `CREATE TABLE` and cannot be anywhere else; (2) **foreign keys and triggers stay after the rows in both policies** on the PostgreSQL side: the data is written in table-creation order, not dependency order, so a foreign key in force during the load would refuse rows, and neither engine offers a checks-off switch both accept; on the SQLite side the foreign keys are declared inline and unenforced (`PRAGMA foreign_keys=OFF`, the dump's first line, honoured by both engines) -- the counterpart of mysqldump's `FOREIGN_KEY_CHECKS=0`; (3) **a FULLTEXT key's counterpart** (a GIN index on PostgreSQL, an FTS5 table on SQLite) is dropped on the PostgreSQL side (DoltgreSQL refuses it) and rebuilt after the rows or maintained by triggers on the SQLite side.

**Measurement rules**, the same as the first pair's with the engines' own settle steps:

* **Wall clock** around one command in a container that is already up: `psql -q -o /dev/null -v ON_ERROR_STOP=0 -f` inside the server's container; `sqlite3 file ".read ..."` and `doltlite file ".read ..."` inside one worker container. `settle_seconds` is timed separately: `CHECKPOINT` for PostgreSQL; `dolt_commit` then `dolt_gc()` for DoltgreSQL; nothing for SQLite (the file is complete when the shell exits); `dolt_commit` then `VACUUM` for DoltLite.
* **Disk** after the settle step: PostgreSQL's data directory without `pg_wal`, minus the empty-server baseline (`pg_database_size` recorded beside it); DoltgreSQL's `<datadir>/<db>` minus `.dolt/stats`; the SQLite file with any `-journal`/`-wal` sidecar; the DoltLite file. For the two Dolt engines the size before the settle step is recorded too (`bytes_before_settle`), because it is the working footprint a load needs and it is up to 37× the settled size (DoltLite, sakila autocommitted).
* **Memory** from the host's cgroup files, four times a second, from before the timed command until after its settle step: the peak of anonymous plus shared memory (with swap off neither can be reclaimed, and PostgreSQL's shared buffers are the shared part), each window's own peak, and the container's own `memory.peak`, page cache included. Every unit runs in a container of its own -- a server started for each PostgreSQL and DoltgreSQL load, over its own root for DoltgreSQL, and a shell container for each SQLite and DoltLite load -- so each figure belongs to that unit alone. The first sampler read every two seconds, anonymous memory only, and stopped before the settle step; the first DoltgreSQL runner shared one server per shape ([review dispositions](/decisions/review-2026-09-10-pairs-dispositions.md)).
* **The method is recorded on every unit** (`method`, currently 2): the runner measures again any unit recorded with an older method and keeps its first record under `superseded`, and the collector reports only units of the current method. Method 2 also reads and writes every dump byte for byte: a text-mode read had turned the carriage returns inside row values into line feeds in the `--inserts` form, which the row and index checks cannot see.
* **Parity before size**: every table's row count and the index set (`pg_indexes.indexdef` read back into its parts -- uniqueness, table, method, key list -- so a printing difference such as PostgreSQL quoting a keyword column is not a missing index; `PRAGMA index_list`/`index_info`) against the reference recorded at export, minus what the dialect dropped. A missing index the engine refused out loud is recorded as a schema object not taken; a missing index with no refusal to explain it fails the unit. FTS5 shadow tables are left out of the reference, since the index is rebuilt.
* **One worker at a time**, memory-capped (`DOLTSAMPLES_MEM_WORKER`, 16 GiB on the 19.5 GiB host); every other stack stopped; cheapest-first within a phase; resumable; a disk floor; `--max-rows` to run the small databases across every shape before the long loads start.

**Stated limitations of the pairs:** the client versions (psql 18.6 versus 17.11) and the SQLite versions (3.46.1 versus the fork's 3.54.0 base) differ between the two sides; the SQLite baseline gets no `VACUUM`; the PostgreSQL pair's data is loaded without foreign keys in force in both policies.

# Status

accepted (2026-09-10).
