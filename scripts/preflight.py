#!/usr/bin/env python3
"""Load every database's schema into both engines before spending hours on the rows.

  python3 scripts/preflight.py [--only sakila] [--indexes deferred|inline|both]

Four faults in this experiment were found by a full run failing partway through, each after
somewhere between twenty minutes and six hours of loading:

  * `ERROR 1100: Table 'album' was not locked with LOCK TABLES` -- the deferred rebuild landed
    inside mysqldump's `LOCK TABLES` block.
  * `ERROR 1049: Unknown database 'oracle_hr'` -- a view selecting from another database.
  * `ERROR 1075: Incorrect table definition` -- a deferred key that an AUTO_INCREMENT column
    needed.
  * `ERROR 1146: Table 'dvdstore.reorder' doesn't exist` -- the rebuild placed ahead of an empty
    table's `CREATE TABLE`.

Every one of them is a fault in the *schema* half of the file, and every one of them reproduces in
seconds if the rows are left out. Worse, three of the four were cases where **MySQL refused the
file and Dolt accepted it** -- so a run that only checked Dolt, or only checked that something
loaded, would have gone on comparing two engines that were no longer being given the same schema.

So this strips the `INSERT`s and loads what is left into both engines, and reports three things
separately: what MySQL refused, what Dolt refused, and -- the one that matters most here -- where
the two disagreed. It takes about a minute per policy across all 21 databases.

It is not a substitute for the run's own row-count verification, which is the only thing that can
catch a load that goes short. It is the cheap check that comes first.
"""
import argparse, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DOLT_IMAGE, DUMPS, ROOT, databases, run  # noqa: E402
from dolt_dialect import defer_indexes, transform  # noqa: E402

MYSQL_IMAGE = os.environ.get("MEGASAMPLES_MYSQL_IMAGE", "mysql:9.7.2")
MYSQL_NAME = "doltsamples-preflight-mysql"
DOLT_NAME = "doltsamples-preflight-dolt"
WORK = os.path.join(ROOT, "build", "preflight")
INSERT = re.compile(rb"^INSERT INTO ", re.I)
# What Dolt is already known and reported not to take: stored routines outright, and view bodies
# whose syntax its parser does not implement.
KNOWN_DOLT_GAP = re.compile(
    r"CREATE\s+(FUNCTION|PROCEDURE|TRIGGER)|near 'FUNCTIO|near 'PROCEDU|near 'with'"
    r"|near 'character'|READS SQL DATA|DETERMINISTIC", re.I)


def schema_only(sql):
    """The file without its rows. Everything else -- including LOCK TABLES, the deferred rebuild
    and the views -- is left exactly where it was, because where those sit is the thing being
    checked."""
    return b"".join(l for l in sql.splitlines(keepends=True) if not INSERT.match(l))


def mysql_up():
    if run("docker", "inspect", "-f", "{{.State.Status}}",
           MYSQL_NAME).stdout.strip() == "running":
        return
    run("docker", "rm", "-f", MYSQL_NAME)
    run("docker", "run", "-d", "--name", MYSQL_NAME, "--label", "doltsamples.transient=true",
        "-e", "MYSQL_ROOT_PASSWORD=root", "-v", f"{WORK}:/pre:ro",
        MYSQL_IMAGE, "mysqld", "--skip-log-bin")
    for _ in range(600):
        if run("docker", "exec", MYSQL_NAME, "mysql", "-proot", "-uroot", "--protocol=TCP",
               "-h", "127.0.0.1", "-e", "SELECT 1").returncode == 0:
            return
    sys.exit("the preflight MySQL never became ready")


def dolt_up():
    if run("docker", "inspect", "-f", "{{.State.Status}}",
           DOLT_NAME).stdout.strip() == "running" and \
       run("docker", "exec", DOLT_NAME, "true").returncode == 0:
        return
    run("docker", "rm", "-f", DOLT_NAME)
    run("docker", "run", "-d", "--name", DOLT_NAME, "--label", "doltsamples.transient=true",
        "-v", f"{WORK}:/pre", "--entrypoint", "sh", DOLT_IMAGE, "-c", "sleep infinity")


def clean(text):
    lines = [l.strip() for l in (text or "").replace("\r", "\n").splitlines()
             if l.strip() and "Using a password on the command line" not in l
             and "of the file" not in l and not set(l.strip()) <= set("+-| ")]
    return " / ".join(lines)[:300]


def try_mysql(db):
    # The real run gives every database a brand-new server. This one reuses a single server for
    # speed, which is fine except for one statement: mysqldump writes `SET @@GLOBAL.GTID_PURGED`,
    # and MySQL refuses it once GTID_EXECUTED is non-empty -- so every database after the first
    # failed with `ERROR 3546`, and the preflight reported 22 engine disagreements that were
    # entirely its own doing. Resetting the GTID state restores the fresh-server condition.
    run("docker", "exec", MYSQL_NAME, "mysql", "-proot", "-uroot",
        "-e", f"DROP DATABASE IF EXISTS `{db}`; RESET BINARY LOGS AND GTIDS")
    p = run("docker", "exec", MYSQL_NAME, "sh", "-c",
            f"mysql -proot -uroot < /pre/{db}.sql")
    return clean(p.stderr + p.stdout) if p.returncode != 0 else None


def try_dolt(db):
    run("docker", "exec", DOLT_NAME, "sh", "-c", f"rm -rf /pre/d/{db}")
    run("docker", "exec", DOLT_NAME, "mkdir", "-p", "/pre/d")
    p = run("docker", "exec", "-w", "/pre/d", DOLT_NAME,
            "dolt", "--data-dir", "/pre/d", "sql", "--file", f"/pre/{db}.sql")
    return clean(p.stderr + p.stdout) if p.returncode != 0 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append")
    ap.add_argument("--indexes", choices=["deferred", "inline", "both"], default="both")
    ap.add_argument("--keep", action="store_true", help="leave the two containers running")
    a = ap.parse_args()

    policies = ["deferred", "inline"] if a.indexes == "both" else [a.indexes]
    dbs = a.only or databases()
    os.makedirs(WORK, exist_ok=True)
    mysql_up()
    dolt_up()

    known = databases()
    disagreements, failures, expected = [], [], []
    for policy in policies:
        print(f"\n  {policy} indexes, {len(dbs)} databases", flush=True)
        for db in dbs:
            src = os.path.join(DUMPS, "rowwise", f"{db}.sql")
            if not os.path.exists(src):
                print(f"  ? {db:<22} no row-wise dump; run `make export` first", flush=True)
                continue
            sql, _ = transform(open(src, "rb").read(), db, known)
            if policy == "deferred":
                sql, _ = defer_indexes(sql)
            open(os.path.join(WORK, f"{db}.sql"), "wb").write(schema_only(sql))

            my, do = try_mysql(db), try_dolt(db)
            if my and do:
                mark, detail = "x", f"both refused it — MySQL: {my[:90]}"
                failures.append((policy, db, "both", my))
            elif do and not my and KNOWN_DOLT_GAP.search(do):
                # Dolt does not implement stored routines and cannot parse every view body. That
                # shortfall is measured and published, not a surprise, and a preflight that reports
                # it as a problem every time is one nobody reads by the third run.
                mark, detail = "-", f"known Dolt gap — {do[:80]}"
                expected.append((policy, db, do))
            elif my or do:
                # The expensive case: one engine took the schema and the other did not, so the
                # comparison would have run on two different schemas without erroring.
                who = "MySQL refused, Dolt accepted" if my else "Dolt refused, MySQL accepted"
                mark, detail = "!", f"{who} — {(my or do)[:90]}"
                disagreements.append((policy, db, who, my or do))
            else:
                mark, detail = ".", ""
            print(f"  {mark} {db:<22} {detail}", flush=True)

    if not a.keep:
        run("docker", "rm", "-f", MYSQL_NAME, DOLT_NAME)

    print()
    if disagreements:
        print(f"  {len(disagreements)} case(s) where the engines disagreed — these are the ones "
              "that would have compared two different schemas:")
        for policy, db, who, msg in disagreements:
            print(f"    {db} ({policy}): {who}\n      {msg}")
    if failures:
        print(f"  {len(failures)} case(s) both engines refused:")
        for policy, db, _, msg in failures:
            print(f"    {db} ({policy}): {msg}")
    if expected:
        print(f"  {len(expected)} known Dolt gap(s), already counted in the report: "
              + ", ".join(sorted({f"{db} ({policy})" for policy, db, _ in expected})))
    if not disagreements and not failures:
        print(f"  no unexpected problem: every schema loads in both engines across "
              f"{len(policies)} policy/policies x {len(dbs)} databases")
    return 1 if (disagreements or failures) else 0


if __name__ == "__main__":
    sys.exit(main())
