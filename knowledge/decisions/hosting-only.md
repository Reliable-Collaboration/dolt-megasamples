---
type: Decision
title: dolt-megasamples hosts databases; the side-by-side tests live in dolt-unofficial-benchmarking
description: The maintainer's split of 2026-10-02 -- this repository keeps only the tooling to spin up a chosen set of Dolt engines x databases x commit history beside their consoles, with sql-megasamples as its prerequisite; every timed and comparative test moved, with this repository's history, to dolt-unofficial-benchmarking, which uses a dolt-megasamples checkout for the exports, dialect rules and images.
resource: /decisions/hosting-only.md
tags:
- repository
- stack
- decision
status: stable
trust: verified
generated:
  by: claude-code/claude-opus-5-5
  at: "2026-10-02T19:00:00Z"
verified:
- by: claude-code/claude-opus-5-5
  at: "2026-10-02T19:00:00Z"
sources:
- resource: https://github.com/Reliable-Collaboration/dolt-unofficial-benchmarking
  title: dolt-unofficial-benchmarking, where the side-by-side tests and their history now live
  accessed: "2026-10-02"
- resource: https://github.com/Reliable-Collaboration/sql-megasamples
  title: sql-megasamples, the prerequisite and the provider of every database
  accessed: "2026-10-02"
- resource: /decisions/stood-up-instances.md
  title: How the stores are served
---

# Question

dolt-megasamples was meant to do for Dolt what sql-megasamples does for MySQL, PostgreSQL and SQLite: host a set of sample databases for someone who wants an instance with records in it, with the Dolt-specific choice of what history the hosted database has had. By release 3 it had become a test harness -- five load shapes per database per pair, two index policies, memory studies, a generated report -- and the hosting was what was left over at the end of a run. What should this repository be?

# Options considered

* **Keep both in one repository.** Lost: a person who wants a hosted Dolt database meets a multi-day timed experiment first, and the hosting is shaped by what the measurements needed (stores named by load shape, consoles sized for a timed host).
* **Split, copying the shared code into both.** Lost: the dialect rules -- each found by a refusal -- would drift between two copies, and a fix the benchmark finds would have to be carried over by hand.
* **Split, with the benchmark depending on dolt-megasamples.** Chosen. One copy of the exports, the dialect rules, the DoltLite image and the version resolver, here; the benchmark measures the same loads people host.

# Evidence

The maintainer's words, 2026-10-02: "This one should only be the tools a person needs to spin up their choice of databases and commit patterns. Note that we don't need different load strategies for 'commit per row' with and without indexes because only the end goal is of concern on the megasamples instance. [...] we will assume that sql-megasamples is a pre-requisite project of dolt-megasamples as it will be the provider of the data. The dolt-unofficial-benchmarking will be where we bring all of the 'side by side testing'." Asked the same day, the maintainer chose: two histories (one commit; one commit per row), the shared code here with the benchmark depending on it, the benchmark carrying this repository's history, and the partial release-3 run deleted rather than carried anywhere; and, for the configuration, each history listing its databases, so a database may be served under both.

Verified on 2026-10-02 by `make export`, `make build`, `make up` and `make test` on sakila and chinook in all three engines, sakila in both histories (Dolt 2.4.0, DoltgreSQL 1.3.3, DoltLite 0.50.14, rootless Podman 5.7): nine stores built and checked against the corpus's row counts (and index sets, for DoltgreSQL and DoltLite); the per-row stores of sakila hold 47,271 commits in Dolt and DoltgreSQL and 47,270 in DoltLite for its 47,268 rows (the rest are the engine's own initial commits and the final commit that adds the indexes); 23 of 23 stack checks passed. The same day, the default set -- the 21 core databases in all three engines with one commit each, and sakila's per-row history in each -- from `make export` on the corpus's images to `make test`: 66 stores built and checked, none failed; the engines refused 31 statements in Dolt (stored functions and the like, which it does not implement), 10 in DoltgreSQL (the views the benchmark has recorded since 1.3.1) and none in DoltLite, each recorded with its store; 80 of 80 stack checks passed.

# Outcome

* `dolt-megasamples.yaml` names, per engine (Dolt, DoltgreSQL, DoltLite), the databases under each history -- `single` or `per-row` -- as a selector sql-megasamples understands (core, quick, all, a tier) or a list; the consoles; the ports; the memory limits. A per-row store is served as `<db>_per_row`.
* The package `doltsamples` (`python3 -m doltsamples <command>`, each a `make` target): `export` (from the corpus's running servers or short-lived containers from its images), `build` (dialect rules, replay, commit, collect, check against the corpus; recorded in `build/stores.json` with the engine version and the export's digest), `up` (compose.yaml generated from the configuration and the built stores), `test`, `status`, `versions`, `update`, `clean`.
* The per-row history is built with the secondary indexes added after the rows (one last commit); Dolt replays in chunks with `dolt gc` between them, and with `dolt sql --continue`, so a refused statement no longer costs the objects after it.
* Removed here and kept in dolt-unofficial-benchmarking: the timed runners, the baselines, the memory studies, the audit and every generated document of the experiment, `docs/upstream/` (the bug reports as filed), and the knowledge records of the measurements; links from the records kept here point there.

# Status

accepted (2026-10-02; the maintainer's decisions, quoted above).
