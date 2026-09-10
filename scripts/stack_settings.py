#!/usr/bin/env python3
"""The stack's resolved settings -- ports, network, container names, account passwords -- in one place.

scripts/stack_config.py resolves them on every `make up`, from `docker compose config` (which merges
compose.yaml, compose.override.yaml and .env) and the password variables compose reads, and writes
them into build/serve.json; `make test-stack` and the landing page read them from there. The first
version typed the defaults into each script, so a password set in .env was honoured by compose and
by the consoles and not by the check or the page.
"""
import copy, json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVE = os.path.join(ROOT, "build", "serve.json")
DEFAULTS = {
    "network": "dolt-megasamples_default",
    "ports": {"dolt": 3307, "doltgres": 5433, "console": 8090, "phpmyadmin": 8091, "adminer": 8092,
              "dbgate": 8093, "cloudbeaver": 8094, "workbench": 8095, "workbench_api": 9002},
    "containers": {"dolt": "doltsamples-dolt", "doltgres": "doltsamples-doltgres", "doltlite": "doltsamples-doltlite",
                   "workbench": "doltsamples-workbench", "console": "doltsamples-console"},
    "passwords": {"demo": "demo", "admin": "admin", "doltgres": "doltsamples", "dolt_root": "root"},
}
PASSWORD_VARS = {"demo": "DEMO_PASSWORD", "admin": "ADMIN_PASSWORD", "doltgres": "DOLTGRES_PASSWORD",
                 "dolt_root": "DOLT_ROOT_PASSWORD"}
PORT_OF = {"dolt": "dolt", "doltgres": "doltgres", "console": "console", "phpmyadmin": "phpmyadmin",
           "adminer": "adminer", "dbgate": "dbgate", "cloudbeaver": "cloudbeaver"}


def dotenv():
    out, path = {}, os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve():
    s = copy.deepcopy(DEFAULTS)
    env = dotenv()
    for key, var in PASSWORD_VARS.items():
        value = os.environ.get(var) or env.get(var)
        if value:
            s["passwords"][key] = value
    try:
        out = subprocess.run(["docker", "compose", "config", "--format", "json"], cwd=ROOT,
                             capture_output=True, text=True, timeout=60).stdout
        cfg = json.loads(out) if out.strip() else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        cfg = {}
    name = ((cfg.get("networks") or {}).get("default") or {}).get("name")
    if name:
        s["network"] = name
    for svc, spec in (cfg.get("services") or {}).items():
        if spec.get("container_name"):
            s["containers"][svc] = spec["container_name"]
        for port in spec.get("ports") or []:
            published, target = port.get("published"), port.get("target")
            key = ("workbench_api" if str(target) == "9002" else "workbench") if svc == "workbench" else PORT_OF.get(svc)
            if key and published and str(published).isdigit():
                s["ports"][key] = int(published)
    return s


def load():
    """What the last `make up` resolved, over the defaults for anything it did not record."""
    s = copy.deepcopy(DEFAULTS)
    try:
        stack = json.load(open(SERVE, encoding="utf-8")).get("stack") or {}
    except (OSError, ValueError):
        stack = {}
    for part in ("ports", "containers", "passwords"):
        s[part].update(stack.get(part) or {})
    s["network"] = stack.get("network") or s["network"]
    return s
