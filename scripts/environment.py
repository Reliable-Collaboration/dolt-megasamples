#!/usr/bin/env python3
"""Record the machine the measurements were taken on.

  python3 scripts/environment.py

Timings are meaningless without the machine that produced them, and sizes are only meaningful if the
engine versions and settings are known. This writes `build/environment.json` and prints a table for
the README, generated rather than typed so it describes the machine that actually ran the tests.

Neither engine is performance-tuned. Both run their published images with stock storage settings,
and MySQL is started with two flags, recorded here rather than described away; the only
non-default flags are the ones needed to load at all (`--local-infile=1`, `--skip-log-bin` on the
timing MySQL). A tuned MySQL — compressed row format, a different page size, a larger buffer pool —
would produce different numbers, and so would a Dolt with a different chunk store configuration.
"""
import json, os, platform, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pairs import DOLTGRES_IMAGE, DOLTGRES_VERSION, LITE_IMAGE, POSTGRES_IMAGE  # noqa: E402
from common import DOLT_IMAGE, ROOT, human, run  # noqa: E402

OUT = os.path.join(ROOT, "build", "environment.json")


def first(path, prefix):
    try:
        for line in open(path, encoding="utf-8"):
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def image_version(image, *cmd):
    p = run("docker", "run", "--rm", "--entrypoint", cmd[0], image, *cmd[1:])
    return (p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr) else None


def main():
    total, used, free = shutil.disk_usage(ROOT)
    mem_kb = first("/proc/meminfo", "MemTotal")
    env = {
        "host": {
            "kernel": platform.release(),
            "platform": platform.platform(),
            "cpu": first("/proc/cpuinfo", "model name"),
            "cpu_threads": os.cpu_count(),
            "memory": human(int(mem_kb.split()[0]) * 1024) if mem_kb else None,
            "filesystem": subprocess.run(["df", "-T", ROOT], capture_output=True, text=True)
                          .stdout.splitlines()[-1].split()[1],
            "disk_total": human(total),
            "disk_free_at_capture": human(free),
            "python": platform.python_version(),
        },
        "docker": {
            "version": run("docker", "version", "-f", "{{.Server.Version}}").stdout.strip(),
            "storage_driver": run("docker", "info", "-f", "{{.Driver}}").stdout.strip(),
        },
        "engines": {
            "mysql_image": os.environ.get("MYSQL_TIMING_IMAGE", "mysql:9.7.2"),
            "mysql_version": image_version(os.environ.get("MYSQL_TIMING_IMAGE", "mysql:9.7.2"),
                                           "mysqld", "--version"),
            "mysql_flags": ["--local-infile=1", "--skip-log-bin"],
            "dolt_image": DOLT_IMAGE,
            "dolt_version": image_version(DOLT_IMAGE, "dolt", "version"),
            "dolt_flags": [],
            # Not "default settings": MySQL is started with two flags, and the row below
            # names them. Saying both are untuned while listing the flags that make one of them
            # not untuned is the kind of small contradiction that costs a reader their trust.
            "tuning": "no performance tuning — stock images, stock storage settings; "
                      "MySQL is started with the two flags below",
            # the two further pairs (scripts/pairs.py): the PostgreSQL image is the base of
            # sql-megasamples' own; DoltgreSQL is pinned by digest; DoltLite is built here from
            # the release's packages, beside Debian's sqlite3, which is the pair's baseline
            "postgres_image": POSTGRES_IMAGE,
            "postgres_version": image_version(POSTGRES_IMAGE, "postgres", "--version"),
            "doltgres_image": DOLTGRES_IMAGE,
            "doltgres_version": DOLTGRES_VERSION,
            "doltlite_image": LITE_IMAGE,
            "doltlite_version": image_version(LITE_IMAGE, "doltlite", "-version"),
            "sqlite3_version": image_version(LITE_IMAGE, "sqlite3", "-version"),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(env, open(OUT, "w", encoding="utf-8"), indent=2, sort_keys=True)

    print(f"  . wrote {os.path.relpath(OUT, ROOT)}")
    for section, fields in env.items():
        for k, v in fields.items():
            print(f"    {section}.{k:<22} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
