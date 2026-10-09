# dolt-megasamples

The sample databases of [sql-megasamples](https://github.com/Reliable-Collaboration/sql-megasamples),
loaded into DoltHub's three versioned engines and served beside a set of web consoles:

* **[Dolt](https://github.com/dolthub/dolt)**, which speaks MySQL's protocol, in place of MySQL;
* **[DoltgreSQL](https://github.com/dolthub/doltgresql)**, which speaks PostgreSQL's, in place of PostgreSQL;
* **[DoltLite](https://github.com/dolthub/doltlite)**, a SQLite with a versioned storage engine, in place of SQLite.

Each is a SQL database with Git's model underneath: commits, branches, merges and diffs of the data
itself. What sets this apart from loading a dump yourself is that you choose **what history each
database has had** when it arrives: a single commit holding the whole database, ready to branch and
change; or a commit for every row, in the order the corpus dumps them, so there is a long log to
browse, diff and travel back through. A database can be served with both side by side.

You pick the engines, the databases and the history in one file; `make run` builds them from your
sql-megasamples checkout, checks every one against the corpus, and `make up` serves them.

<p align="center">
  <img src="docs/screenshots/workbench.png" width="32%" alt="Dolt Workbench: the commit log of sakila_per_row, a commit for every row">
  <img src="docs/screenshots/landing.png" width="32%" alt="The landing page: the consoles, how to connect, and every database served">
  <img src="docs/screenshots/cloudbeaver.png" width="32%" alt="CloudBeaver: sakila's film table on Dolt">
</p>
<p align="center"><sub>Dolt Workbench on <code>sakila_per_row</code>, a commit for every row; the landing page on
<code>http://127.0.0.1:8090/</code>; CloudBeaver on Dolt. Retake them with <code>make screenshots</code>.</sub></p>

## Quick start

```sh
# 1. sql-megasamples, built for the engines you want here (MySQL for Dolt, PostgreSQL for
#    DoltgreSQL, SQLite for DoltLite), beside this checkout -- see its README
git clone https://github.com/Reliable-Collaboration/sql-megasamples ../sql-megasamples

# 2. this repository
cp dolt-megasamples.example.yaml dolt-megasamples.yaml    # optional; edit it
make run           # export from sql-megasamples, build every configured store, check each one
make up            # start the stack, then open http://127.0.0.1:8090/
make test          # prove it answers: both accounts, every store's rows and history, every console
```

Without a `dolt-megasamples.yaml` the default applies: the 21 core databases in all three engines,
each with a single commit, and every console. `make list` shows what the configuration names, and
`make status` what of it is built.

You need:

* **sql-megasamples, built** with the source engines you need: its images (`sql-megasamples-mysql:dev`
  and the others) or its running servers are where every database comes from. It does not have to be
  running; `make export` starts a short-lived container from its image when it is not.
* **Docker** (Engine or Desktop) with Compose. Rootless Podman works too, behind Docker's own client
  pointed at Podman's Docker-compatible socket (`docker context create podman --docker
  host=unix:///run/user/$UID/podman/podman.sock && docker context use podman`).
* **Python 3.11 or newer**. The Makefile makes `.venv` with the one dependency, PyYAML (with
  [`uv`](https://docs.astral.sh/uv/) when it is installed, else with `venv` and `pip`).
* **Room**, which depends on the history: a single commit needs disk of the order of the source
  database; a commit per row needs far more disk, memory and time, so try it on a small database first.

## The two histories

| history | what the store holds | served as | build |
|---|---|---|---|
| `single` | the database in one commit, as the corpus has it | `sakila` | quick: one replay of the dump |
| `per-row` | one commit per row, then one last commit that adds the indexes | `sakila_per_row` | slow: a commit per row, hours for the largest databases |

Both end as the same data: every table holds exactly the rows the corpus holds, which the build
checks. They differ in the log. In a per-row store, `SELECT * FROM dolt_log` lists a commit for every
row; `dolt_diff` between two of them is that row; checking out an early commit gives the database as
it was a few rows in. The single store's log is the import and nothing else, which is what you want
for a database to branch from and change.

A per-row history is expensive in every dimension, and the cost grows with the number of rows: to
write (each commit is a write of the history), to keep (the store is many times the single one) and
to open (a server holds what it opens, so `memory:` may need raising to serve one). How much, engine
by engine and database by database, is what
[dolt-unofficial-benchmarking](https://github.com/Reliable-Collaboration/dolt-unofficial-benchmarking)
measures.

The largest database is past what a modest machine can give Dolt. employees' per-row history is 3.9
million commits: built here under a 10 GiB `memory.build`, with the store collected every 10 chunks,
the replay itself stayed near 3 GiB, but the last commit and collection needed more than 8 GiB and the
host, shared with other services, ran out first (2026-10-08); the benchmark's store of the same
history takes 12 GiB just to open. Ask for a per-row history that large only on a machine with
that much memory to spare; every other database's per-row history opens in Dolt within 1.5 GiB.

## The engines

### Dolt

A MySQL-compatible server on **127.0.0.1:3307**, built from sql-megasamples' MySQL dumps. Version
control is SQL: `SELECT * FROM dolt_log`, `SELECT * FROM dolt_diff('HEAD~1', 'HEAD', 'film')`,
`CALL dolt_checkout('-b', 'mine')`, `CALL dolt_commit('-Am', 'my change')`.

### DoltgreSQL

A PostgreSQL-compatible server on **127.0.0.1:5433**, built from sql-megasamples' PostgreSQL dumps.
The same version control, as functions: `SELECT * FROM dolt_log`, `SELECT dolt_checkout('-b', 'mine')`.
DoltgreSQL scans every table when it opens a store, so a per-row history takes minutes to come up;
the stack allows it half an hour.

### DoltLite

Files, not a server: `/data/<name>.doltlite` in the `doltsamples-doltlite` container, built from
sql-megasamples' SQLite files by replaying their dumps (opening a stock SQLite file in DoltLite would
leave it on SQLite's own storage, with no history). Open one with
`docker exec -it doltsamples-doltlite doltlite /data/sakila.doltlite`, or copy it out with
`docker cp doltsamples-doltlite:/data/sakila.doltlite .`. A DoltLite file is not SQLite pages: the
`doltlite` shell, `libdoltlite` and the Dolt Workbench open it; `sqlite3` cannot.

### What each engine does not take

Each engine is given its source's dump rewritten into its dialect, and every rule that rewrites it
is in `doltsamples/dialects/` with the refusal that made it necessary. No rule touches a row. What an
engine still refuses -- Dolt does not implement stored functions, so sakila's three are not there;
DoltgreSQL cannot yet parse some views -- is recorded for each store in `build/stores.json` with the
engine's own message, and `make status` says how many. The rules and the defects behind them:
[`knowledge/decisions/pair-dialect-rules.md`](knowledge/decisions/pair-dialect-rules.md) and
[`knowledge/decisions/engine-bugs-patch-or-work-around.md`](knowledge/decisions/engine-bugs-patch-or-work-around.md).

## Connect with your own tool

Two accounts on each server, the same as sql-megasamples': **`demo`** reads everything, **`admin`**
can do anything. Passwords are `demo` and `admin` unless `.env` sets `DEMO_PASSWORD` and
`ADMIN_PASSWORD`.

| engine | address | client | URL |
|---|---|---|---|
| Dolt | 127.0.0.1:3307 | `mysql -h 127.0.0.1 -P 3307 -u demo -pdemo sakila` | `mysql://demo:demo@127.0.0.1:3307/sakila` |
| DoltgreSQL | 127.0.0.1:5433 | `PGPASSWORD=demo psql -h 127.0.0.1 -p 5433 -U demo -d sakila` | `postgresql://demo:demo@127.0.0.1:5433/sakila` |
| DoltLite | a file | `docker exec -it doltsamples-doltlite doltlite /data/sakila.doltlite` | — |

The engines' own superusers are `root` / `root` on Dolt and `postgres` / `doltsamples` on DoltgreSQL
(`DOLT_ROOT_PASSWORD`, `DOLTGRES_PASSWORD`). The landing page on 8090 lists every database served,
with its history, rows, commits and size, and says the same for your configuration's ports.

## The consoles

| console | port | reads | |
|---|---|---|---|
| landing page | 8090 | — | every database served and how to connect |
| [Dolt Workbench](https://github.com/dolthub/dolt-workbench) | 8095 (API 9002) | Dolt, DoltgreSQL, DoltLite | branches, commits and diffs, which the others cannot show; every account and every DoltLite file is a saved connection |
| [phpMyAdmin](https://www.phpmyadmin.net/) | 8091 | Dolt | signed in; the server menu switches account |
| [Adminer](https://www.adminer.org/) | 8092 | Dolt, DoltgreSQL | log in as MySQL server `dolt` or PostgreSQL server `doltgres` |
| [DbGate](https://dbgate.org/) | 8093 | Dolt, DoltgreSQL | connections preconfigured |
| [CloudBeaver](https://dbeaver.com/docs/cloudbeaver/) | 8094 | Dolt, DoltgreSQL | open as a guest; connections preconfigured |

Each starts only when an engine it reads is served. Everything binds to 127.0.0.1, one range above
sql-megasamples' ports (3306, 5432, 8080-8084), so both stacks can run at once.

## The configuration file

`dolt-megasamples.yaml` is read by every command;
[`dolt-megasamples.example.yaml`](dolt-megasamples.example.yaml) explains every key.

```yaml
corpus: ../sql-megasamples        # where sql-megasamples is checked out and built
engines:
  dolt:
    single: core                  # a selector sql-megasamples understands: core, quick, all, a tier
    per-row: [sakila, chinook]    # or a list; served as sakila_per_row, chinook_per_row
  doltgres:
    single: quick
  doltlite:
    per-row: [sakila]
consoles: [landing, workbench, phpmyadmin, adminer, dbgate, cloudbeaver]
ports: {dolt: 3307, doltgres: 5433, landing: 8090}      # any you leave out keep their defaults
memory: {dolt: 2g, doltgres: 2g, build: 12g}            # servers, and one build container
```

Change it and run `make run` then `make up` again: what is already built and still current is kept,
anything new is built, and the stack is rewritten to serve exactly what the file names.

## Building piece by piece

`make run` is `make export` then `make build`. Each step can be run on its own, and each takes
`ARGS`:

```sh
make export ARGS="--only sakila"        # take sakila's dumps out of the corpus (build/exports/)
make build  ARGS="--only sakila"        # build sakila wherever the configuration names it (data/)
make build  ARGS="--engine doltgres --force"   # rebuild every DoltgreSQL store
make status                             # what is built, failed or stale
make compose                            # write compose.yaml without starting anything
make down                               # stop the stack (the stores stay)
make clean                              # remove the stores; make clean-all removes the exports too
```

How a store is built, in order: the export of its source engine is rewritten by the engine's dialect
rules; it is replayed into a fresh store in a container of its own, under `memory.build`; for the
per-row history every INSERT is followed by a commit, and Dolt's replay runs in chunks with its store
collected between them; the store is committed and collected (`dolt gc`, DoltLite's `VACUUM`), so it is
served at its settled size; and it is checked against the reference the export recorded -- every
table's row count, and for DoltgreSQL and DoltLite the index set -- before it is recorded as built. A
store that is short of a row is recorded as failed and never served. `build/stores.json` records each
store with the engine version that wrote it and the digest of the export it came from; a store whose
record still matches is not built again.

`compose.yaml` is generated by `make up` (and `make compose`), so after that `docker compose` works on
its own: `docker compose logs dolt`, `docker compose restart doltgres`.

## Versions

`versions.json` names the release of each engine this checkout builds with: Dolt and DoltgreSQL by
the image digest Docker Hub publishes for the release, DoltLite by the SHA-256 of its two Debian
packages (DoltLite ships no image, so `make lite-image` builds one), and the `sqlite3` shell that image
carries, built from sqlite.org's newest release, by its source tarball's checksums.

```sh
make versions      # each engine here beside the newest release upstream
make update        # move them all to the newest (ENGINE=dolt for one)
make lite-image    # rebuild the DoltLite image if DoltLite or SQLite moved
make build         # rebuild every store an older release wrote
```

Nothing moves on its own; a store built by an older release shows as stale in `make status` until it
is rebuilt.

## Measuring them

How much a Dolt engine costs against the database it stands in for -- in disk, time and memory, for
each history, on every database -- is
[dolt-unofficial-benchmarking](https://github.com/Reliable-Collaboration/dolt-unofficial-benchmarking),
which builds its stores with this repository's exports and dialect rules and loads the same data into
MySQL, PostgreSQL and SQLite beside them. Its results, and the bug reports the measurements led to,
live there; this repository's history before October 2026 is that project's history too.

## How the repository is laid out

```
dolt-megasamples.example.yaml   the configuration, every key explained
Makefile                        one target per command
doltsamples/                    the package: python3 -m doltsamples <command>
  config.py                     reads dolt-megasamples.yaml; asks sql-megasamples what core, quick ... mean
  corpus.py                     make export: the dumps and the reference each store is checked against
  dialects/                     what each engine needs changed in its source's dump, and why
  build.py                      make build: replay, commit, collect, check, record
  catalog.py                    reading a database back: rows, indexes, objects; comparing with the reference
  stack.py                      make up: compose.yaml, the consoles' connections, build/serve.json
  landing.py, check.py          the landing page; make test
  versions.py, lite_image.py    the engines' releases; the DoltLite image
docker/                         the accounts' init scripts, the consoles' configuration, the DoltLite Dockerfile
knowledge/                      the decisions behind all of it, and the evidence for them
build/                          generated: exports, prepared dumps, stores.json, serve.json
data/                           generated: the stores, and the served bases
```

## Licensing

The code is Apache-2.0 ([`LICENSE`](LICENSE), [`NOTICE`](NOTICE)). It covers no data: this
repository redistributes no sample data, and every database keeps its upstream licence, which
sql-megasamples records -- several are CC BY-SA, with attribution and share-alike obligations that
travel with any copy of a store you build here.
