---
type: Decision
title: For DoltLite, "the same file" is the dump replayed into a DoltLite-format database
description: What the SQLite/DoltLite pair loads on the DoltLite side, and why opening the stock SQLite file would have measured SQLite twice.
resource: /decisions/doltlite-same-file.md
tags:
- doltlite
- decision
- method
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: /sources/doltlite-readme.md
  title: DoltLite README
  accessed: "2026-09-10"
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9 (verified behaviour)
  accessed: "2026-09-10"
---

# Question

The MySQL/Dolt and PostgreSQL/DoltgreSQL pairs load a dump into two servers. sql-megasamples' SQLite corpus is a file per database, and DoltLite opens SQLite files. What is "the same data, loaded the same way" for this pair?

# Options considered

* **Open the stock `.sqlite` file with `doltlite`.** Lost: the README says a stock file "is detected by its header and opened on SQLite's original B-tree engine", and it does: `dolt_log` answers "dolt version-control features are not available on stock SQLite databases". The load would be zero seconds and the size SQLite's -- SQLite measured twice.
* **`ATTACH` the stock file and `INSERT INTO ... SELECT`** into a DoltLite-format file. Lost: no dump, no per-row shape, no counterpart on the SQLite side; the schema would have to be recreated by hand.
* **Replay `sqlite3 .dump` of the file into a DoltLite-format file** (a file `doltlite` creates), with the same dump replayed by `sqlite3` into a fresh stock file as the baseline. Chosen: one input, five shapes, both engines.

# Evidence

The stock-file behaviour and the replay results (row counts, triggers, views, FTS5, index catalogue all matching the source): [DoltLite v0.50.9](/tools/doltlite-0-50-9.md). A DoltLite file is not readable by `sqlite3` ("file is not a database"), so there is no shared-file shape to measure either way.

# Outcome

`scripts/export_sqlite.py` copies each file and writes its `.dump`; `scripts/pairs.py` loads the dump (after `scripts/doltlite_dialect.py`) with `sqlite3` into `data/sqlite-<mode>/<db>.sqlite` and with `doltlite` into `data/doltlite-<mode>/<db>.doltlite`. The report states this in the pair's description; the baseline `sqlite` unit is a replay of the dump, not the original file, so both sides paid the same load.

# Status

accepted (2026-09-10; user decision: "Accept that the same file for DoltLite means the dump replayed into a DoltLite-format database").
