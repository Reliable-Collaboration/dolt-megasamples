---
type: Decision
title: "Code review of the pairs, 2026-09-10: two passes, their findings and what was done"
description: Two review passes of the PostgreSQL/DoltgreSQL and SQLite/DoltLite pairs found twenty-three verified defects and a dozen smaller ones; all are fixed, every unit now records its measurement method, and every unit taken with the first method is measured again.
resource: /decisions/review-2026-09-10-pairs-dispositions.md
tags:
- review
- method
- decision
status: stable
trust: verified
generated:
  by: claude-code/claude-opus-5
  at: "2026-09-10T19:55:00Z"
verified:
- by: claude-code/claude-opus-5
  at: "2026-09-10T19:55:00Z"
sources:
- resource: /decisions/pair-load-shapes-and-measurement.md
  title: The load shapes, index policies and measurement rules of the two further pairs
  accessed: "2026-09-10"
- resource: /decisions/stood-up-instances.md
  title: DoltgreSQL and DoltLite instances that stay up beside Dolt
  accessed: "2026-09-10"
---

# Question

The code review of `release-2` at commit 6700c3a -- the two further pairs, the stack that serves them and the documents -- returned eight findings. Which of them hold, what does each change in what was measured, and what was done about it?

A second pass ran on the fixed code (commit 6df60b8) from 18:12 to 19:27 UTC, each of its findings checked by a separate verifier, and returned fifteen more, below the first eight in Evidence and Outcome.

# Options considered

* **Patch each symptom where it showed**: strip one more printing difference from the index text, edit the one stale unit in `build/progress.json`. Lost: most findings belong to a class the next database would reach, and a hand edit of `build/progress.json` while a runner holds its own copy is written over -- which is how finding 3 came about.
* **Footnote the DoltgreSQL memory peaks and keep them.** Lost: a peak taken late in a shape was up to an order of magnitude too high, and the time of those loads was taken on the same shared server.
* **Fix the class each finding belongs to, measure again what a fix changes, and prove that the fixes which must not change a measurement change nothing.** Chosen.

# Evidence

The review ran as `/code-review` on 2026-09-10 at 17:15 UTC. Its root-cause angle completed with the eight findings below; its other angles stopped on the session's model rate limit before reporting and are run again on the fixed code. Every finding was checked before anything changed:

| # | finding | checked by |
|---|---|---|
| 1 | every DoltgreSQL load ran in one server per shape, which held every database loaded before it | `build/progress.json`, per-row-commit units in run order: oracle_hr (216 rows, loaded 1st) peaked at 83 MiB and dvdstore (11th) at 2,356 MiB; pubs (255 rows), loaded 23rd after a restart over a directory holding eleven stores, peaked at 976 MiB |
| 2 | the pair figures and facts summed the uncollected DoltLite footprints the tables leave out | `docs/img/pairs-lite.png` labelled DoltLite's one-commit-per-row bar 156x over 18 databases; the totals row under it said 26.28x over 14 |
| 3 | `settled` defaulted to true for units recorded before the flag existed | `doltlite_rowcommit/dvdstore/inline`: status done, a `settle: ... out of memory` error, no `settled` key, printed as 4.8 GiB |
| 4 | index parity compared the printed `indexdef` text | enron's `recipient_pkey` was recorded missing and extra at once: PostgreSQL prints `"position"`, DoltgreSQL `position` |
| 5 | G4 counted a primary key it had not written; G3's comma repair and G6's expansion could fail silently | code reading; no current dump reaches them, since all 248 CREATE TABLE blocks end with `);` on its own line |
| 6 | the served DoltgreSQL catalog was borrowed from a measured store | `compose.override.yaml` mounted `./data/doltgres-rowcommit/postgres`; the served root held an initialisation marker and no catalog |
| 7 | the stack check and the landing page typed the default ports and passwords | `scripts/stack_check.py`, `scripts/console_page.py`: a password set in `.env` reached compose and the consoles only |
| 8 | `make clean-pairs` removed the stores and kept the records | `scripts/run_pairs.py` treats a recorded `done` as done, so a clean was followed by a run that measured nothing |

**Second pass**, each confirmed by a verifier and, where it concerned the data, against the files:

| # | finding | checked by |
|---|---|---|
| 9 | the dumps were read in text mode, turning every carriage return inside a row value into a line feed | `build/dumps/postgres/enron.inserts.sql` holds 32,795 carriage returns and its prepared per-row file held none; stackexchange_beer 47,696 and adventureworks 8 likewise; the COPY dumps escape them and the SQLite dumps write them through `replace()`, so neither was affected |
| 10 | nothing kept two runners apart: each stopped the other's worker and wrote its own copy of `build/progress.json` over the other's | code reading; the guards were process-name matches, which also matched any command line naming a runner's file |
| 11 | the chain's supersede step deleted every DoltgreSQL store on each start, including stores already measured again | `build/supersede_doltgres.py` removed all five shape directories unconditionally |
| 12 | a fresh clone's `make report` deleted every committed pair result, and a changed host fingerprint made the runner save an empty record over `build/progress.json` | `collect_pairs.py` dropped all pair entries before folding; `run_pairs.py` saved the fresh record `load_progress()` returns |
| 13 | the memory sampler missed loads shorter than its two-second interval and stopped before the settle step | every DoltLite one-commit load of 1.6 s or less recorded 4.0 to 4.3 MiB whatever its size; VACUUM's 1.2 GiB peak was outside every window |
| 14 | `anon` alone left out PostgreSQL's shared buffers | every PostgreSQL unit recorded about 10 MiB, from 216 rows to 3.9 million |
| 15 | the runner's done test ignored whether a unit was measured the way the documents report | `make run-pg` found nothing to do while the collector withheld 78 units |
| 16 | the audit skipped uncollected stores entirely, and centred its commit tolerance on zero | a planted short commit count on an uncollected unit passed |
| 17 | the SQLite pair's row counts included each FTS5 table's rows a second time | sakila 48,268 rows against 47,268 in the PostgreSQL table |
| 18 | a failed settle step was published as a schema object the engine refused | README listed DoltLite's VACUUM running out of memory under "What each engine refused" |
| 19 | the facts about the MySQL/Dolt run's repeats counted the pair units | "321 of 439 measured once" where the first run's own figure was 50 of 168 |
| 20 | a password set in `.env` was published and tested but not applied: Dolt's accounts came from a static file and DoltgreSQL's roles were only ever created | `docker/dolt/init.sql`, `docker/doltgres/init.sh` |
| 21 | the landing page hid the PostgreSQL columns whenever no DoltgreSQL size existed | the committed page had no PostgreSQL column with 21 PostgreSQL sizes measured |
| 22 | the memory study and `make up` could open a store a runner was loading | code reading |
| 23 | `make clean-data` stopped on the root-owned pair stores after deleting the records | its container step removed only the Dolt directories |

Also confirmed, though cut from the fifteen for space: the index-policy tables had a one-commit column that could never fill; stale worker containers blocked the next run; the landing page divided by zero without MySQL results; a long-lived SQLite worker kept an old image or memory limit; psql errors were mapped to their objects by splitting the whole file once per error, which could stall a unit for hours, and an error in a file's last object mapped to nothing; non-default passwords would have been written into the committed landing page; the bundle checker needed PyYAML that nothing installed; `make test-stack` wrote DDL into the served stores; stale mount placeholders accumulated in the served directories; and the journal said the DoltgreSQL units "were" measured again before they had been. One verifier ran a disk-wide search during the timed `sqlite_rowwise/employees` unit, which was interrupted soon after and is measured again under method 2.

# Outcome

1. **Each DoltgreSQL load runs in a server started for it alone**, over its own root `data/doltgres-<shape>/<db>/` (the server's `postgres` catalog and that one database), removed once the size, the counts and the index set are read (`pairs.doltgres_up`). Proved on scratch copies before the chain used it, 2026-09-10 18:07 UTC: jaffle_shop, oracle_hr and pubs peaked at 48, 86 and 78 MiB, parity clean, no container left behind. Every DoltgreSQL unit recorded before the fix is moved to `superseded` in `build/progress.json` and measured again, a step the chain takes once no runner is active; until then the collector leaves those units out, so no shared-server number reaches the documents. PostgreSQL already ran in a fresh server per load, and SQLite and DoltLite in a shell per load whose memory ends with it, so neither is measured again.
2. and 3. **An uncollected store has a footprint, not a size.** `collect_pairs.py` decides `settled` from each unit's recorded errors, whichever runner recorded it, and writes an uncollected store as `footprint_bytes` with `disk_bytes` empty, so the tables, totals, figures, facts and audit all leave it out the same way; `audit.py` checks that every failed settle step is reported unsettled. The two scripts that edit `build/progress.json` now (`clean_pairs.py` and the chain's supersede step) refuse while a runner is active.
4. **Index definitions are compared by their parts**: uniqueness, table, method (btree when not printed), key list and what follows, with identifier quotes removed and case folded outside string literals (`pairs.canonical_index`); both sides of enron's index now compare equal. Reading `pg_index` instead was the reviewer's suggestion; `pg_indexes` was kept because it is the view both engines were probed to answer.
5. **The dialect fails loudly.** G3 and G4 stop the unit with an error naming the table when a CREATE TABLE block is not in pg_dump's usual form, G6 names every trigger it could not expand, and the two column walkers are one. The transform's output for all 63 dumps (three forms of 21 databases) is byte-identical before and after.
6. **The served root owns its catalog**: `stack_config.py` creates it once by starting the image over the served root with nothing mounted (created in 3 s on 2026-09-10) and mounts only the chosen stores beside it.
7. **One source for the stack's settings**: `stack_settings.py` resolves ports, container names, network and passwords from `docker compose config` and `.env` on every `make up` into `build/serve.json`, and the check, the landing page and `make up`'s closing lines read them there.
8. **A clean takes the records with the stores**: `clean_pairs.py` removes the pairs' units from `build/progress.json` and their entries from `build/results.json`, and refuses while a runner or a container mounting the stores is up. The needless console restart in `make up` went too.

Two short tests ran beside `sqlite_rowwise/wikipedia_simple` between 18:07:16 and 18:07:36 UTC: the scratch DoltgreSQL loads and the catalog creation. That is twenty seconds of extra disk and CPU against a unit timed in tens of minutes, named here rather than hidden.

**Second pass:**

9. **Dumps are read and written byte for byte** (`newline=""` on every read and write of a dump), and both dialects split statements at line feeds only, since Python's `splitlines` also breaks at carriage returns and other separators inside values. Proved on 2026-09-10: the 32,795 carriage returns of enron's per-row dump survive into its prepared files, every SQLite dump splits into statements that rejoin byte for byte, and enron's message bodies loaded into PostgreSQL from the COPY form and from the per-row form agree in count (9,941), carriage returns (32,409) and digest.
10. and 22. **One lock for every writer**: `build/run.lock`, a kernel file lock held for the life of `run_all.py`, `run_pairs.py`, `clean_pairs.py` and the memory study; `make up` refuses while it is held. Proved by holding it and starting each of them, with the destructive calls made to fail if reached.
11., 12. and 15. **A method version on every unit instead of a clean-up script.** Every unit records `method` (currently 2); the runner measures again any unit recorded with an older method and keeps its first record under `superseded`; the collector reports only current units and withdraws a committed result only when this machine's `build/progress.json` records that unit with an older method, so a fresh clone keeps every committed result. The runner refuses a `build/progress.json` recorded on another host, and `run_all.py` moves such a file aside instead of writing over it. The supersede script is gone.
13. and 14. **Memory** is read four times a second as anonymous plus shared memory, from before the timed command to after its settle step, each window's peak kept, and every unit runs in a container of its own whose `memory.peak` is recorded beside it. Every unit measured with the first sampler is measured again.
16. The audit checks uncollected stores too (all but the settled-size invariant) and expects two or three more commits than rows.
17. Row counts exclude virtual tables everywhere (`pairs.committed_rows`).
18. A settle error stays on the unit but is excluded from refusals, `schema_object_error` and the refusal count.
19. The run facts count only the MySQL/Dolt units.
20. Dolt's accounts come from `docker/dolt/init.sh`, which applies `DEMO_PASSWORD` and `ADMIN_PASSWORD` with `ALTER USER`; DoltgreSQL's roles are altered after creation; both escape quotes; the Workbench URLs percent-encode the passwords; `.env` is parsed the way compose parses it.
21. The landing page shows a pair's columns whenever either engine has a size, links into DoltgreSQL for the databases actually served, says only what its columns hold, and names a non-default password instead of printing it.
23. `make clean-data` is `clean_pairs.py --everything`: the stores go first, through a container, and the records only after.

The smaller items are fixed the same way: per-row phases only in the index-policy tables, workers removed with their unit and at the start of a run, no division by zero, a fresh worker per unit, one pass to map error lines (and the last object mapped), PyYAML installed with matplotlib, `make test-stack` writing only a scratch database, placeholders removed while the stack is down, the journal's tense corrected.

# Status

accepted (2026-09-10); both passes' findings are fixed, and every unit taken with the first method is measured again.
