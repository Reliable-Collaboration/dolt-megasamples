---
type: Source
title: DoltLite LICENSE.md
description: The licence terms of DoltLite -- Apache-2.0 for the DoltLite extensions over public-domain SQLite -- and why GitHub reports no licence.
resource: https://github.com/dolthub/doltlite/blob/main/LICENSE.md
tags:
- doltlite
- license
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: https://api.github.com/repos/dolthub/doltlite/contents/LICENSE.md
  title: LICENSE.md of dolthub/doltlite, raw, default branch
  accessed: "2026-09-10"
- resource: https://api.github.com/repos/dolthub/doltlite/contents
  title: Root listing of dolthub/doltlite
  accessed: "2026-09-10"
---

# What was read

`LICENSE.md` at the root of `dolthub/doltlite` on its default branch (fetched raw on 2026-09-10) and the root listing, which also holds `APACHE_LICENSE` and `.sqlite-upstream-base` (the upstream SQLite revision the fork tracks). GitHub's repository record reports the licence as `NOASSERTION`, which is what it says when a licence file is not a single recognised text.

# Relevant excerpt

> License Information
> ===================
> Doltlite Extensions — Apache License 2.0
> -----------------------------------------
> The Doltlite extensions to SQLite — including the prolly tree storage engine, chunk store, version control functions (dolt_commit, dolt_merge, dolt_diff, etc.), and all related code in the following files — are licensed under the Apache License, Version 2.0:
>   * `src/prolly_*.c` and `src/prolly_*.h` — Prolly tree implementation
>   * `src/chunk_store.c` and `src/chunk_store.h` — Content-addressed chunk store
>   * `src/pager_shim.c` — Pager shim for SQLite integration
>   * `src/doltlite*.c` and `src/doltlite*.h` — Version control functions
>   * `.github/` — CI/CD workflows
> You may obtain a copy of the Apache License at: https://www.apache.org/licenses/LICENSE-2.0

The rest of the file (not quoted) states that the SQLite code the fork is built on keeps SQLite's public-domain dedication.

# What it was used to decide

* That running and redistributing the DoltLite image built here is permitted (Apache-2.0 plus public domain), and what `NOTICE` should say if the image is ever shipped: [DoltLite v0.50.9](/tools/doltlite-0-50-9.md). Nothing is published from this repository; the image is built locally by `make lite-image`.
