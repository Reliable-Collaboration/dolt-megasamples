#!/usr/bin/env python3
"""Spike (2026-09-13): does loading rows over many concurrent connections, with a commit per row,
go faster than one connection? Dolt and DoltgreSQL against MySQL and PostgreSQL.

  .venv/bin/python scripts/spike_concurrent_commits.py --database sakila --workers 1,4,16
  .venv/bin/python scripts/spike_concurrent_commits.py --database dvdstore --engines dolt,doltgres --workers 1,16

The question the maintainer asked: Dolt runs one statement on one goroutine but keeps connections
apart, and this host has 32 threads, so would 16 workers over 16 connections load a database faster
while still producing one Dolt commit for every row? The shape, decided 2026-09-13:

* **deferred constraints**: the tables are created first, the rows go in with foreign-key checks
  off, and the secondary indexes, the foreign keys, the views and the triggers are added after the
  last row -- the deferred-index policy of the experiment, extended to every constraint, so the
  workers need not care which table a row belongs to;
* **one commit per row, on one branch**: every worker runs `BEGIN; INSERT ...; DOLT_COMMIT` per
  row. DOLT_COMMIT commits the SQL transaction and creates the Dolt commit under the branch lock,
  so no row is ever in the shared working set without a commit, and a commit's diff against its
  parent is exactly its own row even when other workers' rows were merged in on the way;
* **the same statements for every engine of a protocol**: MySQL and PostgreSQL get the same
  rows over the same number of connections, one transaction per row, which is their commit-per-row;
* **rows round-robin over the workers**: row i goes to worker i mod N, so every worker holds rows
  of every table.

Recorded per run: the time of the three phases (schema, rows, the deferred rest and the settle),
rows per second over the row phase, the commit count and a sample of per-commit diffs on the Dolt
engines, the row count of every table against the dump, retries and failures, the server's peak
memory and average CPU (its cgroup, sampled every second), and the store size after collection.
Results land in build/spike-concurrent/<database>.json and are printed as a table.

Servers are started with the images versions.json names, under the experiment's worker memory
cap, on ports that nothing else here uses. Nothing in build/progress.json or build/results.json is
touched; this is a spike, not a measurement of the experiment.
"""
import argparse, json, os, random, re, shutil, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DOLT_IMAGE, DUMPS, MEM_WORKER, ROOT, VERSIONS, dumps_dir, human, mem, run  # noqa: E402
from dolt_dialect import defer_indexes  # noqa: E402
from pairs import DOLTGRES_IMAGE, POSTGRES_IMAGE, prepare  # noqa: E402

OUT = os.path.join(ROOT, "build", "spike-concurrent")
DATA = os.path.join(ROOT, "data", "spike-concurrent")
PW = "doltsamples"
ENGINES = {
    # name: (protocol, image, port on 127.0.0.1)
    "dolt": ("mysql", DOLT_IMAGE, 33077),
    "mysql": ("mysql", VERSIONS["mysql"]["image"], 33078),
    "doltgres": ("pg", DOLTGRES_IMAGE, 54337),
    "postgres": ("pg", POSTGRES_IMAGE, 54338),
}
RETRIES = 8


# ------------------------------------------------------------------ the dump, split three ways ---
def split_mysql(text):
    """(session setup, pre, data, post) from a mysqldump-shaped file: the header SETs for every
    session; every DROP/CREATE TABLE, in order, before any row; the INSERT statements; everything
    else (views, triggers, deferred index ALTERs, the restore SETs) after the last row."""
    setup, pre, data, post = [], [], [], []
    lines = text.split("\n")
    in_create = False
    seen_table = False
    for line in lines:
        s = line.strip()
        if in_create:
            pre.append(line)
            if s.startswith(")") and s.endswith(";"):
                in_create = False
            continue
        if s.startswith("INSERT INTO"):
            data.append(s[:-1] if s.endswith(";") else s)
            continue
        if re.match(r"(/\*!\d+ )?(LOCK TABLES|UNLOCK TABLES|ALTER TABLE `?\w+`? (DISABLE|ENABLE) KEYS)", s):
            continue
        if s.startswith("DROP TABLE") or s.startswith("CREATE TABLE"):
            seen_table = True
            pre.append(line)
            in_create = s.startswith("CREATE TABLE") and not s.endswith(";")
            continue
        if not seen_table:
            pre.append(line)
            if s.startswith("SET ") and "@@GLOBAL" not in s and "SQL_LOG_BIN" not in s:
                setup.append(s[:-1].strip() if s.endswith(";") else s)
            continue
        if s.startswith("SET ") and ("character_set_client" in s or "saved_cs_client" in s):
            pre.append(line)
            continue
        if "SQL_LOG_BIN" in s:
            continue           # restores a session variable the pre file's session set; meaningless here
        post.append(line)
    return setup, "\n".join(pre) + "\n", data, "\n".join(post) + "\n"


def split_pg(text):
    """(session setup, pre, data, post) from a pg_dump --inserts file: pg_dump already puts the
    indexes, constraints and triggers after the data, so pre is everything before the first
    INSERT, post everything after it that is not an INSERT. An INSERT with a newline inside a
    value spans lines; it ends where the single quotes balance."""
    setup, pre, data, post = [], [], [], []
    lines = text.split("\n")
    buf = None
    seen_insert = False
    for line in lines:
        if buf is not None:
            buf += "\n" + line
            if buf.count("'") % 2 == 0:
                data.append(buf.rstrip()[:-1] if buf.rstrip().endswith(";") else buf)
                buf = None
            continue
        if line.startswith("INSERT INTO"):
            seen_insert = True
            if line.count("'") % 2 == 0:
                s = line.rstrip()
                data.append(s[:-1] if s.endswith(";") else s)
            else:
                buf = line
            continue
        if line.startswith("\\unrestrict"):
            continue           # pairs with the pre file's \restrict, in another psql session
        (post if seen_insert else pre).append(line)
        s = line.strip()
        if not seen_insert and (s.startswith("SET ") or s.startswith("SELECT pg_catalog.set_config")):
            setup.append(s[:-1] if s.endswith(";") else s)
    return setup, "\n".join(pre) + "\n", data, "\n".join(post) + "\n"


def table_of(insert, protocol):
    m = re.match(r"INSERT INTO\s+(`?[\w.]+`?(?:\.`?\w+`?)?)", insert)
    name = m.group(1).replace("`", "")
    return name.split(".")[-1]


def dump_for(engine, db):
    """The prepared per-row dump with deferred indexes, as the experiment loads it."""
    protocol = ENGINES[engine][0]
    if engine == "dolt":
        path = os.path.join(DUMPS, "dolt", "rowinsert", f"{db}.sql")
        if not os.path.exists(path):
            sys.exit(f"{path} is missing: run the experiment's dolt_rowinsert unit for {db} first, "
                     f"or python3 scripts/run_all.py --only {db} --phase dolt_rowinsert")
        text = open(path, "rb").read().decode("utf-8", "replace")
    elif engine == "mysql":
        raw = open(os.path.join(dumps_dir(True), f"{db}.sql"), "rb").read()
        sql, _ = defer_indexes(raw)
        text = sql.decode("utf-8", "replace")
    else:
        inside, _, _, _ = prepare("pg", db, "doltgres_rowinsert" if engine == "doltgres" else "postgres_rowwise")
        path = os.path.join(ROOT, "build", inside.lstrip("/"))
        if engine == "postgres":
            path = os.path.join(DUMPS, "postgres", f"{db}.inserts.sql")
        text = open(path, encoding="utf-8", newline="").read()
    return (split_mysql if protocol == "mysql" else split_pg)(text)


# ------------------------------------------------------------------------------- servers ---
def sh(container, cmd):
    return run("docker", "exec", container, "sh", "-c", cmd)


def wait_port(engine, port, seconds=180):
    import socket
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                # the MySQL entrypoint answers on TCP only once the real server is up; give it a beat
                time.sleep(1.0)
                return True
        except OSError:
            time.sleep(0.5)
    return False


def server_up(engine, db):
    protocol, image, port = ENGINES[engine]
    name = f"spike-concurrent-{engine}"
    run("docker", "rm", "-f", "-v", name)
    store = os.path.join(DATA, engine)
    if os.path.isdir(store):
        run("docker", "run", "--rm", "-v", f"{DATA}:/d", "--entrypoint", "sh", image if engine != "doltgres" else DOLT_IMAGE,
            "-c", f"rm -rf /d/{engine}")
    os.makedirs(store, exist_ok=True)
    base = ["docker", "run", "-d", "--name", name, *mem(MEM_WORKER), "--label", "doltsamples.transient=true",
            "-p", f"127.0.0.1:{port}:{3306 if protocol == 'mysql' else 5432}"]
    if engine == "dolt":
        cmd = base + ["-e", f"DOLT_ROOT_PASSWORD={PW}", "-e", "DOLT_ROOT_HOST=%", "-v", f"{store}:/var/lib/dolt", image]
    elif engine == "mysql":
        cmd = base + ["-e", f"MYSQL_ROOT_PASSWORD={PW}", image, "mysqld", "--local-infile=1", "--skip-log-bin",
                      "--innodb-buffer-pool-size=2G", "--innodb-redo-log-capacity=512M"]
    elif engine == "doltgres":
        cmd = base + ["-e", f"DOLTGRES_PASSWORD={PW}", "-v", f"{store}:/var/lib/doltgres", image]
    else:
        cmd = base + ["-e", f"POSTGRES_PASSWORD={PW}", image]
    p = run(*cmd)
    if p.returncode != 0:
        sys.exit(f"could not start {name}: {p.stderr.strip()[:300]}")
    if not wait_port(engine, port):
        sys.exit(f"{name} did not answer on port {port}")
    # the server answers on the port before it takes a login; try until it does
    for _ in range(120):
        try:
            c = connect(engine, None)
            c.close()
            break
        except Exception:                                          # noqa: BLE001
            time.sleep(1)
    else:
        sys.exit(f"{name} never accepted a login")
    return name


def connect(engine, db, autocommit=False):
    protocol, _, port = ENGINES[engine]
    if protocol == "mysql":
        import pymysql
        return pymysql.connect(host="127.0.0.1", port=port, user="root", password=PW, database=db,
                               autocommit=autocommit, charset="utf8mb4", connect_timeout=10)
    import psycopg
    return psycopg.connect(host="127.0.0.1", port=port, user="postgres", password=PW,
                           dbname=db or "postgres", autocommit=autocommit, connect_timeout=10)


def create_database(engine, db):
    protocol = ENGINES[engine][0]
    c = connect(engine, None, autocommit=True)
    cur = c.cursor()
    if protocol == "mysql":
        cur.execute(f"DROP DATABASE IF EXISTS `{db}`")
        cur.execute(f"CREATE DATABASE `{db}`")
    else:
        cur.execute(f'DROP DATABASE IF EXISTS "{db}"')
        cur.execute(f'CREATE DATABASE "{db}"')
    c.close()


def run_file(engine, db, text, label):
    """The pre and post parts through the real client, which reads DELIMITER blocks, function
    bodies and psql commands the way the experiment's loads do."""
    protocol, _, port = ENGINES[engine]
    path = os.path.join(OUT, f"{engine}-{db}-{label}.sql")
    open(path, "w", encoding="utf-8", newline="").write(text)
    name = f"spike-concurrent-{engine}"
    run("docker", "cp", path, f"{name}:/tmp/{label}.sql")
    if protocol == "mysql":
        client = "mysql" if engine == "mysql" else None
        if client is None:
            # the Dolt image has no mysql client: the MySQL image's, over the host port
            p = run("docker", "run", "--rm", "--network", f"container:{name}", "-v", f"{path}:/tmp/{label}.sql:ro",
                    VERSIONS["mysql"]["image"], "sh", "-c",
                    f"mysql -h 127.0.0.1 -P 3306 -uroot -p{PW} --default-character-set=utf8mb4 {db} < /tmp/{label}.sql")
        else:
            p = sh(name, f"mysql -uroot -p{PW} --default-character-set=utf8mb4 {db} < /tmp/{label}.sql")
    else:
        p = sh(name, f"PGPASSWORD={PW} psql -X -v ON_ERROR_STOP=0 -q -h 127.0.0.1 -U postgres -d {db} -f /tmp/{label}.sql")
    err = [l for l in (p.stderr or "").splitlines() if l.strip() and "Using a password" not in l]
    return p.returncode, err


# ------------------------------------------------------------------------------- sampler ---
class Sampler(threading.Thread):
    """Peak memory and CPU of the server's cgroup, read inside the container every second."""

    def __init__(self, container):
        super().__init__(daemon=True)
        self.container, self.stop, self.peak, self.cpu = container, threading.Event(), 0, []

    def read(self):
        p = sh(self.container, "cat /sys/fs/cgroup/memory.current; grep usage_usec /sys/fs/cgroup/cpu.stat")
        try:
            cur, usage = p.stdout.split()[0], p.stdout.split()[-1]
            return int(cur), int(usage)
        except (ValueError, IndexError):
            return None, None

    def run(self):
        while not self.stop.is_set():
            cur, usage = self.read()
            if cur is not None:
                self.peak = max(self.peak, cur)
                self.cpu.append((time.time(), usage))
            self.stop.wait(1.0)

    def cores(self, t0, t1):
        pts = [(t, u) for t, u in self.cpu if t0 <= t <= t1]
        if len(pts) < 2:
            return None
        return round((pts[-1][1] - pts[0][1]) / 1e6 / (pts[-1][0] - pts[0][0]), 2)


# -------------------------------------------------------------------------------- workers ---
def worker(engine, db, setup, rows, per_row_commit, stats):
    protocol = ENGINES[engine][0]
    conn = connect(engine, db, autocommit=not per_row_commit)
    cur = conn.cursor()
    for s in setup:
        try:
            cur.execute(s)
        except Exception:                                          # noqa: BLE001
            try:
                conn.rollback()
            except Exception:                                      # noqa: BLE001
                pass
    try:
        conn.commit()
    except Exception:                                              # noqa: BLE001
        pass
    if protocol == "mysql":
        for s in ("SET FOREIGN_KEY_CHECKS=0", "SET UNIQUE_CHECKS=0"):
            cur.execute(s)
    done = retries = failures = 0
    t0 = time.time()
    for n, insert in rows:
        for attempt in range(RETRIES + 1):
            try:
                if per_row_commit:
                    if protocol == "mysql":
                        conn.begin()
                        cur.execute(insert)
                        cur.execute("CALL DOLT_COMMIT('-Am', %s)", (f"row {n}",))
                        conn.commit()
                    else:
                        cur.execute(insert)
                        cur.execute("SELECT dolt_commit('-Am', %s)", (f"row {n}",))
                        conn.commit()
                else:
                    cur.execute(insert)
                done += 1
                break
            except Exception as exc:                               # noqa: BLE001
                try:
                    conn.rollback()
                except Exception:                                  # noqa: BLE001
                    pass
                if attempt == RETRIES:
                    failures += 1
                    stats["errors"].append(f"row {n}: {type(exc).__name__}: {str(exc)[:160]}")
                else:
                    retries += 1
                    time.sleep(0.01 * (attempt + 1))
    conn.close()
    stats["done"] += done
    stats["retries"] += retries
    stats["failures"] += failures
    stats["worker_seconds"].append(round(time.time() - t0, 1))


def query(engine, db, sql, params=None):
    c = connect(engine, db, autocommit=True)
    cur = c.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall() if cur.description else []
    c.close()
    return rows


def store_bytes(engine):
    name = f"spike-concurrent-{engine}"
    path = {"dolt": "/var/lib/dolt", "doltgres": "/var/lib/doltgres", "mysql": "/var/lib/mysql",
            "postgres": "/var/lib/postgresql"}[engine]
    p = sh(name, f"du -sb {path} | cut -f1")
    try:
        return int(p.stdout.split()[0])
    except (ValueError, IndexError):
        return None


def one_run(engine, db, workers, setup, pre, data, post):
    protocol = ENGINES[engine][0]
    versioned = engine in ("dolt", "doltgres")
    name = server_up(engine, db)
    sampler = Sampler(name)
    sampler.start()
    res = {"engine": engine, "version": VERSIONS[engine]["version"], "database": db, "workers": workers,
           "rows": len(data), "commit_per_row": versioned}
    create_database(engine, db)
    t = time.time()
    rc, err = run_file(engine, db, pre, "pre")
    res["schema_seconds"] = round(time.time() - t, 1)
    res["schema_errors"] = err[:5]
    # the rows, round-robin over the workers
    shards = [[] for _ in range(workers)]
    for i, insert in enumerate(data):
        shards[i % workers].append((i + 1, insert))
    stats = {"done": 0, "retries": 0, "failures": 0, "errors": [], "worker_seconds": []}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda shard: worker(engine, db, setup, shard, versioned, stats), shards))
    t1 = time.time()
    res["rows_seconds"] = round(t1 - t0, 1)
    res["rows_per_second"] = round(len(data) / (t1 - t0), 1) if t1 > t0 else None
    res["rows_done"] = stats["done"]
    res["retries"] = stats["retries"]
    res["failures"] = stats["failures"]
    res["errors"] = stats["errors"][:10]
    res["worker_seconds"] = sorted(stats["worker_seconds"])
    res["server_cores_rows"] = sampler.cores(t0, t1)
    # the deferred rest: indexes, constraints, views, triggers; then the settle step
    t = time.time()
    rc, err = run_file(engine, db, post, "post")
    res["post_errors"] = err[:5]
    if versioned:
        q = ("CALL DOLT_COMMIT('-A', '--allow-empty', '-m', 'deferred indexes and constraints')" if protocol == "mysql"
             else "SELECT dolt_commit('-A', '--allow-empty', '-m', 'deferred indexes and constraints')")
        query(engine, db, q)
        query(engine, db, "CALL DOLT_GC()" if protocol == "mysql" else "SELECT dolt_gc()")
    elif engine == "postgres":
        query(engine, db, "CHECKPOINT")
    res["post_seconds"] = round(time.time() - t, 1)
    sampler.stop.set()
    sampler.join(timeout=5)
    res["server_peak_bytes"] = sampler.peak
    res["store_bytes"] = store_bytes(engine)
    # checks: every table's rows, and on the Dolt engines the commits
    expected = {}
    for insert in data:
        expected[table_of(insert, protocol)] = expected.get(table_of(insert, protocol), 0) + 1
    short = {}
    for tbl, n in expected.items():
        try:
            got = query(engine, db, f"SELECT COUNT(*) FROM {('`' + tbl + '`') if protocol == 'mysql' else ('public.' + chr(34) + tbl + chr(34))}")[0][0]
        except Exception as exc:                                   # noqa: BLE001
            got = f"error: {str(exc)[:80]}"
        if got != n:
            short[tbl] = {"expected": n, "got": got}
    res["tables"] = len(expected)
    res["rows_short"] = short
    if versioned:
        commits = query(engine, db, "SELECT COUNT(*) FROM dolt_log")[0][0]
        res["commits"] = commits
        hashes = [r[0] for r in query(engine, db, "SELECT commit_hash FROM dolt_log ORDER BY date DESC LIMIT 5000 OFFSET 2")]
        sample = random.Random(1).sample(hashes, min(12, len(hashes)))
        diffs = []
        for h in sample:
            try:
                if protocol == "mysql":
                    r = query(engine, db, "SELECT COALESCE(SUM(rows_added + rows_modified + rows_deleted), 0) FROM DOLT_DIFF_STAT(%s, %s)", (h + "~", h))
                else:
                    r = query(engine, db, "SELECT COALESCE(SUM(rows_added + rows_modified + rows_deleted), 0) FROM dolt_diff_stat(%s, %s)", (h + "~", h))
                diffs.append(int(r[0][0]))
            except Exception as exc:                               # noqa: BLE001
                diffs.append(f"error: {str(exc)[:60]}")
        res["sampled_commit_row_changes"] = diffs
    run("docker", "rm", "-f", "-v", name)
    return res


def summary(paths):
    """A table per database from the recorded runs: rows per second and the gain over one worker,
    commits, retries and failures, the server's peak memory and cores, the store after collection."""
    order = ["dolt", "doltgres", "mysql", "postgres"]
    for path in paths:
        rs = json.load(open(path))
        db = rs[0]["database"] if rs else os.path.basename(path)
        print(f"\n{db}: {rs[0]['rows']:,} rows, a commit per row on the Dolt engines, one transaction per row on the others"
              if rs else f"\n{db}: nothing recorded")
        print("| engine | workers | rows/s | vs 1 worker | row phase | commits | retries | failures | short | peak memory | server cores | store after gc |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for engine in order:
            runs = sorted((r for r in rs if r["engine"] == engine), key=lambda r: r["workers"])
            base = next((r["rows_per_second"] for r in runs if r["workers"] == 1), None)
            for r in runs:
                gain = f"{r['rows_per_second'] / base:.2f}x" if base and r["rows_per_second"] else "-"
                print(f"| {engine} {r['version']} | {r['workers']} | {r['rows_per_second']:,.0f} | {gain} | {r['rows_seconds']:.0f} s "
                      f"| {r.get('commits', '-')} | {r['retries']} | {r['failures']} | {len(r['rows_short'])} "
                      f"| {human(r['server_peak_bytes'])} | {r['server_cores_rows']} | {human(r['store_bytes']) if r['store_bytes'] else '-'} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--database", default="sakila")
    ap.add_argument("--engines", default="dolt,doltgres,mysql,postgres")
    ap.add_argument("--workers", default="1,16")
    ap.add_argument("--summary", action="store_true", help="print the tables of every recorded database and exit")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.summary:
        summary(sorted(os.path.join(OUT, f) for f in os.listdir(OUT) if f.endswith(".json")))
        return 0
    engines = a.engines.split(",")
    workers = [int(w) for w in a.workers.split(",")]
    path = os.path.join(OUT, f"{a.database}.json")
    results = json.load(open(path)) if os.path.exists(path) else []
    for engine in engines:
        setup, pre, data, post = dump_for(engine, a.database)
        print(f"\n{engine} {VERSIONS[engine]['version']} / {a.database}: {len(data):,} rows in the dump, "
              f"{len(setup)} session settings", flush=True)
        for w in workers:
            print(f"  . {w:>2} worker(s) ... ", end="", flush=True)
            res = one_run(engine, a.database, w, setup, pre, data, post)
            res["measured_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            results = [r for r in results if not (r["engine"] == engine and r["workers"] == w)] + [res]
            json.dump(results, open(path, "w"), indent=2)
            print(f"{res['rows_seconds']:>7.1f}s  {res['rows_per_second']:>7.1f} rows/s  "
                  f"commits {res.get('commits', '-')}  retries {res['retries']}  failures {res['failures']}  "
                  f"short {len(res['rows_short'])} table(s)  peak {human(res['server_peak_bytes'])}  "
                  f"cores {res['server_cores_rows']}  store {human(res['store_bytes']) if res['store_bytes'] else '-'}",
                  flush=True)
            if res["errors"]:
                print("      first error: " + res["errors"][0], flush=True)
            if res["schema_errors"] or res["post_errors"]:
                print("      schema/post messages: " + " | ".join((res["schema_errors"] + res["post_errors"])[:3])[:300],
                      flush=True)
    print(f"\nresults: {os.path.relpath(path, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
