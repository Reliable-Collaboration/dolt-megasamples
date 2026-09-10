---
type: Open Question
title: Why does a PL/pgSQL trigger comparing NEW and OLD fields fail on DoltgreSQL at run time?
description: The port's BEFORE UPDATE triggers are created but every UPDATE that fires one answers `record "old" has no field "*"`; the instance that stays up cannot take updates on those tables until this is understood.
resource: /questions/doltgresql-trigger-old-record.md
tags:
- doltgresql
- question
status: draft
trust: open
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
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
