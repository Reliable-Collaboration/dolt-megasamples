---
type: Source
title: DoltLite release v0.50.9 and its packages
description: The release current on 2026-09-10, its assets, the checksums of the two Debian packages the experiment builds its image from, and the release cadence around it.
resource: https://github.com/dolthub/doltlite/releases/tag/v0.50.9
tags:
- doltlite
- release
- pin
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: https://api.github.com/repos/dolthub/doltlite/releases/tags/v0.50.9
  title: Release v0.50.9 of dolthub/doltlite
  accessed: "2026-09-10"
  version: "v0.50.9, published 2026-09-10T02:28:54Z"
- resource: https://api.github.com/repos/dolthub/doltlite/releases
  title: Release list of dolthub/doltlite (first eight)
  accessed: "2026-09-10"
- resource: https://github.com/dolthub/doltlite/releases/download/v0.50.9/libdoltlite0_0.50.9_amd64.deb
  title: libdoltlite0_0.50.9_amd64.deb
  accessed: "2026-09-10"
  version: "9,235,920 bytes, sha256 bc1c936a7f0975af2182c24d98d20da45e04d4ac101df5f892923928aee1a7eb"
- resource: https://github.com/dolthub/doltlite/releases/download/v0.50.9/doltlite_0.50.9_amd64.deb
  title: doltlite_0.50.9_amd64.deb
  accessed: "2026-09-10"
  version: "19,186,192 bytes, sha256 cf387247a87166f51df73a832b4d93df4162552cb21f3df66bcb44494751e1a5"
stale_after: "2027-03-01"
---

# What was read

* The release record for `v0.50.9`: published `2026-09-10T02:28:54Z`, 19 assets: `doltlite-0.50.9.xcframework.zip` (15,365,071 bytes), `doltlite-amalgamation-0.50.9.zip` (4,585,237), `doltlite-autoconf-0.50.9.tar.gz` (38,553,005), `doltlite-lib-linux-arm64-0.50.9.zip` (28,558,353), `doltlite-lib-linux-x64-0.50.9.zip` (30,630,602), `doltlite-lib-osx-arm64-0.50.9.zip` (11,380,796), `doltlite-lib-win-x64-0.50.9.zip` (9,329,132), `doltlite-tools-linux-arm64-0.50.9.zip` (3,708,579), `doltlite-tools-linux-x64-0.50.9.zip` (3,834,830), `doltlite-tools-osx-arm64-0.50.9.zip` (3,387,556), `doltlite-tools-win-x64-0.50.9.zip` (1,963,511), `doltlite-wasm-0.50.9.zip` (1,453,673), `doltlite_0.50.9_amd64.deb` (19,186,192), `doltlite_0.50.9_arm64.deb` (17,832,182), `install.sh` (4,838), `libdoltlite-dev_0.50.9_amd64.deb` (12,849,758), `libdoltlite-dev_0.50.9_arm64.deb` (12,110,362), `libdoltlite0_0.50.9_amd64.deb` (9,235,920), `libdoltlite0_0.50.9_arm64.deb` (8,560,436). No container image is among them and none is published on Docker Hub under the project's name (searched 2026-09-10).
* The two `amd64` Debian packages were downloaded on 2026-09-10 and checksummed with `sha256sum`; the values are in the frontmatter and in `scripts/pairs.py`, where `scripts/lite_image.py` verifies them before building.
* The release list: `v0.50.9` 2026-09-10, `v0.50.8` 2026-09-09, `v0.50.7` 2026-09-07, `v0.50.6` 2026-09-05, `v0.50.5` 2026-09-04, `v0.50.4` 2026-09-03, `v0.50.3` 2026-09-03, `v0.50.2` 2026-09-01 -- eight releases in ten days.

# Relevant excerpt

> Improved reliability, documentation, and automated validation.
> ### Reliability
> - Fixed a use-after-free in `VACUUM INTO`.
> ### Testing and documentation
> - Source now includes extensive documentation.
> - Added runnable validation for documentation examples, error messages, contracts, and the default `AGENT.md`.
> - Expanded ASan/UBSan coverage to all eligible shell suites while consolidating CI jobs.
> ## Benchmark / SQL workload summary
> ### File-backed
> | Operation | SQLite median total | DoltLite median total | Ratio |
> | Reads | 12.04s | 11.94s | 1.0× |
> | Writes | 3.17s | 4.04s | 1.3× |
> | Autocommit writes | 837.40ms | 3.07s | 3.7× |
> _Full nightly results: performance-report.md_

# What it was used to decide

* Which release to pin and that a pin is needed at all (near-daily releases): [DoltLite v0.50.9](/tools/doltlite-0-50-9.md), [pair load shapes](/decisions/pair-load-shapes-and-measurement.md).
* That the image has to be built here, from the `.deb` packages: `docker/doltlite/Dockerfile` and `scripts/lite_image.py`.
* The project's own autocommit-write ratio (3.7×) is the number the `sqlite_rowwise` / `doltlite_rowinsert` shapes will be compared with.
