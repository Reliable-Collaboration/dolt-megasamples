---
type: Tool
title: PostgreSQL 18.6 as the baseline of the PostgreSQL pair
description: The image, data-directory layout, dump tool and client used for the PostgreSQL side of the pair, and how its size and readiness are read.
resource: https://hub.docker.com/_/postgres
tags:
- engine
- postgresql
- baseline
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: https://hub.docker.com/_/postgres
  title: postgres official image, tag 18.6-bookworm (present locally as sql-megasamples' base; inspected)
  accessed: "2026-09-10"
  version: "sha256:1c59e2c3c818eaa0f0628f695b36e7c9e362d6b219b36a54a32df645cbd7e1af, created 2026-08-25"
stale_after: "2027-03-01"
---

# Facts

* **Image.** `postgres:18.6-bookworm`, digest `sha256:1c59e2c3c818eaa0f0628f695b36e7c9e362d6b219b36a54a32df645cbd7e1af` (created 2026-08-25), the base of `sql-megasamples-postgres:dev`; pinned by digest in `scripts/pairs.py`. `PGDATA` is `/var/lib/postgresql/18/docker` and the declared volume is `/var/lib/postgresql` (the 18 image moved the data directory one level down). `awk`, `du`, `sleep` are present for the measurements; `psql` 18.6 is the client the baseline loads use, executed inside the server's own container.
* **Source of the dumps.** `pg_dump` 18.6 from the running `megasamples-postgres` (sql-megasamples release 2) with `--no-owner --no-privileges --encoding=UTF8`, three forms per database: the default COPY form, `--inserts` (one `INSERT` per row) and `--schema-only`. The output is one block per object under a `-- Name: ...; Type: ...; Schema: ...; Owner: -` header (`-- Data for Name:` for data), which `scripts/doltgres_dialect.py` works on; pg_dump 18 opens the file with `\restrict <token>` and closes it with `\unrestrict`, which psql 17.11 and 18.6 both accept.
* **Readiness.** Two consecutive answers to `SELECT 1` over TCP a second apart: the image's entrypoint restarts the server once after initialising, so a single success can land before the restart.
* **Size.** `du -sb` of `PGDATA` minus `PGDATA/pg_wal`, against the same reading of the empty server (the baseline), after `CHECKPOINT`; `pg_database_size()` is recorded beside it. The write-ahead log is excluded because it is recycled at a fixed size and belongs to no database; MySQL's redo log sat inside the empty-server baseline of the MySQL/Dolt pair for the same reason.
* **A shell loop inside the container is a bad idea.** The first memory sampler ran a `sh` loop inside the container, as `run_all.py` does for Dolt; when it was killed the postmaster -- its parent, since the loop was reparented to PID 1 -- treated the death as a crashed backend and put the server into recovery ("the database system is in recovery mode"). Memory is now sampled from the host's cgroup files (`/sys/fs/cgroup/docker/<id>/memory.stat`), with no process inside any worker.

# Limits

* Loads run with `ON_ERROR_STOP=0`, so a refusal is reported with its line and the rest of the file still loads; the row and index checks decide whether the load counts. PostgreSQL itself refused nothing in the quick subset's preflight.
* Foreign keys and triggers are added after the rows in both index policies (pg_dump's order), see [load shapes](/decisions/pair-load-shapes-and-measurement.md).
