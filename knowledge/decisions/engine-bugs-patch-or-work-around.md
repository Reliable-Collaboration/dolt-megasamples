---
type: Decision
title: Patch the pinned engines' defects, or keep working around them
description: Seven defects found in DoltgreSQL 1.3.1 and DoltLite v0.50.9 -- where each lives in the source, how large a fix would be, that none is fixed after the pinned releases, and what building a patched engine would take; the choice is the maintainer's and is still open.
resource: /decisions/engine-bugs-patch-or-work-around.md
tags:
- doltgresql
- doltlite
- pin
- decision
status: draft
trust: open
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T23:21:13Z"
sources:
- resource: https://github.com/dolthub/doltgresql/tree/v1.3.1
  title: DoltgreSQL source at the pinned tag v1.3.1
  accessed: "2026-09-10"
- resource: https://github.com/dolthub/doltgresql/tree/b7a87dad
  title: DoltgreSQL default branch at b7a87dad, 73 commits after v1.3.1
  accessed: "2026-09-10"
- resource: https://github.com/dolthub/go-mysql-server/tree/da4d8ec7
  title: go-mysql-server at da4d8ec7, the commit DoltgreSQL v1.3.1 builds with
  accessed: "2026-09-10"
- resource: https://github.com/dolthub/doltlite/tree/v0.50.9
  title: DoltLite source at the pinned tag v0.50.9
  accessed: "2026-09-10"
- resource: https://github.com/dolthub/doltlite/tree/0d2ccaef
  title: DoltLite default branch at 0d2ccaef, 44 commits after v0.50.9
  accessed: "2026-09-10"
- resource: https://github.com/dolthub/doltgresql/issues/810
  title: DoltgreSQL issue 810, generated default value column gets backticked when stored, open since 2024-10-03
  accessed: "2026-09-10"
- resource: https://github.com/dolthub/doltlite/pull/1736
  title: DoltLite pull request 1736, guard GC mark queue growth against integer overflow, merged 2026-07-22
  accessed: "2026-09-10"
- resource: /decisions/pair-dialect-rules.md
  title: The dialect rules that work around defects 1 to 5
- resource: /decisions/doltgresql-version-pin.md
  title: The DoltgreSQL pin
- resource: /decisions/doltlite-version-pin.md
  title: The DoltLite pin
---

# Question

Loading the sample databases found seven defects in the pinned engines; `docs/upstream/` holds an unfiled report for each. Can they be fixed here -- by patching the engines' source and building them -- rather than worked around as now, and should they be? The maintainer asked on 2026-09-10: "Are we able to just fix them?"

# Options considered

* **Keep working around them**, as now. Defects 1 to 5 are rewritten away by [the dialect rules](/decisions/pair-dialect-rules.md), identically for both engines of the pair (rule G4 costs two adventureworks_lt tables their secondary indexes and foreign keys, on both sides); DoltLite's files that defect 7 leaves uncollected are reported with their footprint, marked, and left out of the totals; defect 6 is stated on the landing page. The numbers describe the released, pinned engines.
* **Patch the engines and build them here.** Every fix below is small to moderate, except owner-only `DROP DATABASE`. But the engine measured and served would no longer be the pinned release: the pins would be replaced by builds of our own (which [the DoltgreSQL pin](/decisions/doltgresql-version-pin.md) and [the DoltLite pin](/decisions/doltlite-version-pin.md) allow only on the maintainer's explicit request), every affected unit would be measured again, and the patches would have to be carried onto later releases.
* **Offer the fixes to DoltHub as pull requests.** They would reach a later release, which this repository uses only if the maintainer lifts a pin. Outward-facing, so the maintainer's call.
* **File the drafted reports only.** The same, with DoltHub writing the fixes.

# Evidence

Read on 2026-09-10 in the source at the pinned tags and on both default branches, by a research pass whose excerpts were then checked here. **Read** means the code or the issue was read; **inferred** means reasoned from it. Nothing was patched, built or run.

| # | Defect | Where it lives at the pinned tag | Fix size | Fixed after the pin? |
|---|---|---|---|---|
| 1 | a table with a STORED generated column refuses rows after its second alteration | doltgresql `server/expression/coalesce.go:162-168`, fed by `server/ast/select.go:190-194` | a few lines narrowly, tens generally | no; issue 810, open since 2024-10-03, is the same family |
| 2 | `character(n)` keeps its padding through a cast to text | doltgresql `server/cast/char.go:98-104` | a few lines | no |
| 3 | a trigger's `WHEN (old.* IS DISTINCT FROM new.*)` refuses every UPDATE | doltgresql `server/plpgsql/statements.go:547`, `server/plpgsql/interpreter_stack.go:212-233` | tens to about a hundred lines (inferred) | no |
| 4 | a named `NOT NULL` column constraint refuses the table | doltgresql `server/ast/column_table_def.go:35-39` | one to three lines | no |
| 5 | a `CHECK` calling `regexp_like` refuses every row | go-mysql-server `sql/expression/function/regexp_like.go:132-138`, `sql/plan/alter_check.go:172` | a few to tens of lines | no |
| 6 | any role can create and drop any database | doltgresql `server/ast/create_database.go:103`, `server/ast/drop_database.go:33`, `server/auth/auth_handler.go:86` | tens of lines for the `CREATEDB` check; owner-only `DROP DATABASE` is a design change | no |
| 7 | DoltLite's `VACUUM` answers "out of memory" on a large history | doltlite `src/doltlite_gc.c:92-140` and `:274-280` | tens of lines in one file | no; an earlier 2 GB limit, in the rewrite step, was lifted by pull request 1633, which v0.50.9 includes |

**Read, and checked against the excerpts here:**

* **4.** `nodeColumnTableDef` refuses a constraint name on `NOT NULL`, `DEFAULT` or `UNIQUE` with "non-foreign key column constraint names are not yet supported", the message the loads got.
* **2.** The implicit cast from `bpchar` to `text` returns the value unchanged; PostgreSQL strips the trailing blanks.
* **6.** `CREATE DATABASE` and `DROP DATABASE` become go-mysql-server `DBDDL` nodes that carry no authorization information, and `HandleAuth` returns without a check when that information is empty, so neither statement is checked against `rolsuper`, `rolcreatedb` or ownership. `CheckDatabase` is an unimplemented stub as well; that go-mysql-server does not call it at this version is the research pass's reading, not checked here.
* **7.** The garbage collector's mark queue doubles its allocation and returns `SQLITE_NOMEM` once the next size would pass 2^31 bytes (the guard of pull request 1736); processed entries are never released, and a chunk already marked is skipped only when it is taken out, not when it is put in. At 72 bytes an entry, the largest queue is 16,777,216 entries, 1,152 MiB -- beside the 1.2 GiB peak measured on chicago_crimes' file ([VACUUM memory](/questions/doltlite-vacuum-memory.md)). The "out of memory" is that guard, not the machine; the marked-chunk hash set and SQLite's 2 GB single-allocation cap are the next limits.

**Inferred** (the research pass's reading, not checked here):

* **1 and 5 are one defect.** doltgresql wraps function arguments in go-mysql-server aliases that print as `x as y`; `CREATE TABLE` strips them, but an expression stored later -- a generated column after an alteration, a check -- is printed with them and cannot be parsed back. doltgresql's own functions skip the alias when printing (`server/functions/framework/compiled_function.go:295-298`); `coalesce` and go-mysql-server's `regexp_like` do not. The errors the loads got agree: defect 1's refused expression reads `... as (a * 1.0) * b::NUMERIC`, and defect 5's fails "at or near "as"". A rework of expression printing that landed upstream on 2026-09-10 still prints `as`.
* **3.** The `WHEN` clause is compiled as a PL/pgSQL `RETURN`, and its variable substitution joins `old`, `.` and `*` into one name, then looks for a field called `*` -- the error's `record "old" has no field "*"`.

**Building a patched engine** (the build files read, nothing built):

* **DoltgreSQL.** `go.mod` requires Go 1.26.2. The v1.3.1 Dockerfile builds from a source tree with `--build-arg DOLTGRES_VERSION=source`: it regenerates the parser and runs `scripts/build_binaries.sh`, which downloads a cross-compiler and a static ICU library from DoltHub's storage. Its build stage, `golang:1.25-trixie`, would have to move to Go 1.26 (inferred). A patch to go-mysql-server needs a copy of that library in the build context and a `replace` line. About 10 to 20 minutes a build (inferred). This host has no Go or C compiler, so the build runs in Docker.
* **DoltLite.** `configure`, `make doltlite doltlite-remotesrv doltlite-lib` (build-essential and zlib), and nfpm packaging from `packaging/nfpm/`; upstream's linux-x64 build job takes about a minute and a half.

# Outcome

None yet. The dialect rules and the marking of uncollected stores stay as they are, and nothing is patched, built or filed, until the maintainer chooses.

# Status

pending: the maintainer's decision, asked on 2026-09-10.
