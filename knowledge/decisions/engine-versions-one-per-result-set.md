---
type: Decision
title: One version per result set, and no pins
description: The maintainer's rule of 2026-09-12, revised 2026-09-16 -- one version of each engine per run and no pins; a new run (`make new-run`) starts on the newest release of every Dolt engine and keeps those versions until it is complete; a moved engine's old records are dropped, not kept, because the repository presents the current run and its history keeps the earlier ones; the baselines are the corpus's, recorded as found.
resource: /decisions/engine-versions-one-per-result-set.md
tags:
- dolt
- doltgresql
- doltlite
- version
- decision
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-12T22:00:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-12T22:00:00Z"
sources:
- resource: /decisions/doltlite-version-pin.md
  title: The DoltLite pin this replaces
- resource: /decisions/doltgresql-version-pin.md
  title: The DoltgreSQL pin this replaces
- resource: /sources/doltlite-release-v0-50-10.md
  title: DoltLite release v0.50.10, the first version moved to under this rule
- resource: /decisions/engine-bugs-patch-or-work-around.md
  title: Why the DoltLite version moved -- the VACUUM defect fixed upstream
- resource: https://api.github.com/repos/dolthub/dolt/releases/latest
  title: The newest Dolt release when the rule was written
  accessed: "2026-09-12"
  version: "v2.3.3, published 2026-09-09"
- resource: https://api.github.com/repos/dolthub/doltgresql/releases/latest
  title: The newest DoltgreSQL release when the rule was written
  accessed: "2026-09-12"
  version: "v1.3.2, published 2026-09-12"
---

# Question

DoltHub fixed DoltLite's `VACUUM` defect one day after it was reported and released the fix in v0.50.10, while this repository's DoltLite numbers were measured on v0.50.9 under a pin that said "stay unless the maintainer explicitly asks" ([the DoltLite pin](/decisions/doltlite-version-pin.md)). Should the DoltLite version move, and what rule should govern the versions of Dolt, DoltgreSQL and DoltLite from now on?

# Options considered

* **Keep the pins as they were.** Lost: the nine per-row-commit stores recorded `settled: false` would stay uncollected, and the three largest databases' per-row-commit loads could not fit on the disk (about 920 GB projected for oracle_sh and wikipedia_simple against 645 GB free on 2026-09-12), while the fix already existed upstream.
* **Follow the newest release at every run.** Lost: numbers taken over several days would mix versions, and nobody could reproduce a figure without knowing which release produced it -- the reason the pins existed.
* **One version per result set, no pins.** Chosen. Each engine's numbers belong to exactly one version, named in one place; moving an engine is one deliberate command; and a moved version invalidates every recorded unit of that engine, so a result set can never mix versions.
* **Keep the old run's records under `superseded` when a version moves.** Chosen on 2026-09-12, reversed on 2026-09-16. The runners kept one superseded record per unit, so the second move overwrote the first's record, and the review found 253 of 290 kept records were the method-one leftovers rather than the versions' -- but the maintainer's answer was not to keep them better: "we don't want this to become a historical record - old commits can contain old data - we want to present what we know as current with most recent runs". Lost by dropping them: nothing the repository's history does not hold.

# Evidence

The maintainer's words, 2026-09-12: "use the latest DoltLite, but rerun all the tests, moving forward do not pin it but for all three of dolt, doltgres, and doltlite we should run sets of tests against the same version - so if a version changes we re-run everything."

Read on 2026-09-12: DoltLite v0.50.10 carries the fix (pull request 2836 is 20 commits behind the tag; [the release](/sources/doltlite-release-v0-50-10.md)). The newest releases upstream were Dolt v2.3.3 (2026-09-09) and DoltgreSQL v1.3.2 (2026-09-12); the Dolt and DoltgreSQL result sets were measured on 2.3.2 and 1.3.1, every unit of each on one version, and v1.3.2 carries none of the fixes for the issues this repository reported, so neither moved with this decision -- moving them is the maintainer's call, at the cost of measuring that engine's every unit again (Dolt: 105 units, about two days; DoltgreSQL: 87 units, about ten hours of loads).

# Outcome

* `versions.json` at the repository root names every engine's version and how it is named: Dolt, DoltgreSQL and PostgreSQL by image digest, DoltLite by the SHA-256 of its two release packages, MySQL by image tag, SQLite by Debian's package inside the DoltLite image. `scripts/common.py` and `scripts/pairs.py` read it; nothing else carries a version.
* Every unit written to `build/progress.json` records `engine_version`. Both runners (`scripts/run_all.py`, `scripts/run_pairs.py`) refuse, before writing anything, to add to a result set whose recorded units carry another version of an engine, and name them; with `--accept-version-change` they keep each such unit's record under `superseded` and measure it again (`common.version_gate`). The collectors and the audit fold and check only units on the current version, so a moved version's numbers leave the tables until they are measured again.
* `python3 scripts/versions.py --check` (`make versions`) prints each engine's version beside the newest release upstream and fails if `compose.yaml`'s documented image defaults drift from `versions.json`; `--latest <engine>` moves one engine: DoltLite's two packages downloaded and checksummed, DoltgreSQL's or Dolt's image pulled and resolved to its digest, `versions.json` and the compose default rewritten, and the next steps printed. The served stack takes the three engine images from `versions.json` through `compose.override.yaml` on every `make up`, so it serves the version the stores were written with.
* Every document says *Versions* where it said *Pinned versions*: the README's generated table (version, since, how named, what the image answers), the README and journal prose, the report's environment table, the landing page, the banners in `scripts/pairs.py`, `scripts/common.py`, `compose.yaml` and the Dockerfile.
* Applied at once: DoltLite moved from v0.50.9 to v0.50.10 on 2026-09-12 and every DoltLite unit (90 measured with method 2 on v0.50.9) is superseded and measured again; the SQLite baseline (sqlite3 3.46.1, unchanged) is not. [The DoltLite pin](/decisions/doltlite-version-pin.md) and [the DoltgreSQL pin](/decisions/doltgresql-version-pin.md) are deprecated by this record; [DoltLite v0.50.9](/tools/doltlite-0-50-9.md) stays as the record of the version the first DoltLite result set was measured on, and [DoltLite v0.50.10](/tools/doltlite-0-50-10.md) carries what was verified on the new one.

* **Revised 2026-09-16**, in the maintainer's words: "lets not pin anything anymore - We'll want any new run to use the latest release version of everything out there. The only real requirement is that we want all of the experiments in a run to use the same latest version, we don't want to switch in the middle." So: `make new-run` (`scripts/versions.py --latest`) resolves the newest release of every Dolt engine at once, writes `versions.json` and the compose defaults, and drops every unit and memory-study cell of an engine that moved; it refuses while a runner holds the lock, so a run keeps its versions until it is complete. The runners' gate covers every recorded unit of the engines a run touches (not only the run's scope) and has no override; `--accept-version-change` and the `superseded` records are gone. The baselines are recorded, not chosen: MySQL and PostgreSQL as the corpus builds them, the sqlite3 shell as Debian ships it in the DoltLite image, read from the built image into `versions.json` by `make lite-image --record`. The image overrides that could run another engine than the recorded one are gone, and the MySQL timing image comes from `versions.json`. Every folded number and every memory study carries its version and `make check` fails on any that is not this run's; `common.current()` is the one test every reader of `build/progress.json` uses.

# Status

accepted (2026-09-12; revised 2026-09-16; the maintainer's decisions, quoted above).
