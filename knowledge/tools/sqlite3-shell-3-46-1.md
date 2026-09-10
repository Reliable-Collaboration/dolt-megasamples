---
type: Tool
title: The sqlite3 shell 3.46.1 as the baseline of the SQLite pair
description: Debian 13's sqlite3 shell, which writes the dumps and is the stock engine beside DoltLite; what its .dump output looks like and how it behaves on errors.
resource: https://sqlite.org/cli.html
tags:
- engine
- sqlite
- baseline
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: /sources/sqlite-download-page.md
  title: SQLite download page (current release)
  accessed: "2026-09-10"
---

# Facts

* **Identity.** `sqlite3 -version` in the image `docker/doltlite/Dockerfile` builds (Debian 13's `sqlite3` package): `3.46.1 2024-08-13 09:16:08 c9c2ab54ba1f5f46360f1b4f35d849cd3f080e6fc2b6c60e91b16c63f69aalt1 (64-bit)`. It writes every dump the pair loads and runs every baseline load, in the same container as `doltlite`.
* **What `.dump` writes** (sakila, 2026-09-10): `PRAGMA foreign_keys=OFF;` then `BEGIN TRANSACTION;`, then for each table its `CREATE TABLE` immediately followed by one `INSERT INTO t VALUES(...)` per row, then every `CREATE INDEX`, `CREATE TRIGGER` and `CREATE VIEW`, then `COMMIT;`. An FTS5 table's shadow tables (`_data`, `_idx`, `_docsize`, `_config`) are written as ordinary tables with their rows, and the virtual table itself is registered last by `PRAGMA writable_schema=ON; INSERT INTO sqlite_schema(type,name,tbl_name,rootpage,sql) VALUES('table', ..., 0, 'CREATE VIRTUAL TABLE ...'); PRAGMA writable_schema=OFF;`. `.schema` prints `CREATE VIRTUAL TABLE` directly, beside the shadow tables' `CREATE TABLE IF NOT EXISTS`.
* **Errors do not stop `.read`.** A failing statement is reported (`Parse error near line N: ...` or `Runtime error near line N: ...`) and the script continues; a 4-statement script with a bad third statement leaves 2 rows.
* **The single-transaction replay** of sakila's dump took 100 ms; autocommitted, 792 ms (one sample each).

# Limits

* **Version gap.** DoltLite's base is SQLite 3.54.0, ahead of the newest release (3.53.4 on 2026-09-10); the baseline is 3.46.1. The SQL the pair runs is the dump's own DDL and single-row INSERTs, which have not changed between those versions, but the gap is a stated limitation of the pair: [load shapes](/decisions/pair-load-shapes-and-measurement.md).
* **No settle step.** A file written inside one transaction, or statement by statement in rollback-journal mode, is complete when the shell exits; the baseline records `settle_seconds` 0 and no `VACUUM`, so its size is the file as the shell left it.
