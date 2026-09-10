---
type: Open Question
title: What does DoltLite make durable per autocommitted statement?
description: Answered on 2026-09-10 -- DoltLite calls fdatasync once per autocommitted statement, SQLite about four times; both per-row shapes are durable per statement and the comparison stands.
resource: /questions/doltlite-durability-per-statement.md
tags:
- doltlite
- question
- method
status: deprecated
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T17:10:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T17:10:00Z"
sources:
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9 (the observation)
  accessed: "2026-09-10"
- resource: /sources/doltlite-readme.md
  title: DoltLite README
  accessed: "2026-09-10"
---

# Question

SQLite in rollback-journal mode with `synchronous=FULL` syncs the journal and the database on every autocommitted statement. DoltLite has "no rollback journal, WAL, or shared-memory sidecars" and a chunk-store file that grew from 8.5 MB to 319 MB while sakila's dump was replayed statement by statement. Does each statement reach the disk (an `fsync` per statement, as in SQLite), or is durability per `dolt_commit` or per some batch? The `sqlite_rowwise` and `doltlite_rowinsert` times are comparable only if the answer is known.

# Cheapest experiment

`strace -f -c -e trace=fsync,fdatasync,sync_file_range` around `sqlite3 x.sqlite ".read rowinsert.sql"` and `doltlite x.doltlite ".read rowinsert.sql"` on a small database (jaffle_shop, 312 rows); count the sync calls against the statement count. The DoltLite docs directory (`doc/doltlite/`) may state it; read `storage-format.md` and `concurrency.md`.

# Resolves

The wording of the per-row comparison in the report: whether "one INSERT per row, each its own durable transaction" describes both engines, or the DoltLite number needs a qualifier.

# Answer

Yes, per statement. `strace -f -c -e trace=fsync,fdatasync,sync_file_range,msync` around the replay of jaffle_shop's per-row file (312 `INSERT`s, each its own transaction) in the DoltLite image (the pinned v0.50.9), 2026-09-10: `sqlite3` 3.46.1 made 1,268 `fdatasync` calls (about four per statement -- the rollback journal written, synced, the database synced, the journal deleted, at `synchronous=2`, `journal_mode=delete`), `doltlite` v0.50.9 made 319 (one per statement, plus a handful; it reports `journal_mode=wal` and ignores changes, `synchronous=2`). The dump replayed inside its single transaction made 4 and 3 calls respectively. So every autocommitted statement reaches the disk on both engines, and "one INSERT per row, each its own durable transaction" describes `sqlite_rowwise` and `doltlite_rowinsert` alike; DoltLite pays fewer syncs per statement, not none. The 319 MB the file grew to before `VACUUM` is retained chunk-store history, not unsynced data.
