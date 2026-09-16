---
type: Source
title: DoltLite release v0.50.10 and the garbage-collection fix for issue 2820
description: The release published on 2026-09-11, one day after the pinned v0.50.9, which carries pull request 2836 -- the fix for the VACUUM "out of memory" failure this repository reported as issue 2820 -- and the checksums of its two Debian packages, downloaded so the pin can move if the maintainer asks.
resource: https://github.com/dolthub/doltlite/releases/tag/v0.50.10
tags:
- doltlite
- release
- pin
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-12T21:20:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-12T21:20:00Z"
sources:
- resource: https://api.github.com/repos/dolthub/doltlite/releases/tags/v0.50.10
  title: Release v0.50.10 of dolthub/doltlite
  accessed: "2026-09-12"
  version: "v0.50.10, published 2026-09-11T21:59:59Z"
- resource: https://api.github.com/repos/dolthub/doltlite/releases
  title: Release list of dolthub/doltlite (first four)
  accessed: "2026-09-12"
- resource: https://github.com/dolthub/doltlite/issues/2820
  title: Issue 2820, VACUUM answers "out of memory" on a database with a long commit history
  accessed: "2026-09-12"
  version: "opened 2026-09-11T02:25:00Z, closed as completed 2026-09-11T20:01:26Z"
- resource: https://github.com/dolthub/doltlite/pull/2836
  title: Pull request 2836, Bound GC traversal memory and spill large queues
  accessed: "2026-09-12"
  version: "merged 2026-09-11T20:01:25Z as commit 0e1b6ec4"
- resource: https://api.github.com/repos/dolthub/doltlite/compare/v0.50.10...0e1b6ec4722d182432d4ba8609945d082796ed1d
  title: Comparison of the v0.50.10 tag with the fix commit
  accessed: "2026-09-12"
  version: "status behind, 0 ahead, 20 behind -- the tag contains the commit"
- resource: https://github.com/dolthub/doltlite/releases/download/v0.50.10/libdoltlite0_0.50.10_amd64.deb
  title: libdoltlite0_0.50.10_amd64.deb
  accessed: "2026-09-12"
  version: "9,277,140 bytes, sha256 09f2e13df763560712769a2d4c08175445f3b11e249a9efd6aa0f25769547582"
- resource: https://github.com/dolthub/doltlite/releases/download/v0.50.10/doltlite_0.50.10_amd64.deb
  title: doltlite_0.50.10_amd64.deb
  accessed: "2026-09-12"
  version: "19,272,068 bytes, sha256 3a832d5580cf8860e9d07a1c3d2dbe1e66d1e83c586913b81bc1f36a5119029e"
stale_after: "2027-03-01"
---

# What was read

* The release record for `v0.50.10`: published `2026-09-11T21:59:59Z`, 19 assets of the same names as v0.50.9's, among them `libdoltlite0_0.50.10_amd64.deb` (9,277,140 bytes) and `doltlite_0.50.10_amd64.deb` (19,272,068 bytes). No checksum file is published; the two `amd64` packages were downloaded on 2026-09-12 and checksummed with `sha256sum` (values in the frontmatter). Nothing in this repository uses them: the pin stays at v0.50.9 ([the DoltLite pin](/decisions/doltlite-version-pin.md)).
* Issue 2820, filed from this repository on 2026-09-11 at 02:25 UTC with the reproduction repository `Reliable-Collaboration/repro-doltlite-bug-vacuum-out-of-memory`, was closed as completed by `timsehn` at 20:01 UTC the same day, one minute after pull request 2836 merged. The pull request's description: garbage collection over a long history of small, scattered updates retained consumed queue entries and enqueued shared chunks repeatedly until it hit the queue allocation ceiling; the queue is now reused as a ring, chunks are deduplicated when scheduled, and large frontiers spill to a buffered temporary file; queue allocations stay within a 64 MiB budget, while visited hashes and chunk indexes still scale with the chunk count, "so this is not a total-process memory limit".
* The comparison of the tag with the fix commit: the commit is 20 commits behind the tag and 0 ahead, so v0.50.10 contains it.
* The release list on 2026-09-12: `v0.50.10` 2026-09-11, `v0.50.9` 2026-09-10, `v0.50.8` 2026-09-09, `v0.50.7` 2026-09-07.

# Relevant excerpt

> Improved garbage collection, version-control correctness, and CI efficiency.
> ## Reliability and correctness
> - Bounded GC traversal memory with disk spillover for large histories; expanded failure and recovery tests.
> - Fixed generated-column merges, orphaned indexes, and multi-table conflict resolution.
> - Preserved column types and collations in historical queries; corrected diff, patch, rebase, and commit behavior.
> - Fixed read-only status queries blocking writers and a `VACUUM INTO` destination race.
> ## Benchmark / SQL workload summary
> ### File-backed
> | Operation | SQLite median total | DoltLite median total | Ratio |
> | Reads | 10.51s | 10.42s | 1.0× |
> | Writes | 3.64s | 4.16s | 1.1× |
> | Autocommit writes | 2.80s | 8.20s | 2.9× |

# What it was used to decide

Whether the DoltLite pin should move to v0.50.10 so that the nine per-row-commit stores recorded `settled: false` can be collected and the three largest databases' per-row-commit loads fit on the disk: the question put to the maintainer on 2026-09-12 in [patch or work around](/decisions/engine-bugs-patch-or-work-around.md). Not decided; the pin stands. Note the pull request's own caveat: the fix bounds the queue, not the whole process, so whether `VACUUM` collects a 150 GB file is to be tried, not assumed.
