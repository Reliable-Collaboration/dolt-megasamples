# Upstream bug reports

Findings about DoltgreSQL 1.3.1 and DoltLite v0.50.9 that reproduce with one-table probes, written
up here as issue drafts on 2026-09-10 and, on the maintainer's decision, **filed on 2026-09-11** --
each with a public reproduction repository under `Reliable-Collaboration` whose README is the bug
report and whose `repro.sh` runs the failing SQL side by side with PostgreSQL 18.6 or SQLite 3.46.1
in throwaway containers. One stays unfiled: the database-privilege gap is a security matter, its
repository is private, and reporting it to security@dolthub.com waits for the maintainer's word.
Each draft names the record in `knowledge/` that carries the full evidence and says where it was
filed. Versions and dates are those of the probes (2026-09-10).

All of them were found on DoltgreSQL 1.3.1 and DoltLite v0.50.9, the versions this repository measured when the
reports were written (`versions.json` names the current ones; one version per result set). DoltLite's `VACUUM` defect
is fixed upstream in v0.50.10 (2026-09-11), and since 2026-09-12 this repository measures that version, every DoltLite
unit again.

| Draft here | Reproduction repository | Filed as | Upstream, as read on 2026-09-12 |
|---|---|---|---|
| `doltgresql-generated-column-second-alteration.md` | `repro-doltgresql-bug-1` | [doltgresql#3323](https://github.com/dolthub/doltgresql/issues/3323) | fix pull request 3347 open |
| `doltgresql-bpchar-padding-through-text-cast.md` | `repro-doltgresql-bug-bpchar-padding` | [doltgresql#3325](https://github.com/dolthub/doltgresql/issues/3325) | fix pull request 3349 open |
| `doltgresql-trigger-when-whole-row-comparison.md` | `repro-doltgresql-bug-trigger-when-whole-row` | [doltgresql#3336](https://github.com/dolthub/doltgresql/issues/3336) | fix pull request 3357 open |
| `doltgresql-named-not-null-constraint.md` | `repro-doltgresql-bug-named-not-null` | [doltgresql#3332](https://github.com/dolthub/doltgresql/issues/3332) | fix pull request 3354 open |
| `doltgresql-check-with-regexp-like-refuses-rows.md` | `repro-doltgresql-bug-regexp-like-check` | [doltgresql#3333](https://github.com/dolthub/doltgresql/issues/3333) | fix pull request 3355 open |
| `doltgresql-database-privileges-not-enforced.md` | `repro-doltgresql-bug-database-privileges` (private) | reported privately by the maintainer to security@dolthub.com, with the self-granted `CREATEDB` beside it | not public |
| `doltlite-vacuum-out-of-memory-on-large-history.md` | `repro-doltlite-bug-vacuum-out-of-memory` | [doltlite#2820](https://github.com/dolthub/doltlite/issues/2820) | closed as fixed 2026-09-11 (pull request 2836), released in v0.50.10 |

Ten more findings from the loads had no draft here and were reported the same way, each from its own
reproduction repository (`repro-doltgresql-bug-<name>`):

| Finding | Repository name | Filed as | Upstream, as read on 2026-09-12 |
|---|---|---|---|
| brackets dropped from saved expressions (found while investigating #3323) | `brackets` | [#3324](https://github.com/dolthub/doltgresql/issues/3324) | fix pull request 3348 open |
| `convert_from()` not found | `convert-from` | [#3326](https://github.com/dolthub/doltgresql/issues/3326) | fix pull request 3350 open |
| a role with SELECT is refused `COUNT(*)` | `function-execute-default` | [#3327](https://github.com/dolthub/doltgresql/issues/3327) | fix pull request 3351 open |
| `generation_expression` NULL in `information_schema.columns` | `generation-expression` | [#3328](https://github.com/dolthub/doltgresql/issues/3328) | fix pull request 3352 open |
| GIN indexes refused | `gin-index` | [#3329](https://github.com/dolthub/doltgresql/issues/3329) | open, no pull request |
| `information_schema.triggers` empty | `information-schema-triggers` | [#3330](https://github.com/dolthub/doltgresql/issues/3330) | fix pull request 3353 open |
| `JSON_TABLE` refused | `json-table` | [#3331](https://github.com/dolthub/doltgresql/issues/3331) | open, no pull request |
| casts to `regnamespace` fail | `regnamespace` | [#3334](https://github.com/dolthub/doltgresql/issues/3334) | fix pull request 3356 open |
| full-text search functions and `@@` missing | `text-search-operator` | [#3335](https://github.com/dolthub/doltgresql/issues/3335) | open, no pull request |
| `xml` type and `xpath()` missing | `xpath` | [#3337](https://github.com/dolthub/doltgresql/issues/3337) | open, no pull request |
| UPDATE reports the wrong row count | `update-row-count` | comment on existing [#3113](https://github.com/dolthub/doltgresql/issues/3113) | open |

The reading of the issues and pull requests behind these tables: `knowledge/sources/doltgresql-issues-filed-2026-09-11.md`
and `knowledge/sources/doltlite-release-v0-50-10.md`. Where each defect lives in the source, how large a fix would be,
and what building a patched engine would take: `knowledge/decisions/engine-bugs-patch-or-work-around.md`.
