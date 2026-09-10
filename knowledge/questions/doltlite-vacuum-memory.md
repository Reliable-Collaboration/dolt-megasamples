---
type: Open Question
title: What does DoltLite's VACUUM need in memory, and why did a 5 GB file exceed it?
description: The per-row-commit load of dvdstore with the indexes inline left a 5.2 GB DoltLite file whose VACUUM answered "out of memory" under a 16 GiB cgroup; whether that is the file's size, its commit count, or a limit of the shell decides which loads can be settled at all.
resource: /questions/doltlite-vacuum-memory.md
tags:
- doltlite
- question
- method
status: draft
trust: open
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T06:50:00Z"
sources:
- resource: /tools/doltlite-0-50-9.md
  title: DoltLite v0.50.9 (the observation)
  accessed: "2026-09-10"
---

# Question

`doltlite /data/doltlite-rowcommit_inline/dvdstore.doltlite "SELECT dolt_commit('-A', '--allow-empty', '-m', '...'); VACUUM;"` answered `out of memory` on a 5,170,967,610-byte file holding 174,718 commits, inside a container capped at 16 GiB; the deferred-policy file of the same database (1.8 GB, the same commits) vacuumed in 5.4 s. Is the limit DoltLite's own (a soft heap limit, an allocation proportional to the file or to the chunk count), the cgroup's, or the shell's, and at what size does it bite?

# Cheapest experiment

Run the same `VACUUM` on that file again with the host's cgroup memory files sampled every second (`/sys/fs/cgroup/docker/<id>/memory.current` and `memory.stat`'s `anon`) and `PRAGMA soft_heap_limit` / `PRAGMA hard_heap_limit` read first; then the same on the 1.8 GB file. If the peak sits far under 16 GiB when the error comes, the limit is DoltLite's own and the README's `doc/doltlite/storage-format.md` should say what `VACUUM` allocates.

# Resolves

Whether the inline-policy per-row-commit loads of the larger databases can be settled and measured on DoltLite, or must be reported as "loaded, not collectable" with the size before the settle step; and the wording of the tool record's limit.
