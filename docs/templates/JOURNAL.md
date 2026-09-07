# Journal

The lab notebook: why the experiment is built the way it is, what its numbers do not support, and
what went wrong getting them. The results themselves are in [`README.md`](README.md) and
[`REPORT.md`](REPORT.md); this is the reasoning around them.

Like those, this file is generated — `docs/templates/JOURNAL.md` holds the prose and every number
comes from a measurement file.

## The question

Dolt keeps the history of every change; MySQL keeps the current state. That is not a small
difference in how bytes land on a disk, and the honest way to find out what it costs is to load the
same data into both and measure, rather than to reason from the architectures.

## What is being compared

The same {{corpus.databases}} sample databases — {{corpus.rows}} rows across {{corpus.tables}}
tables — loaded into both engines from the same `mysqldump` files.

Three Dolt loads, because "the same data in Dolt" turns out not to be one thing:

| mode | how the rows are written | Dolt commits |
|---|---|---|
| `oneshot` | mysqldump's extended `INSERT`s | one per database |
| `rowinsert` | one `INSERT` statement per row | one per database |
| `rowcommit` | one `INSERT` statement per row | **one per row** |

The first is how anyone would actually load a database. The second isolates *statement* granularity.
The third isolates *history* granularity — and it is the one that matters, because a commit is the
thing Dolt exists to keep.

## Why three, when two would look simpler

Because "one row at a time" is ambiguous, and the ambiguity hides the finding.

In MySQL, one `INSERT` per row versus one big `INSERT` is a difference in parse and transaction
overhead; the bytes on disk end up the same. It is tempting to assume Dolt behaves likewise. It does
— but only for the *stored* result. The load itself behaves very differently, and if you stop at
"one row at a time" without saying whether you mean statements or commits, you cannot tell which of
those two facts you are looking at.

Separating them is what makes the third mode interpretable: whatever `rowcommit` costs above
`rowinsert` is the price of history, not the price of small statements.

## And why each row-by-row load runs twice

The same ambiguity, one level down. A load that writes rows one at a time *and* maintains every
secondary index while doing it is measuring two things, and the interesting one is underneath.
Anyone bulk-loading either engine drops the secondary indexes, loads, and rebuilds — so that is what
these runs do by default, and `--indexes inline` keeps them maintained throughout for comparison.

Two keys are never deferred. The primary key is the row's identity and Dolt keys its prolly tree by
it. And a key an `AUTO_INCREMENT` column depends on stays inline wherever that column does not lead
the primary key, because MySQL requires such a column to lead some key — a rule that Dolt does not
enforce, so deferring it produced a file MySQL refused and Dolt accepted.

## How the comparison is kept fair

A ratio between two databases is worthless if they are not holding the same thing. Six checks, run
on every database, none of them assumed:

1. **The same rows.** `COUNT(*)` on both sides, per table, before any size is recorded.
   `information_schema.table_rows` is an InnoDB estimate and is never used.
2. **The same indexes.** Compared by definition — table, index name, column position, column,
   uniqueness — not by count, and for every mode rather than only the one-shot load.
3. **The same measurement.** `du -sb` of the directory each engine keeps the database in, and a
   `du` that fails raises instead of returning zero.
4. **A packed store, not a journal.** Dolt is garbage-collected before measuring.
5. **A committed store, not a working set.** Every Dolt load ends with a commit, and `dolt_status`
   is clean when the size is taken.
6. **The same file.** Both engines load the identical transformed dump.

Every one of those six is on the list because it was once false.

## What is deliberately excluded, and why

**The server's statistics.** A running `dolt sql-server` writes a per-database statistics repository
at `.dolt/stats`, and `dolt gc` does not reclaim it. Every figure is measured with no server
running, and the server's contribution is measured separately on a copy. The size of that
contribution is not settled: a controlled pass over every table writes a small, even amount per
database, while sustained console use drove one database's statistics past the size of the data they
describe. Both are reported, because quoting only the small one would be misleading and quoting only
the large one would be unreproducible.

## What the numbers do not mean

* **This is the least history Dolt can hold.** One commit per database. A real repository has
  branches, merges and a year of changes, and the `rowcommit` results show how quickly that grows.
* **Nothing here is updated or deleted.** Every database is loaded once and never modified. Dolt's
  storage is designed around change; a workload that rewrites rows would exercise it very
  differently.
* **Neither engine is performance-tuned.** Stock storage settings throughout. MySQL has knobs —
  `ROW_FORMAT=COMPRESSED`, page size — that would move its numbers, and none were touched.
* **It is a fixed set of datasets, not a distribution.** They were chosen to be varied and openly
  licensed, not to be representative of your data. The per-database spread is the reason to measure
  your own rather than take a headline ratio from anyone, including this.

## What went wrong along the way

Recorded because a result you cannot see the mistakes in is harder to trust, not easier. Nearly
every one of these failed the same way: by producing a **plausible value instead of an error**.

* **The dumps were being corrupted before Dolt ever saw them.** The transform read them as UTF-8
  text with `errors="replace"`, which turns every byte that is not valid UTF-8 into U+FFFD, growing
  files that carry binary literals and silently changing rows. The transform works on bytes now and
  refuses a `str`.
* **Three loads truncated silently and were recorded as successes**, because the check for "did it
  work" was whether the output directory existed. The cause was the kernel: one `dolt sql` process
  building a multi-million-commit history exhausted memory and was killed — exit 137, which nothing
  was reading. Every load is now verified table by table against MySQL before its size is recorded.
* **A unit was recorded as done while Docker was not running.** The daemon restarted mid-run; the
  row-count verifier asked MySQL for its table list, got nothing, and concluded that nothing was
  short. It refuses to pass a database it could not actually check, and the run stops at the first
  unit it cannot reach the daemon for.
* **The deferred indexes were never built.** Rebuilding them at the end of the file put the
  `ALTER TABLE`s after the routines, and Dolt rejects `CREATE FUNCTION` — one rejected statement
  aborts the rest of the file, so a database finished with a third of its indexes and nothing said
  so. Moving them to just after the last row then broke MySQL instead, with
  `ERROR 1100: ... was not locked with LOCK TABLES`. They go after the last `UNLOCK TABLES` now —
  and not merely after the last `INSERT`, because a table with no rows contributes a `CREATE TABLE`
  and no `INSERT`, and one such table sorted last produced
  `ERROR 1146: Table ... doesn't exist`.
* **The per-row-commit repositories were measured dirty.** That mode ended with `dolt gc` and no
  commit, which was true until the index rebuild was deferred into the working set.
* **The two engines disagreed about a view, and only one of them said so.** MySQL refused a
  cross-database view with `ERROR 1049`; Dolt accepted it and stored it. The first attempt at
  detecting those matched `` `x`.`y` `` by shape and dropped every view in the corpus, because a
  view body is full of table aliases that parse identically.
* **`SQL SECURITY DEFINER` was surviving the transform.** The pattern removing it expected it to
  follow `ALGORITHM=`, but mysqldump puts `DEFINER=` between them, so views Dolt could otherwise
  take were being rejected.
* **MySQL was declared ready in the middle of initialising itself.** On a fresh data directory the
  entrypoint runs a temporary server on the socket, and the readiness probe connected to that. The
  probe uses TCP now, which the temporary server refuses.
* **Every database in a phase shared one Dolt data directory** — and Dolt opens every database under
  its data directory at startup. So each load paid to open everything loaded before it: the later
  loads in every phase were timed doing more work than the earlier ones, and at the size the
  per-row-commit directory reaches, opening it exhausted the host. Each database has its own
  directory now.
* **A row count was silently truncated and then reasoned from.** It was built as one `UNION ALL`
  over every table using `GROUP_CONCAT`, whose default length limit cut the generated SQL
  mid-statement, so a database with many tables reported a fraction of its rows. Nothing errored,
  and the wrong figure was used in an argument about what Dolt's memory scales with. The check that
  would have caught it was in the same table the whole time: a load that commits once per row must
  end with as many commits as it has rows.
* **The figures failed a colour-vision check.** Two Dolt loads drawn as adjacent bars were
  indistinguishable under protanopia — in exactly the two bars the figure exists to compare. The
  palette is checked by a script now instead of chosen by eye.
* **Figures rendered from fabricated data were committed.** A synthetic results file built to check
  a new chart against full coverage was rendered into `docs/img` and committed. Preview renders go
  to a different directory now, so it cannot happen again.

That list is why this repository generates its documents. Two of those faults were invisible
precisely because a sentence and a measurement had no connection to each other, and the fix for that
class is structural, not a matter of being more careful: no document holds a typed number, every
number resolves from a measurement file, and `make check` fails when a document disagrees with the
evidence. `scripts/audit.py` closes the other half, checking the measurements against invariants
that a plausible wrong answer cannot satisfy.

## What came out

{{block:summary_table}}

## Reproducing it

See [`README.md`](README.md) for the full sequence, the budget, and the memory limits. In short:
`make export`, `make preflight`, `make run`, `make report`, `make docs`, `make check`.

Every number in every document is generated from `build/`. Nothing is typed by hand, so a claim that
disagrees with the measurements cannot survive a regeneration.
