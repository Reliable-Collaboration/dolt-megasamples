---
type: Decision
title: Pin DoltgreSQL at 1.3.1 by digest, marked so it can be undone
description: Every DoltgreSQL number is measured against one build, named by image digest; the pin is marked in the two places it lives and undoing it is a one-line change plus a rerun.
resource: /decisions/doltgresql-version-pin.md
tags:
- doltgresql
- pin
- decision
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: /sources/doltgresql-release-v1-3-1.md
  title: DoltgreSQL release v1.3.1 and its Docker image
  accessed: "2026-09-10"
stale_after: "2027-03-01"
---

# Question

Which DoltgreSQL should the PostgreSQL pair measure and serve, and how should the choice be recorded so that it can be changed later without losing track of what the numbers belong to?

# Options considered

* **The floating `latest` tag.** Lost: a tag that moves makes the recorded numbers unreproducible, and the instance that stays up could change engine under a reader.
* **The current release, pinned by digest** (`dolthub/doltgresql:1.3.1` = `sha256:6c85cb1f35beabf47f094336a420255130b841b1645f36d79ef046276af36851`, published 2026-09-02, the newest release on 2026-09-10). Chosen.
* **Build from source at a commit.** Lost: nothing in the experiment needs a build the project does not ship, and the image is what a reader would run.

# Evidence

The release and image facts: [release v1.3.1](/sources/doltgresql-release-v1-3-1.md). The behaviour verified against that digest: [DoltgreSQL 1.3.1](/tools/doltgresql-1-3-1.md).

# Outcome

Pinned by digest in two places, each under a banner that says PINNED, why, and how to undo it:

* `scripts/pairs.py`: `DOLTGRES_IMAGE` (overridable with `DOLTSAMPLES_DOLTGRES_IMAGE`), the image every timed load and preflight uses.
* `compose.yaml`: the `doltgres` service that stays up, same digest.

**To undo:** set `DOLTSAMPLES_DOLTGRES_IMAGE` (or edit the default and the compose digest to the new release's), then rerun the DoltgreSQL units (`make run-pg ARGS="--redo --phase doltgres_oneshot ..."`) and the preflight -- the recorded numbers belong to the build that produced them and are not carried across a version change. Log the change as an **Update** to this record with the new digest and date.

# Status

accepted (2026-09-10; user decision: "Pin Doltgres on the current most recent release but mark that clearly so we can undo it later").
