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

DOLTGRES = "doltsamples-doltgres"
DOLTLITE = "doltsamples-doltlite"
NETWORK = "dolt-megasamples_default"
CONSOLES = [("landing page", 8090), ("phpMyAdmin", 8091), ("Adminer", 8092), ("DbGate", 8093),
            ("CloudBeaver", 8094), ("Dolt Workbench", 8095)]
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


def main():
    # Dolt over the MySQL protocol, through the mysql client of the sql-megasamples image
    for user, pw, want_write in (("demo", "demo", False), ("admin", "admin", True)):
        p = run("docker", "run", "--rm", "--network", NETWORK, "--label", "doltsamples.transient=true", MYSQL_IMAGE,
                "mysql", "-hdolt", f"-u{user}", f"-p{pw}", "-N", "-e", "SELECT COUNT(*) FROM sakila.film")
        check(f"Dolt as {user}: sakila.film", p.stdout.strip() == "1000", p.stdout.strip() or p.stderr.strip()[-100:])
        p = run("docker", "run", "--rm", "--network", NETWORK, "--label", "doltsamples.transient=true", MYSQL_IMAGE,
                "mysql", "-hdolt", f"-u{user}", f"-p{pw}", "-N", "-e",
                "START TRANSACTION; INSERT INTO sakila.language(name) VALUES ('probe'); ROLLBACK")
        check(f"Dolt as {user}: {'may' if want_write else 'may not'} write", (p.returncode == 0) == want_write,
              (p.stderr.strip().splitlines() or ["ok"])[-1][-100:])
    # DoltgreSQL
    rc, out = pg("postgres", os.environ.get("DOLTGRES_PASSWORD", "doltsamples"), "postgres",
                 "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1")
    dbs = out.splitlines() if rc == 0 else []
    check("DoltgreSQL answers as postgres", rc == 0, f"{len(dbs)} databases" if rc == 0 else out)
    for user, pw, want_write in (("demo", "demo", False), ("admin", "admin", True)):
        rc, out = pg(user, pw, "sakila", "SELECT COUNT(*) FROM film")
        check(f"DoltgreSQL as {user}: sakila.film", out == "1000", out)
        rc, out = pg(user, pw, "sakila", "SELECT COUNT(*) FROM dolt_log")
        check(f"DoltgreSQL as {user}: dolt_log", rc == 0 and out.isdigit(), out)
        rc, out = pg(user, pw, "sakila", "BEGIN; INSERT INTO language(name) VALUES ('probe'); ROLLBACK")
        check(f"DoltgreSQL as {user}: {'may' if want_write else 'may not'} write", (rc == 0) == want_write, out[-100:])
    short = []
    for db in dbs:
        rc, out = pg("demo", "demo", db, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                                           "AND table_type = 'BASE TABLE' ORDER BY 1 LIMIT 1")
        t = out.splitlines()[0] if rc == 0 and out else None
        rc2, out2 = pg("demo", "demo", db, f'SELECT COUNT(*) FROM "{t}"') if t else (1, "no table")
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
    for label, url in (("MySQL login for Dolt", "http://127.0.0.1:8092/?server=dolt&db=sakila"),
                       ("PostgreSQL login for DoltgreSQL", "http://127.0.0.1:8092/?pgsql=doltgres&db=sakila")):
        status, err = http(url)
        check(f"Adminer offers the {label}", status == 200, err or f"HTTP {status}")
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed" + (": " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
