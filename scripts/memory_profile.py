#!/usr/bin/env python3
"""Find how much memory Dolt needs to open and query a database, and what that scales with.

  python3 scripts/memory_profile.py [--mode rowcommit] [--only sakila] [--op count]

The question this answers came from watching a 15.5 GB host run out of memory: how much RAM does
Dolt actually want, and what is it a function of -- rows, bytes on disk, or commits?

Those three are usually correlated, which is what makes the question hard to answer from ordinary
data. This experiment can separate them, because it has the same 21 databases stored two ways:

  * `oneshot`   -- the same rows, three commits per database
  * `rowcommit` -- the same rows, one commit per row, up to 3.9 million of them

Same data, same schema, same engine. If the memory a database needs tracks its row count, the two
modes will want the same amount. If it tracks history, they will not.

Method: run one query against one database in a container with a hard memory ceiling, and walk a
ladder of ceilings to find the smallest that does not get the process killed. A kill is
unambiguous -- the kernel's OOM killer returns exit 137 -- so this needs no interpretation of log
output. The ladder is searched by bisection, so each database costs about three attempts rather
than eight.

Every measurement is a *ceiling that worked*, not the peak the process reached, so read the numbers
as "needs no more than this" at the granularity of the ladder.
"""
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DOLT_IMAGE, MYSQL_CONTAINER, ROOT, data_dir, databases, human,  # noqa: E402
                    run)

OUT = os.path.join(ROOT, "build", "memory.json")
# Megabytes. Coarse at the top because the interesting resolution is at the bottom, and because an
# attempt against an 80 GB repository is not cheap.
LADDER = [64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144, 8192]
OPS = {
    "open": "SELECT 1",
    "count": "SELECT COUNT(*) FROM `{table}`",
    "log": "SELECT COUNT(*) FROM dolt_log",
}


def repo_path(mode, db):
    return os.path.join(data_dir(mode), db, db)


def disk_bytes(mode, db):
    """Size of the stored database, read by a container small enough not to matter."""
    p = run("docker", "run", "--rm", "--memory", "256m", "--memory-swap", "256m",
            "-v", f"{os.path.join(ROOT, 'data')}:/data", "--entrypoint", "sh", DOLT_IMAGE,
            "-c", f"du -sb /data/{os.path.basename(data_dir(mode))}/{db}/{db}")
    parts = p.stdout.split()
    return int(parts[0]) if parts and parts[0].isdigit() else None


def biggest_table_and_rows(db):
    """The largest base table and its exact row count, counted rather than estimated."""
    p = run("docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot", "-proot", "-N", "--batch", "-e",
            "SELECT table_name FROM information_schema.tables WHERE table_schema='"
            + db + "' AND table_type='BASE TABLE' ORDER BY table_rows DESC LIMIT 1")
    table = p.stdout.strip().splitlines()[0] if p.stdout.strip() else None
    if not table:
        return None, None
    q = run("docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot", "-proot", "-N", "--batch",
            "-e", f"SELECT COUNT(*) FROM `{db}`.`{table}`")
    rows = int(q.stdout.strip()) if q.stdout.strip().isdigit() else None
    return table, rows


def total_rows(db):
    p = run("docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot", "-proot", "-N", "--batch", "-e",
            "SELECT GROUP_CONCAT(CONCAT('SELECT COUNT(*) FROM `', table_name, '`') SEPARATOR "
            "' UNION ALL ') FROM information_schema.tables WHERE table_schema='" + db
            + "' AND table_type='BASE TABLE'")
    sql = p.stdout.strip()
    if not sql:
        return None
    q = run("docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot", "-proot", "-N", "--batch",
            f"-D{db}", "-e", sql)
    return sum(int(x) for x in q.stdout.split() if x.isdigit()) or None


def commit_count(mode, db, timeout):
    """Commits in the repository, asked at the top of the ladder because a big history needs it."""
    root = f"/data/{os.path.basename(data_dir(mode))}/{db}"
    cmd = ["docker", "run", "--rm", "--memory", f"{LADDER[-1]}m", "--memory-swap",
           f"{LADDER[-1]}m", "-v", f"{os.path.join(ROOT, 'data')}:/data", "-w", root,
           "--entrypoint", "dolt", DOLT_IMAGE, "--data-dir", root, "--use-db", db,
           "sql", "-r", "csv", "-q", "SELECT COUNT(*) FROM dolt_log"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    return next((int(l.strip()) for l in p.stdout.splitlines() if l.strip().isdigit()), None)


def attempt(mode, db, mb, query, timeout):
    """Run one query under a hard ceiling. Returns 'ok', 'oom', 'timeout' or an error string."""
    root = f"/data/{os.path.basename(data_dir(mode))}/{db}"
    cmd = ["docker", "run", "--rm", "--memory", f"{mb}m", "--memory-swap", f"{mb}m",
           "-v", f"{os.path.join(ROOT, 'data')}:/data", "-w", root,
           "--entrypoint", "dolt", DOLT_IMAGE,
           "--data-dir", root, "--use-db", db, "sql", "-r", "csv", "-q", query]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout"
    if p.returncode == 0:
        return "ok"
    if p.returncode == 137:
        return "oom"
    return f"exit {p.returncode}: {(p.stderr or '').strip()[:120]}"


def smallest_that_works(mode, db, query, timeout, verbose=True):
    """Bisect the ladder for the lowest ceiling the query survives.

    Assumes the ladder is monotonic -- if a ceiling works, every larger one does. That is the
    behaviour of an allocator being capped, and it is checked at the top of the ladder first: a
    database that fails even at the maximum is reported as such rather than bisected pointlessly.
    """
    top = attempt(mode, db, LADDER[-1], query, timeout)
    if top != "ok":
        return None, top
    lo, hi = 0, len(LADDER) - 1
    detail = "ok"
    while lo < hi:
        mid = (lo + hi) // 2
        r = attempt(mode, db, LADDER[mid], query, timeout)
        if verbose:
            print(f"      {LADDER[mid]:>5} MB -> {r[:40]}", flush=True)
        if r == "ok":
            hi = mid
        else:
            detail = r
            lo = mid + 1
    return LADDER[lo], detail


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", action="append",
                    help="which stored form to profile (default: every one present on disk)")
    ap.add_argument("--only", action="append")
    ap.add_argument("--op", choices=sorted(OPS), default="count",
                    help="open: just start against the database. count: scan its largest table. "
                         "log: count its commits")
    ap.add_argument("--timeout", type=float, default=1800)
    a = ap.parse_args()

    modes = a.mode or [m for m in ("oneshot", "rowinsert", "rowcommit",
                                   "rowinsert_inline", "rowcommit_inline")
                       if os.path.isdir(data_dir(m))]
    facts = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}

    for mode in modes:
        dbs = a.only or sorted(d for d in databases() if os.path.isdir(repo_path(mode, d)))
        print(f"\n  {mode}: {len(dbs)} database(s), op={a.op}", flush=True)
        for db in dbs:
            table, table_rows = biggest_table_and_rows(db)
            query = OPS[a.op].format(table=table or "dolt_log")
            print(f"    {db}", flush=True)
            t0 = time.time()
            mb, detail = smallest_that_works(mode, db, query, a.timeout)
            rec = {
                "megabytes": mb,
                "outcome": detail if mb is None else "ok",
                "seconds_to_profile": round(time.time() - t0, 1),
                "rows": total_rows(db),
                "largest_table_rows": table_rows,
                "disk_bytes": disk_bytes(mode, db),
                "commits": commit_count(mode, db, a.timeout),
                "op": a.op,
                "query_table": table,
                "ladder_top_mb": LADDER[-1],
            }
            facts.setdefault(mode, {})[db] = rec
            json.dump(facts, open(OUT, "w", encoding="utf-8"), indent=1, sort_keys=True)
            shown = f"{mb} MB" if mb else f"more than {LADDER[-1]} MB ({detail[:40]})"
            print(f"      => {shown}   rows={rec['rows'] or '?'} "
                  f"disk={human(rec['disk_bytes']) if rec['disk_bytes'] else '?'} "
                  f"commits={rec['commits'] or '?'}", flush=True)

    print(f"\n  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
