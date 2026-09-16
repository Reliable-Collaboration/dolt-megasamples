---
type: Tool
title: DoltgreSQL 1.3.2
description: The DoltgreSQL release the PostgreSQL pair measures since 2026-09-14 (1.3.1 before), named by image digest, with what the 105 loads showed against 1.3.1 -- the same refusals, 0.89x to 0.96x the time, 8.1 GiB at the engine's highest -- what changed in its catalog and its privileges, and what it still does not do.
resource: https://github.com/dolthub/doltgresql
tags:
- engine
- doltgresql
- version
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-16T13:30:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-16T12:00:00Z"
sources:
- resource: /sources/doltgresql-release-v1-3-2.md
  title: DoltgreSQL release v1.3.2, the version of the second result set
- resource: /tools/doltgresql-1-3-1.md
  title: DoltgreSQL 1.3.1, the version measured before, and what was verified on it
- resource: /decisions/engine-versions-one-per-result-set.md
  title: The rule under which the version moved
- resource: /sources/doltgresql-issues-filed-2026-09-11.md
  title: The issues filed from 1.3.1 and DoltHub's response
- resource: /decisions/pair-dialect-rules.md
  title: The dialect rules, applied unchanged to 1.3.2
---

# Facts

* **Identity.** `dolthub/doltgresql@sha256:267aff12…`, the image tagged `1.3.2`, released 2026-09-12; `SELECT version()` still answers `PostgreSQL 15.5`. Every DoltgreSQL unit of the experiment, 105 of them, was measured on it between 2026-09-14 and 2026-09-16, 39 hours of loads, in a server started for each unit under a 16 GiB cap until 2026-09-15 00:54 UTC and 8 GiB then 12 GiB after it (the maintainer's other work; every unit records its cap as `memory_cap`).
* **The dialect rules did not change.** [The seven rules](/decisions/pair-dialect-rules.md) written for 1.3.1 were applied as they were, and every database loaded with the same refusals recorded per unit: the `xpath` views of adventureworks (2) and adventureworks_lt (1), oracle_co's `product_reviews` view (`at or near "as"`), sakila's `actor_info` view (`GROUP BY`), wikipedia_simple's four `convert_from` views. Nothing that 1.3.1 refused loaded, and nothing new was refused.
* **Pace against 1.3.1.** On the twelve units with a 1.3.1 record of the same unit to compare with, 1.3.2 took 0.89x to 0.96x the time on every load above five minutes (adventureworks' per-row-commit load 138.5 min against 150.4, contoso 49.2 against 55.2, lahman 54.8 against 58.4) and 0.74x to 0.75x on enron's; stores came out within a few percent of the same size.
* **Memory.** The engine's highest anonymous-plus-shared peak was 8.1 GiB, on oracle_sh's inline per-row-commit load (1,063,396 commits), which an 8 GiB cap killed at 75 minutes on 2026-09-15 (container OOM event, `die 137`) and a 12 GiB cap carried through; employees' two per-row-commit loads (3,919,015 commits) peaked at 5.1 and 5.2 GiB; everything else stayed under 5 GiB.
* **Database privileges are enforced now.** Probed on 2026-09-16 with the private reproduction's script over the 1.3.2 image: a login role with none of `SUPERUSER`, `CREATEDB` and `CREATEROLE` gets `ERROR: permission denied to create database` on `CREATE DATABASE` and `ERROR: must be owner of database victim` on `DROP DATABASE`, PostgreSQL's wording, and the database survives; 1.3.1 allowed both (pull request 3343, in this release). The stack's `demo` account therefore no longer creates or drops databases by itself.

# Limits

* **A role can still grant itself `CREATEDB`.** In the same probe, `ALTER ROLE demo CREATEDB` run by `demo` succeeded and `pg_roles.rolcreatedb` read true afterwards, where PostgreSQL answers `permission denied`; with it, `demo` could create databases after all. The second half of the private report, still open on 1.3.2.
* **The catalog prints a null ordering the source does not.** `pg_indexes.indexdef` read back `(rowguid nulls first)` for adventureworks_lt's eight unique indexes on `uuid` columns, where PostgreSQL 18.6 and 1.3.1 print `(rowguid)`; in a probe on 2026-09-16 (a table with unique indexes on a `uuid` and a `text` column, a plain index on an `int`, rows including NULLs) the `text` unique index printed `NULLS FIRST` and the `uuid` one did not, so the condition is not the column type alone and is not pinned down. `ORDER BY` put NULLs last ascending and first descending on both engines, identically, so the difference is in what the catalog says, not in what the index does, as far as the probe shows. The parity check keeps such an index and records the difference under `ordering_differs` ([the load shapes](/decisions/pair-load-shapes-and-measurement.md)); not reported upstream.
* **Opening a large per-row-commit store takes longer than the image allows.** Started over adventureworks' per-row-commit store (759,240 commits, 8.1 GB) under a 12 GiB cap, the server logged `failed to scan table public.production_transactionhistoryarchive: context canceled` and the entrypoint gave up: `Doltgres server failed to start within 300 seconds` (2026-09-16); the same for employees' stores and wikipedia_simple's inline one, while every one-commit and row-insert store and the per-row-commit stores up to oracle_sh's (1,063,396 commits) opened in time. The limit is the image's `DOLTGRES_SERVER_TIMEOUT` (default 300); the served stack and the memory study set it higher. How long those stores take to open is what the study's rerun measures.
* **What 1.3.1 could not do, 1.3.2 cannot either**, by the loads: the generated-column, `character(n)`, trigger `WHEN`, named NOT NULL and `regexp_like` limits of [DoltgreSQL 1.3.1](/tools/doltgresql-1-3-1.md) are worked around by the same rules; the fixes for all of them merged upstream on 2026-09-16, after v1.3.3, for a later release.

# Decision

One version per result set ([the decision](/decisions/engine-versions-one-per-result-set.md)): DoltgreSQL moved from 1.3.1 to 1.3.2 on 2026-09-14, once every DoltLite unit was done, and every DoltgreSQL unit was measured again; the 1.3.1 records are kept under `superseded`. v1.3.3 (2026-09-15) carries none of the fixes this repository waits on; moving to the release that does is the maintainer's call, at the cost of measuring the 105 units again.
