---
type: Source
title: DoltgreSQL release v1.3.1 and its Docker image
description: The release current on 2026-09-10, its publication date, and the digest of the Docker Hub image the experiment pins.
resource: https://github.com/dolthub/doltgresql/releases/tag/v1.3.1
tags:
- doltgresql
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
- resource: https://api.github.com/repos/dolthub/doltgresql/releases/tags/v1.3.1
  title: Release v1.3.1 of dolthub/doltgresql
  accessed: "2026-09-10"
  version: "v1.3.1, published 2026-09-02T23:22:02Z"
- resource: https://api.github.com/repos/dolthub/doltgresql/releases/latest
  title: Latest release of dolthub/doltgresql
  accessed: "2026-09-10"
  version: "v1.3.1 on 2026-09-10"
- resource: https://hub.docker.com/r/dolthub/doltgresql
  title: dolthub/doltgresql on Docker Hub, tag 1.3.1 (pulled, then inspected locally)
  accessed: "2026-09-10"
  version: "sha256:6c85cb1f35beabf47f094336a420255130b841b1645f36d79ef046276af36851"
stale_after: "2027-03-01"
---

# What was read

* The release record for tag `v1.3.1` (`gh api repos/dolthub/doltgresql/releases/tags/v1.3.1`): published `2026-09-02T23:22:02Z`; its body is the list of merged pull requests of the Dolt and DoltgreSQL repositories that went into it.
* `releases/latest` on 2026-09-10 answered `v1.3.1`, so this was the current release when the pin was taken.
* The Docker image: `docker pull dolthub/doltgresql:1.3.1` on 2026-09-10 resolved to digest `sha256:6c85cb1f35beabf47f094336a420255130b841b1645f36d79ef046276af36851`; `docker image inspect` reports it created `2026-09-02T23:26:27Z`, 105,464,138 bytes, entrypoint `tini -v -- docker-entrypoint.sh`, volume `/var/lib/doltgres`, port `5432/tcp`. Inside it `/usr/bin/psql` is `psql (PostgreSQL) 17.11 (Debian 17.11-0+deb13u1)`.

# Relevant excerpt

The release body begins:

> # Merged PRs
> ## dolt
> * 11665: go: sqle/resolve: Have SearchPath() parse the search path in a way which is more compliant with postgres. Correctly handle quoted identifiers and ToLower any unquoted ones.
> * 11663: Add Doltgres transaction lifecycle callback [...]

# What it was used to decide

* The pin and its undo path: [DoltgreSQL version pin](/decisions/doltgresql-version-pin.md). The digest above is the one `scripts/pairs.py` and the `doltgres` service in `compose.yaml` name.
* That the server's own `psql` (17.11) can load the dumps `pg_dump` 18.6 writes, `\restrict` lines included: [DoltgreSQL 1.3.1](/tools/doltgresql-1-3-1.md).
