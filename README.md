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

**The repository is the evidence.** Every number below is generated from `build/results.json` by
`scripts/report.py`; nothing in this README is typed by hand. Re-run `make all` and the numbers
regenerate from your own machine.

## The result

<!-- results:start -->
| database | rows | MySQL on disk | Dolt on disk | Dolt ÷ MySQL |
|---|---:|---:|---:|---:|
| `adventureworks` | 759,240 | 292.2 MB | 48.8 MB | **0.17×** |
| `wikipedia_simple` | 1,167,112 | 208.2 MB | 123.7 MB | **0.59×** |
| `oracle_sh` | 1,063,396 | 188.4 MB | 143.4 MB | **0.76×** |
| `lahman` | 706,466 | 178.9 MB | 26.5 MB | **0.15×** |
| `employees` | 3,919,015 | 176.3 MB | 42.5 MB | **0.24×** |
| `contoso` | 753,467 | 135.3 MB | 39.4 MB | **0.29×** |
| `stackexchange_beer` | 62,523 | 73.6 MB | 14.3 MB | **0.19×** |
| `chicago_crimes` | 259,702 | 72.1 MB | 28.8 MB | **0.40×** |
| `enron` | 48,778 | 66.2 MB | 34.3 MB | **0.52×** |
| `dvdstore` | 174,716 | 50.0 MB | 11.9 MB | **0.24×** |
| `sakila` | 47,268 | 22.3 MB | 2.1 MB | **0.09×** |
| `oracle_oe` | 11,518 | 19.7 MB | 4.4 MB | **0.22×** |
| `nyc_taxi` | 48,591 | 16.1 MB | 3.0 MB | **0.19×** |
| `adventureworks_lt` | 4,277 | 12.6 MB | 1.0 MB | **0.08×** |
| `northwind` | 3,308 | 2.8 MB | 541.6 KB | **0.19×** |
| `chinook` | 15,607 | 2.6 MB | 637.0 KB | **0.24×** |
| `oracle_co` | 8,783 | 1.8 MB | 478.3 KB | **0.26×** |
| `pubs` | 255 | 1.5 MB | 99.0 KB | **0.06×** |
| `oracle_hr` | 216 | 1.2 MB | 84.8 KB | **0.07×** |
| `smallsets` | 2,147 | 644.0 KB | 186.3 KB | **0.29×** |
| `jaffle_shop` | 312 | 372.0 KB | 59.7 KB | **0.16×** |
| **all 21** | **9,056,697** | **1.5 GB** | **526.2 MB** | **0.35×** |
<!-- results:end -->

[`REPORT.md`](REPORT.md) has the full table, including what `information_schema` thinks MySQL is
using and the size of the SQL dump each engine was loaded from.

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

The accounts are the same on both sides: `demo` / `demo` can only read, `admin` / `admin` can do
anything. Each console opens on the read-only one.

## How the comparison is kept honest

A size comparison is worthless if the two sides are not holding the same thing, so:

* **Every table is counted on both sides** with `COUNT(*)` before any size is recorded.
  `information_schema.table_rows` is an InnoDB estimate and is not used. All 21 databases match.
* **Dolt is committed and garbage-collected before measuring.** Dolt is a versioned database; data
  left in the working set is not yet in the commit graph, and Dolt writes through a journal until
  told to pack. Measuring before either step flatters it — `jaffle_shop` is 34,926 bytes before
  `dolt gc` and 15,673 after.
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
| `scripts/report.py` | `REPORT.md` and the table above |
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
