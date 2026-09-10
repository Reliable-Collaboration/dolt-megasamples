---
type: Open Question
title: What does DoltLite's VACUUM need in memory, and why did a 5 GB file exceed it?
description: Answered on 2026-09-10 -- the failure is DoltLite's own, not the host's; VACUUM of the 3.6 GB per-row-commit file fails within seconds at a 1.2 GiB peak, with or without a memory cap, so those stores are reported as loaded and not collectable.
resource: /questions/doltlite-vacuum-memory.md
tags:
- doltlite
- question
- method
status: deprecated
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T17:10:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T17:10:00Z"
sources:
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9 (the observation)
  accessed: "2026-09-10"
---

# Question

`doltlite /data/doltlite-rowcommit_inline/dvdstore.doltlite "SELECT dolt_commit('-A', '--allow-empty', '-m', '...'); VACUUM;"` answered `out of memory` on a 5,170,967,610-byte file holding 174,718 commits, inside a container capped at 16 GiB; the deferred-policy file of the same database (1.8 GB, the same commits) vacuumed in 5.4 s. Is the limit DoltLite's own (a soft heap limit, an allocation proportional to the file or to the chunk count), the cgroup's, or the shell's, and at what size does it bite?

The same answer came within 2.5 s from chicago_crimes' deferred-policy file (3,626,990,331 bytes, 260,043 commits), so the limit sits between 1.8 GB and 3.6 GB for these files and is not a slow climb to the cgroup's 16 GiB.

# Cheapest experiment

Run the same `VACUUM` on that file again with the host's cgroup memory files sampled every second (`/sys/fs/cgroup/docker/<id>/memory.current` and `memory.stat`'s `anon`) and `PRAGMA soft_heap_limit` / `PRAGMA hard_heap_limit` read first; then the same on the 1.8 GB file. If the peak sits far under 16 GiB when the error comes, the limit is DoltLite's own and the README's `doc/doltlite/storage-format.md` should say what `VACUUM` allocates.

# Resolves

Whether the inline-policy per-row-commit loads of the larger databases can be settled and measured on DoltLite, or must be reported as "loaded, not collectable" with the size before the settle step; and the wording of the tool record's limit.

# Answer

DoltLite's own limit, not the host's. On a copy of chicago_crimes' per-row-commit file (3,626,991,241 bytes, 260,043 commits), `VACUUM` in the DoltLite image (the pinned v0.50.9) under a 16 GiB cgroup answered `out of memory` after 3.5 s with the cgroup's anonymous memory peaking at 1,165 MiB (sampled from the host every half second), and without any cap it answered the same after 2 s; `PRAGMA soft_heap_limit` and `hard_heap_limit` are both 0 (unlimited) on the file, and the file was unchanged afterwards (2026-09-10). A store the engine cannot collect is therefore a limit of DoltLite v0.50.9 on large per-row-commit histories (between dvdstore's 1.8 GB, which collected, and chicago_crimes' 3.6 GB), and the report says so: such units are kept with `settled: false`, their size is the working footprint of the load, marked in the tables and left out of the totals. The per-row-commit loads of the three largest databases are run for their time and footprint with that understanding ([the dialect rules](/decisions/pair-dialect-rules.md), [DoltLite v0.50.9](/tools/doltlite-0-50-9.md)). `doc/doltlite/storage-format.md` and `concurrency.md` say only that `VACUUM` runs garbage collection and may be deferred while writers hold the graph lock; nothing about what it allocates.
