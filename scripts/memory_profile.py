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
as "needs no more than this" at the granularity of the ladder. Where a database fails at every rung
the result is reported as a bound rather than a number, which is a reason to keep the top of the
ladder above anything the corpus needs.
"""
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DOLT_IMAGE, DOLT_VERSION, ROOT, data_dir, human,  # noqa: E402
                    run)

OUT = os.path.join(ROOT, "build", "memory.json")
# Megabytes. Fine at the bottom, where most databases sit, and continuing far enough up that a
# result is a measurement rather than "more than the ladder". Stopping at 8192 turned the largest
# database into a lower bound; it actually needs between 11,264 and 12,288 MB, which the ladder
# could not say. The top is sized to what a 19.5 GB host can give one container.
LADDER = [64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144, 8192,
          9216, 10240, 11264, 12288, 13312, 14336, 15360, 16384]
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


COUNTS = {}


def table_counts(mode, db, timeout):
    """{table: rows} counted in the store itself, under the top of the ladder, so the study needs
    nothing but the store: the corpus's MySQL may be down by the time it runs (the README's order has
    it down before the timed loads). Counted once per database and reused across the shapes, which
    hold the same rows."""
    if db in COUNTS:
        return COUNTS[db]
    root = f"/data/{os.path.basename(data_dir(mode))}/{db}"
    base = ["docker", "run", "--rm", "--memory", f"{LADDER[-1]}m", "--memory-swap", f"{LADDER[-1]}m",
            "-v", f"{os.path.join(ROOT, 'data')}:/data", "-w", root, "--entrypoint", "dolt", DOLT_IMAGE,
            "--data-dir", root, "--use-db", db, "sql", "-r", "csv", "-q"]

    def ask(query):
        try:
            p = subprocess.run(base + [query], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return []
        return [l.strip() for l in p.stdout.splitlines()[1:] if l.strip()]   # the first line is the csv header

    tables = [t for t in ask(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{db}' "
                             "AND table_type = 'BASE TABLE' ORDER BY table_name") if not t.startswith("dolt_")]
    counts = {}
    if tables:
        for line in ask(" UNION ALL ".join(f"SELECT '{t}' AS t, COUNT(*) AS n FROM `{t}`" for t in tables)):
            t, _, n = line.rpartition(",")
            if n.strip().isdigit():
                counts[t.strip()] = int(n)
    COUNTS[db] = counts
    return counts


def biggest_table_and_rows(mode, db, timeout):
    """The largest base table and its exact row count, counted in the store rather than estimated."""
    counts = table_counts(mode, db, timeout)
    if not counts:
        return None, None
    table = max(counts, key=lambda t: counts[t])
    return table, counts[table]


def total_rows(mode, db, timeout):
    """Exact row count, summed one table at a time in the store. (An earlier version summed a
    `GROUP_CONCAT`ed `UNION ALL` on the source MySQL, which `group_concat_max_len` silently truncated:
    `adventureworks` reported 142,002 rows against an actual 759,240.)"""
    counts = table_counts(mode, db, timeout)
    return sum(counts.values()) if counts else None


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


TOO_SMALL = ("oom", "timeout")   # killed at this ceiling, or not answering within the budget at it


def smallest_that_works(mode, db, query, timeout, verbose=True):
    """Bisect the ladder for the lowest ceiling the query survives: (megabytes, detail, rungs).

    Assumes the ladder is monotonic -- if a ceiling works, every larger one does. That is the
    behaviour of an allocator being capped, and it is checked at the top of the ladder first: a
    database that fails even at the maximum is reported as such rather than bisected pointlessly.
    Only a memory outcome moves the floor up; a rung that fails for another reason (a store that is
    not a repository, a daemon fault) is tried once more and then aborts the cell with that reason,
    so an infrastructure fault is never recorded as a memory need.
    """
    rungs = {}

    def probe(mb):
        r = attempt(mode, db, mb, query, timeout)
        if r != "ok" and r not in TOO_SMALL:
            r2 = attempt(mode, db, mb, query, timeout)
            r = r2 if r2 in ("ok",) + TOO_SMALL else f"aborted at {mb} MB: {r2}"
        rungs[mb] = r
        if verbose:
            print(f"      {mb:>5} MB -> {r[:60]}", flush=True)
        return r

    top = probe(LADDER[-1])
    if top != "ok":
        return None, top, rungs
    lo, hi = 0, len(LADDER) - 1
    detail = "ok"
    while lo < hi:
        mid = (lo + hi) // 2
        r = probe(LADDER[mid])
        if r == "ok":
            hi = mid
        elif r in TOO_SMALL:
            detail = r
            lo = mid + 1
        else:
            return None, r, rungs
    return LADDER[lo], detail, rungs


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
        # only stores that exist and are repositories: a database whose load of this shape has not run
        # (or failed) has no store to open, and that is not a memory result
        wanted = a.only or sorted(d for d in os.listdir(data_dir(mode)) if os.path.isdir(repo_path(mode, d)))
        dbs = [d for d in wanted if os.path.isdir(os.path.join(repo_path(mode, d), ".dolt"))]
        for d in wanted:
            if d not in dbs:
                print(f"    {d}: no {mode} store to open (the load has not run, or failed); skipped", flush=True)
        print(f"\n  {mode}: {len(dbs)} database(s), op={a.op}", flush=True)
        for db in dbs:
            table, table_rows = biggest_table_and_rows(mode, db, a.timeout)
            query = OPS[a.op].format(table=table or "dolt_log")
            print(f"    {db}", flush=True)
            t0 = time.time()
            mb, detail, rungs = smallest_that_works(mode, db, query, a.timeout)
            rec = {
                "megabytes": mb,
                "outcome": detail if mb is None else "ok",
                "rungs": {str(k): v for k, v in sorted(rungs.items())},
                "seconds_to_profile": round(time.time() - t0, 1),
                "rows": total_rows(mode, db, a.timeout),
                "largest_table_rows": table_rows,
                "disk_bytes": disk_bytes(mode, db),
                "commits": commit_count(mode, db, a.timeout),
                "op": a.op,
                "query_table": table,
                "ladder_top_mb": LADDER[-1],
            }
            facts.setdefault(mode, {})[db] = rec
            facts["_versions"] = {"dolt": DOLT_VERSION}   # the study belongs to this run
            json.dump(facts, open(OUT, "w", encoding="utf-8"), indent=1, sort_keys=True)
            shown = (f"{mb} MB" if mb else f"did not open at the ladder's top, {LADDER[-1]} MB ({detail[:40]})"
                     if detail in TOO_SMALL or detail.startswith(("oom", "timeout")) else f"not measured ({detail[:60]})")
            print(f"      => {shown}   rows={rec['rows'] or '?'} "
                  f"disk={human(rec['disk_bytes']) if rec['disk_bytes'] else '?'} "
                  f"commits={rec['commits'] or '?'}", flush=True)

    print(f"\n  wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
