---
type: Runbook
title: Knowledge bundle conventions
description: How every record in this OKF v0.2 bundle is written, typed, trusted, sectioned, indexed and logged; the checker in scripts/okf_check.py enforces the rules marked [checked].
resource: /runbooks/knowledge-bundle-conventions.md
tags:
- okf
- conventions
- process
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: https://github.com/Reliable-Collaboration/sql-megasamples/blob/5aedb80/knowledge/runbooks/knowledge-bundle-conventions.md
  title: sql-megasamples, knowledge bundle conventions (revision 2)
  accessed: "2026-09-10"
  version: "commit 5aedb80, read from the local clone"
---

# Purpose

This bundle conforms to **OKF v0.2** the way the sql-megasamples bundle does; this runbook is that bundle's conventions record, adapted to this repository, and `scripts/okf_check.py` and `scripts/okf_fix_quotes.py` are copies of its checker and canonicaliser (PyYAML is required; exit status 0 clean, 1 errors, 2 environment problem). Rules marked **[checked]** are enforced by the checker. `make okf-check` runs both; `make check` runs it too.

# Directory groups and concept types

| Directory | `type` value | One file per |
|---|---|---|
| `tools/` | `Tool` | engine or tool used by the experiment (version, licence, verified behaviour, limits) |
| `decisions/` | `Decision` | judgment call (question, options, evidence links, outcome, status) |
| `sources/` | `Source` | source artifact actually read (one record per artifact) |
| `runbooks/` | `Runbook` | repeatable procedure |
| `questions/` | `Open Question` | unresolved fact plus the cheapest experiment that resolves it |

The checker also knows `Dataset` and `License` records (`datasets/`, `licenses/`); this bundle has none, because the datasets are sql-megasamples' and their records live there.

# Frontmatter template **[checked]**

Frontmatter is kept in the canonical form written by `scripts/okf_fix_quotes.py` (block style, key order preserved, every date and version quoted as a string, tags as strings); run it after editing frontmatter by hand, and `--check` reports files that are not canonical.

```yaml
---
type: Tool                         # one of the types above; non-empty
title: "DoltgreSQL 1.3.1"          # quote any scalar containing ': ' or ' #'
description: "One sentence."
resource: https://...              # canonical URI of the thing described (upstream URL, or bundle path for abstract concepts)
tags: [engine, doltgresql]         # strings only; quote numeric-looking tags ("1.3")
status: stable                     # required: draft | stable | deprecated
trust: verified                    # required: verified | inferred | open   (see Trust rules)
generated: { by: "claude-code/claude-fable-5-1", at: "2026-09-10T03:45:00Z" }   # ISO 8601; quote it
verified:                          # present if and only if trust == verified
  - { by: "claude-code/claude-fable-5-1", at: "2026-09-10T03:45:00Z" }
sources:                           # every URL here was actually opened on the accessed date
  - resource: https://...
    title: "Page title"
    accessed: "2026-09-10"
    version: "v1.3.1 / commit abc123 / snapshot date"   # when applicable; quote it
stale_after: "2027-03-01"          # optional; version pins and download URLs
---
```

# Trust rules **[checked where noted]**

* `trust: verified`: every **load-bearing** claim (a claim a decision or test relies on) was read in an authoritative source listed under `sources`, or produced by a command whose output is recorded. A verified record **may** contain inferences, provided each is delimited: a sentence or bullet prefixed **Inferred:** or a section headed `# Inferred`. The record-level value describes the load-bearing claims, not every sentence.
* `trust: inferred`: the record's central claim or outcome rests on reasoning, memory or estimation rather than on a read source. No `verified` key.
* `trust: open`: the record is a question; `status: draft`. Used for `Open Question` records and for a `Decision` whose outcome is still pending.
* An **answered** Open Question becomes `status: deprecated`, `trust: verified` with a `verified:` block, and gains an `# Answer` section that states each answer and the command or source that produced it. It keeps its `# Question` and `# Cheapest experiment` sections so the trail stays readable.
* Unmarked hedges: the phrase "from memory" may appear in a `trust: verified` record only inside an **Inferred:**-marked sentence **[checked]**.
* `sources[]` lists only documents that were opened. A `sources[].title` containing "not read" is rejected **[checked]**; the rest of this rule is a human one.
* A measurement is quoted with its unit, what it measures, and the date and command that produced it; a number without those is not a fact.

# Source record granularity

One `Source` record per **source artifact**: a single web page or document, a repository at a pinned commit, a release page with its assets, or one API probe. Every URL read is listed under `sources`. A record must not mix unrelated artifacts (two vendors, two repositories).

# Required sections per type **[checked]** (heading prefix match; a parenthetical suffix is allowed)

| Type | Required `#` headings, in this order |
|---|---|
| Source | `What was read`, `Relevant excerpt`, `What it was used to decide` |
| Decision | `Question`, `Options considered`, `Evidence`, `Outcome`, `Status` |
| Tool | `Facts`, `Limits` (optional: `Inferred`, `Open questions`, `Decision`) |
| Open Question | `Question`, `Cheapest experiment`, `Resolves` |
| Runbook | free |

# Decision status consistency **[checked]**

A Decision whose `# Status` section begins with `accepted` has `status: stable` and `trust` ≠ `open`, and carries no `pending` tag. A Decision whose `# Status` begins with `pending` has `status: draft` and `trust: open`. Deprecated decisions have `status: deprecated` and a `superseded-by` link in `# Status`.

# Links **[checked]**

Absolute bundle links (`/tools/doltlite-0-50-9.md`) are preferred. Links in every file (concepts, `index.md`, `log.md`) and bundle paths in `resource` / `sources[].resource` are resolved; a broken link is a warning while the root `index.md` declares `bundle_status: draft` and an error once it declares `bundle_status: stable` (or with `--strict-links`).

# index.md and log.md **[checked]**

* Every directory has an `index.md` generated by `scripts/okf_check.py --write-index` (no frontmatter except the root's `okf_version: "0.2"` and `bundle_status`); the root intro paragraph between `<!-- intro -->` markers is preserved across regenerations. A hand-edited index that differs from the generated form fails the check.
* `log.md` at the root: `## YYYY-MM-DD` headings only, newest first; every bullet starts with one of **Creation**, **Update**, **Verification**, **Deviation**, **Deprecation**.
* A **Deviation** entry is mandatory whenever the executor departs from `PLAN.md`; it links to the updated Decision record that carries the evidence.

# When to update versus create

* New fact about an existing tool → update that record, bump `generated.at`, add the new source to `sources`, log an **Update**. Re-stamp `verified` only when the load-bearing claims were re-checked.
* New artifact read → new `sources/` record.
* New judgment call → new `decisions/` record; if it replaces an earlier one, set the old one `status: deprecated` and link `superseded-by`.
* Measurement taken during execution (a load time, a size, a refusal) → the generated documents carry it from `build/`; a record quotes it only when a decision rests on it, with the date and the command.
