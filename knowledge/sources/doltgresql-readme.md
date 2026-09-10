---
type: Source
title: DoltgreSQL README (dolthub/doltgresql, main)
description: The project's own description of what DoltgreSQL is, how data goes in, what it does not do, and its correctness and performance claims.
resource: https://github.com/dolthub/doltgresql
tags:
- doltgresql
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
- resource: https://api.github.com/repos/dolthub/doltgresql/readme
  title: README.md of dolthub/doltgresql, raw, default branch
  accessed: "2026-09-10"
  version: "main on 2026-09-10; 9,830 bytes"
- resource: https://api.github.com/repos/dolthub/doltgresql
  title: Repository metadata (licence and description)
  accessed: "2026-09-10"
---

# What was read

The README of `dolthub/doltgresql` on its default branch, fetched raw through the GitHub API on 2026-09-10 (`gh api repos/dolthub/doltgresql/readme -H "Accept: application/vnd.github.raw"`, 9,830 bytes), and the repository record (`gh api repos/dolthub/doltgresql`), which reports the licence as `Apache-2.0` and the description as "DoltgreSQL - Version Controlled PostgreSQL".

# Relevant excerpt

> Git versions file, Doltgres versions tables. It's like Git and Postgres had a baby.

> # Doltgres is 1.0
> [Doltgres is 1.0](https://www.dolthub.com/blog/2026-08-06-doltgres-1-0/), which means it's ready for your production use case.
> The wait is over! Now is the time to try out Doltgres and let us know what you think. Import your existing Postgres database into Doltgres with `pg_dump` and `psql`, and let us know if anything doesn't work.

> # Limitations and differences from Dolt
> - No Git-style CLI for version control like in Dolt, only a SQL interface.
> - No GSSAPI support.
> - Limited extension support.
> - Some Postgres syntax, types, functions, and features are not yet implemented. If you encounter a missing feature you need for your application, please file an issue to let us know.

> # Performance
> Dolt is 1.1X slower than MySQL as measured by a standard suite of Sysbench tests.
> We use these same Sysbench tests to benchmark DoltgreSQL and compare the results to PostgreSQL.

> # Correctness
> [...] Here are DoltgreSQL's sqllogictest results for version `1.0.0`. Tests that did not run could not complete due to a timeout earlier in the run.
> | did not run | 25552 | not ok | 13197 | ok | 5636424 | timeout | 7 | Total Tests | 5675180 |
> | Correctness Percentage | 99.317097 |

(The sysbench numbers in the README are the project's for 1.0.0 and are not repeated here; this repository measures its own.)

# What it was used to decide

* The import path for the PostgreSQL pair -- `pg_dump` then `psql` -- is the one the project recommends: [pair load shapes](/decisions/pair-load-shapes-and-measurement.md).
* Version control is SQL-only (`dolt_commit(...)` as a function), which is why the settle step is a query and not a CLI call: [DoltgreSQL 1.3.1](/tools/doltgresql-1-3-1.md), the pinned version.
* "Some Postgres syntax, types, functions, and features are not yet implemented" is the reason the preflight exists and refusals are recorded rather than assumed: [dialect rules](/decisions/pair-dialect-rules.md).
