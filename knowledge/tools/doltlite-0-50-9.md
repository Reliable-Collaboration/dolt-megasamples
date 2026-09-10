---
type: Tool
title: DoltLite v0.50.9
description: The SQLite fork with a versioned storage engine that the SQLite pair measures, built here into an image from its Debian packages, with what was verified by replaying sakila into it before the experiment ran.
resource: https://github.com/dolthub/doltlite
tags:
- engine
- doltlite
- pin
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T10:10:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T10:10:00Z"
sources:
- resource: /sources/doltlite-readme.md
  title: DoltLite README
  accessed: "2026-09-10"
- resource: /sources/doltlite-release-v0-50-9.md
  title: DoltLite release v0.50.9 and its packages
  accessed: "2026-09-10"
- resource: /sources/doltlite-license.md
  title: DoltLite LICENSE.md
  accessed: "2026-09-10"
stale_after: "2027-03-01"
---

# Facts

Everything below was observed on 2026-09-10 with the image `docker/doltlite/Dockerfile` builds: `debian:13-slim` (digest `sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132`) plus `libdoltlite0_0.50.9_amd64.deb` and `doltlite_0.50.9_amd64.deb` (checksums in the release record), plus Debian's `sqlite3` package. Licence: Apache-2.0 for the DoltLite extensions over public-domain SQLite.

* **Identity.** `doltlite -version` answers `DoltLite v0.50.9 (SQLite 3.54.0, 64-bit)`; `SELECT dolt_version()` answers `v0.50.9`. The shell is SQLite's shell (`-help` lists SQLite's options; `.read`, `.dump`, `.schema` work). It links glibc 2.38: on `debian:12-slim` (glibc 2.36) it refuses to start (`GLIBC_2.38' not found`), on Debian 13 (glibc 2.41) it runs.
* **A stock SQLite file is not versioned.** Opening sql-megasamples' `sakila.sqlite` with `doltlite` answers plain queries (film 1,000) but `SELECT COUNT(*) FROM dolt_log` answers `dolt version-control features are not available on stock SQLite databases`. A DoltLite-format file is not a SQLite file: `sqlite3 sakila.doltlite` answers `file is not a database (26)`. Hence [the "same file" decision](/decisions/doltlite-same-file.md).
* **The dump replays.** `sqlite3 sakila.sqlite .dump` (5,228,218 bytes, 48,317 INSERTs) read by `doltlite sakila.dl ".read ..."` produced no error; afterwards film 1,000, payment 16,044, rental 16,044; `sqlite_schema` 21 tables, 27 indexes, 24 triggers, 6 views -- the same as the source. Triggers fire (an UPDATE that changes a name moves `last_update` on both engines to the same second); views answer (`film_list` 1,000; `sales_by_store` 2); FTS5 works (`MATCH 'drama'` answers 106 on both), including in a file created fresh (`CREATE VIRTUAL TABLE t USING fts5(a)`). `PRAGMA index_list` / `index_info` answer as SQLite's do.
* **Commits and VACUUM.** `SELECT dolt_commit('-Am', 'msg')` returns a hash; `SELECT dolt_commit('-A', '--allow-empty', '-m', 'msg')` too; `dolt_log` counts them (a fresh file starts with one). `VACUUM` is garbage collection and the difference is large: sakila replayed inside the dump's single transaction was 8,756,887 bytes, 8,541,254 after `VACUUM` (the stock file is 5,251,072); replayed with every statement autocommitted it was 319,067,787 bytes before and 8,541,014 after; replayed with a `dolt_commit` after every INSERT (47,269 commits, 29.1 s, about 1,600 commits per second in-process) it was 411,235,360 bytes before `VACUUM`.
* **Timing, one sample.** The single-transaction replay of sakila's dump: 150 ms in `doltlite`, 100 ms in `sqlite3`; autocommitted: 1,054 ms and 792 ms. One sample each on the shared machine; the timed runs are the measurement.
* **Foreign keys.** `PRAGMA foreign_keys` is honoured as in SQLite: off by default (an orphan row is accepted), enforced when on (`FOREIGN KEY constraint failed`). The dump's `PRAGMA foreign_keys=OFF` therefore applies to both engines.
* **Errors do not stop a script.** Both `doltlite` and `sqlite3` report a failing statement of a `.read` script and continue (a 4-statement script with a bad third statement leaves 2 rows in both).

# Limits

Found by refusal on sakila's dump and on the quick subset's schemas (2026-09-10); each is a dialect rule applied to both engines of the pair, so that the comparison stays between engines:

* **A table is committed only when every table its foreign keys name exists.** With `staff` (which references `store`) dumped before `store`, `dolt_commit` after a `staff` row answers `foreign key on table `staff` requires the referenced table `store`` until `store` is created -- the rows go in, the commits are lost. Rule L1 puts every `CREATE TABLE` ahead of the first `INSERT`: [dialect rules](/decisions/pair-dialect-rules.md).
* **The dump's virtual-table registration only works inside the dump's own transaction.** `.dump` registers an FTS5 table by `INSERT INTO sqlite_schema(...)` under `PRAGMA writable_schema=ON`; run as its own statement, both engines answer `table sqlite_master may not be modified`, and once the virtual table exists first, both refuse the dump's shadow-table rows (`object name reserved for internal use`). Rule L2 creates the virtual table with `CREATE VIRTUAL TABLE`, drops the shadow-table statements and rebuilds the index after the rows (or, under the inline policy, keeps it in step with the port's sync triggers).
* **Version gap to the baseline.** The fork's base is SQLite 3.54.0, ahead of the newest SQLite release (3.53.4 on 2026-09-10); the stock shell beside it is Debian 13's 3.46.1: [sqlite3 shell](/tools/sqlite3-shell-3-46-1.md).
* **`VACUUM` runs out of memory on the larger per-row-commit files.** dvdstore with the indexes inline (174,718 commits, 5,170,967,610 bytes before the settle step) and chicago_crimes under the deferred policy (260,043 commits, 3,626,990,331 bytes) both answered `Error in 2nd command line argument: out of memory` to `SELECT dolt_commit(...); VACUUM;` within seconds (2.5 s for chicago_crimes), inside a worker cgroup capped at 16 GiB whose anonymous memory during the load peaked at 179 MB and 221 MB; dvdstore under the deferred policy (1,823,235,885 bytes) vacuumed in 5.4 s and enron (410,260,509 bytes) in 1.5 s (2026-09-10). Such a unit is kept with `settled: false`, its size marked as the working footprint in the tables and left out of the totals: [open question](/questions/doltlite-vacuum-memory.md).
* **Durability per autocommitted statement** is not documented in the README and was not measured: [open question](/questions/doltlite-durability-per-statement.md).
* No container image is published; the one here is built by `make lite-image` and never pushed.
