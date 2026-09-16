---
type: Source
title: DoltLite README (dolthub/doltlite, main)
description: The project's own description of DoltLite, how it installs, how stock SQLite files are treated, where it departs from SQLite, and its beta status.
resource: https://github.com/dolthub/doltlite
tags:
- doltlite
- upstream
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: https://api.github.com/repos/dolthub/doltlite/readme
  title: README.md of dolthub/doltlite, raw, default branch
  accessed: "2026-09-10"
  version: "main on 2026-09-10; 11,997 bytes"
- resource: https://api.github.com/repos/dolthub/doltlite
  title: Repository metadata (licence and description)
  accessed: "2026-09-10"
---

# What was read

The README of `dolthub/doltlite` on its default branch, fetched raw through the GitHub API on 2026-09-10 (11,997 bytes), and the repository record, which reports the description "DoltLite - Version Controlled SQLite" and the licence as `NOASSERTION` (GitHub could not classify it; [the LICENSE.md record](/sources/doltlite-license.md) says why).

# Relevant excerpt

> A SQLite fork that replaces the B-tree storage engine with a content-addressed prolly tree, giving Git-like version control on a SQL database. The parser, planner, and VDBE stay upstream-derived above SQLite's `btree.h` seam; below it, a single-file chunk store backs prolly trees instead of SQLite pages.

> [DoltLite is Beta](https://www.dolthub.com/blog/2026-08-31-doltlite-beta/).

> ## Install
> Prebuilt binaries: github.com/dolthub/doltlite/releases. Each install method places the same set of files (paths shown for `/usr/local`):
> - `bin/doltlite`, `bin/doltlite-remotesrv` — the CLI shell and remote sync server
> - `include/doltlite.h` — embedding header (`sqlite3_*` plus DoltLite C APIs)
> - `lib/libdoltlite.a` — static library
> - `lib/libdoltlite.{so,dylib}` — shared library

> ## Using Existing SQLite Databases
> Stock SQLite files are detected by their header and opened on SQLite's original B-tree engine, directly or via `ATTACH`. Version control applies only to DoltLite-format databases.

> ## SQLite Compatibility
> DoltLite keeps SQLite's SQL semantics and `sqlite3_*` API. Storage-coupled behaviour differs:
> - Own on-disk format; no rollback journal, WAL, or shared-memory sidecars. `PRAGMA journal_mode` reports `wal` and ignores changes.
> - `VACUUM` and `PRAGMA wal_checkpoint` run DoltLite garbage collection.
> - A write transaction may touch only one file-backed database.
> - Non-integer primary keys are clustered and `NOT NULL`; `rowid` is a read-only alias for them.
> - Rowids come from a counter shared by every branch, so implicit-rowid inserts merge cleanly.
> - `sqlite_schema` is a projection of the catalog with canonical `CREATE` text.

> ## Concurrency
> Multiple connections and processes may share one file. Coordination is explicit: [...] One durable writer at a time. A concurrent writer gets `SQLITE_BUSY`.

> ## Storage Format
> A DoltLite database is one content-addressed chunk-store file, not SQLite pages. Format version 12 is frozen for the beta: every version-12 file stays readable and writable by later version-12 builds.

# What it was used to decide

* A stock SQLite file opened by DoltLite is not versioned, so "the same file" has to mean the dump replayed into a DoltLite-format database: [DoltLite same file](/decisions/doltlite-same-file.md).
* `VACUUM` is the settle step for DoltLite, the counterpart of `dolt gc`: [pair load shapes](/decisions/pair-load-shapes-and-measurement.md).
* The `bin/doltlite` shell is the client, and there is no server: the worker container runs the shell over files: [DoltLite v0.50.9](/tools/doltlite-0-50-9.md), the pinned version.
