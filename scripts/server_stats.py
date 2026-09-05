#!/usr/bin/env python3
"""Measure what a running `dolt sql-server` adds to a database directory, without disturbing the
measurement of the database itself.

  python3 scripts/server_stats.py

The size figures everywhere else in this repository come from a run with **no server** — the load is
done by the `dolt` CLI and nothing serves the data afterwards. That is deliberate: a server that has
served a database leaves things behind in its directory, and mixing the two states is how an earlier
version of this experiment ended up reporting a total that moved by 68 MB between runs for no
apparent reason.

So this measures the server's contribution separately and on a **copy**, which is the only way to
have both numbers without one changing the other:

  1. copy `data/dolt` to `data/dolt-served`
  2. start a server on the copy and run one query against every database, so it collects statistics
  3. stop the server and measure `.dolt/stats` per database

The result is recorded as `server_stats_bytes` and reported in its own section. It is real disk that
a real deployment will use; it is just not the size of the data.
"""
import json, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, DOLT_IMAGE, human, load_results, run, save_results  # noqa: E402

SERVED = f"{DATA}-served"
NAME = "doltsamples-statsprobe"


def main():
    results = load_results()
    dbs = sorted(d for d in os.listdir(DATA) if os.path.isdir(os.path.join(DATA, d)))
    if not dbs:
        sys.exit("no Dolt databases; run `make load` first")

    print(f"copying {len(dbs)} database(s) so the served copy cannot affect the measured one")
    run("docker", "run", "--rm", "-v", f"{DATA}:/src", "-v", f"{os.path.dirname(SERVED)}:/dst",
        "--entrypoint", "sh", DOLT_IMAGE, "-c",
        f"rm -rf /dst/{os.path.basename(SERVED)} && cp -a /src /dst/{os.path.basename(SERVED)}")

    run("docker", "rm", "-f", NAME)
    p = run("docker", "run", "-d", "--name", NAME, "--label", "doltsamples.transient=true",
            "-e", "DOLT_ROOT_PASSWORD=root", "-v", f"{SERVED}:/var/lib/dolt", DOLT_IMAGE)
    if p.returncode != 0:
        sys.exit(f"could not start the probe server: {p.stderr.strip()[:200]}")
    try:
        for _ in range(60):
            if run("docker", "exec", NAME, "bash", "-c",
                   "cat < /dev/null > /dev/tcp/127.0.0.1/3306").returncode == 0:
                break
            time.sleep(2)
        else:
            sys.exit("the probe server never started listening")

        # Every table, not just the catalogue. Dolt collects statistics per table when a query
        # touches it, so a single `information_schema` query produces almost nothing -- 22 KB a
        # database -- while real use produces a great deal more. Reading every table is the closest
        # cheap approximation of a database that has actually been used.
        print("querying every table in every database, which is what triggers statistics")
        for db in dbs:
            t = run("docker", "exec", NAME, "dolt", "--data-dir", "/var/lib/dolt", "--use-db", db,
                    "sql", "-r", "csv", "-q",
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'")
            tables = [l.strip() for l in t.stdout.splitlines()[1:] if l.strip()]
            if not tables:
                continue
            sql = " UNION ALL ".join(f"SELECT COUNT(*) FROM `{x}`" for x in tables)
            run("docker", "exec", NAME, "dolt", "--data-dir", "/var/lib/dolt", "--use-db", db,
                "sql", "-q", sql)
            print(f"    {db:<24} {len(tables)} tables read")
        print("  waiting for statistics collection to settle")
        time.sleep(60)          # collection is asynchronous
    finally:
        run("docker", "rm", "-f", NAME)

    total = 0
    for db in dbs:
        p = run("docker", "run", "--rm", "-v", f"{SERVED}:/d", "--entrypoint", "du", DOLT_IMAGE,
                "-sb", f"/d/{db}/.dolt/stats")
        n = int(p.stdout.split()[0]) if p.returncode == 0 and p.stdout.split() else 0
        results.setdefault(db, {})["server_stats_bytes"] = n
        total += n
        if n:
            print(f"  . {db:<24} {human(n):>10}")
    save_results(results)
    print(f"\nstatistics a running server wrote: {human(total)} across {len(dbs)} databases")
    print(f"the served copy is left at {os.path.relpath(SERVED, os.getcwd())}; "
          f"`make clean-data` removes it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
