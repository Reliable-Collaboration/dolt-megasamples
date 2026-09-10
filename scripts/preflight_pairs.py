#!/usr/bin/env python3
"""Load every schema -- no rows -- into both engines of each new pair, and say what only one side
refuses. The gate before a row is loaded, as scripts/preflight.py was for MySQL and Dolt.

  python3 scripts/preflight_pairs.py [--pair pg|lite] [--only sakila ...]

PostgreSQL pair: `<db>.schema.sql` (pg_dump --schema-only), transformed by doltgres_dialect.py,
through psql into a throwaway PostgreSQL and a throwaway DoltgreSQL; every psql error is read
back into the pg_dump block (type and name) it fell in. SQLite pair: `<db>.schema.sql` (sqlite3
.schema), transformed by doltlite_dialect.py, through the sqlite3 and doltlite shells. What a
dialect rule already removed is listed per database beside what the engine still refused.
Results: build/preflight/pairs.json and the table printed.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import mem, run  # noqa: E402
import doltgres_dialect, doltlite_dialect  # noqa: E402
from pairs import (DOLTGRES_IMAGE, LITE_DUMPS, LITE_IMAGE, PG_DUMPS, POSTGRES_IMAGE, PREFLIGHT, PW,  # noqa: E402
                   exported, psql, psql_errors, psql_file, psql_value, q, wait_pg)

PG = "doltsamples-preflight-postgres"
DG = "doltsamples-preflight-doltgres"
LT = "doltsamples-preflight-lite"
RESULT = os.path.join(PREFLIGHT, "pairs.json")


def up_pg_pair():
    run("docker", "rm", "-f", PG, DG)
    run("docker", "run", "-d", "--name", PG, "--label", "doltsamples.transient=true", *mem("2g"),
        "-e", f"POSTGRES_PASSWORD={PW}", "-v", f"{PREFLIGHT}:/preflight:ro", POSTGRES_IMAGE)
    run("docker", "run", "-d", "--name", DG, "--label", "doltsamples.transient=true", *mem("2g"),
        "-e", f"DOLTGRES_PASSWORD={PW}", "-v", f"{PREFLIGHT}:/preflight:ro", DOLTGRES_IMAGE)
    wait_pg(PG)
    wait_pg(DG)


def up_lite():
    run("docker", "rm", "-f", LT)
    run("docker", "run", "-d", "--name", LT, "--label", "doltsamples.transient=true", *mem("2g"),
        "-v", f"{PREFLIGHT}:/preflight", LITE_IMAGE)


def pg_pair(db):
    text = open(os.path.join(PG_DUMPS, f"{db}.schema.sql"), encoding="utf-8").read()
    sql, notes, dropped = doltgres_dialect.transform(text, db)
    with open(os.path.join(PREFLIGHT, f"{db}.pg.sql"), "w", encoding="utf-8") as fh:
        fh.write(sql)
    out = {"objects": doltgres_dialect.kinds(text), "notes": notes, "dropped": dropped}
    for name, c in (("postgres", PG), ("doltgres", DG)):
        psql(c, "postgres", f"DROP DATABASE IF EXISTS {q(db)}")
        psql_value(c, "postgres", f"CREATE DATABASE {q(db)}")
        t0 = time.time()
        p = psql_file(c, db, f"/preflight/{db}.pg.sql")
        errs = psql_errors(p, sql)
        out[name] = {"seconds": round(time.time() - t0, 1),
                     "refused": [f"{e.get('object') or 'line ' + str(e['line'])}: {e['message']}" for e in errs]}
    return out


def lite_pair(db):
    text = open(os.path.join(LITE_DUMPS, f"{db}.schema.sql"), encoding="utf-8").read()
    sql, notes = doltlite_dialect.transform(text, db)
    with open(os.path.join(PREFLIGHT, f"{db}.lite.sql"), "w", encoding="utf-8") as fh:
        fh.write(sql)
    out = {"objects": doltlite_dialect.kinds(text), "notes": notes, "dropped": []}
    for name, binary, ext in (("sqlite", "sqlite3", "sqlite"), ("doltlite", "doltlite", "doltlite")):
        t0 = time.time()
        p = run("docker", "exec", LT, "sh", "-c",
                f"rm -f /tmp/{db}.{ext}; {binary} /tmp/{db}.{ext} '.read /preflight/{db}.lite.sql' >/dev/null")
        out[name] = {"seconds": round(time.time() - t0, 1),
                     "refused": [l.strip()[:200] for l in (p.stderr or "").splitlines() if l.strip()]}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pair", choices=["pg", "lite"], action="append")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    os.makedirs(PREFLIGHT, exist_ok=True)
    results = json.load(open(RESULT, encoding="utf-8")) if os.path.exists(RESULT) else {}
    try:
        for pair in a.pair or ["pg", "lite"]:
            dbs = a.only or exported(pair)
            if not dbs:
                print(f"nothing exported for the {pair} pair yet", flush=True)
                continue
            (up_pg_pair if pair == "pg" else up_lite)()
            base, versioned = ("postgres", "doltgres") if pair == "pg" else ("sqlite", "doltlite")
            print(f"\n{pair} pair: {len(dbs)} schema(s)\n  {'database':22} {'objects':>8} "
                  f"{base + ' refused':>18} {versioned + ' refused':>18}  dialect rules", flush=True)
            for db in dbs:
                r = (pg_pair if pair == "pg" else lite_pair)(db)
                results.setdefault(pair, {})[db] = r
                with open(RESULT, "w", encoding="utf-8") as fh:
                    json.dump(results, fh, indent=1, sort_keys=True)
                rules = "; ".join(n.split(" ", 1)[0] + (f"({n.split()[2]})" if n[0] in "LG" else "") for n in r["notes"])
                print(f"  {db:22} {sum(r['objects'].values()):>8} {len(r[base]['refused']):>18} "
                      f"{len(r[versioned]['refused']):>18}  {rules}", flush=True)
                for side in (base, versioned):
                    for line in r[side]["refused"][:6]:
                        print(f"      {side}: {line[:150]}")
                    if len(r[side]["refused"]) > 6:
                        print(f"      {side}: ... {len(r[side]['refused']) - 6} more")
    finally:
        run("docker", "rm", "-f", PG, DG, LT)
    print(f"\nrecorded in {os.path.relpath(RESULT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
