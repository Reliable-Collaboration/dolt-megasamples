#!/usr/bin/env python3
"""Remove the two further pairs' stores, prepared dumps and recorded units -- or, with --everything,
every store and record of both runs, which is what `make clean-data` does.

  python3 scripts/clean_pairs.py [--everything]

The stores were written as root by the worker containers, so they are removed through one. The
units the runner recorded, and the pair entries of build/results.json, go with them: the runner's
test of whether a unit is done is its record, so the first version of this target left the records
behind, after which `make run-pg` measured nothing while the documents kept numbers whose evidence
was gone. It holds build/run.lock while it works, so no runner can start and write the records or
the stores back, and it refuses while the stack mounts the stores. --everything also removes the
MySQL/Dolt stores, build/results.json and build/progress.json; the first `make clean-data` could not
delete the root-owned pair stores and stopped with the records already gone (2026-09-10 review).
"""
import argparse, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DOLT_IMAGE, ROOT, load_results, run, run_lock, save_results  # noqa: E402
from pairs import ENGINE, LITE_IMAGE, WORKERS  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")
RESULTS = os.path.join(ROOT, "build", "results.json")
MOUNTING = {"doltsamples-dolt", "doltsamples-doltgres", "doltsamples-doltlite", "doltsamples-workbench",
            "doltsamples-doltgres-catalog", "doltsamples-memory-probe"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--everything", action="store_true",
                    help="every store and record of both runs, the MySQL/Dolt ones included")
    a = ap.parse_args()
    lock, holder = run_lock("clean_pairs.py")
    if lock is None:
        sys.exit(f"refusing to clean: build/run.lock is held by {holder}")
    serving = sorted(set(run("docker", "ps", "--format", "{{.Names}}").stdout.split()) & MOUNTING)
    if serving:
        sys.exit("refusing to clean: the stack mounts the stores (" + ", ".join(serving) + "); `make down` first")
    stale = sorted(set(run("docker", "ps", "-a", "--format", "{{.Names}}").stdout.split()) & set(WORKERS))
    if stale:
        run("docker", "rm", "-f", *stale)          # the lock proves no runner is using them
    targets = "/data/postgres-timing /data/doltgres-* /data/sqlite-* /data/doltlite-* /dumps/pairs"
    if a.everything:
        targets += " /data/dolt /data/dolt-* /data/mysql /dumps/dolt"
    image = LITE_IMAGE if run("docker", "image", "inspect", LITE_IMAGE).returncode == 0 else DOLT_IMAGE
    p = run("docker", "run", "--rm", "--label", "doltsamples.transient=true",
            "-v", f"{os.path.join(ROOT, 'data')}:/data", "-v", f"{os.path.join(ROOT, 'build', 'dumps')}:/dumps",
            "--entrypoint", "sh", image, "-c", f"rm -rf {targets}")
    if p.returncode != 0:
        sys.exit(f"could not remove the stores, and no record was touched: {p.stderr.strip()[:200]}")
    if a.everything:
        shutil.rmtree(os.path.join(ROOT, "data"), ignore_errors=True)
        for f in (RESULTS, PROGRESS):
            if os.path.exists(f):
                os.remove(f)
        print("  . removed every store of both runs, the prepared dumps, build/results.json and build/progress.json")
        return 0
    dropped = 0
    if os.path.exists(PROGRESS):
        prog = json.load(open(PROGRESS, encoding="utf-8"))
        keep = {k: u for k, u in (prog.get("units") or {}).items()
                if not (u.get("pair") or k.split("/")[0] in ENGINE)}
        dropped = len(prog.get("units") or {}) - len(keep)
        prog["units"] = keep
        prog.pop("pairs", None)
        prog.pop("superseded", None)
        tmp = PROGRESS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(prog, fh, indent=2, sort_keys=True)
        os.replace(tmp, PROGRESS)
    results = load_results()
    for entry in results.values():
        if isinstance(entry, dict):
            entry.pop("pairs", None)
    save_results(results)
    print(f"  . removed the PostgreSQL, DoltgreSQL, SQLite and DoltLite stores of every shape and the prepared dumps;\n"
          f"    dropped {dropped} recorded pair unit(s) and the pair entries of build/results.json.\n"
          f"    `make run-pg` and `make run-lite` measure them again; `make docs` then regenerates the documents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
