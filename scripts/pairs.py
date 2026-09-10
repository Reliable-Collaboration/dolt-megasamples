#!/usr/bin/env python3
"""The two further pairs -- PostgreSQL/DoltgreSQL and SQLite/DoltLite -- and how each engine is
loaded, settled, sized and checked. run_pairs.py drives the timed loads; preflight_pairs.py loads
schemas only; export_postgres.py / export_sqlite.py write the sources this reads.

Five shapes per pair, the same five the MySQL/Dolt pair has (see run_all.py):

| key                  | engine       | how the rows are written                                     |
|---|---|---|
| `postgres`           | PostgreSQL   | pg_dump's COPY form, into a fresh server                     |
| `postgres_rowwise`   | PostgreSQL   | pg_dump --inserts: one INSERT per row, each autocommitted    |
| `doltgres_oneshot`   | DoltgreSQL   | the COPY form, one dolt_commit for the database              |
| `doltgres_rowinsert` | DoltgreSQL   | one INSERT per row, one commit for the database              |
| `doltgres_rowcommit` | DoltgreSQL   | one INSERT per row and `dolt_commit` after every row         |
| `sqlite`             | SQLite       | sqlite3's .dump replayed inside its one transaction          |
| `sqlite_rowwise`     | SQLite       | the same statements, each its own durable transaction        |
| `doltlite_oneshot`   | DoltLite     | the dump replayed into a DoltLite-format file, one commit    |
| `doltlite_rowinsert` | DoltLite     | one INSERT per row autocommitted, one commit for the database|
| `doltlite_rowcommit` | DoltLite     | one INSERT per row and `dolt_commit` after every row         |

Both engines of a pair load the same transformed file (the dialect modules say what changed and
why), through the same client: `psql` executed inside the server's own container for the
PostgreSQL pair, the `sqlite3` and `doltlite` shells inside one worker container for the SQLite
pair. Every load is timed on a wall clock around that one command, in a container that is
already up; the settle step (CHECKPOINT; dolt_commit + dolt_gc; nothing; dolt_commit + VACUUM)
is timed separately; memory is sampled from the worker's cgroup every two seconds; and the row
counts and the index set are checked against the reference recorded at export before any size
is kept.

"The same file" for DoltLite means the dump replayed into a DoltLite-format database. A stock
SQLite file opened by DoltLite runs on SQLite's own B-tree engine without version control, which
would measure SQLite twice.
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DUMPS, MEGASAMPLES_DIR, MEM_WORKER, ROOT, mem, run  # noqa: E402
import doltgres_dialect, doltlite_dialect  # noqa: E402

# --------------------------------------------------------------------------------- images ---
# PostgreSQL 18.6, the base of sql-megasamples' own image, pinned by digest (postgres:18.6-bookworm).
POSTGRES_IMAGE = os.environ.get(
    "DOLTSAMPLES_POSTGRES_IMAGE",
    "postgres@sha256:1c59e2c3c818eaa0f0628f695b36e7c9e362d6b219b36a54a32df645cbd7e1af")

# ====================================================================================================
# PINNED: DoltgreSQL 1.3.1 (the release current on 2026-09-10; published 2026-09-02).
# Every DoltgreSQL number in this repository was measured against this one build, named by digest so
# a moved tag cannot change it. TO UNDO THE PIN: set DOLTSAMPLES_DOLTGRES_IMAGE (or edit the default
# below, and the `doltgres` service in compose.yaml, which carries the same digest), then rerun the
# loads -- the numbers belong to the build that produced them. The decision and the digest's
# provenance: knowledge/decisions/doltgresql-version-pin.md.
# ====================================================================================================
DOLTGRES_VERSION = "1.3.1"
DOLTGRES_IMAGE = os.environ.get(
    "DOLTSAMPLES_DOLTGRES_IMAGE",
    "dolthub/doltgresql@sha256:6c85cb1f35beabf47f094336a420255130b841b1645f36d79ef046276af36851")

# DoltLite v0.50.9 (published 2026-09-10): no image exists, so docker/doltlite/Dockerfile builds one
# from these two packages after scripts/lite_image.py has checked them against the recorded sha256.
LITE_VERSION = "0.50.9"
LITE_IMAGE = f"doltsamples-doltlite:{LITE_VERSION}"
_LITE_RELEASE = f"https://github.com/dolthub/doltlite/releases/download/v{LITE_VERSION}/"
LITE_PACKAGES = [
    (f"libdoltlite0_{LITE_VERSION}_amd64.deb", _LITE_RELEASE + f"libdoltlite0_{LITE_VERSION}_amd64.deb",
     "bc1c936a7f0975af2182c24d98d20da45e04d4ac101df5f892923928aee1a7eb"),
    (f"doltlite_{LITE_VERSION}_amd64.deb", _LITE_RELEASE + f"doltlite_{LITE_VERSION}_amd64.deb",
     "cf387247a87166f51df73a832b4d93df4162552cb21f3df66bcb44494751e1a5"),
]

# ----------------------------------------------------------------------------- containers ---
PW = "doltsamples"
PG_TIMING = "doltsamples-postgres-timing"        # a fresh PostgreSQL per load
DOLTGRES_RUNNER = "doltsamples-doltgres-runner"  # one DoltgreSQL server per mode, one database per load
LITE_RUNNER = "doltsamples-lite-runner"          # the sqlite3 and doltlite shells, files under /data
WORKERS = {PG_TIMING, DOLTGRES_RUNNER, LITE_RUNNER, "doltsamples-dolt-runner", "doltsamples-mysql-timing"}
PGDATA = "/var/lib/postgresql/18/docker"
DOLTGRES_DATA = "/var/lib/doltgres"

PG_DUMPS = os.path.join(DUMPS, "postgres")
LITE_DUMPS = os.path.join(DUMPS, "sqlite")
PREPARED = os.path.join(DUMPS, "pairs")
DATA = os.path.join(ROOT, "data")
PREFLIGHT = os.path.join(ROOT, "build", "preflight")

PHASES = {
    "pg": ["postgres", "postgres_rowwise", "doltgres_oneshot", "doltgres_rowinsert", "doltgres_rowcommit"],
    "lite": ["sqlite", "sqlite_rowwise", "doltlite_oneshot", "doltlite_rowinsert", "doltlite_rowcommit"],
}
ENGINE = {"postgres": "postgres", "postgres_rowwise": "postgres", "doltgres_oneshot": "doltgres",
          "doltgres_rowinsert": "doltgres", "doltgres_rowcommit": "doltgres",
          "sqlite": "sqlite", "sqlite_rowwise": "sqlite", "doltlite_oneshot": "doltlite",
          "doltlite_rowinsert": "doltlite", "doltlite_rowcommit": "doltlite"}
MODE_OF = {"postgres": "oneshot", "postgres_rowwise": "rowinsert", "doltgres_oneshot": "oneshot",
           "doltgres_rowinsert": "rowinsert", "doltgres_rowcommit": "rowcommit",
           "sqlite": "oneshot", "sqlite_rowwise": "rowinsert", "doltlite_oneshot": "oneshot",
           "doltlite_rowinsert": "rowinsert", "doltlite_rowcommit": "rowcommit"}
PER_ROW = {ph for ph, m in MODE_OF.items() if m != "oneshot"}
PAIR_OF = {ph: pair for pair, phs in PHASES.items() for ph in phs}
LABEL = {"postgres": "PostgreSQL, COPY", "postgres_rowwise": "PostgreSQL, one INSERT per row",
         "doltgres_oneshot": "DoltgreSQL, one commit per database",
         "doltgres_rowinsert": "DoltgreSQL, one INSERT per row", "doltgres_rowcommit": "DoltgreSQL, one commit per row",
         "sqlite": "SQLite, the dump in one transaction", "sqlite_rowwise": "SQLite, one INSERT per row",
         "doltlite_oneshot": "DoltLite, one commit per database",
         "doltlite_rowinsert": "DoltLite, one INSERT per row", "doltlite_rowcommit": "DoltLite, one commit per row"}


def mode_key(phase, indexes):
    return MODE_OF[phase] + ("_inline" if indexes == "inline" and phase in PER_ROW else "")


def data_dir(engine, mode):
    return os.path.join(DATA, "postgres-timing" if engine == "postgres" else f"{engine}-{mode}")


def reference(pair, db):
    path = os.path.join(PG_DUMPS if pair == "pg" else LITE_DUMPS, f"{db}.reference.json")
    if not os.path.exists(path):
        raise RuntimeError(f"no reference for {db}: run scripts/export_{'postgres' if pair == 'pg' else 'sqlite'}.py first")
    return json.load(open(path, encoding="utf-8"))


def exported(pair):
    d = PG_DUMPS if pair == "pg" else LITE_DUMPS
    if not os.path.isdir(d):
        return []
    return sorted(f[:-len(".reference.json")] for f in os.listdir(d) if f.endswith(".reference.json"))


# ---------------------------------------------------------------------------- preparation ---
def prepare(pair, db, phase, indexes="deferred"):
    """The one file both engines of the pair load for this phase; returns (path inside the
    container, notes, indexes the dialect dropped, mode)."""
    mode = mode_key(phase, indexes)
    out_dir = os.path.join(PREPARED, pair, mode)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{db}.sql")
    per_row = MODE_OF[phase] != "oneshot"
    if pair == "pg":
        src = os.path.join(PG_DUMPS, f"{db}.{'inserts' if per_row else 'copy'}.sql")
        sql, notes, dropped = doltgres_dialect.transform(open(src, encoding="utf-8").read(), db)
        if indexes == "inline" and per_row:
            sql, n = doltgres_dialect.inline_indexes(sql)
            notes.append(f"inline policy: {n} index/unique-constraint block(s) moved ahead of the rows")
        if MODE_OF[phase] == "rowcommit":
            sql, n = doltgres_dialect.per_row_commits(sql)
            notes.append(f"a dolt_commit after each of {n:,} INSERT statements")
    else:
        src = os.path.join(LITE_DUMPS, f"{db}.dump.sql")
        sql, notes = doltlite_dialect.transform(open(src, encoding="utf-8").read(), db)
        dropped = []
        if per_row:
            sql = doltlite_dialect.strip_transaction(sql)
            notes.append("the dump's single transaction removed: every statement is its own durable transaction")
        if indexes == "inline" and per_row:
            sql, n = doltlite_dialect.inline_indexes(sql)
            notes.append(f"inline policy: {n} CREATE INDEX statement(s) moved ahead of the rows")
        if MODE_OF[phase] == "rowcommit":
            sql, n = doltlite_dialect.per_row_commits(sql)
            notes.append(f"a dolt_commit after each of {n:,} INSERT statements")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(sql)
    return f"/dumps/pairs/{pair}/{mode}/{db}.sql", notes, dropped, mode


# -------------------------------------------------------------------------------- docker ---
def state(name):
    return run("docker", "inspect", "-f", "{{.State.Status}}", name).stdout.strip()


def mounts(name):
    p = run("docker", "inspect", "-f", "{{json .Mounts}}", name)
    try:
        return {m["Destination"]: m["Source"] for m in json.loads(p.stdout or "[]")}
    except ValueError:
        return {}


def stop_others(keep):
    """Exactly one worker beside whatever else the user has running."""
    alive = [l for l in run("docker", "ps", "--format", "{{.Names}}").stdout.splitlines()
             if l in WORKERS and l != keep]
    if alive:
        run("docker", "stop", "-t", "30", *alive)


def ensure_dir(path):
    """Created as this user before Docker can create it as root."""
    os.makedirs(path, exist_ok=True)
    return path


def wipe(host_dir, pattern="*"):
    """Empty a directory Docker wrote into as root."""
    return run("docker", "run", "--rm", "--label", "doltsamples.transient=true", "-v", f"{host_dir}:/d",
               "--entrypoint", "sh", LITE_IMAGE, "-c", f"rm -rf /d/{pattern} /d/.[!.]* 2>/dev/null || true")


def du_bytes(container, path):
    """Size of a path, or an exception -- never a zero standing in for a failed measurement."""
    p = run("docker", "exec", container, "du", "-sb", path)
    first = p.stdout.split()[0] if p.stdout.split() else ""
    if p.returncode != 0 or not first.isdigit():
        raise RuntimeError(f"could not measure {path} in {container}: exit {p.returncode} "
                           f"{(p.stderr or '').strip()[:120]}")
    return int(first)


def du_or_zero(container, path):
    try:
        return du_bytes(container, path)
    except RuntimeError:
        return 0


# memory, sampled from the host: the container's cgroup is readable at
# /sys/fs/cgroup/docker/<id>/ (cgroup v2, cgroupfs driver), so no process runs inside the worker
# to do it. The first version ran a shell loop inside the container the way run_all.py does for
# Dolt; inside a PostgreSQL container that loop is reparented to the postmaster, which took the
# loop's death for a crashed backend and put the server into recovery. `anon` is what the cgroup
# cannot reclaim and what decides a kill; one reading every two seconds.
SAMPLER_SECONDS = 2


class Sampler:
    def __init__(self, container):
        import threading
        cid = run("docker", "inspect", "-f", "{{.Id}}", container).stdout.strip()
        self.dir = f"/sys/fs/cgroup/docker/{cid}"
        self.container = container
        self.anon = self.total = 0
        self.readable = os.path.exists(os.path.join(self.dir, "memory.stat"))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _read(self):
        if self.readable:
            try:
                stat = open(os.path.join(self.dir, "memory.stat")).read()
                cur = open(os.path.join(self.dir, "memory.current")).read().strip()
            except OSError:
                return None, None
        else:
            p = run("docker", "exec", self.container, "sh", "-c",
                    "cat /sys/fs/cgroup/memory.stat; echo current $(cat /sys/fs/cgroup/memory.current)")
            stat, cur = p.stdout, ""
            for line in p.stdout.splitlines():
                if line.startswith("current "):
                    cur = line.split()[1]
        anon = next((int(l.split()[1]) for l in stat.splitlines() if l.startswith("anon ")), None)
        return anon, (int(cur) if cur.isdigit() else None)

    def _loop(self):
        while not self._stop.is_set():
            anon, cur = self._read()
            self.anon = max(self.anon, anon or 0)
            self.total = max(self.total, cur or 0)
            self._stop.wait(SAMPLER_SECONDS)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        """(peak anonymous bytes, peak total bytes) seen since start."""
        self._stop.set()
        self._thread.join(timeout=SAMPLER_SECONDS + 5)
        anon, cur = self._read()
        self.anon = max(self.anon, anon or 0)
        self.total = max(self.total, cur or 0)
        return (self.anon or None), (self.total or None)


def sampler_start(container):
    return Sampler(container).start()


# ---------------------------------------------------------------------------------- psql ---
def psql(container, db, sql):
    """One query, tuples only, unaligned; the CompletedProcess."""
    return run("docker", "exec", "-e", f"PGPASSWORD={PW}", container, "psql", "-X", "-h", "127.0.0.1",
               "-U", "postgres", "-d", db, "-tA", "-c", sql)


def psql_value(container, db, sql):
    p = psql(container, db, sql)
    if p.returncode != 0:
        raise RuntimeError(f"{container}: {sql[:80]}: {(p.stderr or '').strip()[:200]}")
    return p.stdout.strip()


def psql_file(container, db, inside):
    """Load a file the way both engines of the pair get it: quietly, output discarded, every
    error reported with its line, never stopping at the first one -- the row and index checks
    are the arbiter, and psql's per-line errors say exactly which object was refused."""
    return run("docker", "exec", "-e", f"PGPASSWORD={PW}", container, "psql", "-X", "-h", "127.0.0.1",
               "-U", "postgres", "-d", db, "-q", "-o", "/dev/null", "-v", "ON_ERROR_STOP=0", "-f", inside)


PSQL_ERROR = re.compile(r"^psql:(?P<file>\S+?):(?P<line>\d+): (?P<level>ERROR|FATAL|PANIC):\s*(?P<msg>.*)$")


def psql_errors(p, prepared_text=None):
    """[{line, message, object}] for every ERROR psql reported while loading a file."""
    out = []
    for line in (p.stderr or "").splitlines():
        m = PSQL_ERROR.match(line.strip())
        if not m:
            continue
        entry = {"line": int(m.group("line")), "message": m.group("msg")[:200]}
        if prepared_text is not None:
            t, name = doltgres_dialect.block_at_line(prepared_text, entry["line"])
            entry["object"] = f"{t}: {name}" if t else None
        out.append(entry)
    return out


def wait_pg(container, seconds=180):
    """Ready means two consecutive answers over TCP a second apart: the image's entrypoint
    restarts the server once after initialising, and a single success can land before that."""
    ok = 0
    for _ in range(seconds):
        if psql(container, "postgres", "SELECT 1").returncode == 0:
            ok += 1
            if ok == 2:
                return True
        else:
            ok = 0
        time.sleep(1)
    raise RuntimeError(f"{container} did not answer within {seconds}s: "
                       + run("docker", "logs", "--tail", "5", container).stderr[-300:])


USER_SCHEMAS = "('pg_catalog', 'information_schema', 'pg_toast')"


def pg_catalog(container, db):
    """Rows per base table, the index set, and object counts -- read the same way from every
    PostgreSQL-speaking engine."""
    tables = [t for t in psql_value(
        container, db, "SELECT table_schema || '.' || table_name FROM information_schema.tables "
        f"WHERE table_type = 'BASE TABLE' AND table_schema NOT IN {USER_SCHEMAS} ORDER BY 1").splitlines()
        if t and not t.split(".", 1)[1].startswith("dolt_")]
    rows = {}
    for t in tables:
        s, n = t.split(".", 1)
        p = psql(container, db, f'SELECT COUNT(*) FROM "{s}"."{n}"')
        rows[t] = int(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip().isdigit() else None
    idx = psql_value(container, db, "SELECT schemaname || '.' || tablename || '|' || indexname || '|' || indexdef "
                     f"FROM pg_indexes WHERE schemaname NOT IN {USER_SCHEMAS} ORDER BY 1")
    indexes = sorted(" ".join(l.split()) for l in idx.splitlines() if l.strip())
    objects = {}
    for key, sql in (("views", f"SELECT COUNT(*) FROM pg_views WHERE schemaname NOT IN {USER_SCHEMAS}"),
                     ("triggers", "SELECT COUNT(*) FROM pg_trigger WHERE NOT tgisinternal"),
                     ("routines", "SELECT COUNT(*) FROM information_schema.routines "
                                  f"WHERE specific_schema NOT IN {USER_SCHEMAS}"),
                     ("foreign_keys", "SELECT COUNT(*) FROM information_schema.table_constraints "
                                      f"WHERE constraint_type = 'FOREIGN KEY' AND table_schema NOT IN {USER_SCHEMAS}")):
        p = psql(container, db, sql)
        objects[key] = int(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip().isdigit() else None
    return {"rows": rows, "indexes": indexes, "objects": objects}


# ------------------------------------------------------------------- sqlite3 and doltlite ---
def lite_up():
    if state(LITE_RUNNER) == "running":
        return
    run("docker", "rm", "-f", LITE_RUNNER)
    ensure_dir(DATA)
    p = run("docker", "run", "-d", "--name", LITE_RUNNER, *mem(MEM_WORKER),
            "-v", f"{DATA}:/data", "-v", f"{DUMPS}:/dumps:ro", LITE_IMAGE)
    if p.returncode != 0:
        raise RuntimeError(f"could not start {LITE_RUNNER}: {p.stderr.strip()[:200]} "
                           f"(python3 scripts/lite_image.py builds the image)")


def lite_sh(cmd, container=None):
    return run("docker", "exec", container or LITE_RUNNER, "sh", "-c", cmd)


def q(name):
    return '"' + name.replace('"', '""') + '"'


def lit(name):
    return "'" + name.replace("'", "''") + "'"


def lite_catalog(binary, inside_path, tables=None, container=None, script_host=None, script_inside=None):
    """Rows per table and the index set of one file, through the named shell.

    Two scripts: the first counts every table and lists its indexes, the second reads the columns
    of every index the first found. Written to a file and `.read`, so hundreds of tables cost two
    process starts, and an error on one statement is reported and does not stop the rest."""
    container = container or LITE_RUNNER
    p = lite_sh(f"{binary} {inside_path} \"SELECT name FROM sqlite_schema WHERE sql LIKE 'CREATE VIRTUAL%' ORDER BY 1\"",
                container)
    virtual = [l for l in p.stdout.splitlines() if l.strip()]
    if tables is None:
        p = lite_sh(f"{binary} {inside_path} \"SELECT name FROM sqlite_schema WHERE type = 'table' "
                    f"AND name NOT LIKE 'sqlite_%' ORDER BY 1\"", container)
        # a virtual table's shadow tables hold its index pages, not data: the loads rebuild the
        # index, so its page layout is not expected to match and they are left out
        tables = [l for l in p.stdout.splitlines() if l.strip()
                  and not any(l.startswith(v + "_") for v in virtual)]
    lines = []
    for t in tables:
        lines += [f"SELECT '@rows', {lit(t)}, COUNT(*) FROM {q(t)};", f"SELECT '@table', {lit(t)};",
                  f"PRAGMA index_list({q(t)});"]
    rows, listed, errors = {}, {}, []
    out = _lite_script(binary, inside_path, lines, container, script_host, script_inside)
    current = None
    for line in out.stdout.splitlines():
        bits = line.split("|")
        if bits[0] == "@rows" and len(bits) == 3:
            rows[bits[1]] = int(bits[2]) if bits[2].isdigit() else None
        elif bits[0] == "@table":
            current = bits[1]
        elif current is not None and len(bits) >= 4 and bits[0].isdigit():
            listed[(current, bits[1])] = (bits[2], bits[3])        # unique, origin
    errors += [l for l in out.stderr.splitlines() if l.strip()]
    for t in tables:
        rows.setdefault(t, None)
    lines = []
    for (t, name) in listed:
        lines += [f"SELECT '@index', {lit(t)}, {lit(name)};", f"PRAGMA index_info({q(name)});"]
    cols, key = {}, None
    if lines:
        out = _lite_script(binary, inside_path, lines, container, script_host, script_inside)
        for line in out.stdout.splitlines():
            bits = line.split("|")
            if bits[0] == "@index" and len(bits) == 3:
                key = (bits[1], bits[2])
                cols[key] = []
            elif key is not None and len(bits) == 3 and bits[0].isdigit():
                cols[key].append(bits[2])
        errors += [l for l in out.stderr.splitlines() if l.strip()]
    indexes = sorted(f"{t}|{name}|unique={u}|origin={o}|{','.join(cols.get((t, name), []))}"
                     for (t, name), (u, o) in listed.items())
    p = lite_sh(f"{binary} {inside_path} \"SELECT type || '|' || COUNT(*) FROM sqlite_schema "
                f"WHERE name NOT LIKE 'sqlite_%' GROUP BY type\"", container)
    objects = {l.split("|")[0]: int(l.split("|")[1]) for l in p.stdout.splitlines() if "|" in l}
    p = lite_sh(f"{binary} {inside_path} \"SELECT COUNT(*) FROM sqlite_schema WHERE sql LIKE 'CREATE VIRTUAL%'\"", container)
    objects["virtual tables"] = int(p.stdout.strip()) if p.stdout.strip().isdigit() else None
    return {"rows": rows, "indexes": indexes, "objects": objects, "virtual_tables": virtual,
            "catalog_errors": errors[:10]}


def _lite_script(binary, inside_path, lines, container, script_host, script_inside):
    script_host = script_host or os.path.join(PREPARED, "lite", "catalog.sql")
    script_inside = script_inside or "/dumps/pairs/lite/catalog.sql"
    os.makedirs(os.path.dirname(script_host), exist_ok=True)
    with open(script_host, "w", encoding="utf-8") as fh:
        fh.write(".mode list\n" + "\n".join(lines) + "\n")
    return lite_sh(f"{binary} {inside_path} \".read {script_inside}\"", container)


# -------------------------------------------------------------------------------- parity ---
IDX = re.compile(r"^create (unique )?index ([^\s(]+) on (?:only )?([^\s(]+) ?(?:using (\w+) ?)?\((.*)$")


def canonical_index(entry):
    """One PostgreSQL-pair index as both engines should agree on it.

    pg_indexes.indexdef is printed text, and the two engines print the same index differently:
    PostgreSQL quotes an identifier that is a keyword (`"position"`), DoltgreSQL does not. Comparing
    the text made every such difference a missing index plus an extra one. The definition is read
    back into its parts instead -- unique or not, the table, the method (btree when an engine leaves
    it out), the key list and whatever follows it -- with identifier quotes removed, whitespace
    collapsed and everything outside string literals case-folded. The name stays in the second field,
    where the refusal matching looks for it. SQLite-pair entries, already built from PRAGMA
    index_list and index_info, pass through unchanged."""
    parts = entry.split("|", 2)
    if len(parts) != 3 or not parts[2].lstrip().upper().startswith("CREATE"):
        return entry
    table, name, ddl = parts
    out, i, n = [], 0, len(ddl)
    while i < n:
        c = ddl[i]
        if c == "'":
            j = i + 1
            while j < n:
                if ddl[j] == "'":
                    if j + 1 < n and ddl[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append(ddl[i:j + 1])
            i = j + 1
            continue
        if c != '"':
            out.append(c.lower())
        i += 1
    text = re.sub(r"\s*([(),])\s*", r"\1", " ".join("".join(out).split()))
    table = table.replace('"', "").lower()
    m = IDX.match(text)
    if not m:
        return f"{table}|{name}|{text}"
    unique, _, on, method, rest = m.groups()
    return f"{table}|{name}|unique={bool(unique)}|on={on}|using={method or 'btree'}|({rest}"


def compare(ref, got, dropped=()):
    """What is short: a row-count message or None, and the index report."""
    short = None
    for t, want in ref["rows"].items():
        g = got["rows"].get(t)
        if g != want:
            short = f"{t} has {g if g is not None else 'no'} rows, expected {want:,}"
            break
    dropped = set(dropped)
    want_idx = {canonical_index(i) for i in ref["indexes"] if i.split("|")[1] not in dropped}
    got_idx = {canonical_index(i) for i in got["indexes"]}
    report = {"missing": sorted(want_idx - got_idx), "extra": sorted(got_idx - want_idx),
              "dropped_by_dialect": sorted(dropped), "checked": len(want_idx)}
    extra_tables = sorted(set(got["rows"]) - set(ref["rows"]))
    if extra_tables:
        report["extra_tables"] = extra_tables
    return short, report


# ------------------------------------------------------------------- PostgreSQL, fresh ---
def pg_bytes(container=PG_TIMING):
    """The data directory without its write-ahead log. The log is recycled at a fixed size and
    charged to nobody; MySQL's redo log was inside the empty-server baseline for the same reason."""
    return du_bytes(container, PGDATA) - du_or_zero(container, os.path.join(PGDATA, "pg_wal"))


def postgres_fresh():
    d = ensure_dir(data_dir("postgres", "oneshot"))
    run("docker", "rm", "-f", PG_TIMING)
    wipe(d)
    p = run("docker", "run", "-d", "--name", PG_TIMING, *mem(MEM_WORKER), "-e", f"POSTGRES_PASSWORD={PW}",
            "-v", f"{d}:/var/lib/postgresql", "-v", f"{DUMPS}:/dumps:ro", POSTGRES_IMAGE)
    if p.returncode != 0:
        raise RuntimeError(f"could not start {PG_TIMING}: {p.stderr.strip()[:200]}")
    wait_pg(PG_TIMING)


def load_postgres(db, phase, indexes="deferred"):
    inside, notes, dropped, mode = prepare("pg", db, phase, indexes)
    text = open(os.path.join(PREPARED, "pg", mode, f"{db}.sql"), encoding="utf-8").read()
    stop_others(PG_TIMING)
    postgres_fresh()
    baseline = pg_bytes()
    psql_value(PG_TIMING, "postgres", f'CREATE DATABASE {q(db)}')
    # A new PostgreSQL database is a copy of template1's catalog before it holds a row -- about
    # 7.4 MiB -- which is a floor MySQL's per-schema directory and Dolt's repository do not have.
    # Recorded so the report can show the size with and without it.
    psql(PG_TIMING, db, "CHECKPOINT")
    empty = pg_bytes() - baseline
    sampler = sampler_start(PG_TIMING)
    started = time.time()
    p = psql_file(PG_TIMING, db, inside)
    load_s = time.time() - started
    anon, total = sampler.stop()
    errors = psql_errors(p, text)
    started = time.time()
    psql(PG_TIMING, db, "CHECKPOINT")
    settle_s = time.time() - started
    outcome = {"exit_code": p.returncode, "seconds": round(load_s, 1), "settle_seconds": round(settle_s, 1),
               "bytes": pg_bytes() - baseline, "baseline_bytes": baseline, "empty_database_bytes": empty,
               "database_bytes": int(psql_value(PG_TIMING, db, "SELECT pg_database_size(current_database())")),
               "memory_anon_peak_bytes": anon, "memory_total_peak_bytes": total, "notes": notes}
    return finish(outcome, errors, reference("pg", db), pg_catalog(PG_TIMING, db), dropped)


def finish(outcome, errors, ref, got, dropped):
    """The common ending: every refusal kept, the row check the arbiter, the index set compared."""
    outcome["errors"] = errors[:40]
    outcome["error_count"] = len(errors)
    outcome["output_tail"] = " / ".join(e.get("message", str(e)) for e in errors[-3:])[:600]
    short, report = compare(ref, got, dropped)
    # An index the engine refused out loud is a schema object it would not take, recorded with its
    # reason and counted by the report; an index missing with no refusal to explain it is a failed
    # load. DoltgreSQL 1.3.1 refuses every second alteration of a table with a STORED generated
    # column ("Invalid default value ... syntax error at 'as'"), which is what this distinguishes.
    refused = {}
    for e in errors:
        obj = e.get("object") or ""
        if obj.startswith(("INDEX: ", "CONSTRAINT: ")):
            refused[obj.split(": ", 1)[1].split()[-1]] = e["message"]
    explained = [i for i in report["missing"] if i.split("|")[1] in refused]
    report["missing"] = [i for i in report["missing"] if i.split("|")[1] not in refused]
    report["refused"] = {i: refused[i.split("|")[1]][:160] for i in explained}
    outcome["index_parity"] = report
    outcome["objects"] = got.get("objects")
    settle = [e["message"] for e in errors if e.get("object") == "settle" or e.get("message", "").startswith("settle:")]
    # A store whose garbage collection failed holds every row (the checks below still apply) but
    # its size is the working footprint, not the settled size the tables compare. DoltLite's VACUUM
    # answers "out of memory" within seconds on per-row-commit files above about 2 GB (2026-09-10);
    # the unit is kept with `settled: false`, and the tables mark the size rather than hide it or
    # load the same rows again to meet the same limit.
    outcome["settled"] = not settle
    if settle:
        outcome["notes"].append("the settle step failed, so the size is the working footprint, not a collected "
                                "store: " + settle[0][:160])
    if short:
        outcome["error"] = "the load did not finish: " + short
    elif report["missing"]:
        outcome["error"] = (f"index parity: {len(report['missing'])} of {report['checked']} indexes missing, "
                            f"first {report['missing'][0][:120]}")
    elif explained:
        outcome["notes"].append(f"{len(explained)} index(es) not carried: the engine refused them, and the "
                                f"size below is without them: {', '.join(i.split('|')[1] for i in explained)}")
    elif errors:
        outcome["schema_object_error"] = outcome["output_tail"][:300]
        outcome["notes"].append(f"the engine refused {len(errors)} statement(s) after or beside the rows; every "
                                f"table and index matches the reference, so the shortfall is in the schema objects "
                                f"the report counts separately: {outcome['output_tail'][:200]}")
    return outcome


# ------------------------------------------------------------------------------ DoltgreSQL ---
def doltgres_root(mode, db):
    """One unit's own data directory: the server's `postgres` catalog and this one database."""
    return os.path.join(data_dir("doltgres", mode), db)


def doltgres_up(mode, db):
    """A fresh server over an empty root for one unit, so what a load costs is that database's alone.

    The first version kept one server per shape and loaded every database of the shape into it, the
    way one MySQL server holds many schemas. A Dolt server holds every database under its data
    directory, so each unit's memory peak carried every store loaded before it: in run order, a
    255-row database peaked at 976 MiB after eleven others had been loaded (2026-09-10 review). That
    is the contamination run_all.py avoided for Dolt with one data directory per database. Starting a
    server costs a few seconds, outside the timed window; the store lands at `<root>/<db>`."""
    root = ensure_dir(doltgres_root(mode, db))
    run("docker", "rm", "-f", DOLTGRES_RUNNER)
    wipe(root)
    p = run("docker", "run", "-d", "--name", DOLTGRES_RUNNER, *mem(MEM_WORKER), "-e", f"DOLTGRES_PASSWORD={PW}",
            "-v", f"{root}:{DOLTGRES_DATA}", "-v", f"{DUMPS}:/dumps:ro", DOLTGRES_IMAGE)
    if p.returncode != 0:
        raise RuntimeError(f"could not start {DOLTGRES_RUNNER}: {p.stderr.strip()[:200]}")
    wait_pg(DOLTGRES_RUNNER)


def doltgres_bytes(db):
    repo = f"{DOLTGRES_DATA}/{db}"
    total = du_bytes(DOLTGRES_RUNNER, repo)
    stats = du_or_zero(DOLTGRES_RUNNER, f"{repo}/.dolt/stats")
    return total - stats, stats


def load_doltgres(db, phase, indexes="deferred"):
    inside, notes, dropped, mode = prepare("pg", db, phase, indexes)
    text = open(os.path.join(PREPARED, "pg", mode, f"{db}.sql"), encoding="utf-8").read()
    stop_others(DOLTGRES_RUNNER)
    doltgres_up(mode, db)
    try:
        psql_value(DOLTGRES_RUNNER, "postgres", f'CREATE DATABASE {q(db)}')
        sampler = sampler_start(DOLTGRES_RUNNER)
        started = time.time()
        p = psql_file(DOLTGRES_RUNNER, db, inside)
        load_s = time.time() - started
        anon, total = sampler.stop()
        errors = psql_errors(p, text)
        before, _ = doltgres_bytes(db)
        started = time.time()
        c1 = psql(DOLTGRES_RUNNER, db, "SELECT dolt_commit('-A', '--allow-empty', '-m', 'import from sql-megasamples')")
        c2 = psql(DOLTGRES_RUNNER, db, "SELECT dolt_gc()")
        settle_s = time.time() - started
        for c, what in ((c1, "dolt_commit"), (c2, "dolt_gc")):
            if c.returncode != 0:
                errors.append({"line": 0, "message": f"{what}: {(c.stderr or '').strip()[:200]}", "object": "settle"})
        size, stats = doltgres_bytes(db)
        commits = psql(DOLTGRES_RUNNER, db, "SELECT COUNT(*) FROM dolt_log").stdout.strip()
        catalog = pg_catalog(DOLTGRES_RUNNER, db)
    finally:
        # the server goes with the unit; its root stays, holding the store the stack can serve
        run("docker", "rm", "-f", DOLTGRES_RUNNER)
    outcome = {"exit_code": p.returncode, "seconds": round(load_s, 1), "settle_seconds": round(settle_s, 1),
               "bytes": size, "bytes_before_settle": before, "stats_bytes": stats,
               "commits": int(commits) if commits.isdigit() else None,
               "memory_anon_peak_bytes": anon, "memory_total_peak_bytes": total, "notes": notes,
               "isolation": "one server per unit"}
    return finish(outcome, errors, reference("pg", db), catalog, dropped)


# ------------------------------------------------------------------ SQLite and DoltLite ---
def lite_path(engine, mode, db):
    return f"/data/{engine}-{mode}/{db}.{'sqlite' if engine == 'sqlite' else 'doltlite'}"


def lite_bytes(path):
    p = lite_sh(f"du -sb {path} {path}-journal {path}-wal {path}-shm 2>/dev/null | awk '{{s+=$1}} END {{print s}}'")
    v = p.stdout.strip()
    if not v.isdigit():
        raise RuntimeError(f"could not measure {path} in {LITE_RUNNER}: {(p.stderr or '').strip()[:120]}")
    return int(v)


def load_lite(db, phase, indexes="deferred"):
    engine = ENGINE[phase]
    inside, notes, dropped, mode = prepare("lite", db, phase, indexes)
    stop_others(LITE_RUNNER)
    ensure_dir(data_dir(engine, mode))
    lite_up()
    path = lite_path(engine, mode, db)
    binary = "sqlite3" if engine == "sqlite" else "doltlite"
    lite_sh(f"rm -f {path} {path}-journal {path}-wal {path}-shm")
    sampler = sampler_start(LITE_RUNNER)
    started = time.time()
    p = lite_sh(f'{binary} {path} ".read {inside}" >/dev/null')
    load_s = time.time() - started
    anon, total = sampler.stop()
    errors = [{"line": _line_of(l), "message": l.strip()[:200]} for l in (p.stderr or "").splitlines() if l.strip()]
    before = lite_bytes(path)
    started = time.time()
    if engine == "doltlite":
        c = lite_sh(f"{binary} {path} \"SELECT dolt_commit('-A', '--allow-empty', '-m', 'import from sql-megasamples'); "
                    f"VACUUM;\" >/dev/null")
        if c.returncode != 0:
            errors.append({"line": 0, "message": "settle: " + (c.stderr or "").strip()[:200]})
    settle_s = time.time() - started
    outcome = {"exit_code": p.returncode, "seconds": round(load_s, 1), "settle_seconds": round(settle_s, 1),
               "bytes": lite_bytes(path), "bytes_before_settle": before,
               "memory_anon_peak_bytes": anon, "memory_total_peak_bytes": total, "notes": notes}
    if engine == "doltlite":
        commits = lite_sh(f"{binary} {path} 'SELECT COUNT(*) FROM dolt_log'").stdout.strip()
        outcome["commits"] = int(commits) if commits.isdigit() else None
    ref = reference("lite", db)
    got = lite_catalog(binary, path, tables=list(ref["rows"]))
    return finish(outcome, errors, ref, got, dropped)


LINE_OF = re.compile(r"near line (\d+)")


def _line_of(msg):
    m = LINE_OF.search(msg)
    return int(m.group(1)) if m else 0


LOADERS = {"postgres": load_postgres, "doltgres": load_doltgres, "sqlite": load_lite, "doltlite": load_lite}


def load(db, phase, indexes="deferred"):
    return LOADERS[ENGINE[phase]](db, phase, indexes)
