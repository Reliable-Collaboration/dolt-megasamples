"""Prove the stack that is up answers: both accounts on Dolt and on DoltgreSQL, every DoltLite file,
every console's front page, and the Workbench's saved connections. `make test` after `make up`.

Only what this configuration serves is checked. Every line is a check that ran; the exit status is 1
if any failed. Nothing is written into a served store: the read-only account is proved read-only by
being refused, and the full-access account writes only into a scratch database it then drops.
"""
import json, os, sys, time, urllib.error, urllib.request

from doltsamples import corpus
from doltsamples.stack import CONTAINERS, MYSQL_CLIENT, NETWORK, SERVE
from doltsamples.util import TRANSIENT, load_json, run

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'.' if ok else 'x'} {name}" + (f"  {detail[:120]}" if detail else ""), flush=True)
    return ok


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


def largest(source, db):
    """The largest table of a database and its row count, from the reference its export recorded."""
    try:
        rows = corpus.reference(source, db)["rows"]
    except RuntimeError:
        return None, None
    t, n = max(rows.items(), key=lambda kv: kv[1] or 0)
    return (t.split(".", 1)[1] if source == "postgres" else t), n


def mysql(user, pw, sql):
    p = run("docker", "run", "--rm", "--network", NETWORK, "--label", TRANSIENT, MYSQL_CLIENT,
            "mysql", "-hdolt", f"-u{user}", f"-p{pw}", "-N", "-e", sql)
    return p.returncode, (p.stdout.strip() or p.stderr.strip())


def pg(user, pw, db, sql):
    p = run("docker", "exec", "-e", f"PGPASSWORD={pw}", CONTAINERS["doltgres"], "psql", "-X", "-h", "127.0.0.1",
            "-U", user, "-d", db, "-tA", "-c", sql)
    return p.returncode, (p.stdout.strip() or p.stderr.strip())


def check_dolt(stores, PW):
    for s in stores:
        table, want = largest("mysql", s["database"])
        rc, out = mysql("demo", PW["demo"], f"SELECT COUNT(*) FROM `{s['name']}`.`{table}`; "
                                            f"SELECT COUNT(*) FROM `{s['name']}`.dolt_log")
        got = out.split()
        check(f"Dolt: {s['name']}.{table} has its rows, and {s['commits']:,} commits in its log",
              rc == 0 and got[:2] == [str(want), str(s["commits"])], " ".join(got[:2]) if rc == 0 else out[-100:])
    for user, may in (("demo", False), ("admin", True)):
        rc, out = mysql(user, PW[user], "DROP DATABASE IF EXISTS probe_stack_check; CREATE DATABASE probe_stack_check; "
                                        "DROP DATABASE probe_stack_check")
        check(f"Dolt as {user}: {'may' if may else 'may not'} write", (rc == 0) == may, (out.splitlines() or ["ok"])[-1][-100:])


def check_doltgres(stores, PW):
    for s in stores:
        table, want = largest("postgres", s["database"])
        rc, out = pg("demo", PW["demo"], s["name"], f'SELECT COUNT(*) FROM "{table}"')
        rc2, out2 = pg("demo", PW["demo"], s["name"], "SELECT COUNT(*) FROM dolt_log")
        check(f"DoltgreSQL: {s['name']}.{table} has its rows, and {s['commits']:,} commits in its log",
              rc == 0 and rc2 == 0 and out == str(want) and out2 == str(s["commits"]), f"{out} {out2}"[:100])
    probe = stores[0]["name"]
    rc, out = pg("demo", PW["demo"], probe, "CREATE TABLE probe_stack_check (id int)")
    if rc == 0:
        pg("admin", PW["admin"], probe, "DROP TABLE probe_stack_check")
    check("DoltgreSQL as demo: may not write into a served database", rc != 0, out[-100:])
    pg("admin", PW["admin"], "postgres", "DROP DATABASE IF EXISTS probe_stack_check")
    rc, out = pg("admin", PW["admin"], "postgres", "CREATE DATABASE probe_stack_check")
    if rc == 0:
        pg("admin", PW["admin"], "postgres", "DROP DATABASE probe_stack_check")
    check("DoltgreSQL as admin: may write", rc == 0, out[-100:])


def check_doltlite(stores):
    for s in stores:
        p = run("docker", "exec", CONTAINERS["doltlite"], "doltlite", f"/data/{s['name']}.doltlite",
                "SELECT COUNT(*) FROM dolt_log")
        got = p.stdout.strip()
        check(f"DoltLite: {s['name']}.doltlite opens with {s['commits']:,} commits in its log",
              p.returncode == 0 and got == str(s["commits"]), got or (p.stderr or "").strip()[:100])


def check_workbench(engines, P):
    def gql(query):
        req = urllib.request.Request(f"http://127.0.0.1:{P['workbench_api']}/graphql",
                                     data=json.dumps({"query": query}).encode(), headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:                                    # noqa: BLE001
            return {"errors": [{"message": str(e)}]}
    saved = {c["name"]: c["connectionUrl"] for c in
             (gql("{ storedConnections { name connectionUrl } }").get("data") or {}).get("storedConnections") or []}
    want = ([n for n in ("Dolt (read-only)", "Dolt (full access)") if engines.get("dolt")]
            + [n for n in ("DoltgreSQL (read-only)", "DoltgreSQL (full access)") if engines.get("doltgres")]
            + [f"DoltLite {s['name']}" for s in engines.get("doltlite") or []])
    check(f"Workbench: {len(want)} connection(s) saved", sorted(saved) == sorted(want),
          f"missing {sorted(set(want) - set(saved))[:4]}" if set(want) - set(saved) else "")
    probes = [(n, k) for n, k in (("Dolt (read-only)", "Mysql"), ("DoltgreSQL (read-only)", "Postgres")) if n in saved]
    probes += [(n, "Sqlite") for n in want if n.startswith("DoltLite ")][:1]
    for name, kind in probes:
        r = gql(f'mutation {{ addDatabaseConnection(name: "{name}", connectionUrl: "{saved[name]}", type: {kind}, '
                f'hideDoltFeatures: false, useSSL: false) {{ currentDatabase }} }}')
        db = ((r.get("data") or {}).get("addDatabaseConnection") or {}).get("currentDatabase")
        check(f"Workbench connects with {name}", bool(db), db or str((r.get("errors") or [{}])[0].get("message", ""))[:100])


def main():
    s = load_json(SERVE, {}) or {}
    stack, engines = s.get("stack") or {}, s.get("engines") or {}
    if not stack:
        sys.exit("nothing has been brought up from this checkout (make up)")
    P, PW, consoles = stack["ports"], stack["passwords"], stack.get("consoles") or []
    if engines.get("dolt"):
        check_dolt(engines["dolt"], PW)
    if engines.get("doltgres"):
        check_doltgres(engines["doltgres"], PW)
    if engines.get("doltlite"):
        check_doltlite(engines["doltlite"])
    for c in consoles:
        status, err = http(f"http://127.0.0.1:{P[c]}/")
        check(f"{c} answers on {P[c]}", status is not None and status < 400, err or f"HTTP {status}")
    if "workbench" in consoles:
        check_workbench(engines, P)
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed" + (": " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0
