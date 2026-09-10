---
type: Decision
title: DoltgreSQL and DoltLite instances that stay up beside Dolt
description: How the loaded databases are served after the experiment -- a DoltgreSQL server on 5433 with the two accounts, the DoltLite files with their shell, the consoles that can open them, and a landing page that says how to connect.
resource: /decisions/stood-up-instances.md
tags:
- stack
- decision
- pending
status: draft
trust: open
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: /tools/doltgresql-1-3-1.md
  title: DoltgreSQL 1.3.1
  accessed: "2026-09-10"
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9
  accessed: "2026-09-10"
---

# Question

`make up` leaves Dolt and its consoles running on ports one range above sql-megasamples. What is the same for DoltgreSQL and DoltLite: which data, which accounts, which consoles can open each, and what the landing page must say for a tool of one's own?

# Options considered

* **DoltgreSQL served from the one-shot load's data directory** (`data/doltgres-oneshot`, every database a repository with one commit), port 5433, the `demo` (read) and `admin` (all) accounts created by an init step with `psql`; consoles get a PostgreSQL connection per account. To be verified: which of Adminer, DbGate, CloudBeaver and Dolt Workbench open it, by a `test-console` step, before any is listed.
* **DoltLite served as files** in a container that holds the `doltlite` shell (`data/doltlite-oneshot/<db>.doltlite`), since no web console reads a DoltLite file (it is not SQLite pages) and there is no server; the landing page gives the `docker exec` command and the `docker cp` path.
* **A DoltLite remote server** (`doltlite-remotesrv`) for sync. Deferred: nothing in the plan needs it.

# Evidence

Pending: the console tests have not run. The engine facts they rest on: [DoltgreSQL 1.3.1](/tools/doltgresql-1-3-1.md) (the trigger bodies that fail at run time matter here: an `UPDATE` on a ported table with an `ON UPDATE` trigger is refused), [DoltLite v0.50.9](/tools/doltlite-0-50-9.md).

# Outcome

Pending; `PLAN.md` phase 3 describes the intended shape.

# Status

pending (2026-09-10).
