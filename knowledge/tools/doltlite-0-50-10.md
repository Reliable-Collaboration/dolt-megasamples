---
type: Tool
title: DoltLite v0.50.10
description: The DoltLite release the SQLite pair measures since 2026-09-12 (one version per result set; v0.50.9 before), built here into an image from its two checksummed Debian packages, with what was verified on it before the loads ran again -- above all that VACUUM now collects a per-row-commit file v0.50.9 answered "out of memory" on.
resource: https://github.com/dolthub/doltlite
tags:
- engine
- doltlite
- version
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-15T15:00:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-12T23:20:00Z"
sources:
- resource: /sources/doltlite-release-v0-50-10.md
  title: DoltLite release v0.50.10 and the garbage-collection fix for issue 2820
  accessed: "2026-09-12"
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9, the version measured before, and what was verified on it
- resource: /decisions/engine-versions-one-per-result-set.md
  title: The rule under which the version moved
- resource: /questions/doltlite-vacuum-memory.md
  title: What VACUUM needed on v0.50.9, the limit this version lifts
- resource: https://github.com/dolthub/doltlite/tree/v0.50.10
  title: DoltLite source at v0.50.10 (commit 6c99916d), src/doltlite_gc.c, src/prolly_hashset.c, src/chunk_index.c, src/chunk_wal.c, src/chunk_staging.c
  accessed: "2026-09-15"
- resource: https://github.com/dolthub/doltlite/issues/2936
  title: Issue 2936, VACUUM still answers "out of memory" at 3.9 million commits on v0.50.10, filed from this repository
  accessed: "2026-09-15"
---

# Facts

* **Identity and build.** `scripts/lite_image.py` downloaded `libdoltlite0_0.50.10_amd64.deb` (9,277,140 bytes) and `doltlite_0.50.10_amd64.deb` (19,272,068 bytes), verified them against the SHA-256 values in `versions.json`, and built `doltsamples-doltlite:0.50.10` (285 MB) over `debian:13-slim` by digest in 8.5 s on 2026-09-12. Inside it, `doltlite -version` answers `DoltLite v0.50.10 (SQLite 3.54.0, 64-bit)` and `sqlite3 -version` answers `3.46.1 2024-08-13 09:16:08 c9c2ab54ba1f…` (64-bit): the same SQLite core as v0.50.9 and the same baseline shell, so the SQLite units of the pair are not measured again.
* **`VACUUM` collects the per-row-commit file v0.50.9 could not.** On a copy of chicago_crimes' per-row-commit store as v0.50.9 wrote it (3,626,991,241 bytes, 260,043 commits; v0.50.9 answered `out of memory` within seconds, [VACUUM memory](/questions/doltlite-vacuum-memory.md)), `doltlite /w/chicago_crimes.doltlite "VACUUM;"` in this image under a 16 GiB cgroup exited 0 after 8.1 s and left 1,931,050,868 bytes (1.93 GB, 53% of the size before); the container's memory peaked at about 1,825 MiB (`docker stats`, one-second samples, so a peak between samples may be higher); afterwards `SELECT count(*) FROM dolt_log` answers 260043 and `PRAGMA integrity_check` answers `ok` (2026-09-12, session script `v0.50.10-check/vacuum-old-file.sh`). The fix is pull request 2836, which bounds the mark queue and spills it to disk; its own caveat stands -- visited hashes and chunk indexes still scale with the chunk count -- so the peak on the largest files is a number the loads will produce, not one to assume.
* **File format.** A file written by v0.50.9 opens, collects and checks clean under v0.50.10 (the run above), so the format did not change between the two releases in a way that refuses the older files. The loads write every file afresh all the same.

# Limits

* **`VACUUM` still fails on the largest per-row-commit store.** employees' per-row-commit load with deferred indexes (3,919,015 commits, 341 GB) answered `Error in 2nd command line argument: out of memory` 2.3 s into its settle step, with the engine at 2.9 GiB (2026-09-14), while every other per-row-commit store collected -- up to oracle_sh's inline file, 438 GB and 1,063,396 commits, 64 min, 22.5 million chunks after collection. Read in the v0.50.10 source on 2026-09-15: pull request 2836 bounded only the mark queue; the materialised chunk index (`src/chunk_index.c:455`, `src/doltlite_gc.c:603` and `:753`, 32 bytes an entry, about 67.1 million chunks), the marked-chunk hash set (`src/prolly_hashset.c:23` and `:93`, 20-byte slots, a power of two grown at half full, so 2^25 = 33.5 million chunks) and the checkpoint index page (`src/chunk_wal.c:1236`, an `int`-sized allocation) are each capped at 2 GiB, and a failure within 2.3 s is one of the first two, before any traversal. The limit is therefore a chunk count of about 33.5 million, not a file size or a commit count; which allocation fired was not determined. Reported as dolthub/doltlite issue 2936 on 2026-09-15 with these numbers and lines. The unit is kept with `settled: false`; its inline twin was not run, its working file being beyond this disk.
* **What the loads have not yet shown.** The dialect rules, the durability behaviour and the size and time figures recorded for v0.50.9 ([DoltLite v0.50.9](/tools/doltlite-0-50-9.md)) were not re-verified one by one on this version before the loads ran again; the loads are the re-verification, unit by unit, and every refusal is recorded per unit as before. This record gains an **Update** when the DoltLite result set on v0.50.10 is complete.

# Decision

One version per result set ([the decision](/decisions/engine-versions-one-per-result-set.md)): DoltLite moved from v0.50.9 to v0.50.10 on 2026-09-12 and every DoltLite unit is measured again, the ninety v0.50.9 records kept under `superseded` in `build/progress.json`.
