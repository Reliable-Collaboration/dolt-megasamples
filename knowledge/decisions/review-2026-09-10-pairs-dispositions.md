---
type: Decision
title: "Code review of the pairs, 2026-09-10: eight findings and what was done"
description: The review of the PostgreSQL/DoltgreSQL and SQLite/DoltLite pairs found eight defects, all confirmed against the code and the recorded data; the DoltgreSQL units are measured again with one server per unit, and the rest are fixed without changing a measurement.
resource: /decisions/review-2026-09-10-pairs-dispositions.md
tags:
- review
- method
- decision
status: stable
trust: verified
generated:
  by: claude-code/claude-opus-5
  at: "2026-09-10T18:20:00Z"
verified:
- by: claude-code/claude-opus-5
  at: "2026-09-10T18:20:00Z"
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

# Outcome

1. **Each DoltgreSQL load runs in a server started for it alone**, over its own root `data/doltgres-<shape>/<db>/` (the server's `postgres` catalog and that one database), removed once the size, the counts and the index set are read (`pairs.doltgres_up`). Proved on scratch copies before the chain used it, 2026-09-10 18:07 UTC: jaffle_shop, oracle_hr and pubs peaked at 48, 86 and 78 MiB, parity clean, no container left behind. Every DoltgreSQL unit recorded before the fix is moved to `superseded` in `build/progress.json` and measured again, a step the chain takes once no runner is active; until then the collector leaves those units out, so no shared-server number reaches the documents. PostgreSQL already ran in a fresh server per load, and SQLite and DoltLite in a shell per load whose memory ends with it, so neither is measured again.
2. and 3. **An uncollected store has a footprint, not a size.** `collect_pairs.py` decides `settled` from each unit's recorded errors, whichever runner recorded it, and writes an uncollected store as `footprint_bytes` with `disk_bytes` empty, so the tables, totals, figures, facts and audit all leave it out the same way; `audit.py` checks that every failed settle step is reported unsettled. The two scripts that edit `build/progress.json` now (`clean_pairs.py` and the chain's supersede step) refuse while a runner is active.
4. **Index definitions are compared by their parts**: uniqueness, table, method (btree when not printed), key list and what follows, with identifier quotes removed and case folded outside string literals (`pairs.canonical_index`); both sides of enron's index now compare equal. Reading `pg_index` instead was the reviewer's suggestion; `pg_indexes` was kept because it is the view both engines were probed to answer.
5. **The dialect fails loudly.** G3 and G4 stop the unit with an error naming the table when a CREATE TABLE block is not in pg_dump's usual form, G6 names every trigger it could not expand, and the two column walkers are one. The transform's output for all 63 dumps (three forms of 21 databases) is byte-identical before and after.
6. **The served root owns its catalog**: `stack_config.py` creates it once by starting the image over the served root with nothing mounted (created in 3 s on 2026-09-10) and mounts only the chosen stores beside it.
7. **One source for the stack's settings**: `stack_settings.py` resolves ports, container names, network and passwords from `docker compose config` and `.env` on every `make up` into `build/serve.json`, and the check, the landing page and `make up`'s closing lines read them there.
8. **A clean takes the records with the stores**: `clean_pairs.py` removes the pairs' units from `build/progress.json` and their entries from `build/results.json`, and refuses while a runner or a container mounting the stores is up. The needless console restart in `make up` went too.

Two short tests ran beside `sqlite_rowwise/wikipedia_simple` between 18:07:16 and 18:07:36 UTC: the scratch DoltgreSQL loads and the catalog creation. That is twenty seconds of extra disk and CPU against a unit timed in tens of minutes, named here rather than hidden.

# Status

accepted (2026-09-10); the review's remaining angles are run again on the fixed code, and anything they find is added here.
