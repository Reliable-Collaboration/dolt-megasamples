---
type: Open Question
title: Why does a PL/pgSQL trigger comparing NEW and OLD fields fail on DoltgreSQL at run time?
description: Answered on 2026-09-10 -- not the body but the trigger's WHEN clause, which compares whole rows; expanded column by column by dialect rule G6, the triggers run on both engines.
resource: /questions/doltgresql-trigger-old-record.md
tags:
- doltgresql
- question
status: deprecated
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T07:00:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T07:00:00Z"
sources:
- resource: /tools/doltgresql-1-3-1.md
  title: DoltgreSQL 1.3.1 (the observation)
  accessed: "2026-09-10"
---

# Question

On 1.3.1 with sakila loaded, `UPDATE actor SET first_name = first_name WHERE actor_id = 1` answers `ERROR:  record "old" has no field "*"`. The trigger body is `IF NEW."last_update" IS NOT DISTINCT FROM OLD."last_update" THEN NEW."last_update" := CURRENT_TIMESTAMP; END IF; RETURN NEW;`. Is it `IS NOT DISTINCT FROM` on record fields, the quoted field names, or `OLD` in a `BEFORE UPDATE` trigger that DoltgreSQL's PL/pgSQL does not handle?

# Cheapest experiment

Three one-table variants on a throwaway server: the same body with `<>` instead of `IS NOT DISTINCT FROM`; unquoted field names; a body that only reads `OLD.x` into a variable. Whichever passes names the construct; then the same on the next release.

# Resolves

Whether the stood-up DoltgreSQL instance can take updates on the ported tables ([stood-up instances](/decisions/stood-up-instances.md)), and whether sql-megasamples' PL/pgSQL emitter could choose a form both engines run without changing what the trigger does.

# Answer

Not the body. The trigger's `WHEN ((old.* IS DISTINCT FROM new.*))` clause, which pg_dump writes for the port's "only when the row changed" guard, is what DoltgreSQL 1.3.1 cannot evaluate; every variant of the body (`IS NOT DISTINCT FROM`, `<>`, quoted or unquoted fields, `OLD` read into a variable, no `OLD` at all) works under a per-column `WHEN`, and none works under the whole-row one. Reproduced with sakila's `actor` objects alone (`scripts/doltgres_dialect.py` blocks, 2026-09-10) and bisected through the creation order, `check_function_bodies`, the search path, the identity column, COPY versus INSERT and the comment headers. Dialect rule G6 expands the clause column by column from the table's CREATE TABLE block; with it `UPDATE actor SET first_name = first_name` answers `UPDATE 0` and leaves `last_update`, `UPDATE actor SET first_name = 'X'` moves it, on DoltgreSQL and on PostgreSQL 18.6 alike ([the dialect rules](/decisions/pair-dialect-rules.md), [DoltgreSQL 1.3.1](/tools/doltgresql-1-3-1.md)). One run-time limit remains: a `BEFORE INSERT` trigger that fills a NOT NULL column is refused before it runs.
