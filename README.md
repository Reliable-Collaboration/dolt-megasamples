# dolt-megasamples

**An experiment: how much disk does the same data cost in Dolt compared with MySQL?**

[Dolt](https://github.com/dolthub/dolt) is a SQL database with Git-like versioning — branches,
commits, diffs and merges over tables — and it speaks the MySQL wire protocol, so the same clients
work against both. It also stores data in an entirely different way: MySQL's InnoDB writes B-tree
pages into a tablespace per table, while Dolt writes content-addressed chunks into prolly trees.
Those are different enough that "how big will it be?" is not a question you can answer by reasoning
about it.

So this repository answers it by measurement. It takes the 21 sample databases from
[`mysql-megasamples`](https://github.com/Reliable-Collaboration/mysql-megasamples) — 9,056,697 rows
of real, varied, publicly-licensed data — loads every one into both engines from the same
`mysqldump` files, and measures what each engine puts on the filesystem.

**The repository is the evidence.** Every number and every chart below is generated from
`build/results.json`; nothing here is typed by hand. Re-run `make all` and they regenerate from your
own machine. [`JOURNAL.md`](JOURNAL.md) is the lab notebook — why it was built this way, what the
numbers do *not* support, and what went wrong along the way.

## The result

![All 21 databases: MySQL 1,523 MB against Dolt 525 MB](docs/img/totals.png)

The same 9,056,697 rows cost **a third as much in Dolt** as in MySQL — but that headline is the least
useful number here, because the per-database ratio varies by more than ten to one.

![Dolt ÷ MySQL for each database](docs/img/ratio-by-database.png)

![Disk used per database](docs/img/size-by-database.png)

<!-- results:start -->
| database | rows | MySQL | Dolt<br>one commit | Dolt<br>row INSERTs | Dolt<br>commit per row | Dolt ÷ MySQL |
|---|---:|---:|---:|---:|---:|---:|
| `adventureworks` | 759,240 | 292.2 MB | 48.7 MB | — | — | **0.17×** |
| `wikipedia_simple` | 1,167,112 | 208.2 MB | 123.2 MB | — | — | **0.59×** |
| `oracle_sh` | 1,063,396 | 188.4 MB | 143.6 MB | — | — | **0.76×** |
| `lahman` | 706,466 | 178.9 MB | 26.3 MB | — | — | **0.15×** |
| `employees` | 3,919,015 | 176.3 MB | 42.6 MB | — | — | **0.24×** |
| `contoso` | 753,467 | 135.3 MB | 39.3 MB | — | — | **0.29×** |
| `stackexchange_beer` | 62,523 | 73.6 MB | 14.0 MB | — | — | **0.19×** |
| `chicago_crimes` | 259,702 | 72.1 MB | 28.9 MB | 28.8 MB | — | **0.40×** |
| `enron` | 48,778 | 66.2 MB | 34.3 MB | — | — | **0.52×** |
| `dvdstore` | 174,716 | 50.0 MB | 11.9 MB | 11.9 MB | — | **0.24×** |
| `sakila` | 47,268 | 22.3 MB | 2.0 MB | — | — | **0.09×** |
| `oracle_oe` | 11,518 | 19.7 MB | 4.4 MB | 4.2 MB | 815.6 MB | **0.22×** |
| `nyc_taxi` | 48,591 | 16.1 MB | 3.0 MB | — | — | **0.19×** |
| `adventureworks_lt` | 4,277 | 12.6 MB | 1.0 MB | 1.0 MB | 37.5 MB | **0.08×** |
| `northwind` | 3,308 | 2.8 MB | 519.5 KB | 519.5 KB | 26.6 MB | **0.18×** |
| `chinook` | 15,607 | 2.6 MB | 615.0 KB | 615.0 KB | 112.4 MB | **0.23×** |
| `oracle_co` | 8,783 | 1.8 MB | 456.3 KB | 456.3 KB | 68.4 MB | **0.25×** |
| `pubs` | 255 | 1.5 MB | 77.0 KB | 77.0 KB | 758.3 KB | **0.05×** |
| `oracle_hr` | 216 | 1.2 MB | 62.8 KB | 62.8 KB | 786.1 KB | **0.05×** |
| `smallsets` | 2,147 | 644.0 KB | 164.3 KB | 164.3 KB | 8.3 MB | **0.26×** |
| `jaffle_shop` | 312 | 372.0 KB | 37.7 KB | 37.7 KB | 738.6 KB | **0.10×** |
| **all 21** | **9,056,697** | **1.5 GB** | **524.8 MB** | **47.8 MB** | — | **0.34×** |
<!-- results:end -->

[`REPORT.md`](REPORT.md) has the full table, including what `information_schema` thinks MySQL is
using and the size of the SQL dump each engine was loaded from.

## But it depends entirely on how you write the rows

The figures above are one load: the whole database in a single Dolt commit. Dolt is a *version
controlled* database, so the obvious next question is what the version control costs. Two more loads
of the same data, one question each.

![The same rows written four ways](docs/img/commit-granularity.png)

**One `INSERT` per row instead of extended `INSERT`s changes nothing that is stored** — every green
bar sits on its orange one: within 0.5% for ten of the eleven databases measured, eight of them
byte-identical, and 4.1% for the one outlier. Statement batching
is a load-time concern, not a storage one.

**One commit per row changes everything.** The same rows cost **10× to 187×** the single-commit load,
and for seven of the nine databases Dolt then uses *more* disk than MySQL — `chinook` goes from 615 KB
to 112 MB. In a controlled check, 1,000 rows in one commit is 16,202 bytes and the same 1,000 rows in
1,000 commits is 2,929,110 bytes: **181× for identical data**.

That is not waste to be tuned away — it is what the product is for. Each commit is an addressable,
diffable state of the entire database, and a million of them cost what a million of anything costs.
The practical question is not "is Dolt bigger" but **"what does my commit rate cost me"**, and the
answer scales with commits, not with rows.

[`REPORT.md`](REPORT.md) has both tables in full. The per-row-commit load was run on the nine
smallest databases: at the measured rate, all 9 million rows would need tens of gigabytes and several
hours, and would show nothing the small ones do not.

## What the spread means

The headline ratio is the least interesting number here. The per-database ratios differ by more than
a factor of ten, and the reasons are visible in the data:

* **Small databases favour Dolt heavily.** InnoDB allocates a tablespace per table whether or not
  there is anything in it, so a database of a few hundred rows spread over a dozen tables is mostly
  empty pages. `pubs` and `oracle_hr` are the extreme cases.
* **Wide, low-cardinality tables compress well in Dolt.** `lahman` and `adventureworks` are many
  narrow columns with heavy repetition.
* **Text-heavy data narrows the gap.** `enron` (raw email bodies) and `wikipedia_simple` (article
  text) are the two where Dolt's advantage is smallest, because neither engine can do much with
  incompressible prose.
* **`oracle_sh` is the closest of all** — a star schema whose fact table is nearly a million rows of
  dense numeric columns, which is close to the best case for InnoDB's row format.

## Running it yourself

You need `mysql-megasamples` running, because it is the source of every dump:

```sh
cd ../mysql-megasamples && make up      # MySQL on 3306, its consoles on 8080-8084
cd ../dolt-megasamples  && make all     # export -> load -> measure -> report
```

`make all` takes a few minutes, most of it loading. Then bring the Dolt side up:

```sh
make up          # Dolt on 3307, its own consoles on 8090-8094
make down
```

Both stacks can run at once — that is why the ports are one range apart — so you can put the same
query side by side against the same data in two engines.

| | mysql-megasamples | dolt-megasamples |
|---|---|---|
| database | `127.0.0.1:3306` | `127.0.0.1:3307` |
| landing page | <http://127.0.0.1:8080/> | <http://127.0.0.1:8090/> |
| phpMyAdmin | 8081 | 8091 |
| Adminer | 8082 | 8092 |
| DbGate | 8083 | 8093 |
| CloudBeaver | 8084 | 8094 |
| **Dolt Workbench** | — | **8095** |

The accounts are the same on both sides: `demo` / `demo` can only read, `admin` / `admin` can do
anything. Each console opens on the read-only one.

### Dolt Workbench, for the part the others cannot show

phpMyAdmin, Adminer, DbGate and CloudBeaver all see Dolt as a MySQL server, which means they show
tables and rows and nothing of what makes it Dolt. [Dolt
Workbench](https://github.com/dolthub/dolt-workbench) at <http://127.0.0.1:8095/> shows the branches,
the commit log and the diff between any two commits.

It is the only console here that cannot be preconfigured — it reads no connection from the
environment — so enter it once:

| field | value |
|---|---|
| type | MySQL |
| connection URL | `mysql://admin:admin@dolt:3306/sakila` |
| name | anything |

`dolt`, not `127.0.0.1`: the Workbench's own API makes the connection from inside the compose
network, and only your browser talks to `127.0.0.1`.

Every database here has one branch, `main`, and three commits — Dolt's `Initialize data repository`
and `CREATE DATABASE`, then the single `import from mysql-megasamples` that carries the whole
database. That is deliberate, and it is why the sizes below are Dolt's floor rather than a typical
working repository.

## How the comparison is kept honest

A size comparison is worthless if the two sides are not holding the same thing, so:

* **Every table is counted on both sides** with `COUNT(*)` before any size is recorded.
  `information_schema.table_rows` is an InnoDB estimate and is not used. All 21 databases match.
* **Every index is compared by definition** — table, index name, column position, column,
  uniqueness — not by count. Indexes are a large part of what a database costs on disk, so a
  comparison where one engine had quietly dropped some would be worthless. **613 in MySQL, 613 in
  Dolt, identical in every database.**
* **The history is the least Dolt can hold**: one data commit per database, and `dolt_status` clean
  afterwards so nothing sits uncommitted and unmeasured. Rows are *not* committed individually. A
  branch or a week of edits would store more — this is the floor, not a typical repository.
* **Everything is measured with no server running**, and what a server adds is measured separately
  on a copy. `dolt sql-server` writes a per-database statistics repository at `.dolt/stats` that
  `dolt gc` does not reclaim. A controlled pass — start a server, read every table — writes 22 KB per
  database. Sustained use writes far more: during this project's own console browsing,
  `adventureworks`'s statistics reached **68.2 MB — more than the 48.7 MB of data they describe**,
  which a single pass does not reproduce. Mixing served and unserved directories is what made an
  earlier total move by 68 MB for no visible reason.
* **Dolt is committed and garbage-collected before measuring.** Dolt is a versioned database; data
  left in the working set is not yet in the commit graph, and Dolt writes through a journal until
  told to pack. Measuring before either step flatters it — `jaffle_shop` is 35,550 bytes after its
  commit and 16,951 after `dolt gc`.
* **Both sides are measured the same way**: `du -sb` of the directory the engine keeps the database
  in. Not `information_schema`, which under-reports MySQL by ignoring free pages in the tablespace.
* **The dumps are transformed only where Dolt cannot parse mysqldump's output**, never in a way that
  touches a row. `scripts/dolt_dialect.py` documents each rule and why it exists.

## What Dolt would not accept

Recorded rather than smoothed over, because it is a result too:

* **Cross-database foreign keys.** `oracle_oe.customers` references `oracle_hr.employees`; Dolt keeps
  each database as its own repository and says so — *"only foreign keys on the same database are
  currently supported"*. Three such constraints are dropped when loading. Without that, the whole
  database fails to load and measures 56 KB against MySQL's 19.7 MB.
* **`CREATE FUNCTION`.** Stored functions do not load. `sakila` has 6 routines in MySQL and 0 in
  Dolt; `employees` 7 and 0; `pubs` 3 and 0. Views do load, once mysqldump's `ALGORITHM=` and
  `SQL SECURITY` clauses are removed.
* **mysqldump's version-gated comments** (`/*!50001 CREATE VIEW ... */`). Dolt does not parse the
  form, so views and routines silently never arrive unless the wrapper is removed first.

None of these affect a single row, which is why the row counts still match.

## Layout

| path | what it holds |
|---|---|
| `REPORT.md` | the full comparison, generated |
| `scripts/export_mysql.py` | one `mysqldump` per database |
| `scripts/dolt_dialect.py` | the transformations Dolt needs, and why each exists |
| `scripts/load_dolt.py` | load, commit, `dolt gc` |
| `scripts/measure.py` | size both engines, verify they hold the same rows |
| `scripts/report.py` | `REPORT.md` and the tables above |
| `scripts/charts.py` | the figures, with matplotlib |
| `JOURNAL.md` | the lab notebook: reasoning, caveats, and what went wrong |
| `docs/img/` | the generated figures |
| `compose.yaml` | Dolt plus four consoles, on 3307 and 8090-8094 |
| `build/results.json` | every measurement, as JSON — the evidence behind the report |

`build/dumps/` and `data/` are gitignored: they are large and reproducible. `build/results.json`,
the report and this README are committed, because they are the findings.

## Licence

Project code is **Apache-2.0** — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

**The data is not covered by it and is not redistributed here.** No sample data is committed to this
repository: `make export` pulls it from your own running `mysql-megasamples`, where each dataset
keeps its upstream licence — several are CC BY-SA and share-alike. If you publish anything built
from those databases, the obligations that travel with them are described in that repository's
`LICENSES.md` and `NOTICE.md`, and Apache-2.0 does nothing to satisfy them.
