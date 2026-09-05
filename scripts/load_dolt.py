#!/usr/bin/env python3
"""Load the MySQL dumps into Dolt, commit them, and garbage-collect before anything is measured.

  python3 scripts/load_dolt.py [--only sakila] [--force]

Each dump is executed by the `dolt` CLI against a shared data directory, which gives Dolt one
directory per database -- the unit the size comparison measures.

Two steps after the load matter for the comparison to be fair:

* **commit.** Dolt is a versioned database. Data left in the working set is not yet in the commit
  graph, so measuring there would flatter Dolt by omitting the history it exists to keep. Every
  database gets exactly one commit, which is the smallest honest amount of history.
* **gc.** Dolt writes through a journal and only packs chunks when told to. Measuring before
  `dolt gc` reports the write-ahead state rather than the stored state: jaffle_shop is 34,926 bytes
  before and 15,673 after, so the difference is not a rounding error.

Anything the dump does that Dolt rejects is recorded per database rather than swallowed -- a size
comparison between a complete database and a partial one would be worthless.
"""
import argparse, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, DOLT_IMAGE, DUMPS, dolt, human, load_results, run, save_results  # noqa: E402
from dolt_dialect import transform  # noqa: E402


def loaded_databases():
    p = dolt("sql", "-q", "SHOW DATABASES")
    if p.returncode != 0:
        return set()
    return {l.strip(" |") for l in p.stdout.splitlines()
            if l.startswith("|") and l.strip(" |") not in ("Database", "information_schema", "mysql")}


def prepare_dump(db):
    """Rewrite the dump into the dialect Dolt accepts, keeping every row untouched.

    Written beside the originals so both are on disk and the difference can be inspected;
    scripts/dolt_dialect.py explains each transformation and why it is needed."""
    src = os.path.join(DUMPS, f"{db}.sql")
    out_dir = os.path.join(DUMPS, "dolt")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{db}.sql")
    sql, notes = transform(open(src, "rb").read(), db)   # bytes: see scripts/dolt_dialect.py
    open(out, "wb").write(sql)
    return f"/dumps/dolt/{db}.sql", notes


def load(db, force):
    dump = os.path.join(DUMPS, f"{db}.sql")
    if not os.path.exists(dump):
        return {"error": "no dump; run scripts/export_mysql.py first"}
    target = os.path.join(DATA, db)
    if os.path.isdir(target) and not force:
        print(f"  = {db:<24} already loaded")
        return None
    if os.path.isdir(target) and force:
        run("docker", "run", "--rm", "-v", f"{DATA}:/var/lib/dolt", "--entrypoint", "sh",
            DOLT_IMAGE, "-c", f"rm -rf /var/lib/dolt/{db}")

    inside, notes = prepare_dump(db)
    started = time.time()
    p = dolt("--data-dir", "/var/lib/dolt", "sql", "--file", inside)
    load_s = time.time() - started
    problems = sorted({m.strip() for m in re.findall(r"error on line \d+ for query [^\n]{0,120}",
                                                     p.stdout + p.stderr)})
    if p.returncode != 0 and not os.path.isdir(target):
        return {"error": (p.stderr or p.stdout).strip()[:300], "load_seconds": round(load_s, 1)}

    started = time.time()
    commit = run("docker", "run", "--rm", "-v", f"{DATA}:/var/lib/dolt", "-w", f"/var/lib/dolt/{db}",
                 "--entrypoint", "sh", DOLT_IMAGE, "-c",
                 'dolt add -A && dolt commit -m "import from mysql-megasamples" '
                 '--author "megasamples <megasamples@localhost>" ; dolt gc')
    gc_s = time.time() - started
    print(f"  . {db:<24} load {load_s:7.1f}s  commit+gc {gc_s:6.1f}s"
          + (f"  [{len(problems)} statement error(s)]" if problems else ""))
    return {"load_seconds": round(load_s, 1), "gc_seconds": round(gc_s, 1),
            "statement_errors": problems[:20], "statement_error_count": len(problems),
            "dialect_notes": notes, "commit_ok": commit.returncode == 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append")
    ap.add_argument("--force", action="store_true", help="drop and reload a database that exists")
    a = ap.parse_args()

    os.makedirs(DATA, exist_ok=True)
    names = a.only or sorted(f[:-4] for f in os.listdir(DUMPS) if f.endswith(".sql"))
    if not names:
        sys.exit("no dumps found; run scripts/export_mysql.py first")

    results = load_results()
    print(f"loading {len(names)} database(s) into Dolt ({DOLT_IMAGE.split('@')[0]})")
    for db in names:
        outcome = load(db, a.force)
        if outcome is None:
            continue
        results.setdefault(db, {})["dolt"] = outcome
        if "error" in outcome:
            print(f"  x {db:<24} {outcome['error'][:120]}")
        save_results(results)

    failed = [d for d, r in results.items() if "error" in (r.get("dolt") or {})]
    print(f"\n{len(names) - len(failed)}/{len(names)} loaded"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
