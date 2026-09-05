#!/usr/bin/env python3
"""Shared settings and helpers for the MySQL-to-Dolt comparison.

The experiment has one question: for the same data, how much disk does Dolt use compared with
MySQL? Everything here exists to make that comparison honest -- the same rows, loaded the same way,
measured the same way, with the engines' own storage left to do whatever it does.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMPS = os.path.join(ROOT, "build", "dumps")
DATA = os.path.join(ROOT, "data", "dolt")
RESULTS = os.path.join(ROOT, "build", "results.json")

MYSQL_CONTAINER = os.environ.get("MEGASAMPLES_CONTAINER", "megasamples-mysql")
MYSQL_IMAGE = os.environ.get("MEGASAMPLES_IMAGE", "mysql-megasamples:dev")
DOLT_IMAGE = os.environ.get(
    "DOLT_IMAGE",
    "dolthub/dolt-sql-server@sha256:38d5e900583267f35e36ad738e13f202e62860b351aa4c088dceaf7dbaed7ab6")

# schemas that are not sample data: MySQL's own, and the provenance registry the image carries
SKIP = {"mysql", "information_schema", "performance_schema", "sys", "megasamples"}


def run(*args, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(list(args), **kw)


def mysql(sql, container=None):
    p = run("docker", "exec", container or MYSQL_CONTAINER, "mysql", "-uroot", "-proot",
            "-N", "--batch", "-e", sql)
    if p.returncode != 0:
        sys.exit(f"could not query {container or MYSQL_CONTAINER}: {p.stderr.strip()[:200]}\n"
                 f"Is mysql-megasamples running? `cd ../mysql-megasamples && make up`")
    return [line.split("\t") for line in p.stdout.splitlines() if line.strip()]


def databases(container=None):
    rows = mysql("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name",
                 container)
    return [r[0] for r in rows if r[0] not in SKIP]


def dolt(*args, mounts=(), workdir=None):
    """Run a dolt CLI command in a throwaway container over the shared data directory."""
    cmd = ["docker", "run", "--rm",
           "--label", "doltsamples.transient=true",
           "-v", f"{DATA}:/var/lib/dolt",
           "-v", f"{DUMPS}:/dumps"]
    for host, inside in mounts:
        cmd += ["-v", f"{host}:{inside}"]
    cmd += ["-w", workdir or "/var/lib/dolt", "--entrypoint", "dolt", DOLT_IMAGE, *args]
    return run(*cmd)


def load_results():
    return json.load(open(RESULTS, encoding="utf-8")) if os.path.exists(RESULTS) else {}


def save_results(data):
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    json.dump(data, open(RESULTS, "w", encoding="utf-8"), indent=2, sort_keys=True)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
