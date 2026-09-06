#!/usr/bin/env python3
"""Stop the run before it fills the disk.

  python3 scripts/disk_guard.py [--floor-gb 150] [--every 60]

The per-row-commit phase writes an amount of disk that cannot be predicted well in advance: the
measured cost ranges from 2.3 KB per row to 126 KB per row across the sample databases, a factor of
55, so a projection built from the small ones understates the large ones by an order of magnitude.

Rather than guess, this watches free space and stops the runner if it falls below the floor. Stopping
is safe: `run_all.py` records each unit in `build/progress.json` as it finishes, so everything
completed is kept and the run can be resumed later with `make run`. The alternative — filling the
filesystem — would take the whole machine down with it, including the databases being measured.
"""
import argparse, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT  # noqa: E402

GB = 1024 ** 3


def runner_pids():
    p = subprocess.run(["ps", "-eo", "pid,args", "--no-headers"], capture_output=True, text=True)
    return [int(l.split()[0]) for l in p.stdout.splitlines()
            if "run_all.py" in l and "grep" not in l]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--floor-gb", type=float, default=150.0)
    ap.add_argument("--every", type=int, default=60)
    a = ap.parse_args()

    print(f"guarding {ROOT}: stop the run if free space falls below {a.floor_gb:.0f} GB, "
          f"checked every {a.every}s", flush=True)
    while True:
        free = shutil.disk_usage(ROOT).free / GB
        pids = runner_pids()
        if not pids:
            print(f"the runner has exited; guard stopping (free {free:.0f} GB)", flush=True)
            return 0
        if free < a.floor_gb:
            print(f"FREE SPACE {free:.0f} GB IS BELOW THE {a.floor_gb:.0f} GB FLOOR — "
                  f"stopping the run ({', '.join(str(p) for p in pids)})", flush=True)
            for pid in pids:
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass
            print("stopped. Everything already recorded in build/progress.json is kept; "
                  "`make run` resumes from there once space is freed.", flush=True)
            return 1
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
