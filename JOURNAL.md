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

## And why each row-by-row load is then run twice

The same ambiguity, one level down. A load that writes rows one at a time *and* maintains every
secondary index while doing it is measuring two things, and the interesting one is underneath.
Anyone bulk-loading either engine drops the secondary indexes, loads, and rebuilds — so that is what
these runs do by default, and `--indexes inline` keeps them maintained throughout for the
comparison.

The primary key is never deferred. It is not an optimisation to leave out: it is the row's identity,
Dolt stores a table as a prolly tree keyed by it, and a table loaded without one is a different
table. Everything else — `KEY`, `UNIQUE KEY`, `FULLTEXT KEY`, `SPATIAL KEY` and the foreign key
constraints — comes out for the load and goes back with `ALTER TABLE` after the last row, which for
Dolt puts them inside the final commit. Both policies finish with the same schema, and index parity
against MySQL is checked under each.

Tests 1 and 3 have no policy, because there is nothing to vary: mysqldump's extended `INSERT`s build
an index over batches whichever way you ask, and both policies produced byte-identical files.

## How the comparison is kept fair

A ratio between two databases is worthless if they are not holding the same thing. Six checks, run
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
5. **A committed store, not a working set.** Every Dolt load ends with a commit before that gc, and
   `dolt_status` is clean when the size is taken. This was the last of the four to be true: the
   per-row-commit mode ended with `dolt gc` alone, which was sound until the deferred index rebuild
   started landing in the working set and never held for databases whose views and routines
   mysqldump writes after the last row.
6. **The same file.** Both engines load the identical transformed dump. They did not to begin with —
   MySQL read mysqldump's original while Dolt read the transformed copy — which meant the two were
   never quite given the same work. What the transform removes is listed in `dolt_dialect.py` and
   named in the report.

## What is deliberately excluded, and why

**The server's statistics.** A running `dolt sql-server` writes a per-database statistics repository
at `.dolt/stats`, and `dolt gc` does not reclaim it. Every figure here is therefore measured with no
server running, and the server's contribution is measured separately on a copy.

The size of that contribution is not settled. A controlled pass — start a server, read every table in
every database — writes an even 22 KB per database, 462 KB in total. But during this project's own
console use, four web clients browsing over a working session, `adventureworks`'s statistics reached
68.2 MB — more than the 49.0 MB of data they describe. A single pass does not reproduce that, so the
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

**One `INSERT` per row, still one commit:** the same, to within 0.5% for 15 of the 21 databases
tried — eight of them byte-identical — and 4.1% for the one outlier. Statement batching is a load-time concern and not a storage one. It is worth knowing precisely
because it is the assumption most people would make either way without checking.

**One commit per row** (measured on 18 of the 21 so far)**:** 12× to 368× the single-commit load, and for 16 of the 18 databases more
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
* **Three loads truncated silently and were recorded as successes**, because the check for "did it
  work" was whether the output directory existed. `employees` stopped at 1,854,812 of 3.9 million
  rows with `titles` never created. The cause was the kernel: one `dolt sql` process building a
  multi-million-commit history exhausted memory and was killed — exit 137, which nothing was
  reading. Every load is now verified table by table against MySQL before its size is recorded, and
  the large ones are split into chunks so each process can give its memory back.
* **A whole run was recorded as successful while Docker was not running.** The daemon restarted
  mid-run; the row-count verifier asked MySQL for its table list, got nothing, and concluded that
  nothing was short. A unit went into the record as `done` with exit code 1 and no size. The
  verifier now refuses to pass a database it could not actually check, and the run stops at the
  first unit it cannot reach the daemon for rather than recording a hundred more like it.
* **The deferred indexes were never built.** Rebuilding them at the end of the file put the
  `ALTER TABLE`s after the routines, and Dolt rejects `CREATE FUNCTION` — one rejected statement
  aborts the rest of the file, so sakila finished with 16 of its 42 indexes and nothing said so.
  Moving them to just after the last row then broke MySQL instead, with `ERROR 1100: Table 'album'
  was not locked with LOCK TABLES`, because mysqldump wraps each table's rows in `LOCK TABLES`.
  They go after the `UNLOCK TABLES` now. Dolt does not enforce LOCK TABLES and had loaded the broken
  file without complaint, which is the kind of difference that leaves two engines quietly running
  different SQL.
* **The per-row-commit repositories were measured dirty.** That mode ended with `dolt gc` and no
  commit, on the reasoning that every row had already been committed — true until the index rebuild
  was deferred into the working set, and never true for databases whose views and routines mysqldump
  emits after the last row. Seven modified uncommitted tables were being weighed against a rival
  that had committed everything.
* **The two engines disagreed about a view, and only one of them said so.** `oracle_oe` has two
  views onto `oracle_hr`. MySQL refused them with `ERROR 1049: Unknown database`; Dolt accepted them
  and stored them. "The same file" was not being loaded. They are dropped now and named in the
  notes, like the cross-database foreign keys. The first attempt at detecting them matched
  `` `x`.`y` `` by shape and dropped every view in the corpus, sakila's seven included, because a
  view body is full of table aliases that parse identically.
* **MySQL was declared ready in the middle of initialising itself.** On a fresh data directory the
  entrypoint runs a temporary server on the socket, and the readiness probe connected to that. Two
  loads in the first fifteen died with `ERROR 2002`. The probe uses TCP now, which the temporary
  server refuses.
* **The figures failed a colour-vision check.** Dolt's one-commit-per-database and one-INSERT-per-row
  loads were drawn as adjacent bars in a green and an orange 4.5 apart under protanopia, against a
  floor of 8 — indistinguishable, to a red-green colourblind reader, in the two bars the figure
  exists to compare. The palette is checked by a script now instead of chosen by eye.

## Reproducing it

```sh
cd ../mysql-megasamples && make up               # the source of every dump
cd ../dolt-megasamples  && make down             # a running Dolt server writes into what is measured
make export                                      # one mysqldump per database, both statement styles
make run                                         # all five loads, timed, indexes deferred
python3 scripts/run_all.py --indexes inline      # tests 2, 4 and 5 with the indexes maintained
make report                                      # REPORT.md, the README tables, every figure
```

`make experiment` used to run the row-by-row loads over a hand-picked list of the smallest
databases. That is where the holes in the first report came from — figures whose bars stood for
different populations under titles that did not say so — so the target now refuses and points at
`make run`, which covers every database.

Every number in `README.md` and `REPORT.md` is generated from `build/results.json`. Nothing is typed
by hand, so a claim that disagrees with the measurements cannot survive a regeneration.
