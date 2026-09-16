---
type: Open Question
title: Does a later DoltgreSQL accept a second alteration of a table with a STORED generated column?
description: DoltgreSQL 1.3.1 accepts one ALTER TABLE or CREATE INDEX on such a table and refuses the next with a syntax error in its own re-serialised expression; whether a newer release fixes it matters only if the maintainer asks for the pin on 1.3.1 to be removed, and then decides whether adventureworks_lt's indexes can be carried.
resource: /questions/doltgresql-generated-column-alteration.md
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

On 1.3.1, the pinned version, `CREATE TABLE t (id integer NOT NULL, a numeric(19,4), b smallint, c numeric(38,6) GENERATED ALWAYS AS (COALESCE(a * (b)::numeric, 0.0)) STORED)` followed by `ALTER TABLE ONLY t ADD CONSTRAINT t_pkey PRIMARY KEY (id)` succeeds, and `CREATE INDEX t_b ON t USING btree (b)` after it fails with `Invalid default value for '(coalesce("a" * 1.0 * "b"::NUMERIC as (a * 1.0) * b::NUMERIC,0.0))': at or near "as": syntax error`. Is this fixed in a later release, and is it reported upstream?

# Cheapest experiment

Run the four statements above against the next DoltgreSQL release (`docker run --rm -e DOLTGRES_PASSWORD=x dolthub/doltgresql:<tag>` and `psql`); search the project's issues for "Invalid default value" and "generated". If it is fixed, that is reported to the maintainer: DoltgreSQL stays pinned at 1.3.1 unless the maintainer explicitly asks for the pin to be removed ([the pin](/decisions/doltgresql-version-pin.md)), and only then is `adventureworks_lt` rerun on both index policies. Checked in part on 2026-09-10: no release after 1.3.1 exists, a reading of the default branch at b7a87dad (not run) finds the defect unfixed there, and [issue 810](https://github.com/dolthub/doltgresql/issues/810), open since 2024-10-03, is the same family; where it lives and how large a fix would be: [patch or work around](/decisions/engine-bugs-patch-or-work-around.md).

# Resolves

Whether `adventureworks_lt`'s 8 secondary indexes and 5 foreign keys on `salesorderdetail` and `salesorderheader` stay recorded as refused ([dialect rules](/decisions/pair-dialect-rules.md)) or are carried; and whether to file the issue upstream (a decision for the repository's owner, since it is outward-facing).
