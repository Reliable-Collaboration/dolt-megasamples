# DoltLite v0.50.9: VACUUM answers "out of memory" on a 3.6 GB file with 260k commits, at a 1.2 GiB peak

*Found on DoltLite v0.50.9, the version dolt-megasamples pins by the SHA-256 of its two release packages. It was the newest release on 2026-09-10; no newer release has been tried.*

Record: `knowledge/tools/doltlite-0-50-9.md`, `knowledge/questions/doltlite-vacuum-memory.md`.

**Steps:** a DoltLite-format file produced by replaying a 260,041-row SQLite dump with `SELECT dolt_commit('-Am', ...)` after every `INSERT` (260,043 commits, 3,626,991,241 bytes); then `doltlite the.db "VACUUM;"` from the `doltlite_0.50.9_amd64.deb` shell on Debian 13.

**Result:** `Error in 2nd command line argument: out of memory` after 2 to 3.5 s, whether the process runs under a 16 GiB cgroup (anonymous memory peaked at 1,165 MiB, sampled every half second) or with no limit on a 19.5 GiB host; `PRAGMA soft_heap_limit` and `hard_heap_limit` are 0. A 1.8 GB file with 174,718 commits collects in 5.4 s; 15 GB files with 706k and 753k commits fail the same way. The file is unchanged afterwards.

**Where it comes from** (read in the v0.50.9 source, not patched): in `src/doltlite_gc.c`, `gcQueuePush` (lines 92-140) doubles the mark queue and returns `SQLITE_NOMEM` once the next size would pass 2^31 bytes (the guard added by #1736). `gcQueuePop` never releases processed entries, and a chunk already marked is skipped only when it is taken out (line 280), so the queue keeps every child reference ever pushed. At 72 bytes an entry the largest queue is 16,777,216 entries, 1,152 MiB, beside the 1.2 GiB peak above: the "out of memory" is that guard, not the machine. Skipping marked chunks before pushing, and releasing processed entries, would lift it; the marked-chunk hash set and SQLite's 2 GB single-allocation cap are the next limits.

**Why it matters:** a per-row-commit history above about 2 GB cannot be garbage-collected at all, so its working footprint is its permanent size.
