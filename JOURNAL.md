# Journal

A record of what was done, why, and what the numbers do and do not support. Written for someone
picking this up cold and deciding whether to trust it.

## The question

Dolt stores data in a way that has nothing in common with InnoDB. MySQL writes B-tree pages into a
tablespace per table; Dolt writes content-addressed chunks into prolly trees and keeps the history of
every change. Both speak the MySQL wire protocol, which makes them look interchangeable from a client
and tells you nothing about what they cost on disk.

That gap is the whole reason for this repository. "How much bigger will Dolt be?" is not answerable
by reasoning about the architectures — the honest answer is *it depends on the data and on how you
put it there*, and the only way to say more is to measure it.

## What is being compared

The same 21 sample databases from `mysql-megasamples` — 9,056,697 rows of real, varied,
publicly-licensed data, from 216-row teaching schemas to a million-row star schema — loaded into both
engines from the same `mysqldump` files.

Three loads, because "the same data in Dolt" turns out not to be one thing:

| mode | how the rows are written | Dolt commits |
|---|---|---|
| `oneshot` | mysqldump's extended `INSERT`s, thousands of rows per statement | one per database |
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

## How the comparison is kept fair

A ratio between two databases is worthless if they are not holding the same thing. Four checks, run
on every database, none of them assumed:

1. **The same rows.** `COUNT(*)` on both sides, per table, before any size is recorded.
   `information_schema.table_rows` is an InnoDB estimate and is never used.
2. **The same indexes.** Compared by definition — table, index name, column position, column,
   uniqueness — not by count. Indexes are a large part of what a database costs, so an engine quietly
   dropping some would invalidate everything. 613 in MySQL, 613 in Dolt, identical in every database.
3. **The same measurement.** `du -sb` of the directory each engine keeps the database in. Not
   `information_schema`, which under-reports MySQL by ignoring free pages in its own tablespaces.
4. **A packed store, not a journal.** Dolt is garbage-collected before measuring. `jaffle_shop` is
   35,550 bytes after its commit and 16,951 after `dolt gc`; measuring the wrong one of those by
   accident would have been easy.

## What is deliberately excluded, and why

**The server's statistics.** A running `dolt sql-server` writes a per-database statistics repository
at `.dolt/stats`, and `dolt gc` does not reclaim it. Every figure here is therefore measured with no
server running, and the server's contribution is measured separately on a copy.

The size of that contribution is not settled. A controlled pass — start a server, read every table in
every database — writes an even 22 KB per database, 462 KB in total. But during this project's own
console use, four web clients browsing over a working session, `adventureworks`'s statistics reached
68.2 MB — more than the 48.7 MB of data they describe. A single pass does not reproduce that, so the
growth depends on sustained querying in a way this experiment has not characterised. Both numbers are
reported because quoting only the small one would be misleading and quoting only the large one would
be unreproducible.

None of this was designed in advance. It was found because a re-measurement disagreed with the
previous one by 68 MB, and the cause turned out to be that a server had run in between. The
measurement discipline — server down for the data, copy for the server — came out of that.

## What came out

**One commit per database:** the 21 databases take 1,523 MB in MySQL and 525 MB in Dolt — 0.34×.
The per-database ratio runs from 0.05× to 0.76×, a spread of more than fifteen to one, and the shape
of that spread is legible: tiny databases favour Dolt enormously because InnoDB allocates a
tablespace per table whether or not anything is in it, and text-heavy data narrows the gap because
neither engine can do much with incompressible prose.

**One `INSERT` per row, still one commit:** the same, to within 0.5% for ten of the eleven databases
tried — eight of them byte-identical — and 4.1% for the one outlier. Statement batching is a load-time concern and not a storage one. It is worth knowing precisely
because it is the assumption most people would make either way without checking.

**One commit per row:** 10× to 187× the single-commit load, and for seven of the nine databases more
disk than MySQL uses. `chinook` goes from 615 KB to 112 MB. A controlled check outside the sample
data makes the same point without any schema in the way: 1,000 rows in one commit is 16,202 bytes;
the same 1,000 rows in 1,000 commits is 2,929,110 bytes, **181× for identical data**.

The third result is the one worth carrying away, and it is not "Dolt is big". Each commit is an
addressable, diffable state of the whole database. Storing a million of them costs what storing a
million of anything costs. The useful question is not how Dolt compares to MySQL at rest, but **what
your commit rate costs you** — and that scales with commits, not with rows.

## What the numbers do not mean

Read the results as a floor, not as a forecast:

* **This is the least history Dolt can hold.** One commit per database, `dolt_status` clean
  afterwards. A real repository has branches, merges and a year of changes, and the `rowcommit`
  results show how quickly that grows.
* **Nothing here is updated or deleted.** Every database is loaded once and never modified. Dolt's
  storage is designed around change; a workload that rewrites rows would exercise it very differently.
* **Neither engine is tuned.** Stock InnoDB page size, stock compression settings, stock everything.
  MySQL has knobs — `ROW_FORMAT=COMPRESSED`, page size, `innodb_file_per_table` — that would move its
  numbers, and none were touched.
* **It is 21 datasets, not a distribution.** They were chosen to be varied and openly licensed, not
  to be representative of your data. The per-database spread of more than ten to one is the reason to
  measure your own rather than take a headline ratio from anyone, including this.

## What went wrong along the way

Recorded because a result you cannot see the mistakes in is harder to trust, not easier.

* **The dumps were being corrupted before Dolt ever saw them.** The dialect transform read them as
  UTF-8 text with `errors="replace"`, which turns every byte that is not valid UTF-8 into U+FFFD.
  `adventureworks` carries 20,156 `_binary` spatial literals; the file grew by 267,588 bytes and the
  rows were silently wrong. Dolt caught it by rejecting the first corrupted `INSERT`. The transform
  now works on bytes and refuses a `str`.
* **A "clean reload" was not clean.** Dolt's container writes as root, so `rm -rf data` failed with
  permission errors that were not checked, and the next run reported every database as "already
  loaded". The reload had to be done from inside a container; `make clean-data` now does that.
* **The first healthcheck tested the wrong thing.** It ran `dolt sql -q 'SELECT 1'`, which answers
  from the data directory whether or not a server is listening. Compose went green and the account
  setup then failed to connect.
* **Indexes were not checked at all** in the first version of this report. The ratios turned out to
  be right, but they were published before anyone had confirmed the two sides had the same indexes,
  which is not the same as being right.

## Reproducing it

```sh
cd ../mysql-megasamples && make up          # the source of every dump
cd ../dolt-megasamples  && make all         # export, load, measure, report
make experiment                             # the rowinsert and rowcommit modes
make charts                                 # regenerate the figures
```

Every number in `README.md` and `REPORT.md` is generated from `build/results.json`. Nothing is typed
by hand, so a claim that disagrees with the measurements cannot survive a regeneration.
