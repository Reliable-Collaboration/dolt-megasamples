"""The data, taken from a built sql-megasamples: one export per database per source engine.

  python3 -m doltsamples export [--only sakila ...] [--force] [--all]

Each Dolt engine loads the dump of the engine it stands in for, so every database is exported from
the corpus three ways, into build/exports/:

* mysql/      for Dolt.       `<db>.sql` (mysqldump's extended INSERTs, what a one-commit load replays),
                              `per-row/<db>.sql` (one INSERT per row, what a per-row history replays),
                              `<db>.reference.json` (every base table's row count, read with COUNT(*)).
* postgres/   for DoltgreSQL. `<db>.copy.sql` (pg_dump's COPY form), `<db>.inserts.sql` (one INSERT per
                              row), `<db>.schema.sql`, and `<db>.reference.json` (rows, the index set
                              and object counts, read the way the build reads a store back).
* sqlite/     for DoltLite.   `<db>.sqlite` (the corpus's file), `<db>.dump.sql` (sqlite3's .dump),
                              `<db>.schema.sql`, and `<db>.reference.json`.

The source is the corpus's own server when it is running (`docker compose up -d mysql` there), and
otherwise a short-lived container started here from the image the corpus built
(`sql-megasamples-mysql:dev`, `sql-megasamples-postgres:dev`, `sql-megasamples-sqlite:dev`) and
removed afterwards. The SQLite files are read from the corpus's build tree when it has one.

By default only what dolt-megasamples.yaml asks for is exported; `--all` exports every database the
corpus image holds. A database already exported is skipped unless `--force`.
"""
import hashlib, json, os, shutil, subprocess, sys, time

from doltsamples import catalog
from doltsamples.util import EXPORTS, TRANSIENT, ensure_dir, human, lite_image, now, rel, run

SOURCE_ENGINE = {"dolt": "mysql", "doltgres": "postgres", "doltlite": "sqlite"}
RUNNING = {"mysql": "megasamples-mysql", "postgres": "megasamples-postgres", "sqlite": "megasamples-sqlite"}
IMAGE = {"mysql": os.environ.get("MEGASAMPLES_MYSQL_IMAGE", "sql-megasamples-mysql:dev"),
         "postgres": os.environ.get("MEGASAMPLES_POSTGRES_IMAGE", "sql-megasamples-postgres:dev"),
         "sqlite": os.environ.get("MEGASAMPLES_SQLITE_IMAGE", "sql-megasamples-sqlite:dev")}
TEMPORARY = {"mysql": "doltsamples-source-mysql", "postgres": "doltsamples-source-postgres",
             "sqlite": "doltsamples-source-sqlite"}
EXPORTER = "doltsamples-sqlite-export"
NOT_SAMPLES = {"mysql", "information_schema", "performance_schema", "sys", "megasamples", "postgres"}

MYSQLDUMP = ["--no-tablespaces", "--skip-comments", "--routines", "--events", "--triggers",
             "--single-transaction", "--default-character-set=utf8mb4"]


def export_dir(source):
    return os.path.join(EXPORTS, source)


def reference_path(source, db):
    return os.path.join(export_dir(source), f"{db}.reference.json")


def reference(source, db):
    path = reference_path(source, db)
    if not os.path.exists(path):
        raise RuntimeError(f"{db} has not been exported from the corpus's {source} (make export)")
    return json.load(open(path, encoding="utf-8"))


def dump_path(source, db, per_row):
    """The file a store of this history replays."""
    if source == "mysql":
        return os.path.join(export_dir("mysql"), "per-row" if per_row else "", f"{db}.sql")
    if source == "postgres":
        return os.path.join(export_dir("postgres"), f"{db}.{'inserts' if per_row else 'copy'}.sql")
    return os.path.join(export_dir("sqlite"), f"{db}.dump.sql")


def digest(paths):
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------------------- sources ---
class Source:
    """The corpus's server for one engine: its running container, or one started from its image."""

    def __init__(self, engine):
        self.engine = engine
        self.started = False
        self.name = None

    def __enter__(self):
        running = run("docker", "inspect", "-f", "{{.State.Status}}", RUNNING[self.engine]).stdout.strip()
        if running == "running":
            self.name = RUNNING[self.engine]
            return self
        if run("docker", "image", "inspect", IMAGE[self.engine]).returncode != 0:
            sys.exit(f"neither the corpus's {RUNNING[self.engine]} container nor its image {IMAGE[self.engine]} is "
                     f"here. Build sql-megasamples with {self.engine} selected first (its `make run`).")
        self.name = TEMPORARY[self.engine]
        run("docker", "rm", "-f", self.name)
        p = run("docker", "run", "-d", "--name", self.name, "--label", TRANSIENT, "--memory", "2g", IMAGE[self.engine])
        if p.returncode != 0:
            sys.exit(f"could not start {IMAGE[self.engine]}: {p.stderr.strip()[:200]}")
        self.started = True
        self.wait()
        print(f"  . started {self.name} from {IMAGE[self.engine]}", flush=True)
        return self

    def wait(self, seconds=600):
        probe = {"mysql": ["mysql", "-uroot", "-proot", "--protocol=TCP", "-h", "127.0.0.1", "-e", "SELECT 1"],
                 "postgres": ["psql", "-U", "postgres", "-d", "postgres", "-tAc", "SELECT 1"],
                 "sqlite": ["true"]}[self.engine]
        ok = 0
        for _ in range(seconds):
            ok = ok + 1 if run("docker", "exec", self.name, *probe).returncode == 0 else 0
            if ok == 2:
                return
            time.sleep(1)
        sys.exit(f"{self.name} did not answer within {seconds}s: "
                 + run("docker", "logs", "--tail", "5", self.name).stderr[-300:])

    def __exit__(self, *exc):
        if self.started:
            run("docker", "rm", "-f", self.name)


# --------------------------------------------------------------------------------- MySQL ---
def mysql_query(container, sql):
    p = run("docker", "exec", container, "mysql", "-uroot", "-proot", "-N", "--batch", "-e", sql)
    if p.returncode != 0:
        raise RuntimeError(f"{container}: {sql[:80]}: {p.stderr.strip()[:200]}")
    return [l.split("\t") for l in p.stdout.splitlines() if l.strip()]


def mysql_databases(container):
    return sorted(r[0] for r in mysql_query(container, "SHOW DATABASES") if r[0] not in NOT_SAMPLES)


def mysqldump(container, db, out, *flags):
    ensure_dir(os.path.dirname(out))
    with open(out + ".part", "wb") as fh:
        p = subprocess.run(["docker", "exec", container, "mysqldump", "-uroot", "-proot", *MYSQLDUMP, *flags,
                            "--databases", db], stdout=fh, stderr=subprocess.PIPE)
    if p.returncode != 0:
        os.remove(out + ".part")
        raise RuntimeError(f"mysqldump {db}: {p.stderr.decode('utf-8', 'replace').strip()[:300]}")
    os.replace(out + ".part", out)
    return os.path.getsize(out)


def export_mysql(container, db):
    d = export_dir("mysql")
    sizes = {"sql": mysqldump(container, db, os.path.join(d, f"{db}.sql")),
             "per-row": mysqldump(container, db, os.path.join(d, "per-row", f"{db}.sql"), "--skip-extended-insert")}
    tables = [r[0] for r in mysql_query(container, f"SELECT table_name FROM information_schema.tables WHERE "
                                                   f"table_schema='{db}' AND table_type='BASE TABLE' ORDER BY 1")]
    rows = {t: int(mysql_query(container, f"SELECT COUNT(*) FROM `{db}`.`{t}`")[0][0]) for t in tables}
    objects = {}
    for key, sql in (("views", f"SELECT COUNT(*) FROM information_schema.views WHERE table_schema='{db}'"),
                     ("routines", f"SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema='{db}'"),
                     ("triggers", f"SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='{db}'")):
        objects[key] = int(mysql_query(container, sql)[0][0])
    version = mysql_query(container, "SELECT VERSION()")[0][0]
    return {"rows": rows, "objects": objects, "server": f"MySQL {version}", "dump_bytes": sizes}


# ---------------------------------------------------------------------------- PostgreSQL ---
def pg_databases(container):
    out = run("docker", "exec", container, "psql", "-U", "postgres", "-d", "postgres", "-tAc",
              "SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1").stdout
    return [d for d in out.split() if d not in NOT_SAMPLES]


def pg_dump(container, db, out, *flags):
    with open(out + ".part", "wb") as fh:
        p = subprocess.run(["docker", "exec", container, "pg_dump", "-U", "postgres", "--no-owner", "--no-privileges",
                            "--encoding=UTF8", *flags, db], stdout=fh, stderr=subprocess.PIPE)
    if p.returncode != 0:
        os.remove(out + ".part")
        raise RuntimeError(f"pg_dump {db} {' '.join(flags)}: {p.stderr.decode(errors='replace').strip()[:300]}")
    os.replace(out + ".part", out)
    return os.path.getsize(out)


def export_postgres(container, db):
    d = ensure_dir(export_dir("postgres"))
    sizes = {kind: pg_dump(container, db, os.path.join(d, f"{db}.{kind}.sql"), *flags)
             for kind, flags in (("copy", ()), ("inserts", ("--inserts",)), ("schema", ("--schema-only",)))}
    ref = catalog.pg_catalog(container, db)
    ref["server"] = run("docker", "exec", container, "pg_dump", "--version").stdout.strip()
    ref["dump_bytes"] = sizes
    return ref


# -------------------------------------------------------------------------------- SQLite ---
def sqlite_files(corpus):
    """{db: host path} of the corpus's SQLite build tree, or {} when it has none."""
    tree = os.path.join(corpus, "build", "sqlite")
    if not os.path.isdir(tree):
        return {}
    return {n: os.path.join(tree, n, f"{n}.sqlite") for n in sorted(os.listdir(tree))
            if os.path.exists(os.path.join(tree, n, f"{n}.sqlite"))}


def sqlite_databases(container, corpus):
    files = sqlite_files(corpus)
    if files:
        return sorted(files)
    out = run("docker", "exec", container, "sh", "-c", "ls /data/*.sqlite /shared/*.sqlite 2>/dev/null").stdout
    return sorted({os.path.basename(l)[:-len(".sqlite")] for l in out.split() if l.endswith(".sqlite")})


def export_sqlite(container, corpus, db, exporter):
    d = ensure_dir(export_dir("sqlite"))
    dest = os.path.join(d, f"{db}.sqlite")
    files = sqlite_files(corpus)
    if db in files:
        shutil.copyfile(files[db], dest + ".part")
    else:
        inside = run("docker", "exec", container, "sh", "-c",
                     f"ls /data/{db}.sqlite /shared/{db}.sqlite 2>/dev/null | head -1").stdout.strip()
        p = run("docker", "cp", f"{container}:{inside or f'/data/{db}.sqlite'}", dest + ".part")
        if p.returncode != 0:
            raise RuntimeError(f"docker cp {db}: {p.stderr.strip()[:200]}")
    os.replace(dest + ".part", dest)
    for kind, cmd in (("dump", ".dump"), ("schema", ".schema")):
        p = run("docker", "exec", exporter, "sh", "-c",
                f"sqlite3 /x/{db}.sqlite '{cmd}' > /x/{db}.{kind}.sql.part && mv /x/{db}.{kind}.sql.part /x/{db}.{kind}.sql")
        if p.returncode != 0:
            raise RuntimeError(f"sqlite3 {cmd} {db}: {p.stderr.strip()[:200]}")
    ref = catalog.lite_catalog("sqlite3", f"/x/{db}.sqlite", exporter,
                               os.path.join(d, ".catalog.sql"), "/x/.catalog.sql")
    uncounted = sorted(t for t, n in ref["rows"].items() if n is None)
    if uncounted:
        raise RuntimeError(f"{db}: the exporter's sqlite3 could not count {', '.join(uncounted)} (a shell built "
                           f"without FTS5?); nothing recorded. Its errors: {str(ref.get('catalog_errors'))[:200]}")
    ref["server"] = "sqlite3 " + run("docker", "exec", exporter, "sqlite3", "-version").stdout.strip()
    ref["dump_bytes"] = {k: os.path.getsize(os.path.join(d, f"{db}.{k}")) for k in ("sqlite", "dump.sql", "schema.sql")}
    return ref


# ---------------------------------------------------------------------------------- main ---
def export(cfg, only=None, force=False, everything=False):
    """Export what the configuration needs (or `only` those databases, or everything the corpus holds)."""
    wanted = {}
    for engine, _, db in cfg.wanted():
        wanted.setdefault(SOURCE_ENGINE[engine], set()).add(db)
    if everything:
        wanted = {"mysql": None, "postgres": None, "sqlite": None}
    if only:
        wanted = {s: set(only) for s in (wanted or {"mysql": None, "postgres": None, "sqlite": None})}
    if not wanted:
        print("dolt-megasamples.yaml asks for no databases; nothing to export")
        return 0
    failed = 0
    for source in ("mysql", "postgres", "sqlite"):
        if source not in wanted:
            continue
        print(f"== {source} (for {[e for e, s in SOURCE_ENGINE.items() if s == source][0]})", flush=True)
        with Source(source) as src:
            have = {"mysql": mysql_databases, "postgres": pg_databases}.get(source, lambda c: sqlite_databases(c, cfg.corpus))(src.name)
            dbs = sorted(have) if wanted[source] is None else [d for d in have if d in wanted[source]]
            missing = sorted((wanted[source] or set()) - set(have))
            for db in missing:
                print(f"  x {db}: the corpus's {source} does not hold it (build it there first)", flush=True)
            failed += len(missing)
            exporter = None
            if source == "sqlite":
                exporter = start_exporter()
            try:
                for db in dbs:
                    if os.path.exists(reference_path(source, db)) and not force:
                        print(f"  = {db}: exported already", flush=True)
                        continue
                    t0 = time.time()
                    ref = {"mysql": lambda: export_mysql(src.name, db),
                           "postgres": lambda: export_postgres(src.name, db),
                           "sqlite": lambda: export_sqlite(src.name, cfg.corpus, db, exporter)}[source]()
                    ref.update({"database": db, "source": src.name, "exported": now()})
                    with open(reference_path(source, db) + ".part", "w", encoding="utf-8") as fh:
                        json.dump(ref, fh, indent=1, sort_keys=True)
                    os.replace(reference_path(source, db) + ".part", reference_path(source, db))
                    rows = sum(v or 0 for v in ref["rows"].values())
                    print(f"  . {db:<22} {len(ref['rows']):>4} tables {rows:>12,} rows  "
                          f"{human(sum(ref['dump_bytes'].values()))} written ({time.time() - t0:.0f}s)", flush=True)
            finally:
                if exporter:
                    run("docker", "rm", "-f", exporter)
    print(f"\nexports in {rel(EXPORTS)}/")
    return 1 if failed else 0


def start_exporter():
    """The sqlite3 shell the DoltLite image carries, built from sqlite.org's release with FTS5."""
    run("docker", "rm", "-f", EXPORTER)
    image = lite_image()
    if run("docker", "image", "inspect", image).returncode != 0:
        sys.exit(f"{image} is not built; `make lite-image` builds it")
    p = run("docker", "run", "-d", "--name", EXPORTER, "--label", TRANSIENT,
            "-v", f"{export_dir('sqlite')}:/x", image)
    if p.returncode != 0:
        sys.exit(f"could not start {EXPORTER}: {p.stderr.strip()[:200]}")
    return EXPORTER
