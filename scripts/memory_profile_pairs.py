#!/usr/bin/env python3
"""Find how much memory DoltgreSQL and DoltLite need to open and query a database, in each
stored shape -- the memory study of scripts/memory_profile.py, repeated for the two further pairs.

  python3 scripts/memory_profile_pairs.py [--engine doltgres|doltlite] [--mode rowcommit] [--only sakila]

Method, as for Dolt: one query against one database in a container with a hard memory ceiling,
walking a ladder of ceilings by bisection to the smallest that does not get the process killed.
For DoltgreSQL the container is the server itself, started over that one database's directory
(the unit's own root: DoltgreSQL's `postgres` catalog and that one database) and asked
`SELECT COUNT(*)` over the database's largest table through its own psql; a kill is the server
dying under the ceiling before it answers. For DoltLite it is the shell over the file, as it is
for Dolt. Every result is a ceiling that worked, at the ladder's granularity; a database that
fails at the top is reported as a bound. Results go to build/memory_pairs.json, which
scripts/stack_config.py reads to hold the served DoltgreSQL server to its memory limit the way
the Dolt study holds the Dolt server.
"""
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, run, run_lock  # noqa: E402
from pairs import DOLTGRES_IMAGE, LITE_IMAGE, PW, reference  # noqa: E402
from memory_profile import LADDER  # noqa: E402

OUT = os.path.join(ROOT, "build", "memory_pairs.json")
DATA = os.path.join(ROOT, "data")
MODES = ["oneshot", "rowinsert", "rowcommit", "rowinsert_inline", "rowcommit_inline"]
PROBE = "doltsamples-memory-probe"


def store(engine, mode, db):
    if engine == "doltgres":
        return os.path.join(DATA, f"doltgres-{mode}", db)
    return os.path.join(DATA, f"doltlite-{mode}", f"{db}.doltlite")


def present(engine, mode):
    d = os.path.join(DATA, f"{engine}-{mode}")
    if not os.path.isdir(d):
        return []
    if engine == "doltgres":
        return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n, n, ".dolt")))
    return sorted(n[:-len(".doltlite")] for n in os.listdir(d) if n.endswith(".doltlite"))


def largest_table(engine, db):
    pair = "pg" if engine == "doltgres" else "lite"
    rows = reference(pair, db)["rows"]
    t, n = max(rows.items(), key=lambda kv: kv[1] or 0)
    return (t.split(".", 1)[1] if pair == "pg" else t), n


def attempt(engine, mode, db, mb, table, timeout):
    """'ok', 'oom', 'timeout' or an error string, for one query under one ceiling."""
    run("docker", "rm", "-f", PROBE)
    if engine == "doltlite":
        cmd = ["docker", "run", "--rm", "--name", PROBE, "--memory", f"{mb}m", "--memory-swap", f"{mb}m",
               "-v", f"{store(engine, mode, db)}:/f.doltlite", LITE_IMAGE,
               "doltlite", "/f.doltlite", f'SELECT COUNT(*) FROM "{table}"']
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            run("docker", "rm", "-f", PROBE)
            return "timeout"
        if p.returncode == 0 and p.stdout.strip().isdigit():
            return "ok"
        if p.returncode == 137 or "Killed" in (p.stderr or ""):
            return "oom"
        return f"exit {p.returncode}: {(p.stderr or p.stdout).strip()[:120]}"
    # DoltgreSQL: the server over the unit's own root (its `postgres` catalog and this one database),
    # in a container under the ceiling. Not while the stack serves the same store.
    p = run("docker", "run", "-d", "--name", PROBE, "--memory", f"{mb}m", "--memory-swap", f"{mb}m",
            "-e", f"DOLTGRES_PASSWORD={PW}", "-v", f"{store(engine, mode, db)}:/var/lib/doltgres", DOLTGRES_IMAGE)
    if p.returncode != 0:
        return f"could not start: {p.stderr.strip()[:120]}"
    deadline = time.time() + timeout
    result = "timeout"
    while time.time() < deadline:
        state = run("docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}", PROBE).stdout.split()
        if not state or state[0] != "running":
            result = "oom" if (state and (state[2] == "true" or state[1] == "137")) else f"exited {state[1] if state else '?'}"
            break
        q = run("docker", "exec", "-e", f"PGPASSWORD={PW}", PROBE, "psql", "-X", "-h", "127.0.0.1", "-U", "postgres",
                "-d", db, "-tA", "-c", f'SELECT COUNT(*) FROM "{table}"')
        if q.returncode == 0 and q.stdout.strip().isdigit():
            result = "ok"
            break
        if q.returncode == 0:
            result = f"answered {q.stdout.strip()[:60]}"
            break
        time.sleep(2)
    run("docker", "rm", "-f", PROBE)
    return result


def smallest_that_works(engine, mode, db, table, timeout, verbose=True):
    top = attempt(engine, mode, db, LADDER[-1], table, timeout)
    if top != "ok":
        return None, top
    lo, hi, detail = 0, len(LADDER) - 1, "ok"
    while lo < hi:
        mid = (lo + hi) // 2
        r = attempt(engine, mode, db, LADDER[mid], table, timeout)
        if verbose:
            print(f"      {LADDER[mid]:>5} MB -> {r[:40]}", flush=True)
        if r == "ok":
            hi = mid
        else:
            detail, lo = r, mid + 1
    return LADDER[lo], detail


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", action="append", choices=["doltgres", "doltlite"])
    ap.add_argument("--mode", action="append", choices=MODES)
    ap.add_argument("--only", action="append")
    ap.add_argument("--timeout", type=float, default=900)
    a = ap.parse_args()
    # a measurement in its own right: never beside a runner, which may be writing the very store, and
    # never while the stack serves the stores, which would put two servers over one repository
    lock, holder = run_lock("memory_profile_pairs.py")
    if lock is None:
        sys.exit(f"build/run.lock is held by {holder}: the study would start servers over stores being written")
    up = set(run("docker", "ps", "--format", "{{.Names}}").stdout.split())
    serving = sorted(up & {"doltsamples-doltgres", "doltsamples-doltlite", "doltsamples-workbench"})
    if serving:
        sys.exit("the stack is serving the stores the study would open (" + ", ".join(serving) + "); `make down` first")
    facts = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    for engine in a.engine or ["doltgres", "doltlite"]:
        for mode in a.mode or MODES:
            dbs = [d for d in (a.only or present(engine, mode)) if os.path.exists(store(engine, mode, d))]
            if not dbs:
                continue
            print(f"\n  {engine} {mode}: {len(dbs)} database(s)", flush=True)
            for db in dbs:
                table, n = largest_table(engine, db)
                print(f"    {db} ({table}, {n:,} rows)", flush=True)
                t0 = time.time()
                mb, detail = smallest_that_works(engine, mode, db, table, a.timeout)
                facts.setdefault(engine, {}).setdefault(mode, {})[db] = {
                    "megabytes": mb, "outcome": detail if mb is None else "ok",
                    "seconds_to_profile": round(time.time() - t0, 1), "query_table": table, "largest_table_rows": n,
                    "ladder_top_mb": LADDER[-1], "measured": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                json.dump(facts, open(OUT, "w", encoding="utf-8"), indent=1, sort_keys=True)
                print(f"      -> {mb if mb else 'more than ' + str(LADDER[-1])} MB ({detail})", flush=True)
    print(f"\n  . wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
