---
type: Open Question
title: What does DoltLite make durable per autocommitted statement?
description: sqlite_rowwise fsyncs on every statement by SQLite's default; DoltLite's README says nothing about it, and its file grew to 319 MB for 48,317 autocommitted statements before VACUUM, so the two per-row baselines may not be paying the same durability.
resource: /questions/doltlite-durability-per-statement.md
tags:
- doltlite
- question
- method
status: draft
trust: open
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
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
