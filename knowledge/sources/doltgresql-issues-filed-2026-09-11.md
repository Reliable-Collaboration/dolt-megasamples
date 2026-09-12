---
type: Source
title: The DoltgreSQL issues filed from this repository on 2026-09-11, and DoltHub's response
description: Fifteen issues on dolthub/doltgresql (3323 to 3337) and one comment on the existing issue 3113, each backed by a public reproduction repository under Reliable-Collaboration that runs the failing SQL side by side with PostgreSQL 18.6; as read on 2026-09-12, all are open and labelled "customer issue", eleven have a fix pull request open, and none is in a release.
resource: https://github.com/dolthub/doltgresql/issues?q=author%3Amattchristenson
tags:
- doltgresql
- issue
- upstream
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-12T21:20:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-12T21:20:00Z"
sources:
- resource: https://api.github.com/repos/dolthub/doltgresql/issues?creator=mattchristenson&state=all
  title: The issues on dolthub/doltgresql created by the maintainer's account
  accessed: "2026-09-12"
  version: "15 issues, 3323 to 3337, all open"
- resource: https://api.github.com/repos/dolthub/doltgresql/issues/3113/comments
  title: Comments on issue 3113, UPDATE metadata semantics incorrect
  accessed: "2026-09-12"
- resource: https://api.github.com/repos/dolthub/doltgresql/pulls/3341
  title: Pull request 3341, Fixes many issues (closed unmerged; split into one pull request per issue)
  accessed: "2026-09-12"
- resource: https://github.com/dolthub/doltgresql/pulls?q=author%3AHydrocharged+%22Fixed+Issue%22
  title: Pull requests 3347 to 3357, "Fixed Issue #NNNN", one per reported issue
  accessed: "2026-09-12"
  version: "all opened 2026-09-11T22:55Z to 23:04Z, all open, none merged"
- resource: https://api.github.com/repos/dolthub/doltgresql/releases/tags/v1.3.2
  title: Release v1.3.2 of dolthub/doltgresql
  accessed: "2026-09-12"
  version: "published 2026-09-12T00:07:06Z; its notes list Dolt and go-mysql-server merges, none of the pull requests above"
stale_after: "2026-12-01"
---

# What was read

The issues, in the order filed on 2026-09-11 (times UTC), the reproduction repository behind each (all `https://github.com/Reliable-Collaboration/<name>`, public, each README the bug report with a `repro.sh` that exits 1 while DoltgreSQL's output differs from PostgreSQL 18.6's), and what DoltHub had done by 2026-09-12 21:00 UTC:

| Issue | Filed | Title | Repository | DoltHub |
|---|---|---|---|---|
| 3323 | 00:36 | Generated column with COALESCE: every INSERT fails after ALTER TABLE ADD PRIMARY KEY | repro-doltgresql-bug-1 | assigned to Hydrocharged; pull request 3347 open |
| 3324 | 01:23 | Brackets are dropped from saved expressions: generated columns, defaults and CHECK constraints compute wrong results | repro-doltgresql-bug-brackets | assigned; pull request 3348 open |
| 3325 | 02:07 | Casting a character(n) value to text keeps its trailing spaces, so comparisons and CHECK constraints fail | repro-doltgresql-bug-bpchar-padding | assigned; pull request 3349 open |
| 3326 | 02:20 | `convert_from()` is not found | repro-doltgresql-bug-convert-from | assigned; pull request 3350 open |
| 3327 | 02:20 | A role with SELECT on a table is refused COUNT(*) on it: "permission denied for routine count" | repro-doltgresql-bug-function-execute-default | assigned; pull request 3351 open |
| 3328 | 02:21 | `generation_expression` in `information_schema.columns` is NULL for a generated column | repro-doltgresql-bug-generation-expression | assigned; pull request 3352 open |
| 3329 | 02:21 | GIN indexes are refused with "index method gin is not yet supported" | repro-doltgresql-bug-gin-index | unassigned; no pull request |
| 3330 | 02:21 | `information_schema.triggers` is empty while the trigger exists and fires | repro-doltgresql-bug-information-schema-triggers | assigned; pull request 3353 open |
| 3331 | 02:22 | `JSON_TABLE` is refused with a syntax error at `COLUMNS` | repro-doltgresql-bug-json-table | unassigned; no pull request |
| 3332 | 02:22 | A named NOT NULL column constraint refuses the whole table | repro-doltgresql-bug-named-not-null | assigned; pull request 3354 open |
| 3333 | 02:23 | A CHECK constraint that calls regexp_like with a cast argument refuses every row | repro-doltgresql-bug-regexp-like-check | assigned; pull request 3355 open |
| 3334 | 02:23 | Casts to regnamespace fail with "unable to resolve type" | repro-doltgresql-bug-regnamespace | assigned; pull request 3356 open |
| 3335 | 02:23 | Full-text search fails: `to_tsvector` and `to_tsquery` are not found, and `@@` is not yet supported | repro-doltgresql-bug-text-search-operator | unassigned; no pull request |
| 3336 | 02:24 | A trigger with `WHEN (old.* IS DISTINCT FROM new.*)` makes every UPDATE of its table fail | repro-doltgresql-bug-trigger-when-whole-row | assigned; pull request 3357 open |
| 3337 | 02:24 | The `xml` type does not exist, and `xpath()` is not found | repro-doltgresql-bug-xpath | unassigned; no pull request |
| 3113 (existing) | 02:25, comment | UPDATE metadata semantics incorrect | repro-doltgresql-bug-update-row-count | open, one comment (ours) |

Every issue carries the label `customer issue`. Pull request 3341, "Fixes many issues", was opened and closed unmerged on 2026-09-11 in favour of one pull request per issue; the eleven that replaced it were opened between 22:55 and 23:04 UTC and were all open and unmerged when read. The four without a pull request are the four that ask for a feature (GIN indexes, `JSON_TABLE`, full-text search, `xml`). DoltgreSQL v1.3.2, published 2026-09-12 00:07 UTC, predates all eleven; its notes list Dolt and go-mysql-server merges only.

Not filed: the database-privilege gap ([DoltgreSQL 1.3.1](/tools/doltgresql-1-3-1.md), limit "Database privileges are not enforced"). Its reproduction repository, `repro-doltgresql-bug-database-privileges`, is private; DoltgreSQL's `SECURITY.md` asks for security reports by email to security@dolthub.com, and whether to send one is the maintainer's call, pending on 2026-09-12.

# Relevant excerpt

Our comment on issue 3113, 2026-09-11 02:25 UTC:

> A runnable reproduction of this bug on DoltgreSQL 1.3.1, side by side with PostgreSQL 18.6, is at https://github.com/Reliable-Collaboration/repro-doltgresql-bug-update-row-count

# What it was used to decide

The outcome of [patch or work around](/decisions/engine-bugs-patch-or-work-around.md): the defects are reported, not patched here, and the pins stand until the fixes reach a release and the maintainer asks. The `docs/upstream/` index links each draft to its filing.
