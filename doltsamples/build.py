"""Build the stores dolt-megasamples.yaml asks for: each database in each engine with its history.

  python3 -m doltsamples build [--only sakila ...] [--engine dolt] [--force]

For every (engine, history, database) the configuration names, from the export of the engine the
Dolt engine stands in for (`make export`):

1. **The dump is rewritten into the engine's dialect** (doltsamples/dialects/), every change named:
   what each engine refuses and why is recorded there. No rule touches a row.
2. **It is replayed into a fresh store** in a container of its own, under the build memory limit.
   For the per-row history every INSERT is followed by its own commit, so the store's log holds one
   commit per row, in the order the corpus dumped them; secondary indexes are added after the rows
   and land in one last commit. A per-row replay runs in chunks, each its own process, and Dolt's
   store is collected between chunks, which keeps what one process has to hold within reach.
3. **The store is committed and collected**: the single history is one commit holding the whole
   database; either history ends with `dolt gc` (DoltLite: VACUUM), so it is served at its settled size.
4. **It is checked against the corpus**: every table's row count against the reference the export
   recorded (and for DoltgreSQL and DoltLite the index set too). A store that is short of a row is
   recorded as failed, never served as if it were whole. What the engine refused (a stored routine
   Dolt does not implement, a view DoltgreSQL cannot parse) is recorded with its reason.

Each store is recorded in build/stores.json with the engine version that wrote it and the digest of
the export it came from; a store whose record still matches is not built again (`--force` rebuilds).

    data/dolt/<history>/<db>/<db>         a Dolt repository (its parent is that store's own data directory)
    data/doltgres/<history>/<db>/<db>     a DoltgreSQL database (its parent holds the server's `postgres` catalog)
    data/doltlite/<history>/<db>.doltlite a DoltLite file
"""
import os, re, sys, time

from doltsamples import catalog, corpus
from doltsamples.config import HISTORY_LABEL
from doltsamples.dialects import dolt as dolt_dialect, doltgres as doltgres_dialect, doltlite as doltlite_dialect
from doltsamples.util import (BUILD, DATA, STORES, TRANSIENT, duration, ensure_dir, human, lite_image, load_json,
                              lock, mem, now, rel, remove_tree, run, save_json, versions)

PREPARED = os.path.join(BUILD, "prepared")
CONTAINER = {"dolt": "doltsamples-build-dolt", "doltgres": "doltsamples-build-doltgres",
             "doltlite": "doltsamples-build-doltlite"}
AUTHOR = "megasamples <megasamples@localhost>"
CHUNK_STATEMENTS = 50_000     # one `dolt sql` process per this many statements of a per-row replay
GC_EVERY = 10                 # chunks between `dolt gc` during a per-row replay (0: never)
DOLTGRES_START = "1800"       # the image's entrypoint gives the server this long to accept connections


def store_dir(engine, history):
    return os.path.join(DATA, engine, history)


def store_path(engine, history, db):
    """The host path of the store itself: what the stack mounts."""
    if engine == "doltlite":
        return os.path.join(store_dir(engine, history), f"{db}.doltlite")
    return os.path.join(store_dir(engine, history), db, db)


def key(engine, history, db):
    return f"{engine}/{history}/{db}"


def records():
    return load_json(STORES, {}) or {}


def export_digest(engine, history, db):
    source = corpus.SOURCE_ENGINE[engine]
    return corpus.digest([corpus.dump_path(source, db, history == "per-row"), corpus.reference_path(source, db)])


def current(rec, engine, history, db, v):
    """Whether a recorded store is still what a build would produce now."""
    return (rec and rec.get("status") == "done" and rec.get("version") == v[engine]["version"]
            and rec.get("export") == export_digest(engine, history, db)
            and os.path.exists(store_path(engine, history, db)))


def start(name, image, limit, *options, command=()):
    run("docker", "rm", "-f", name)
    p = run("docker", "run", "-d", "--name", name, "--label", TRANSIENT, *mem(limit), *options, image, *command)
    if p.returncode != 0:
        raise RuntimeError(f"could not start {name} from {image}: {p.stderr.strip()[:200]}")


def write_prepared(engine, history, db, data):
    out = os.path.join(ensure_dir(os.path.join(PREPARED, engine, history)), f"{db}.sql")
    with open(out, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else
                                                                  {"encoding": "utf-8", "newline": ""})) as fh:
        fh.write(data)
    return out


# ------------------------------------------------------------------------------------ Dolt ---
def chunk(path, statements_per_chunk=CHUNK_STATEMENTS):
    """Split a prepared per-row dump into files of at most N statements, each carrying the preamble
    (character set, checks, `USE <db>`), since every chunk is a session of its own."""
    out, body, count, head, in_head = [], [], 0, [], True
    with open(path, "rb") as fh:
        for line in fh:
            if in_head:
                if not line.strip():
                    continue
                if line.startswith((b"/*", b"--", b"SET ", b"CREATE DATABASE", b"USE ")):
                    head.append(line)
                    continue
                in_head = False
            body.append(line)
            if line.rstrip().endswith(b";"):
                count += 1
            if count >= statements_per_chunk:
                out.append(head + body)
                body, count = [], 0
    if body:
        out.append(head + body)
    paths = []
    for i, part in enumerate(out):
        q = f"{path}.part{i:03d}"
        with open(q, "wb") as fh:
            fh.writelines(part)
        paths.append(q)
    return paths


def build_dolt(cfg, history, db, v):
    name, per_row = CONTAINER["dolt"], history == "per-row"
    src = corpus.dump_path("mysql", db, per_row)
    known = [f[:-len(".reference.json")] for f in os.listdir(corpus.export_dir("mysql")) if f.endswith(".reference.json")]
    sql, notes = dolt_dialect.transform(open(src, "rb").read(), db, known)
    if per_row:
        sql, more = dolt_dialect.defer_indexes(sql)
        notes += more
        sql, n = dolt_dialect.per_row_commits(sql)
        notes.append(f"a commit after each of {n:,} INSERT statements")
    prepared = write_prepared("dolt", history, db, sql)
    parts = chunk(prepared) if per_row else [prepared]
    root = os.path.dirname(store_path("dolt", history, db))
    remove_tree(root)
    ensure_dir(root)
    start(name, v["dolt"]["image"], cfg.memory["build"], "-v", f"{root}:/root-db", "-v", f"{PREPARED}:/prepared:ro",
          "--entrypoint", "sh", command=("-c", "sleep infinity"))
    try:
        run("docker", "exec", name, "sh", "-c", f"dolt config --global --add user.name megasamples && "
                                                 f"dolt config --global --add user.email megasamples@localhost")
        p, gcs, refused = None, 0, []
        for i, part in enumerate(parts, 1):
            inside = "/prepared/" + os.path.relpath(part, PREPARED)
            # --continue: a statement Dolt refuses (a stored function it cannot parse) is reported and
            # the rest of the file still runs, so every object after it arrives
            p = run("docker", "exec", "-w", "/root-db", name, "dolt", "--data-dir", "/root-db", "sql", "--continue",
                    "--file", inside)
            refused += refusals(p)
            if per_row and len(parts) > 1:
                print(f"    {db}: {i}/{len(parts)} chunks replayed", end="\r", flush=True)
                if i == len(parts):
                    print(" " * 60, end="\r", flush=True)
            if p.returncode != 0 and not os.path.isdir(os.path.join(root, db)):
                break
            if per_row and GC_EVERY and i % GC_EVERY == 0 and i < len(parts):
                run("docker", "exec", "-w", f"/root-db/{db}", name, "dolt", "gc")
                gcs += 1
        if per_row and len(parts) > 1:
            notes.append(f"replayed in {len(parts)} chunks, the store collected {gcs} time(s) along the way")
        for part in parts:
            if part != prepared:
                os.remove(part)
        if not os.path.isdir(os.path.join(root, db, ".dolt")):
            raise RuntimeError("Dolt wrote no repository: " + tail(p))
        message = "add the indexes after the rows" if per_row else f"{db}, imported from sql-megasamples"
        s = run("docker", "exec", "-w", f"/root-db/{db}", name, "sh", "-c",
                f'dolt add -A && dolt commit --allow-empty --author "{AUTHOR}" -m "{message}" && dolt gc')
        if s.returncode != 0:
            raise RuntimeError("the final commit and gc failed: " + tail(s))
        ref = corpus.reference("mysql", db)
        got = {}
        for t in ref["rows"]:
            c = run("docker", "exec", "-w", "/root-db", name, "dolt", "--data-dir", "/root-db", "--use-db", db,
                    "sql", "-r", "csv", "-q", f"SELECT COUNT(*) FROM `{t}`")
            got[t] = next((int(l) for l in c.stdout.split() if l.strip().isdigit()), None)
        short = next((f"{t} has {got[t] if got[t] is not None else 'no'} rows, expected {n:,}"
                      for t, n in ref["rows"].items() if got[t] != n), None)
        commits = scalar(run("docker", "exec", "-w", "/root-db", name, "dolt", "--data-dir", "/root-db", "--use-db", db,
                             "sql", "-r", "csv", "-q", "SELECT COUNT(*) FROM dolt_log"))
        size = scalar(run("docker", "exec", name, "du", "-sb", f"/root-db/{db}"))
    finally:
        run("docker", "rm", "-f", name)
    return outcome(short, got, ref, size, commits, notes, refused)


# ------------------------------------------------------------------------------ DoltgreSQL ---
def build_doltgres(cfg, history, db, v):
    name, per_row = CONTAINER["doltgres"], history == "per-row"
    text = open(corpus.dump_path("postgres", db, per_row), encoding="utf-8", newline="").read()
    sql, notes, dropped = doltgres_dialect.transform(text, db)
    if per_row:
        sql, n = doltgres_dialect.per_row_commits(sql)
        notes.append(f"a commit after each of {n:,} INSERT statements")
    prepared = write_prepared("doltgres", history, db, sql)
    root = os.path.dirname(store_path("doltgres", history, db))
    remove_tree(root)
    ensure_dir(root)
    start(name, v["doltgres"]["image"], cfg.memory["build"], "-e", f"DOLTGRES_PASSWORD={catalog.PW}",
          "-e", f"DOLTGRES_SERVER_TIMEOUT={DOLTGRES_START}",
          "-v", f"{root}:/var/lib/doltgres", "-v", f"{PREPARED}:/prepared:ro")
    try:
        catalog.wait_pg(name)
        catalog.psql_value(name, "postgres", f'CREATE DATABASE "{db}"')
        p = catalog.psql_file(name, db, "/prepared/" + os.path.relpath(prepared, PREPARED))
        errors = catalog.psql_errors(p, sql)
        for stmt in ("SELECT dolt_commit('-A', '--allow-empty', '-m', " +
                     ("'add the indexes after the rows'" if per_row else f"'{db}, imported from sql-megasamples'") + ")",
                     "SELECT dolt_gc()"):
            c = catalog.psql(name, db, stmt)
            if c.returncode != 0:
                raise RuntimeError(f"{stmt.split('(')[0][7:]} failed: {(c.stderr or '').strip()[:200]}")
        got = catalog.pg_catalog(name, db)
        commits = scalar(catalog.psql(name, db, "SELECT COUNT(*) FROM dolt_log"))
        size = scalar(run("docker", "exec", name, "du", "-sb", f"/var/lib/doltgres/{db}"))
    finally:
        run("docker", "rm", "-f", name)
    ref = corpus.reference("postgres", db)
    short, parity = catalog.compare(ref, got, dropped)
    refused = [{"line": e["line"], "object": e.get("object"), "message": e["message"]} for e in errors]
    return outcome(short, got["rows"], ref, size, commits, notes, refused, parity)


# -------------------------------------------------------------------------------- DoltLite ---
def build_doltlite(cfg, history, db, v):
    name, per_row = CONTAINER["doltlite"], history == "per-row"
    text = open(corpus.dump_path("sqlite", db, per_row), encoding="utf-8", newline="").read()
    sql, notes = doltlite_dialect.transform(text, db)
    if per_row:
        sql = doltlite_dialect.strip_transaction(sql)
        sql, n = doltlite_dialect.per_row_commits(sql)
        notes.append(f"a commit after each of {n:,} INSERT statements")
    prepared = write_prepared("doltlite", history, db, sql)
    host = store_path("doltlite", history, db)
    ensure_dir(os.path.dirname(host))
    for f in (host, host + "-journal", host + "-wal", host + "-shm"):
        if os.path.exists(f):
            remove_tree(f)
    start(name, lite_image(v), cfg.memory["build"], "-v", f"{os.path.dirname(host)}:/data",
          "-v", f"{PREPARED}:/prepared:ro")
    path = f"/data/{db}.doltlite"
    try:
        p = catalog.lite_sh(f'doltlite {path} ".read /prepared/{os.path.relpath(prepared, PREPARED)}" >/dev/null', name)
        refused = [{"line": 0, "message": l.strip()[:200]} for l in (p.stderr or "").splitlines() if l.strip()]
        message = "add the indexes after the rows" if per_row else f"{db}, imported from sql-megasamples"
        c = catalog.lite_sh(f"doltlite {path} \"SELECT dolt_commit('-A', '--allow-empty', '-m', '{message}'); "
                            f"VACUUM;\" >/dev/null", name)
        if c.returncode != 0:
            raise RuntimeError("the final commit and VACUUM failed: " + (c.stderr or "").strip()[:200])
        ref = corpus.reference("sqlite", db)
        got = catalog.lite_catalog("doltlite", path, name, os.path.join(PREPARED, ".catalog.sql"),
                                   "/prepared/.catalog.sql", tables=list(ref["rows"]))
        commits = scalar(catalog.lite_sh(f"doltlite {path} 'SELECT COUNT(*) FROM dolt_log'", name))
        size = scalar(catalog.lite_sh(f"du -sb {path}", name))
    finally:
        run("docker", "rm", "-f", name)
    short, parity = catalog.compare(ref, got)
    return outcome(short, got["rows"], ref, size, commits, notes, refused, parity)


# --------------------------------------------------------------------------------- common ---
def scalar(p):
    for tok in (p.stdout or "").split():
        if tok.isdigit():
            return int(tok)
    return None


def tail(p):
    text = ((p.stderr or "") + (p.stdout or "")).strip() if p else ""
    return text[-300:] or "no output"


PROGRESS = re.compile(r"Processed [\d.]+% of the file")
REFUSED = re.compile(r"^error on line (\d+) for query (.*)$", re.I)


def refusals(p):
    """Each statement Dolt refused, once: `dolt sql --continue` reports one as "error on line N for
    query ..." followed by the reason, on both its output streams and between progress meters."""
    lines = [l.strip() for l in PROGRESS.sub("\n", (p.stderr or "") + "\n" + (p.stdout or "")).splitlines() if l.strip()]
    out, seen, current = [], set(), None
    for l in lines:
        m = REFUSED.match(l)
        if m:
            n = int(m.group(1))
            current = None if n in seen else {"line": n, "message": m.group(2)[:100]}
            if current:
                seen.add(n)
                out.append(current)
        elif current and "error" in l.lower() and "reason" not in current:
            current["reason"] = l.split(" : ", 1)[-1][:160]
            current["message"] = f"{current['message']} -- {current['reason']}"
        elif not out and "error" in l.lower():
            out.append({"line": 0, "message": l[:200]})
    return out


def outcome(short, got, ref, size, commits, notes, refused, parity=None):
    rec = {"rows": sum(v or 0 for v in got.values()), "tables": len(ref["rows"]), "bytes": size, "commits": commits,
           "notes": notes, "refused": refused[:40], "refused_count": len(refused)}
    if parity:
        rec["indexes"] = {k: parity[k] for k in ("checked", "missing", "dropped_by_dialect") if k in parity}
        if parity.get("refused"):
            rec["indexes"]["refused"] = parity["refused"]
    if short:
        rec["error"] = "the store is short of rows: " + short
    elif parity and parity.get("missing"):
        refused_names = {(e.get("object") or "").split(": ", 1)[-1].split()[-1] for e in refused if e.get("object")}
        unexplained = [i for i in parity["missing"] if i.split("|")[1] not in refused_names]
        if unexplained:
            rec["error"] = f"{len(unexplained)} of {parity['checked']} indexes missing, first {unexplained[0][:120]}"
    return rec


BUILDERS = {"dolt": build_dolt, "doltgres": build_doltgres, "doltlite": build_doltlite}


def build(cfg, only=None, engine=None, force=False):
    held, holder = lock("build")
    if held is None:
        sys.exit(f"{holder} holds build/build.lock; one build at a time")
    up = set(run("docker", "ps", "--format", "{{.Names}}").stdout.split())
    if up & {"doltsamples-dolt", "doltsamples-doltgres", "doltsamples-doltlite", "doltsamples-workbench"}:
        sys.exit("the stack is up and mounts the stores; `make down` first, then build, then `make up`")
    v = versions()
    todo = [(e, h, db) for e, h, db in cfg.wanted() if (not only or db in only) and (not engine or e == engine)]
    if not todo:
        print("nothing to build: dolt-megasamples.yaml (or --only/--engine) names no database")
        return 0
    recs = records()
    failed = 0
    print(f"{len(todo)} store(s); build memory {cfg.memory['build']}", flush=True)
    for i, (e, h, db) in enumerate(todo, 1):
        k = key(e, h, db)
        label = f"[{i}/{len(todo)}] {e:<9} {h:<8} {db:<22}"
        try:
            fresh = current(recs.get(k), e, h, db, v)
        except (OSError, RuntimeError) as exc:
            print(f"  x {label} {exc}", flush=True)
            failed += 1
            continue
        if fresh and not force:
            print(f"  = {label} built already ({human(recs[k]['bytes'] or 0)}, {recs[k]['commits']:,} commits)", flush=True)
            continue
        t0 = time.time()
        try:
            rec = BUILDERS[e](cfg, h, db, v)
        except (RuntimeError, OSError) as exc:
            rec = {"error": str(exc)[:400]}
        rec.update({"engine": e, "history": h, "database": db, "version": v[e]["version"], "built": now(),
                    "seconds": round(time.time() - t0, 1), "memory_limit": cfg.memory["build"],
                    "status": "error" if "error" in rec else "done", "store": rel(store_path(e, h, db))})
        try:
            rec["export"] = export_digest(e, h, db)
        except OSError:
            pass
        recs = records()
        recs[k] = rec
        save_json(STORES, recs)
        if rec["status"] == "done":
            extra = f"; {rec['refused_count']} statement(s) refused" if rec.get("refused_count") else ""
            print(f"  . {label} {human(rec['bytes'] or 0):>10} {rec['commits'] or 0:>11,} commits "
                  f"{duration(rec['seconds']):>12}{extra}", flush=True)
        else:
            failed += 1
            print(f"  x {label} {rec['error'][:160]}", flush=True)
    print(f"\n{len(todo) - failed} of {len(todo)} store(s) ready; build/stores.json records them"
          + ("" if not failed else f"; {failed} failed (see above)"), flush=True)
    return 1 if failed else 0


def status(cfg):
    """What the configuration asks for beside what is built."""
    recs, v = records(), versions()
    for e, h, db in cfg.wanted():
        rec = recs.get(key(e, h, db))
        if rec and current(rec, e, h, db, v):
            state = f"built   {human(rec['bytes'] or 0):>10} {rec['commits'] or 0:>11,} commits"
        elif rec and rec.get("status") == "error":
            state = "failed  " + rec["error"][:80]
        elif rec:
            state = "stale   (a newer engine version or export; `make build` rebuilds it)"
        else:
            state = "not built"
        print(f"  {e:<9} {h:<8} {db:<22} {state}")
    return 0


__all__ = ["build", "status", "store_path", "HISTORY_LABEL"]
