---
type: Decision
title: Pin DoltLite at v0.50.9 until the maintainer asks otherwise
description: Every DoltLite number is measured with DoltLite v0.50.9 from its checksummed release packages; newer releases are not taken up unless the maintainer explicitly asks for the pin to be removed, and every document marks the version as pinned.
resource: /decisions/doltlite-version-pin.md
tags:
- doltlite
- pin
- decision
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T22:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T22:45:00Z"
sources:
- resource: /sources/doltlite-release-v0-50-9.md
  title: DoltLite release v0.50.9 and its packages
  accessed: "2026-09-10"
- resource: https://api.github.com/repos/dolthub/doltlite/releases
  title: Release list of dolthub/doltlite, newest first
  accessed: "2026-09-10"
  version: "v0.50.9 still the newest release at 22:25 UTC"
stale_after: "2027-03-01"
---

# Question

DoltLite is a beta that DoltHub releases almost daily. Which DoltLite should the experiment measure and the stack serve, and what happens when a newer release appears while the measurements are still running or after they are published?

# Options considered

* **Follow the newest release.** Lost: numbers taken over several days would mix versions, nobody could reproduce a figure without knowing which release produced it, and a newer release would trigger another round of measurements before any could be published.
* **Measure again on the newest release before publishing.** Lost as a default: roughly half of the SQLite/DoltLite machine time again, the dialect rules re-checked, and another release likely in the meantime. It stays available as an explicit later run.
* **Pin one release and keep it until the maintainer explicitly asks to remove the pin.** Chosen.

# Evidence

DoltLite published eight releases between 2026-09-01 and 2026-09-10 (v0.50.2 to v0.50.9, [the release record](/sources/doltlite-release-v0-50-9.md)); v0.50.9 was still the newest release when the maintainer decided, at 22:25 UTC on 2026-09-10. The maintainer's words, on 2026-09-10: "Stick with the pinned version unless explicitely asked to remove the pin. Clearly mark that it is pinned in any documentation so that it's clear."

# Outcome

* DoltLite v0.50.9 is pinned by the SHA-256 of its two Debian packages (`libdoltlite0_0.50.9_amd64.deb`, `doltlite_0.50.9_amd64.deb`), recorded in `scripts/pairs.py`, verified by `scripts/lite_image.py` before `docker/doltlite/Dockerfile` builds the image `doltsamples-doltlite:0.50.9` over `debian:13-slim` pinned by digest.
* The pin is not removed on account of a newer release. It is removed only when the maintainer explicitly asks, and then the version, the package URLs, both checksums, the Dockerfile's package names and the image tag in `compose.yaml` change together, and every DoltLite unit is measured again.
* Every document marks the version as pinned: the README's *Pinned versions* table (generated from the pins, with the other engines' pins beside it), the README and journal prose, the report's environment table, the landing page, the issue drafts in `docs/upstream/`, and the PINNED banners in `scripts/pairs.py`, `compose.yaml` and the Dockerfile. [The DoltgreSQL pin](/decisions/doltgresql-version-pin.md) follows the same rule.

# Status

accepted (2026-09-10; the maintainer's decision).
