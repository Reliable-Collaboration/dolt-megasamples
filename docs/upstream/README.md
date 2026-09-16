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
reports were written (`versions.json` names the current ones, DoltgreSQL 1.3.2 and DoltLite v0.50.10; one version per
result set). DoltgreSQL's eleven fixes merged on 2026-09-16, after v1.3.3, so no release carries them yet. DoltLite's `VACUUM` defect
is fixed upstream in v0.50.10 (2026-09-11), and since 2026-09-12 this repository measures that version, every DoltLite
unit again.

| Draft here | Reproduction repository | Filed as | Upstream, as read on 2026-09-16 |
|---|---|---|---|
| `doltgresql-generated-column-second-alteration.md` | `repro-doltgresql-bug-1` | [doltgresql#3323](https://github.com/dolthub/doltgresql/issues/3323) | fixed: pull request 3347 merged 2026-09-16, issue closed, not yet in a release |
| `doltgresql-bpchar-padding-through-text-cast.md` | `repro-doltgresql-bug-bpchar-padding` | [doltgresql#3325](https://github.com/dolthub/doltgresql/issues/3325) | fixed: pull request 3349 merged 2026-09-16, issue closed, not yet in a release |
| `doltgresql-trigger-when-whole-row-comparison.md` | `repro-doltgresql-bug-trigger-when-whole-row` | [doltgresql#3336](https://github.com/dolthub/doltgresql/issues/3336) | fixed: pull request 3357 merged 2026-09-16, issue closed, not yet in a release |
| `doltgresql-named-not-null-constraint.md` | `repro-doltgresql-bug-named-not-null` | [doltgresql#3332](https://github.com/dolthub/doltgresql/issues/3332) | fixed: pull request 3354 merged 2026-09-16, issue closed, not yet in a release |
| `doltgresql-check-with-regexp-like-refuses-rows.md` | `repro-doltgresql-bug-regexp-like-check` | [doltgresql#3333](https://github.com/dolthub/doltgresql/issues/3333) | fixed: pull request 3355 merged 2026-09-16, issue closed, not yet in a release |
| `doltgresql-database-privileges-not-enforced.md` | `repro-doltgresql-bug-database-privileges` (private) | reported privately by the maintainer to security@dolthub.com, with the self-granted `CREATEDB` beside it | `CREATE`/`DROP DATABASE` enforced in v1.3.2 (pull request 3343); the self-grant remains |
| `doltlite-vacuum-out-of-memory-on-large-history.md` | `repro-doltlite-bug-vacuum-out-of-memory` | [doltlite#2820](https://github.com/dolthub/doltlite/issues/2820) | closed as fixed 2026-09-11 (pull request 2836), released in v0.50.10; the ceiling that remains is [doltlite#2936](https://github.com/dolthub/doltlite/issues/2936), fix in review |

Ten more findings from the loads had no draft here and were reported the same way, each from its own
reproduction repository (`repro-doltgresql-bug-<name>`):

| Finding | Repository name | Filed as | Upstream, as read on 2026-09-16 |
|---|---|---|---|
| brackets dropped from saved expressions (found while investigating #3323) | `brackets` | [#3324](https://github.com/dolthub/doltgresql/issues/3324) | fixed: pull request 3348 merged 2026-09-16, issue closed, not yet in a release |
| `convert_from()` not found | `convert-from` | [#3326](https://github.com/dolthub/doltgresql/issues/3326) | fixed: pull request 3350 merged 2026-09-16, issue closed, not yet in a release |
| a role with SELECT is refused `COUNT(*)` | `function-execute-default` | [#3327](https://github.com/dolthub/doltgresql/issues/3327) | fixed: pull request 3351 merged 2026-09-16, issue closed, not yet in a release |
| `generation_expression` NULL in `information_schema.columns` | `generation-expression` | [#3328](https://github.com/dolthub/doltgresql/issues/3328) | fixed: pull request 3352 merged 2026-09-16, issue closed, not yet in a release |
| GIN indexes refused | `gin-index` | [#3329](https://github.com/dolthub/doltgresql/issues/3329) | open, a feature request |
| `information_schema.triggers` empty | `information-schema-triggers` | [#3330](https://github.com/dolthub/doltgresql/issues/3330) | fixed: pull request 3353 merged 2026-09-16, issue closed, not yet in a release |
| `JSON_TABLE` refused | `json-table` | [#3331](https://github.com/dolthub/doltgresql/issues/3331) | open, a feature request |
| casts to `regnamespace` fail | `regnamespace` | [#3334](https://github.com/dolthub/doltgresql/issues/3334) | fixed: pull request 3356 merged 2026-09-16, issue closed, not yet in a release |
| full-text search functions and `@@` missing | `text-search-operator` | [#3335](https://github.com/dolthub/doltgresql/issues/3335) | open, a feature request |
| `xml` type and `xpath()` missing | `xpath` | [#3337](https://github.com/dolthub/doltgresql/issues/3337) | open, a feature request |
| UPDATE reports the wrong row count | `update-row-count` | comment on existing [#3113](https://github.com/dolthub/doltgresql/issues/3113) | open |
| DoltLite 0.50.10: `VACUUM` still fails at 3.9M commits, three allocations capped at 2 GiB (found by the loads, no repository) | — | [doltlite#2936](https://github.com/dolthub/doltlite/issues/2936) | filed 2026-09-15 |

The reading of the issues and pull requests behind these tables: `knowledge/sources/doltgresql-issues-filed-2026-09-11.md`
and `knowledge/sources/doltlite-release-v0-50-10.md`. Where each defect lives in the source, how large a fix would be,
and what building a patched engine would take: `knowledge/decisions/engine-bugs-patch-or-work-around.md`.
