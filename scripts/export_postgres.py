#!/usr/bin/env python3
"""pg_dump every database out of the running sql-megasamples PostgreSQL, and record the reference
every PostgreSQL-pair load is checked against.

  python3 scripts/export_postgres.py [--only sakila ...] [--force]

Three dumps per database into build/dumps/postgres/: `<db>.copy.sql` (pg_dump's default COPY
form, the one-shot input), `<db>.inserts.sql` (`--inserts`: one INSERT per row, the per-row
input) and `<db>.schema.sql` (`--schema-only`, what the preflight loads). `--no-owner
--no-privileges` because the loading servers have neither the source's roles nor its grants.
`<db>.reference.json` holds the rows per table, the index set (pg_indexes.indexdef) and the
object counts as the source answers them, read with the same queries the loads use afterwards.
"""
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import human  # noqa: E402
from pairs import PG_DUMPS, pg_catalog, psql_value  # noqa: E402

SOURCE = os.environ.get("MEGASAMPLES_POSTGRES_CONTAINER", "megasamples-postgres")
NOT_SAMPLES = {"postgres", "megasamples"}


def databases():
    out = psql_value(SOURCE, "postgres", "SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1")
    return [d for d in out.splitlines() if d and d not in NOT_SAMPLES]


def dump(db, path, *flags):
    with open(path + ".part", "wb") as fh:
        p = subprocess.run(["docker", "exec", SOURCE, "pg_dump", "-U", "postgres", "--no-owner", "--no-privileges",
                            "--encoding=UTF8", *flags, db], stdout=fh, stderr=subprocess.PIPE)
    if p.returncode != 0:
        os.remove(path + ".part")
        raise RuntimeError(f"pg_dump {db} {' '.join(flags)}: {p.stderr.decode(errors='replace').strip()[:300]}")
    os.replace(path + ".part", path)
    return os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true", help="re-export databases already exported")
    a = ap.parse_args()
    os.makedirs(PG_DUMPS, exist_ok=True)
    dbs = a.only or databases()
    for db in dbs:
        ref_path = os.path.join(PG_DUMPS, f"{db}.reference.json")
        if os.path.exists(ref_path) and not a.force:
            print(f"  = {db}: exported already", flush=True)
            continue
        t0 = time.time()
        sizes = {kind: dump(db, os.path.join(PG_DUMPS, f"{db}.{kind}.sql"), *flags)
                 for kind, flags in (("copy", ()), ("inserts", ("--inserts",)), ("schema", ("--schema-only",)))}
        ref = pg_catalog(SOURCE, db)
        ref.update({"database": db, "source": SOURCE, "exported": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "dump_bytes": sizes, "pg_dump": subprocess.run(["docker", "exec", SOURCE, "pg_dump", "--version"],
                                                                  capture_output=True, text=True).stdout.strip()})
        with open(ref_path, "w", encoding="utf-8") as fh:
            json.dump(ref, fh, indent=1, sort_keys=True)
        print(f"  . {db}: {len(ref['rows'])} tables, {sum(v or 0 for v in ref['rows'].values()):,} rows, "
              f"{len(ref['indexes'])} indexes; copy {human(sizes['copy'])}, inserts {human(sizes['inserts'])} "
              f"({time.time() - t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
