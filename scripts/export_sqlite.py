#!/usr/bin/env python3
"""Copy every SQLite database file sql-megasamples built, write its dump, and record the reference
every SQLite-pair load is checked against.

  python3 scripts/export_sqlite.py [--only sakila ...] [--force]

Into build/dumps/sqlite/: `<db>.sqlite` (the file itself, the reference the loads are counted
against), `<db>.dump.sql` (sqlite3's `.dump`: one INSERT per row inside one transaction, the
input of every load once doltlite_dialect.py has had it) and `<db>.schema.sql` (`.schema`, what
the preflight loads). The shells run in the DoltLite image (scripts/lite_image.py), because the
sqlite3 there is the one the baseline loads use. `<db>.reference.json` holds the rows per table,
the index set (PRAGMA index_list / index_info) and the object counts, read the way the loads read
them back afterwards.

The files come from sql-megasamples' build tree (MEGASAMPLES_DIR/build/sqlite/<db>/<db>.sqlite);
failing that, from its running `megasamples-sqlite` container.
"""
import argparse, json, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MEGASAMPLES_DIR, ROOT, human, run  # noqa: E402
from pairs import LITE_DUMPS, LITE_IMAGE, lite_catalog  # noqa: E402

EXPORTER = "doltsamples-sqlite-export"


def source_dirs():
    for d in (MEGASAMPLES_DIR, os.path.join(os.path.dirname(ROOT), "sql-megasamples"),
              os.path.join(os.path.dirname(ROOT), "mysql-megasamples")):
        if os.path.isdir(os.path.join(d, "build", "sqlite")):
            yield os.path.join(d, "build", "sqlite")


def databases():
    for d in source_dirs():
        names = sorted(n for n in os.listdir(d) if os.path.exists(os.path.join(d, n, f"{n}.sqlite")))
        if names:
            return d, names
    p = run("docker", "exec", "megasamples-sqlite", "sh", "-c", "ls /data/*.sqlite 2>/dev/null")
    names = sorted(os.path.basename(l)[:-7] for l in p.stdout.split() if l.endswith(".sqlite"))
    return None, names


def fetch(src_dir, db, dest):
    if src_dir:
        shutil.copyfile(os.path.join(src_dir, db, f"{db}.sqlite"), dest + ".part")
    else:
        p = run("docker", "cp", f"megasamples-sqlite:/data/{db}.sqlite", dest + ".part")
        if p.returncode != 0:
            raise RuntimeError(f"docker cp {db}: {p.stderr.strip()[:200]}")
    os.replace(dest + ".part", dest)


def exporter_up():
    run("docker", "rm", "-f", EXPORTER)
    p = run("docker", "run", "-d", "--name", EXPORTER, "--label", "doltsamples.transient=true",
            "-v", f"{LITE_DUMPS}:/dumps/sqlite", "-v", f"{os.path.dirname(LITE_DUMPS)}:/dumps", LITE_IMAGE)
    if p.returncode != 0:
        raise RuntimeError(f"could not start {EXPORTER}: {p.stderr.strip()[:200]} (python3 scripts/lite_image.py first)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(LITE_DUMPS, exist_ok=True)
    src_dir, names = databases()
    dbs = a.only or names
    exporter_up()
    try:
        for db in dbs:
            ref_path = os.path.join(LITE_DUMPS, f"{db}.reference.json")
            if os.path.exists(ref_path) and not a.force:
                print(f"  = {db}: exported already", flush=True)
                continue
            t0 = time.time()
            fetch(src_dir, db, os.path.join(LITE_DUMPS, f"{db}.sqlite"))
            for kind, cmd in (("dump", ".dump"), ("schema", ".schema")):
                p = run("docker", "exec", EXPORTER, "sh", "-c",
                        f"sqlite3 /dumps/sqlite/{db}.sqlite '{cmd}' > /dumps/sqlite/{db}.{kind}.sql.part "
                        f"&& mv /dumps/sqlite/{db}.{kind}.sql.part /dumps/sqlite/{db}.{kind}.sql")
                if p.returncode != 0:
                    raise RuntimeError(f"sqlite3 {cmd} {db}: {p.stderr.strip()[:200]}")
            ref = lite_catalog("sqlite3", f"/dumps/sqlite/{db}.sqlite", container=EXPORTER,
                               script_host=os.path.join(LITE_DUMPS, "catalog.sql"),
                               script_inside="/dumps/sqlite/catalog.sql")
            sizes = {k: os.path.getsize(os.path.join(LITE_DUMPS, f"{db}.{k}")) for k in ("sqlite", "dump.sql", "schema.sql")}
            v = run("docker", "exec", EXPORTER, "sqlite3", "-version").stdout.strip()
            ref.update({"database": db, "source": src_dir or "megasamples-sqlite", "sqlite3": v,
                        "exported": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "file_bytes": sizes})
            with open(ref_path, "w", encoding="utf-8") as fh:
                json.dump(ref, fh, indent=1, sort_keys=True)
            print(f"  . {db}: {len(ref['rows'])} tables, {sum(v or 0 for v in ref['rows'].values()):,} rows, "
                  f"{len(ref['indexes'])} indexes; file {human(sizes['sqlite'])}, dump {human(sizes['dump.sql'])} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    finally:
        run("docker", "rm", "-f", EXPORTER)
        for f in ("catalog.sql",):
            try:
                os.remove(os.path.join(LITE_DUMPS, f))
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
