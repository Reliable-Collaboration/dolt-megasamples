---
type: Source
title: DoltgreSQL release v1.3.2, the version of the second result set
description: The release published 2026-09-12 that the DoltgreSQL pair was measured on from 2026-09-14, named by image digest; what its notes list for doltgresql itself (among them the authorization check on CREATE and DROP DATABASE), and the releases and merges around it -- v1.3.3 on 2026-09-15 without the fixes for this repository's reports, which merged on 2026-09-16.
resource: https://github.com/dolthub/doltgresql/releases/tag/v1.3.2
tags:
- doltgresql
- release
- version
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-16T12:00:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-16T12:00:00Z"
sources:
- resource: https://api.github.com/repos/dolthub/doltgresql/releases/tags/v1.3.2
  title: Release v1.3.2 of dolthub/doltgresql
  accessed: "2026-09-16"
  version: "v1.3.2, published 2026-09-12T00:07:06Z"
- resource: https://api.github.com/repos/dolthub/doltgresql/releases
  title: Release list of dolthub/doltgresql (first three)
  accessed: "2026-09-16"
  version: "v1.3.3 2026-09-15T22:07:36Z, v1.3.2 2026-09-12, v1.3.1 2026-09-02"
- resource: https://hub.docker.com/r/dolthub/doltgresql
  title: The image dolthub/doltgresql:1.3.2, pulled 2026-09-14 and resolved to its repository digest by scripts/versions.py
  accessed: "2026-09-14"
  version: "sha256:267aff12f01c63f2f0fe54541edf788e58b10ffd907935d1189049b03985b2ae"
- resource: https://github.com/dolthub/doltgresql/pull/3343
  title: Pull request 3343, Enforce authorization for CREATE DATABASE and DROP DATABASE, in v1.3.2
  accessed: "2026-09-16"
- resource: https://github.com/dolthub/doltgresql/pulls?q=is%3Apr+author%3AHydrocharged+%22Fixed+Issue%22
  title: Pull requests 3347 to 3357, one per issue this repository filed
  accessed: "2026-09-16"
  version: "all eleven merged between 2026-09-16T09:02Z and 10:22Z, after v1.3.3"
stale_after: "2026-12-01"
---

# What was read

* The release record for `v1.3.2`: published `2026-09-12T00:07:06Z`. `scripts/versions.py --latest doltgres` pulled `dolthub/doltgresql:1.3.2` on 2026-09-14 and recorded its repository digest `sha256:267aff12…` in `versions.json`; the DoltgreSQL pair was measured on that digest from 2026-09-14 02:40 UTC to 2026-09-16 11:10 UTC.
* Its notes are mostly Dolt and go-mysql-server merges; the `## doltgresql` section lists pull request 3343, "Enforce authorization for CREATE DATABASE and DROP DATABASE", 3342, "Support Dolt virtual ref indexes in the catalog", 3340 and 3320. The first is the fix for the database-privilege gap this repository found on 1.3.1 and reported privately; [DoltgreSQL 1.3.2](/tools/doltgresql-1-3-2.md) records it verified by probe.
* The release list on 2026-09-16: `v1.3.3` was published 2026-09-15T22:07:36Z. The eleven pull requests that fix the issues this repository filed (3323 to 3336, less the four feature requests) merged on 2026-09-16 between 09:02 and 10:22 UTC, after v1.3.3, so neither 1.3.2 nor 1.3.3 carries them; the issues are closed. Issues 3329, 3331, 3335 and 3337 -- GIN indexes, `JSON_TABLE`, full-text search, `xml` -- stay open.

# Relevant excerpt

> ## doltgresql
> * [3343](https://github.com/dolthub/doltgresql/pull/3343): Enforce authorization for CREATE DATABASE and DROP DATABASE
> * [3342](https://github.com/dolthub/doltgresql/pull/3342): Support Dolt virtual ref indexes in the catalog
> * [3340](https://github.com/dolthub/doltgresql/pull/3340): Added regression test for issue 3083
> * [3320](https://github.com/dolthub/doltgresql/pull/3320): Limit test server logging to warnings and errors

# What it was used to decide

Which version the second DoltgreSQL result set belongs to, under [one version per result set](/decisions/engine-versions-one-per-result-set.md): the newest release at the moment every DoltLite unit was done, as the maintainer asked. Whether to move again -- to v1.3.3, which changes nothing this repository waits on, or to the release after it, which will carry the eleven fixes -- is the maintainer's call and costs a full DoltgreSQL rerun, about 39 hours of loads.
