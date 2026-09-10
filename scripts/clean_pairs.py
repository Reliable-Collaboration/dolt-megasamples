#!/usr/bin/env python3
"""Remove the two further pairs' stores and prepared dumps, and the measurements that described them.

  python3 scripts/clean_pairs.py

The stores were written as root by the worker containers, so they are removed through one. The
units the runner recorded, and the pair entries of build/results.json, go with them: the runner's
only test of whether a unit is done is its record, so the first version of this target left the
records behind, after which `make run-pg` measured nothing while the documents kept numbers whose
evidence was gone (2026-09-10 review). The exports (build/dumps/postgres, build/dumps/sqlite) and
the MySQL/Dolt measurements are kept; `make clean-data` removes everything. It refuses while a
runner is working or a container that mounts the stores is up, since both would write the records
or the stores back.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DOLT_IMAGE, ROOT, load_results, run, save_results  # noqa: E402
from pairs import ENGINE, LITE_IMAGE, WORKERS  # noqa: E402

PROGRESS = os.path.join(ROOT, "build", "progress.json")
MOUNTING = {"doltsamples-doltgres", "doltsamples-doltlite", "doltsamples-workbench", "doltsamples-doltgres-catalog",
            "doltsamples-memory-probe"}


def busy():
    """What would write the records or the stores back while they are removed."""
    why = []
    runners = [l for l in run("pgrep", "-fa", "run_pair[s].py").stdout.splitlines() if l.strip()]
    if runners:
        why.append("a runner is working: " + runners[0][:80])
    up = set(run("docker", "ps", "--format", "{{.Names}}").stdout.split())
    held = sorted(up & (set(WORKERS) | MOUNTING))
    if held:
        why.append("containers that mount the stores are up: " + ", ".join(held) + " (make down)")
    return why


def main():
    why = busy()
    if why:
        sys.exit("refusing to clean the pairs:\n  " + "\n  ".join(why))
    image = LITE_IMAGE if run("docker", "image", "inspect", LITE_IMAGE).returncode == 0 else DOLT_IMAGE
    p = run("docker", "run", "--rm", "-v", f"{os.path.join(ROOT, 'data')}:/data",
            "-v", f"{os.path.join(ROOT, 'build', 'dumps')}:/dumps", "--entrypoint", "sh", image, "-c",
            "rm -rf /data/postgres-timing /data/doltgres-* /data/sqlite-* /data/doltlite-* /dumps/pairs")
    if p.returncode != 0:
        sys.exit(f"could not remove the stores: {p.stderr.strip()[:200]}")
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
