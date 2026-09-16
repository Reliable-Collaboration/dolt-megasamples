# Agent handover: release 3, a fresh run on a fresh machine

Written 2026-09-16 at the end of the session that produced release 2 (merged into `main` as
6ff2ec2). This branch, `release-3`, is that repository with every measured artefact removed, so
that a new session on a new machine can measure everything again on the newest releases and
nothing from the previous machine survives into the new documents. Read this file first, then
`knowledge/index.md`, then the decision records it names. The maintainer will point you here.

## What this repository is, in one paragraph

Two things. First, the 21 sample databases of
[`sql-megasamples`](https://github.com/Reliable-Collaboration/sql-megasamples) loaded into
DoltHub's three versioned engines (Dolt in place of MySQL, DoltgreSQL in place of PostgreSQL,
DoltLite in place of SQLite) and served beside a set of web consoles, so people can open real data
in each engine. Second, an experiment: for the same data, what does a Dolt engine cost against the
database it stands in for, in disk, time and memory, measured by loading every database five ways
into both sides of each pair. The README tells that story; REPORT.md carries every table and
figure; JOURNAL.md the method and history; `knowledge/` the research trail and the decisions.
Every number in those documents is generated from the measurement files in `build/` and
`make check` fails if a document disagrees with them.

## The maintainer's standing instructions

These were given during release 2 and still hold. Quote them back when a decision rests on them.

- **Status updates.** "Report back at least every 1 hour with a status update. Be sure that status
  updates are complete with a full list of what needs to get done, what's left to do. Also provide a
  list of decisions that were made and things that I should know about, as well as if input is
  needed from me. Author status updates so that they are cumulative." A detached monitor that prints
  the state hourly is the reliable way; see *Things that went wrong before* below.
- **Never publish anything without explicit approval**: no GitHub issues, no comments on upstream
  repositories, no pull-request merges, no pushes to `main`. Pushing to this branch is fine.
- **Verified versus inferred.** Say which is which. A claim about an engine's behaviour is verified
  by running it, and the knowledge bundle records how. Never present an inference as a measurement.
- **No sudo workarounds.** If something needs root, say so and stop.
- **No number typed by hand into a generated document.** README.md, REPORT.md and JOURNAL.md are
  rendered from `docs/templates/` by `scripts/render.py`; a number reaches them as a fact
  (`scripts/facts.py`) or a block (`scripts/render.py`, `scripts/report_pairs.py`,
  `scripts/report.py`). Prose claims must be things the data makes; the code review of 2026-09-16
  found two that it did not, and they were replaced by computed text.
- **One version per run, no pins** (revised 2026-09-16): "lets not pin anything anymore - We'll want
  any new run to use the latest release version of everything out there. The only real requirement
  is that we want all of the experiments in a run to use the same latest version, we don't want to
  switch in the middle." `make new-run` is that rule in one command.
- **Present the current run, not a history**: "we don't want this to become a historical record -
  old commits can contain old data - we want to present what we know as current with most recent
  runs". A new run drops the old one's records; git history is the archive. Never build a
  historical table into the documents.
- **Commits**: end each message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`
  and the `Claude-Session:` line the harness gives you; pull-request bodies end with the
  `🤖 Generated with [Claude Code]` line and the session link. Commit and push to this branch as
  work lands; open a pull request from `release-3` to `main` when the run is complete, and leave the
  merge to the maintainer.
- **Knowledge bundle**: every finding, decision and verified engine behaviour is recorded under
  `knowledge/` in the form `knowledge/runbooks/knowledge-bundle-conventions.md` describes;
  `make okf-check` validates it and `scripts/okf_check.py --bundle knowledge --write-index`
  regenerates its indexes. Add a `log.md` entry for every session's work.

## What the previous run found, in brief

On the previous machine (an i9-14900KF, 32 threads, 19.5 GiB of memory under WSL2, 1.5 TB of
disk), on MySQL 9.7.2, Dolt 2.3.2, PostgreSQL 18.6, SQLite 3.46.1, DoltgreSQL 1.3.2 and DoltLite
0.50.10, every unit of every pair was measured, both index policies, plus the three memory studies.
The finding: loaded once with one commit, a Dolt engine's store is a fraction of MySQL's and
PostgreSQL's and somewhat larger than SQLite's; one commit per row costs tens of times the
baseline's disk and hundreds to thousands of times its time, in every engine, and what a Dolt
engine's store tracks is its commits. The numbers are in `main`'s README, REPORT.md and
`build/` (commit 6ff2ec2) and the story of how they were reached is in `knowledge/log.md`.
Expect the new run to differ in detail and, if the engines improved, in kind.

Upstream at the time of writing: Dolt 2.3.5 and DoltgreSQL 1.3.3 are newer than what was
measured; DoltLite 0.50.10 was the newest. `make versions` says what is newest now.

## What this branch starts with

`make clean-run` was run on it: no `build/results.json`, no memory studies, no `build/method.json`,
no `build/environment.json`, no `build/serve.json`, no spike results, no figures, no screenshots,
and the console page says nothing is served. `versions.json` still names the previous run's
versions (`make new-run` rewrites it) and `build/catalogue.json` still holds each database's
description (not a measurement; `make catalogue` rewrites it from the corpus checkout). The
rendered documents show `[not measured]` wherever a fact has no measurement yet, and `make check`
passes in that state. The knowledge bundle is complete and describes the previous run; add to it,
do not rewrite it.

## The machine needs

- **Docker Engine** (Docker Desktop on WSL2 worked; every container carries a memory limit and
  swap is off inside them), **Python 3.11 or newer** with PyYAML importable by `python3` (the
  Makefile makes `.venv` with matplotlib and PyYAML for the figures and the bundle checker, using
  `uv` if present), `git`, `gh` (for the pull request), and `make`.
- **The corpus beside this checkout**: `../sql-megasamples` (or `MEGASAMPLES_DIR=...` in the
  environment), cloned and built for MySQL, PostgreSQL and SQLite with the 21 core databases (in
  that repository: `uv sync`, `make configure`, `make run`; hours). The exports here read its running
  `megasamples-mysql` and `megasamples-postgres` containers and its `build/sqlite/` tree.
- **Disk**: the previous run's stores and exports took several hundred gigabytes, most of it the
  per-row-commit loads of the largest databases, and the maintainer provided 1.5 TB. The runners
  stop before a unit that would take free space below `--floor-gb`.
- **Memory**: the worker cap defaults to 16 GiB (`DOLTSAMPLES_MEM_WORKER`); Dolt's garbage
  collection of the largest per-row-commit store ran at the top of that, and DoltgreSQL's largest
  loads needed 12 GiB (8 GiB was killed). More is better; the memory studies walk a ladder up to
  16 GiB by default, and `make memory-pairs ARGS="--top 12288"` caps the pairs' study on a smaller host.
- **Time**: the previous machine spent roughly two days on the MySQL/Dolt run (both policies),
  39 hours of loads on DoltgreSQL, 18 on DoltLite, and some hours on the three memory studies.
  `make estimate` projects from measured rates once a few units exist.

## The order of work

Nothing else may run on the machine while loads are timed; the corpus's stack must be down for
the timed pairs (its MySQL is needed only for `make export`, its PostgreSQL only for
`make export-pairs`).

1. `make versions`, then **`make new-run`**: resolves the newest release of Dolt, DoltgreSQL and
   DoltLite, writes `versions.json` and the compose defaults, builds the DoltLite image and records
   the sqlite3 shell it carries. Commit `versions.json`.
2. In the corpus checkout: `make compose && docker compose up -d mysql`. Here: `make export`
   (mysqldump every database), then `make preflight` (every schema into MySQL and Dolt, no rows;
   what each refuses). Read what the preflight refuses: a newer Dolt may take objects the transform
   used to drop, and `scripts/dolt_dialect.py` says why each rule exists.
3. **`make run`**, then **`make run ARGS="--indexes inline"`**: the MySQL/Dolt loads, five per
   database, resumable, cheapest first. `make progress` shows the state.
4. In the corpus checkout: `docker compose up -d postgres`. Here: `make export-pairs` (pg_dump three
   ways, the SQLite files and their dumps, the references every unit is checked against), then
   `make preflight-pairs`. Then bring the corpus's stack down (`make down` there).
5. **`make run-pg`**, **`make run-pg ARGS="--indexes inline"`**, **`make run-lite`**,
   **`make run-lite ARGS="--indexes inline"`**. Each refuses to start beside another runner or a
   served stack. `make progress` shows both pairs.
6. **`make memory`** (Dolt's memory study, `build/memory.json`) and **`make memory-pairs`**
   (DoltgreSQL's and DoltLite's, `build/memory_pairs.json`). Neither may run beside a runner or the
   served stack; both take the run lock.
7. **`make report`** (records the machine, runs the method checks, folds the units into
   `build/results.json`, draws the figures, renders the documents, writes the console page), then
   **`make check`**. Do this after every batch of units as well: the documents are meant to fill in
   from the top as the run proceeds.
8. **`make up`**, **`make test-stack`**, **`make screenshots`**, then `make report` and
   `make check` again, so the README's pictures show this machine's stack.
9. Knowledge: a tool record per new engine version (what was verified on it, as
   `knowledge/tools/doltgresql-1-3-2.md` and `knowledge/tools/doltlite-0-50-10.md` do), the older
   ones deprecated; `log.md` entries; `make okf-check`. Then the pull request.

## Things that went wrong before, so they need not again

- **The harness kills background processes it started** when it decides memory is short, even
  with plenty free. Anything that must outlive a turn (a chain of runs, an hourly status monitor, a
  disk watchdog) is started with `setsid nohup ... > build/some.log 2>&1 &` from a shell so it is not
  the harness's child, and checked by reading its log. `build/run-*` and `build/*.log` are ignored
  by git.
- **Pausing and resuming a run**: stop the driver shell first, then send the runner SIGTERM, then
  `docker rm -f` its worker container (`doltsamples-dolt-runner`, `doltsamples-doltgres-runner`,
  `doltsamples-lite-runner`, `doltsamples-mysql-timing`, `doltsamples-postgres-timing`). The unit
  in flight is recorded `running` with no runner alive; the next run redoes it. Never edit
  `build/progress.json` while a runner is alive.
- **A zsh pipeline hides an exit code**: `make check | tail` reports `tail`'s status. Use
  `$pipestatus[1]` or redirect to a file and test `$?`.
- **DoltgreSQL's image gives the server 300 s to start**; a per-row-commit store of hundreds of
  thousands of commits takes longer, because the server scans every table on opening. The served
  stack and the memory probe set `DOLTGRES_SERVER_TIMEOUT` (1800 s, `common.DOLTGRES_START_LIMIT`).
- **DoltLite's `VACUUM` had a ceiling** at 0.50.10: its collector's allocations were capped at 2 GiB,
  so the largest per-row-commit store could not be collected (upstream issue dolthub/doltlite#2936,
  fix pull request 2944 in review on 2026-09-16). Such a unit is recorded `settled: false` at its
  working footprint and marked † in the tables. On a newer release, check whether the ceiling is
  gone; `knowledge/questions/doltlite-vacuum-memory.md` and `knowledge/tools/doltlite-0-50-10.md`
  record the finding.
- **The two largest DoltLite inline loads were skipped for disk** on the previous machine, because
  their working files before collection would not fit. With 1.5 TB free and a collector that works,
  run them.
- **DoltgreSQL refused nine views** (functions it lacks: `xpath`, `convert_from`; a `JSON_TABLE`
  view; a `GROUP BY` it rejects), and needed nine dialect rules (`scripts/doltgres_dialect.py`,
  `knowledge/decisions/pair-dialect-rules.md`), each found by refusal. The maintainer reported the
  defects upstream with reproduction repositories (`docs/upstream/`,
  `knowledge/sources/doltgresql-issues-filed-2026-09-11.md`); DoltHub merged fixes for eleven of them
  on 2026-09-16, after 1.3.3 shipped. On a release that carries them, some rules may no longer be
  needed: the preflight shows what is still refused, and a rule that fires without a refusal to
  justify it should be retired and the decision record updated.
- **DoltgreSQL prints a null ordering** (`nulls first`) in some index definitions that PostgreSQL
  does not; the parity check records it as `ordering_differs` rather than failing. Whether to report
  it upstream is an open question for the maintainer.
- **Memory caps**: `DOLTSAMPLES_MEM_WORKER=12g` was the smallest that finished every DoltgreSQL
  load; every unit records the cap it ran under.

## Open items the maintainer has not decided

- Whether to report the `nulls first` index-definition finding to DoltHub.
- Whether JOURNAL.md should be reframed the way the README was (story first); the maintainer's
  review of the README applies to it too.
- The presentation decision record (`knowledge/decisions/documents-story-first.md`) is pending the
  maintainer's review of the rendered documents.

## Where to look

- `knowledge/index.md`, then the decisions: `engine-versions-one-per-result-set.md` (the version
  rule, revised 2026-09-16), `documents-story-first.md` (how the documents are told),
  `pair-load-shapes-and-measurement.md` (what is measured and how), `pair-dialect-rules.md` (what
  each engine needed changed), `stood-up-instances.md` (the served stack),
  `engine-bugs-patch-or-work-around.md` (the defects and what DoltHub did).
- `knowledge/runbooks/pairs-run.md`: running the pairs, step by step, and the new-run procedure.
- `docs/upstream/`: the bug reports as filed, and their state.
- The README's *Layout* section: what every script is for. `make help` lists every target.
- `PLAN.md`: the plan for release 2, kept as written; this file is the plan for release 3.
