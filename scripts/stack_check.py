#!/usr/bin/env python3
"""Prove the stack that stays up answers: both accounts on Dolt and on DoltgreSQL, every DoltLite
file, and every console's front page. `make test-stack` after `make up`.

  python3 scripts/stack_check.py

Every line is a check that ran; the exit status is 1 if any failed. Nothing is written to any
database: the read-only account is proved read-only by being refused an INSERT.
"""
import os, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MYSQL_IMAGE, run  # noqa: E402
import stack_settings  # noqa: E402

S = stack_settings.load()
P, PW = S["ports"], S["passwords"]
DOLTGRES = S["containers"]["doltgres"]
DOLTLITE = S["containers"]["doltlite"]
NETWORK = S["network"]
CONSOLES = [("landing page", P["console"]), ("phpMyAdmin", P["phpmyadmin"]), ("Adminer", P["adminer"]),
            ("DbGate", P["dbgate"]), ("CloudBeaver", P["cloudbeaver"]), ("Dolt Workbench", P["workbench"])]
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'.' if ok else 'x'} {name}" + (f"  {detail[:120]}" if detail else ""), flush=True)
    return ok


def pg(user, pw, db, sql):
    p = run("docker", "exec", "-e", f"PGPASSWORD={pw}", DOLTGRES, "psql", "-X", "-h", "127.0.0.1", "-U", user,
            "-d", db, "-tA", "-c", sql)
    return p.returncode, (p.stdout.strip() or p.stderr.strip())


def http(url, seconds=90):
    last = ""
    for _ in range(seconds // 3):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.status, ""
        except urllib.error.HTTPError as e:
            return e.code, str(e)
        except Exception as e:                                    # noqa: BLE001
            last = str(e)
            time.sleep(3)
    return None, last


def probe_table(db):
    """The largest table of a served database and its row count, from the export's reference."""
    import json as _json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "dumps", "postgres",
                        f"{db}.reference.json")
    if not os.path.exists(path):
        return None, None
    rows = _json.load(open(path, encoding="utf-8"))["rows"]
    t, n = max(rows.items(), key=lambda kv: kv[1] or 0)
    return t.split(".", 1)[1], n


def served(engine):
    """What scripts/stack_config.py said the stack serves for an engine; sakila first when present."""
    import json as _json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "serve.json")
    dbs = []
    if os.path.exists(path):
        dbs = _json.load(open(path, encoding="utf-8"))["engines"].get(engine, {}).get("databases") or []
    return sorted(dbs, key=lambda d: (d != "sakila", d))


def main():
    # Dolt over the MySQL protocol, through the mysql client of the sql-megasamples image
    dolt_db = (served("dolt") or ["sakila"])[0]
    table, want = probe_table(dolt_db)
    for user, pw, want_write in (("demo", PW["demo"], False), ("admin", PW["admin"], True)):
        p = run("docker", "run", "--rm", "--network", NETWORK, "--label", "doltsamples.transient=true", MYSQL_IMAGE,
                "mysql", "-hdolt", f"-u{user}", f"-p{pw}", "-N", "-e", f"SELECT COUNT(*) FROM {dolt_db}.{table}")
        check(f"Dolt as {user}: {dolt_db}.{table}", p.stdout.strip() == str(want), p.stdout.strip() or p.stderr.strip()[-100:])
        # a scratch database created and dropped: the probe writes nothing into a served store, which
        # is a measured one (the first version created a table inside the store and left a change in
        # its working set)
        p = run("docker", "run", "--rm", "--network", NETWORK, "--label", "doltsamples.transient=true", MYSQL_IMAGE,
                "mysql", "-hdolt", f"-u{user}", f"-p{pw}", "-N", "-e",
                "DROP DATABASE IF EXISTS probe_stack_check; CREATE DATABASE probe_stack_check; "
                "DROP DATABASE probe_stack_check")
        check(f"Dolt as {user}: {'may' if want_write else 'may not'} write", (p.returncode == 0) == want_write,
              (p.stderr.strip().splitlines() or ["ok"])[-1][-100:])
    # DoltgreSQL
    rc, out = pg("postgres", PW["doltgres"], "postgres",
                 "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1")
    dbs = out.splitlines() if rc == 0 else []
    check("DoltgreSQL answers as postgres", rc == 0, f"{len(dbs)} databases" if rc == 0 else out)
    pg_db = (served("doltgres") or ["sakila"])[0]
    pg_table, pg_want = probe_table(pg_db)
    for user, pw, want_write in (("demo", PW["demo"], False), ("admin", PW["admin"], True)):
        rc, out = pg(user, pw, pg_db, f'SELECT COUNT(*) FROM "{pg_table}"')
        check(f"DoltgreSQL as {user}: {pg_db}.{pg_table}", out == str(pg_want), out)
        rc, out = pg(user, pw, pg_db, "SELECT COUNT(*) FROM dolt_log")
        check(f"DoltgreSQL as {user}: dolt_log", rc == 0 and out.isdigit(), out)
        # a scratch database, as for Dolt: nothing is written into a served store
        pg(user, pw, "postgres", "DROP DATABASE IF EXISTS probe_stack_check")
        rc, out = pg(user, pw, "postgres", "CREATE DATABASE probe_stack_check")
        if rc == 0:
            pg(user, pw, "postgres", "DROP DATABASE probe_stack_check")
        check(f"DoltgreSQL as {user}: {'may' if want_write else 'may not'} write", (rc == 0) == want_write, out[-100:])
    short = []
    for db in dbs:
        rc, out = pg("demo", PW["demo"], db, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                                           "AND table_type = 'BASE TABLE' ORDER BY 1 LIMIT 1")
        t = out.splitlines()[0] if rc == 0 and out else None
        rc2, out2 = pg("demo", PW["demo"], db, f'SELECT COUNT(*) FROM "{t}"') if t else (1, "no table")
        if not (t and rc2 == 0 and out2.isdigit()):
            short.append(f"{db}: {out2[:60]}")
    check(f"DoltgreSQL as demo: one table of each of {len(dbs)} databases", not short, "; ".join(short))
    # DoltLite files
    p = run("docker", "exec", DOLTLITE, "sh", "-c", "ls /data/*.doltlite 2>/dev/null")
    files = [os.path.basename(f) for f in p.stdout.split()]
    check("DoltLite files present", bool(files), f"{len(files)} files")
    bad = []
    for f in files:
        p = run("docker", "exec", DOLTLITE, "doltlite", f"/data/{f}",
                "SELECT COUNT(*) FROM dolt_log; SELECT COUNT(*) FROM sqlite_schema WHERE type = 'table'")
        lines = p.stdout.split()
        if p.returncode != 0 or len(lines) < 2 or not lines[0].isdigit():
            bad.append(f"{f}: {(p.stderr or p.stdout).strip()[:60]}")
    check("DoltLite: every file opens with a commit log and tables", not bad, "; ".join(bad))
    # consoles
    for name, port in CONSOLES:
        status, err = http(f"http://127.0.0.1:{port}/")
        check(f"{name} on {port}", status is not None and status < 400, err or f"HTTP {status}")
    for label, url in (("MySQL login for Dolt", f"http://127.0.0.1:{P['adminer']}/?server=dolt&db=sakila"),
                       ("PostgreSQL login for DoltgreSQL", f"http://127.0.0.1:{P['adminer']}/?pgsql=doltgres&db=sakila")):
        status, err = http(url)
        check(f"Adminer offers the {label}", status == 200, err or f"HTTP {status}")
    # the Workbench's saved connections, and that its API connects with each engine's account
    import json as _json
    def gql(query):
        req = urllib.request.Request(f"http://127.0.0.1:{P['workbench_api']}/graphql", data=_json.dumps({"query": query}).encode(),
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return _json.loads(r.read().decode())
        except Exception as e:                                    # noqa: BLE001
            return {"errors": [{"message": str(e)}]}
    saved = gql("{ storedConnections { name type } }").get("data", {}).get("storedConnections") or []
    names = sorted(c["name"] for c in saved)
    want = ["DoltgreSQL (full access)", "DoltgreSQL (read-only)", "dolt-megasamples (full access)", "dolt-megasamples (read-only)"]
    servers = [n for n in names if not n.startswith("DoltLite ")]
    check("Workbench: the four server connections saved", servers == want, ", ".join(servers) or "none")
    lite_saved = sorted(n[len("DoltLite "):] for n in names if n.startswith("DoltLite "))
    lite_files = sorted(f[:-len(".doltlite")] for f in files)
    check(f"Workbench: a saved connection for each of {len(lite_files)} DoltLite files", lite_saved == lite_files,
          f"{len(lite_saved)} saved" + ("" if lite_saved == lite_files else f"; missing {sorted(set(lite_files) - set(lite_saved))[:5]}"))
    # connect with the saved connections as saved: the Workbench refuses a known name with a
    # different URL, and the saved URL names whichever database the stack serves first
    saved_url = {c["name"]: c["connectionUrl"] for c in gql("{ storedConnections { name connectionUrl } }")
                 .get("data", {}).get("storedConnections") or []}
    probes = [("DoltgreSQL (read-only)", "Postgres"), ("dolt-megasamples (read-only)", "Mysql")]
    if lite_files:
        lite_db = sorted(lite_files, key=lambda d: (d != "sakila", d))[0]
        probes.insert(0, (f"DoltLite {lite_db}", "Sqlite"))
    for name, kind in probes:
        url = saved_url.get(name, "")
        r = gql(f'mutation {{ addDatabaseConnection(name: "{name}", connectionUrl: "{url}", type: {kind}, '
                f'hideDoltFeatures: false, useSSL: false) {{ currentDatabase }} }}')
        db = ((r.get("data") or {}).get("addDatabaseConnection") or {}).get("currentDatabase")
        check(f"Workbench connects with {name}", bool(db), db or str(r.get("errors", [{}])[0].get("message", ""))[:100])
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed" + (": " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
