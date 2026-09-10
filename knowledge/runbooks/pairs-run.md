---
type: Runbook
title: Running the PostgreSQL/DoltgreSQL and SQLite/DoltLite pairs
description: The order of the steps that produce every number of the two further pairs, what each needs to be running, and how the first run was sequenced.
resource: /runbooks/pairs-run.md
tags:
- runbook
- doltgresql
- doltlite
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T04:10:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T04:10:00Z"
sources:
- resource: /decisions/pair-load-shapes-and-measurement.md
  title: The load shapes, index policies and measurement rules of the two further pairs
  accessed: "2026-09-10"
---

# The steps

Every step is a Makefile target over one script; every script says what it does at the top.

1. **`make lite-image`** -- downloads the two DoltLite packages of the pinned release into
   `build/doltlite/`, checks them against the recorded sha256, builds `doltsamples-doltlite:0.50.9`.
   Needed by every later step of the SQLite pair (the image carries both shells) and by the
   PostgreSQL pair's helper (`wipe`).
2. **`make export-pairs`** -- with sql-megasamples' stack up (`make -C ../sql-megasamples up`;
   `megasamples-postgres` is the source of the PostgreSQL dumps, its `build/sqlite/` the source of
   the files): `pg_dump` in three forms and a reference per database into `build/dumps/postgres/`;
   the `.sqlite` file, its `.dump`, its `.schema` and a reference into `build/dumps/sqlite/`.
   `ARGS="--only sakila"` restricts it; a database already exported is skipped without `--force`.
3. **`make preflight-pairs`** -- every exported schema into throwaway PostgreSQL, DoltgreSQL,
   SQLite and DoltLite; the table of refusals and `build/preflight/pairs.json`. The gate: a
   refusal not yet covered by a dialect rule or recorded as accepted goes into
   `scripts/doltgres_dialect.py` / `scripts/doltlite_dialect.py` before any row is loaded. The
   preflight loads no rows, so a refusal that only shows at row time is found by the loads.
4. **Stop everything else.** `make down` here and in the sql-megasamples checkout; `run_pairs.py`
   refuses to time loads beside other stacks (`--allow-busy` overrides, and the numbers then say
   nothing).
5. **`make run-pg`** and **`make run-lite`** -- the five shapes, resumable, cheapest-first,
   `ARGS="--max-rows N"` to keep a pass short, `ARGS="--indexes inline"` for the second policy,
   `ARGS="--redo --only pubs"` to measure a unit again after a dialect change (both engines of the
   pair, since both load the changed file). Progress in `build/progress.json`; `make progress`.
6. **`make report`** -- folds the units into `build/results.json` (`collect_pairs.py`), regenerates
   `README.md`, `JOURNAL.md`, `REPORT.md` and the landing page; **`make check`** fails if any
   document disagrees with the measurements or an invariant fails (`audit.py`).
7. **`make up`** then **`make test-stack`** -- the stack with DoltgreSQL and the DoltLite files
   beside Dolt, and the proof that both accounts, every file and every console answer.

# How the first run was sequenced (2026-09-10)

The quick subset (`make -C ../sql-megasamples list-quick`, 15 databases) first, under
`--max-rows 200000`, every shape of both pairs and both policies, so that complete tables existed
before any long load started; then the stack test; then the export and preflight of the six
remaining databases; then the quick subset up to a million rows; then the one-commit shapes of
everything; then the per-row shapes of the largest databases, cheapest first, for as long as the
night lasted. The drivers were two shell scripts under `build/` (gitignored), each a sequence of
the commands above; a run interrupted anywhere resumes with the same command.

# What to do when a unit records an error

`build/progress.json` keeps the error, every refusal with its line and the object it fell in, and
the index-parity report. A row-count shortfall is a refused row: look at `errors` for the
`TABLE DATA` object, reproduce it on a throwaway server (`docker run --rm -e DOLTGRES_PASSWORD=x
dolthub/doltgresql@<digest>`), decide whether a dialect rule can carry the data without touching a
row, record the finding in the engine's tool record, and rerun the unit with `--redo`. A missing
index the engine refused out loud is recorded as a schema object not taken and is not an error.
