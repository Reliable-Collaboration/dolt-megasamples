---
type: Open Question
title: Do 16 concurrent connections load a database faster with a commit per row?
description: Answered on 2026-09-13 by a spike -- no. With a Dolt commit per row, 16 workers over 16 connections made Dolt 0.66x as fast as one connection on dvdstore and DoltgreSQL 0.92x (0.33x on sakila), with more CPU, two to three times the memory and twice the store; every commit still held exactly one row. MySQL and PostgreSQL scaled 3x to 13x on the same rows.
resource: /questions/concurrent-commits-per-row.md
tags:
- dolt
- doltgresql
- concurrency
- spike
- question
status: deprecated
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-13T02:20:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-13T02:20:00Z"
sources:
- resource: /decisions/pair-load-shapes-and-measurement.md
  title: The load shapes the spike compares with -- one client stream, a commit per row
- resource: /tools/doltgresql-1-3-1.md
  title: DoltgreSQL 1.3.1, the version the spike ran
- resource: https://github.com/dolthub/dolt/releases/tag/v2.3.2
  title: Dolt 2.3.2, the version the spike ran (the image versions.json names)
  accessed: "2026-09-13"
---

# Question

The maintainer, 2026-09-13: Dolt runs one statement on one thread but keeps connections in their own space, and this host has more than 16 cores; would a load that spreads the row inserts and their commits over 16 workers on concurrent connections go faster, while still producing a commit for every row, accepting that the order of commits may vary? And, from the maintainer as well: can the commit be isolated to one row's change by putting the INSERT and the `DOLT_COMMIT` in one explicit transaction, rather than by giving each worker a branch?

# Cheapest experiment

`scripts/spike_concurrent_commits.py` (2026-09-13). One server per engine from the images `versions.json` names, under the experiment's 16 GiB worker cap; the experiment's own per-row dump with deferred indexes, split into the tables (created first), the INSERT statements (round-robin over N worker threads, one connection each, foreign-key checks off) and the rest (indexes, constraints, views, triggers, after the last row -- **deferred constraints**, the maintainer's choice, so no worker needs the table order). On Dolt and DoltgreSQL each worker runs `BEGIN; INSERT; DOLT_COMMIT('-Am', ...)` per row on the one branch; on MySQL and PostgreSQL one autocommitted INSERT per row. Recorded per run: the row phase's time and rows per second, the commit count and twelve sampled per-commit diffs, every table's row count against the dump, retries and failures, the server cgroup's peak memory and average cores, and the store after `dolt_gc`. sakila (47k rows) at 1, 4 and 16 workers on all four engines; dvdstore (175k rows) at 1 and 16 on the two Dolt engines. About 1 h 40 min, with the measurement run paused.

# Resolves

Whether a sixth load shape -- concurrent connections with a commit per row -- belongs in the experiment, and whether the per-row-commit loads could be run faster that way.

# Answer

**No.** With a commit per row, more connections make the Dolt engines slower, not faster, while the baselines scale. dvdstore, 174,716 rows, the clean run (every row loaded, no failures):

| engine | workers | rows/s | vs 1 worker | commits | retried rows | peak memory | server cores | store after gc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dolt 2.3.2 | 1 | 391 | 1.00x | 174,718 | 0 | 5.4 GiB | 0.67 | 1.7 GiB |
| Dolt 2.3.2 | 16 | 259 | 0.66x | 174,718 | 10 | 13.5 GiB | 1.25 | 3.6 GiB |
| DoltgreSQL 1.3.1 | 1 | 244 | 1.00x | 174,719 | 0 | 6.2 GiB | 0.96 | 1.8 GiB |
| DoltgreSQL 1.3.1 | 16 | 225 | 0.92x | 174,719 | 12 | 14.1 GiB | 1.7 | 3.6 GiB |

sakila, 47,268 rows on the PostgreSQL protocol: DoltgreSQL 164 rows/s at 1 worker, 54 at 4 and 54 at 16 (0.33x); PostgreSQL 1,850, 5,018 and 5,891 (3.2x). On the MySQL protocol the sakila runs are not usable for rates: 461 rows of `address` failed on every attempt on both Dolt and MySQL because the driver path mangles the dump's GEOMETRY literal (`invalid GIS data provided to function DeserializePoint`; MySQL: `Cannot get geometry object`), and the retry back-off then dominates the one-worker time (about 166 s of sleep in 304 s on Dolt). Taking the sleep out, Dolt on sakila went from about 340 rows/s at 1 worker to about 250 at 16, the same direction as dvdstore; MySQL went from about 1,700 to 3,045 (12.9x as printed, about 1.8x corrected).

**The commit per row held on one branch, without branches per worker.** On every Dolt-engine run the commit count is the row count plus the two or three schema commits, and all twelve sampled commits differ from their parent by exactly one row. The maintainer's reading is right: `DOLT_COMMIT` inside an explicit transaction commits the SQL transaction and creates the Dolt commit together, so no row is ever in the shared working set without its commit, and whatever other workers landed in between is already in the parent. The rows that were retried (10 and 12 of 174,716 at 16 workers) all succeeded on a later attempt; none failed.

**Why it does not scale** (inferred from the numbers, not read in the source for this record): every commit's tail -- merging the session's working set with what other sessions landed since, then moving the branch head -- runs under the branch lock, one commit at a time, and with 16 writers every commit first merges up to 15 others' changes. The server used more CPU with 16 workers (1.25 and 1.7 cores against 0.67 and 0.96) for fewer rows per second, its memory peaked at 2.3x to 2.5x (13.5 and 14.1 GiB, under the 16 GiB cap, so not starved but close), and the collected store came out twice as large (3.6 GB against 1.7 and 1.8 GB): the merged intermediate roots stay reachable from the history. All 16 workers finished within a second of each other, so the workers were not unbalanced; they were waiting on the same lock.

**What follows.** No sixth load shape; the per-row-commit loads stay single-stream, which is also their fastest form for these engines. A concurrent shape would measure lock contention, not load speed. Two side findings for the spike's own record: the driver path (pymysql over utf8mb4) cannot carry mysqldump's GEOMETRY literals, so sakila's MySQL-protocol rows are best loaded through the `mysql` client as the experiment does; and DoltgreSQL's collapse at 4 workers on sakila (0.33x) against 0.92x on dvdstore is not explained here. Results: `build/spike-concurrent/{chinook,sakila,dvdstore}.json`; `scripts/spike_concurrent_commits.py --summary` prints the tables.
