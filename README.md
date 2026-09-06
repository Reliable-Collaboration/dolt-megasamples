# dolt-megasamples

**An experiment: for the same data, what does [Dolt](https://github.com/dolthub/dolt) cost against
MySQL — in disk, and in time?**

Dolt is a SQL database with Git-like versioning that speaks the MySQL wire protocol, so the same
clients work against both. It stores data in an entirely different way: MySQL's InnoDB writes B-tree
pages into a tablespace per table, while Dolt writes content-addressed chunks into prolly trees and
keeps the history of every change. Those are different enough that "how big will it be, and how long
will it take?" is not answerable by reasoning about it.

So this measures it, on the 21 sample databases from
[`mysql-megasamples`](https://github.com/Reliable-Collaboration/mysql-megasamples) — 9,056,697 rows
of real, varied, publicly-licensed data, from 216-row teaching schemas to a million-row star schema.

**The repository is the evidence.** Every number and figure below is generated from
`build/results.json`; nothing is typed by hand. [Reproduce it](#reproducing-this) and you get your
own report, figures included.

## The tests

The same `mysqldump` files are loaded five ways. Nothing differs but how the rows are written.

| # | test | engine | how the rows are written | why it is here |
|---|---|---|---|---|
| 1 | `mysql` | MySQL 9.7.2 | mysqldump's extended `INSERT`s — thousands of rows per statement | the baseline anyone would actually use |
| 2 | `mysql_rowwise` | MySQL 9.7.2 | one `INSERT` per row | isolates what row-by-row writing costs **in MySQL**, so Dolt's row-wise cost can be separated from the cost of row-wise writing at all |
| 3 | `dolt_oneshot` | Dolt 2.3.2 | extended `INSERT`s, one commit for the whole database | the Dolt equivalent of test 1 |
| 4 | `dolt_rowinsert` | Dolt 2.3.2 | one `INSERT` per row, still one commit | isolates *statement* granularity from *commit* granularity |
| 5 | `dolt_rowcommit` | Dolt 2.3.2 | one `INSERT` per row, and one commit **after every row** | isolates what history costs — the thing Dolt exists to keep |

Tests 2 and 5 are the closest each engine has to the other's worst case: MySQL commits every
autocommitted statement, so one `INSERT` per row is one durable transaction per row.

**Tests 2, 4 and 5 are each run under two index policies**, because a row-by-row load that also
maintains an index measures two things at once.

| policy | what happens during the load | flag |
|---|---|---|
| **deferred** (default) | secondary indexes and foreign keys are taken out of `CREATE TABLE`, the rows load with `UNIQUE_CHECKS` and `FOREIGN_KEY_CHECKS` off, and `ALTER TABLE ... ADD` rebuilds them after the last row — for Dolt, inside the final commit | `--indexes deferred` |
| **inline** | every index and constraint is maintained on every row | `--indexes inline` |

This is the standard way to bulk-load either engine, and separating it out is what lets the cost of
*writing rows one at a time* be told apart from the cost of *maintaining an index while doing it*.
The primary key is never deferred — it is the row's identity, Dolt stores tables as a prolly tree
keyed by it, and a table loaded without one is a different table. Both policies end with the same
schema; index parity against MySQL is checked either way. Tests 1 and 3 have no policy: mysqldump's
extended `INSERT`s build an index over batches whatever you do, and the two policies produced
byte-identical files.

### How each load is performed

* **MySQL** is loaded into a **fresh, empty server** — not read from the megasamples image. The image
  was built by a `mysqlsh` restore with deferred index builds and is measurably more compact than the
  same data loaded from SQL; comparing against it would compare Dolt against a differently-built
  MySQL. Each database is dropped and reloaded from the dump. The server runs the stock image with
  two flags, `--local-infile=1` and `--skip-log-bin` — not quite "defaults", and `--skip-log-bin`
  favours MySQL by not writing a binary log.
* **Dolt** is loaded by the `dolt` CLI into a data directory, one directory per database. The dumps
  are transformed only where Dolt cannot parse mysqldump's output — `scripts/dolt_dialect.py`
  documents each rule — and never in a way that touches a row.
* **Sizes exclude what a server writes.** A `dolt sql-server` writes statistics into the database
  directory at `.dolt/stats`, and `dolt gc` does not reclaim them, so `du` of a served directory and
  an unserved one are not comparable. The measurement subtracts `.dolt/stats`, and what a server adds
  is reported separately.

  This is worth stating precisely, because an earlier version of this file claimed no server was
  running during measurement and that was **false** — the console stack was serving `data/dolt`
  throughout, and all 21 databases have a statistics directory as a result. Re-measuring every
  database with the stack stopped moved **no** size by more than a kilobyte, so the subtraction was
  doing its job and the numbers stand. The claim was still wrong, and the check is the reason it can
  be said so.

### How each load is measured

* **Disk** — `du -sb` of the directory the engine keeps the database in, after the load has settled:
  for Dolt, after `dolt add`/`dolt commit` and `dolt gc`, because Dolt writes through a journal and
  measuring before packing reports the write-ahead state rather than the stored one.
* **Time** — wall clock around the load itself, excluding the dump, the transform, and the
  measurement. For Dolt the commit and `gc` are timed separately and included in the total, because
  they are part of what it costs to get the data stored.

  **Both engines are timed the same way**, which they were not to begin with. MySQL was loaded with
  `docker exec` into a running server while Dolt was loaded by `docker run`, so every Dolt load paid
  container creation twice and MySQL paid it not at all — a measured 0.36 s that was under 1% of the
  large loads but **76–84% of the smallest**. Dolt now runs by `docker exec` into a long-lived
  container of its own, so neither engine's timings contain startup.
* **Repeats, where a repeat is affordable.** Each unit runs up to three times and the median of every
  sample is kept, until it has spent `--repeat-budget` seconds (180 by default); after that it is a
  single sample. Cheap loads therefore carry a measured spread and expensive ones say plainly that
  they do not, rather than the distinction being made by hand. Each unit records how many samples it
  got, the figures draw a whisker over the range where there is one, and there is no whisker where
  the number was measured once.
* **Every Dolt load ends committed.** The per-row-commit test used to finish with `dolt gc` alone,
  on the reasoning that each row had already been committed — but the deferred index rebuild, and
  the views and routines mysqldump emits after the last row, were then left in the working set. A
  repository with seven modified uncommitted tables is not the thing this is trying to measure.
* **Correctness, before any size is recorded** — every table counted with `COUNT(*)` on both sides,
  and every index compared by definition: table, index name, column position, column, uniqueness.
  A load that is short in any table is recorded as a failure, not as a small number. This matters:
  three per-row-commit loads truncated silently in the first full run and were recorded as
  successful because their output directory existed.

  Coverage of that check, as run: **tests 1–4 verified on all 21 databases** — 248 tables and 613
  indexes matching for the Dolt loads, 248 tables matching for the MySQL row-wise load. Test 5 is
  verified for each database as it completes.

## What would make a reviewer hesitate

Everything here that weakens the result, found by auditing the method against the code rather than
re-reading the prose. None of it is hidden in a footnote because all of it changes how the numbers
should be read. Several entries that used to be in this list are gone because they were fixed
rather than disclosed — MySQL loading different SQL from Dolt, `--force` hiding failed loads,
MySQL's shared InnoDB files going unattributed, and the two engines being timed differently. What
follows is what is still true.

**The per-row-commit size is the one number here that does not repeat.** Three loads of a
byte-identical file into an empty directory gave 81.4, 83.1 and 84.0 MB for `chinook`; a separate
triple of the same thing produced a sample at 101.4 MB, 22% above its own median. MySQL repeats to
the byte and the other Dolt loads to within four bytes, so treat test 5's disk figures as good to
roughly ±10% and no better. The commit graph is content-addressed but `dolt gc`'s packing is not
deterministic, and there is one gc per load.

**The expensive loads are single samples.** Repeats stop once a unit has spent 180 seconds, so the
cheap loads carry a measured spread and the slow ones — which is most of tests 2, 4 and 5 on the
large databases — are one run each. The figures draw a whisker only where there is a spread to draw,
and every unit records how many samples it got. A cell with no whisker was measured once.

**The machine was not idle.** The run shares the host with the source MySQL it reads the dumps from,
and with whatever else is on the machine. It is realistic but it is not a benchmark rig.

**Dolt is not given quite the same schema.** Both engines now load the identical transformed file,
but the transform removes things Dolt cannot take: three cross-database foreign keys in `oracle_oe`
(Dolt supports only same-database foreign keys), two cross-database views in the same database, and
stored functions, which do not load at all — so several databases have fewer routines in Dolt than
in MySQL. All of it makes Dolt's job slightly smaller. None of it touches a row.

The cross-database views are worth singling out, because the two engines *disagreed* about them
rather than both failing: MySQL refused `oracle_oe.account_managers` outright with `ERROR 1049:
Unknown database 'oracle_hr'`, while Dolt accepted the view and stored it. Dropping them is what
keeps "the same file" true.

**The largest per-row-commit loads are split into chunks.** One `dolt sql` process building a
multi-million-commit history is killed by the kernel on this host — `employees` died at 1,854,812 of
3.9 million rows, every time. Files over 150,000 statements are split so each process can exit and
give its memory back. That adds a process start per chunk to the timing, which is disclosed rather
than hidden; the alternative is a measurement that cannot be taken on this machine at all.

**Every MySQL figure here excludes what an empty MySQL costs.** Each database is loaded into its own
fresh server, and the size charged to it is the growth over that server's empty data directory. An
empty MySQL 9.7.2 data directory is **205.4 MB** — measured 19 times during this run, with 145 bytes
between the largest and the smallest — and none of it is charged to any database. That is the right
call for comparing *data*, because it is a per-server cost that does not grow: across 19 loads the
InnoDB shared files grew by **0 bytes**, so the bytes charged to a database equal that database's own
directory, exactly. But it is worth knowing before quoting a ratio, because Dolt has no equivalent —
its cost is the database directory and there is nothing outside it. For `jaffle_shop` at 372 KB, the
server it needs is over five hundred times the size of the data in it.

**MySQL runs with two non-default flags**, `--local-infile=1` and `--skip-log-bin`. The second
favours MySQL by not writing a binary log.

**Sizes exclude what a server writes.** A running `dolt sql-server` writes statistics into
`.dolt/stats` that `dolt gc` does not reclaim, so a served directory and an unserved one are not
comparable by `du`. The measurement subtracts `.dolt/stats` and reports separately what a server
adds.

## The machine

Timings mean nothing without it. Neither engine is performance-tuned: both run their published
images with stock storage settings. MySQL is started with two flags, which the table names — calling
that "default settings" while listing the flags would be a small dishonesty in the middle of a
methods section.

<!-- environment:start -->
| | |
|---|---|
| CPU | Intel(R) Core(TM) i9-14900KF (32 threads) |
| Memory | 15.5 GB |
| Disk | 1,006.9 GB ext4 |
| Kernel | 6.18.33.2-microsoft-standard-WSL2 |
| Docker | 29.6.2, storage driver `overlayfs` |
| MySQL | `mysql:9.7.2` — /usr/sbin/mysqld  Ver 9.7.2 for Linux on x86_64 (MySQL Community Server - GPL) |
| Dolt | `dolthub/dolt-sql-server` — dolt version 2.3.2 |
| Tuning | none — both engines run their published images with default settings |
| MySQL flags | `--local-infile=1`, `--skip-log-bin` |
<!-- environment:end -->

## The results

<!-- results:start -->
| database | rows | 1. MySQL | 2. MySQL<br>row-wise | 3. Dolt<br>1 commit/db | 4. Dolt<br>1 INSERT/row | 5. Dolt<br>1 commit/row |
|---|---:|---:|---:|---:|---:|---:|
| `employees` | 3,919,015 | 178.3 MB<br>12s | 178.3 MB<br>**1.00×**<br>2,841s | 42.5 MB<br>**0.24×**<br>36s | 37.5 MB<br>**0.21×**<br>1.7h | —<br>— |
| `wikipedia_simple` | 1,167,112 | 318.2 MB<br>19s | 374.2 MB<br>**1.18×**<br>1,024s | 123.5 MB<br>**0.39×**<br>132s | 123.0 MB<br>**0.39×**<br>2,290s | —<br>— |
| `oracle_sh` | 1,063,396 | 220.2 MB<br>11s | 220.2 MB<br>**1.00×**<br>734s | 143.4 MB<br>**0.65×**<br>58s | 134.0 MB<br>**0.61×**<br>2,872s | —<br>— |
| `adventureworks` | 759,240 | 335.9 MB<br>10s | 335.9 MB<br>**1.00×**<br>463s | 49.0 MB<br>**0.15×**<br>25s | 48.5 MB<br>**0.14×**<br>2,331s | 15.1 GB<br>**46×**<br>1.8h |
| `contoso` | 753,467 | 156.3 MB<br>7s | 156.3 MB<br>**1.00×**<br>469s | 39.3 MB<br>**0.25×**<br>20s | 39.3 MB<br>**0.25×**<br>1,627s | 11.2 GB<br>**73×**<br>3,000s |
| `lahman` | 706,466 | 191.8 MB<br>9s | 191.8 MB<br>**1.00×**<br>453s | 26.3 MB<br>**0.14×**<br>22s | 26.3 MB<br>**0.14×**<br>1,607s | 8.5 GB<br>**45×**<br>2,957s |
| `chicago_crimes` | 259,702 | 84.1 MB<br>5s | 84.1 MB<br>**1.00×**<br>190s | 28.7 MB<br>**0.34×**<br>16s | 28.8 MB<br>**0.34×**<br>839s | 10.3 GB<br>**125×**<br>1,314s |
| `dvdstore` | 174,716 | 60.0 MB<br>2s | 60.1 MB<br>**1.00×**<br>120s | 11.9 MB<br>**0.20×**<br>5s | 11.9 MB<br>**0.20×**<br>345s | 3.3 GB<br>**57×**<br>699s |
| `stackexchange_beer` | 62,523 | 82.6 MB<br>2s | 88.6 MB<br>**1.07×**<br>47s | 14.1 MB<br>**0.17×**<br>14s | 13.9 MB<br>**0.17×**<br>157s | 2.0 GB<br>**24×**<br>310s |
| `enron` | 48,778 | 94.2 MB<br>2s | 134.2 MB<br>**1.42×**<br>43s | 34.2 MB<br>**0.36×**<br>46s | 34.2 MB<br>**0.36×**<br>242s | 5.9 GB<br>**64×**<br>460s |
| `nyc_taxi` | 48,591 | 19.1 MB<br>1s | 19.1 MB<br>**1.00×**<br>37s | 3.0 MB<br>**0.16×**<br>4s | 3.0 MB<br>**0.16×**<br>104s | 928.6 MB<br>**49×**<br>200s |
| `sakila` | 47,268 | 24.1 MB<br>1s | 24.1 MB<br>**1.00×**<br>36s | 2.0 MB<br>**0.08×**<br>4s | 2.0 MB<br>**0.08×**<br>109s | 709.6 MB<br>**29×**<br>271s |
| `chinook` | 15,607 | 2.7 MB<br>0s | 2.7 MB<br>**1.00×**<br>13s | 615.0 KB<br>**0.22×**<br>1s | 615.0 KB<br>**0.22×**<br>31s | 112.8 MB<br>**42×**<br>72s |
| `oracle_oe` | 11,518 | 27.5 MB<br>1s | 27.6 MB<br>**1.00×**<br>11s | 4.3 MB<br>**0.16×**<br>5s | 4.2 MB<br>**0.15×**<br>50s | 818.2 MB<br>**30×**<br>94s |
| `oracle_co` | 8,783 | 1.8 MB<br>0s | 1.8 MB<br>**1.00×**<br>7s | 456.3 KB<br>**0.24×**<br>1s | 456.3 KB<br>**0.24×**<br>17s | 68.3 MB<br>**37×**<br>42s |
| `adventureworks_lt` | 4,277 | 12.5 MB<br>1s | 12.5 MB<br>**1.00×**<br>5s | 1.0 MB<br>**0.08×**<br>1s | 1.0 MB<br>**0.08×**<br>9s | 37.6 MB<br>**3.01×**<br>22s |
| `northwind` | 3,308 | 2.6 MB<br>1s | 2.6 MB<br>**1.00×**<br>4s | 519.5 KB<br>**0.19×**<br>2s | 519.5 KB<br>**0.19×**<br>8s | 26.4 MB<br>**10×**<br>18s |
| `smallsets` | 2,147 | 644.0 KB<br>0s | 644.0 KB<br>**1.00×**<br>2s | 164.3 KB<br>**0.26×**<br>1s | 164.3 KB<br>**0.26×**<br>6s | 8.2 MB<br>**13×**<br>10s |
| `jaffle_shop` | 312 | 372.0 KB<br>0s | 372.0 KB<br>**1.00×**<br>0s | 37.7 KB<br>**0.10×**<br>1s | 37.7 KB<br>**0.10×**<br>1s | 721.7 KB<br>**1.94×**<br>2s |
| `pubs` | 255 | 1.5 MB<br>0s | 1.5 MB<br>**1.00×**<br>0s | 77.0 KB<br>**0.05×**<br>1s | 77.0 KB<br>**0.05×**<br>2s | 945.9 KB<br>**0.63×**<br>2s |
| `oracle_hr` | 216 | 1.1 MB<br>0s | 1.1 MB<br>**1.00×**<br>1s | 62.8 KB<br>**0.06×**<br>1s | 62.8 KB<br>**0.06×**<br>1s | 858.9 KB<br>**0.78×**<br>2s |
| **all 18 with every test** | **2,907,174** | **1.1 GB<br>45s** | **1.04×<br>42× time** | **0.20×<br>3.8× time** | **0.20×<br>167× time** | **55×<br>358× time** |

*Each cell is disk then time. 3 database(s) do not yet have every test and are excluded from the totals row: `employees`, `oracle_sh`, `wikipedia_simple`.*
<!-- results:end -->

![What each load costs](docs/img/cost-by-mode.png)

![Disk used, every database, every load](docs/img/disk-by-database.png)

![Disk as a ratio of MySQL](docs/img/ratio-by-database.png)

![Time to load, every database, every load](docs/img/time-by-database.png)

And what the index policy is worth — tests 2, 4 and 5 run a second time with every index maintained
throughout, as a change against dropping them and rebuilding at the end:

![What maintaining the indexes costs](docs/img/index-policy.png)

[`REPORT.md`](REPORT.md) has the same numbers with the per-test analysis and the validity checks.
[`JOURNAL.md`](JOURNAL.md) is the lab notebook: why it is built this way, what the numbers do not
support, and what went wrong along the way.

## Reproducing this

You need Docker, Python 3.11+, and a running `mysql-megasamples` — it is the source of every dump,
and building it is itself a long job (see that repository's README; `make image` there fetches and
loads 21 datasets).

**Budget before you start.** The full run took **18.5 hours** on the machine below and needs
**roughly 200 GB of free disk** — nearly all of it for the per-row-commit loads, whose cost per row
varies by a factor of fifty across these databases, so it cannot be projected from a small sample.
The other four loads together finish in about eight hours and need about 3 GB.

```sh
cd ../mysql-megasamples && make up      # MySQL on 3306, its consoles on 8080-8084
cd ../dolt-megasamples
make down                               # stop this repo's own stack: a running Dolt server
                                        # writes into the directories being measured
make export                             # mysqldump every database, both statement styles
make run                                # all five loads, indexes deferred — the primary result
python3 scripts/run_all.py --indexes inline   # tests 2, 4 and 5 again, indexes maintained
make report                             # REPORT.md, the README tables, and every figure
```

`make run` takes `--repeat N` (up to N samples per unit, median kept, spread recorded) and
`--repeat-budget S` (stop repeating a unit after S seconds, so the cheap loads get a spread without
the expensive ones tripling the run). The published numbers use `--repeat 3 --repeat-budget 180`.

`build/results.json` is committed, because it is the evidence. That would otherwise be a trap for
you: a fresh clone already carries completed units, and a resume would skip them and republish
measurements from this machine as if they were yours. `make run` compares a host fingerprint and
starts clean when it does not match, so you get your own numbers by default; `--resume` overrides
that deliberately. `build/progress.json` is **not** committed — it is run state that any partial run
rewrites, and everything a reader needs from it is folded into `results.json`.

`make report` regenerates the visualizations as part of its output, so a reproduction produces the
whole report and not just numbers. `make environment` records your machine into the tables above.

**It runs for a long time and is built to be watched.** Every unit of work is written to
`build/progress.json` the moment it finishes:

```sh
make progress      # what is done, what is running, how long each phase took, what is left
make watch         # the same, redrawn every minute
```

The run is **resumable** — a completed unit is skipped, so it can be stopped and picked up with
`make run` — and units go cheapest-first and smallest-first, so results accrue from the top rather
than arriving all at once at the end.

The run stops itself before a unit that would take free space below `--floor-gb` (8 GB by default),
and stops rather than continuing if the Docker daemon stops answering — an earlier run recorded a
load that never happened as successful because the daemon restarted underneath it. Recorded progress
is kept either way, so freeing space and re-running the same command picks up where it left off.
`scripts/disk_guard.py` watches from outside if you would rather be warned than stopped.

The per-row-commit load writes tens of gigabytes and its cost per row varies by a factor of fifty
across these databases, so the space it needs cannot be projected reliably from a small sample.

## Running the databases

Both stacks can run at once — the ports are one range apart — so the same query can go side by side
against the same data in two engines.

| | mysql-megasamples | dolt-megasamples |
|---|---|---|
| database | `127.0.0.1:3306` | `127.0.0.1:3307` |
| landing page | <http://127.0.0.1:8080/> | <http://127.0.0.1:8090/> |
| phpMyAdmin | 8081 | 8091 |
| Adminer | 8082 | 8092 |
| DbGate | 8083 | 8093 |
| CloudBeaver | 8084 | 8094 |
| **Dolt Workbench** | — | **8095** |

```sh
make up      # Dolt plus its consoles
make down
```

The accounts are the same on both sides: `demo` / `demo` reads, `admin` / `admin` writes. Each
console opens on the read-only one.

**Dolt Workbench** at <http://127.0.0.1:8095/> is the only one that shows what makes Dolt Dolt —
branches, commits, and diffs between them. It is also the only console that cannot be preconfigured,
so enter the connection once: type MySQL, URL `mysql://admin:admin@dolt:3306/sakila`. Use `dolt`, not
`127.0.0.1`: its API connects from inside the compose network.

## Layout

| path | what it holds |
|---|---|
| `REPORT.md` | the full comparison, generated |
| `JOURNAL.md` | the lab notebook: reasoning, caveats, and what went wrong |
| `scripts/run_all.py` | the five loads, timed, resumable, observable |
| `scripts/progress.py` | what the run has done and has left |
| `scripts/export_mysql.py` | one `mysqldump` per database, both statement styles |
| `scripts/dolt_dialect.py` | the transformations Dolt needs, and why each exists |
| `scripts/measure.py` | rows, indexes and sizes; the fairness checks |
| `scripts/report.py` | `REPORT.md` and the README tables |
| `scripts/charts.py` | the figures |
| `scripts/environment.py` | the machine, recorded |
| `scripts/check_claims.py` | pins the prose numbers to the measurements |
| `build/results.json` | every measurement — the evidence behind the report |

`build/dumps/`, `data/` and `build/progress.json` are gitignored: the first two are large and
reproducible, and the third is run state that any partial run rewrites. The results, the report and
the figures are committed, because they are the findings.

## Licence

Project code is **Apache-2.0** — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

**The data is not covered by it and is not redistributed here.** No sample data is committed:
`make export` pulls it from your own running `mysql-megasamples`, where each dataset keeps its
upstream licence — several are CC BY-SA and share-alike. If you publish anything built from those
databases, the obligations that travel with them are in that repository's `LICENSES.md` and
`NOTICE.md`, and Apache-2.0 does nothing to satisfy them.
