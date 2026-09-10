#!/usr/bin/env python3
"""Choose which loads the stack serves, and write what compose and the Workbench need for it.

  python3 scripts/stack_config.py [--serve MODE] [--databases "sakila chinook" | all]
                                  [--dolt-mem 1536m] [--doltgres-mem 1536m]

`make up` runs this first (`make up SERVE=rowcommit`, `SERVE_DATABASES=...`, `DOLT_MEM=...`,
`DOLTGRES_MEM=...`); the same choices persist in `.env` as `DOLTSAMPLES_SERVE`,
`DOLTSAMPLES_SERVE_DATABASES`, `DOLTSAMPLES_DOLT_MEM`, `DOLTSAMPLES_DOLTGRES_MEM`.

Every load shape leaves its own stores behind -- `data/dolt-<mode>/<db>/<db>`,
`data/doltgres-<mode>/<db>`, `data/doltlite-<mode>/<db>.doltlite` -- and a stack can serve any one
of them: `oneshot` (the default: one commit per database), `rowinsert`, `rowcommit` (one commit per
row, the history the Workbench is for), `rowinsert_inline`, `rowcommit_inline`. Three files come out
of the choice:

* `compose.override.yaml`, which compose merges on its own: each chosen store mounted where its
  server looks for a database (Dolt and DoltgreSQL scan one level under their data directory; a
  DoltLite file is mounted by name for the `doltlite` container and for the Workbench), over a
  neutral base directory per engine, and the two servers' memory limits.
* `docker/workbench/store/store.json`: the Workbench's saved connections -- both accounts on Dolt
  and on DoltgreSQL, and one per served DoltLite file.
* `build/serve.json`: what is served, for the landing page and `make test-stack`.

Which databases: `--databases all` serves every database the chosen mode holds for each engine; a
list serves those. With neither, every database present is served, except that the Dolt server
is held to its memory limit: `build/memory.json` (the memory study in README.md) says what each
database needs to open in each shape, and a per-row-commit history can need gigabytes (employees:
12 GiB), so databases are taken smallest need first until the limit is reached and the rest are
named, with the override that would include them. DoltgreSQL and DoltLite have no such study
yet and serve everything present.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT  # noqa: E402

MODES = ["oneshot", "rowinsert", "rowcommit", "rowinsert_inline", "rowcommit_inline"]
DATA = os.path.join(ROOT, "data")
OVERRIDE = os.path.join(ROOT, "compose.override.yaml")
STORE = os.path.join(ROOT, "docker", "workbench", "store", "store.json")
SERVE = os.path.join(ROOT, "build", "serve.json")
MEMORY = os.path.join(ROOT, "build", "memory.json")
DEFAULT_MEM = {"dolt": "1536m", "doltgres": "1536m"}
LABEL = {"oneshot": "one commit per database", "rowinsert": "one INSERT per row, one commit per database",
         "rowcommit": "one commit per row", "rowinsert_inline": "one INSERT per row with the indexes inline, one commit",
         "rowcommit_inline": "one commit per row with the indexes inline"}


def dotenv():
    """KEY=VALUE lines of .env, the file compose reads too."""
    out = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def setting(name, cli, env, default):
    if cli:
        return cli
    if os.environ.get(name):
        return os.environ[name]
    return env.get(name) or default


def mode_dir(engine, mode):
    if engine == "dolt":
        return os.path.join(DATA, "dolt" if mode == "oneshot" else f"dolt-{mode}")
    return os.path.join(DATA, f"{engine}-{mode}")


def present(engine, mode):
    """{db: host path of its store} for what the mode's directory holds for the engine."""
    d = mode_dir(engine, mode)
    found = {}
    if not os.path.isdir(d):
        return found
    for name in sorted(os.listdir(d)):
        if engine == "dolt":
            nested, flat = os.path.join(d, name, name, ".dolt"), os.path.join(d, name, ".dolt")
            if os.path.isdir(nested):
                found[name] = os.path.join(d, name, name)
            elif os.path.isdir(flat):
                found[name] = os.path.join(d, name)
        elif engine == "doltgres":
            if os.path.isdir(os.path.join(d, name, ".dolt")) and name != "postgres":
                found[name] = os.path.join(d, name)
        elif engine == "doltlite" and name.endswith(".doltlite"):
            found[name[:-len(".doltlite")]] = os.path.join(d, name)
    return found


def megabytes(limit):
    s = limit.strip().lower()
    unit = {"k": 1 / 1024, "m": 1, "g": 1024, "t": 1024 * 1024}.get(s[-1], None)
    return float(s[:-1]) * unit if unit else float(s) / (1024 * 1024)


def choose(engine, mode, have, wanted, mem_limit):
    """(served {db: path}, left_out {db: reason})."""
    if wanted == "all":
        return dict(have), {}
    if wanted:
        names = wanted.split()
        left = {n: "not loaded in this mode for this engine" for n in names if n not in have}
        return {n: have[n] for n in names if n in have}, left
    if engine != "dolt" or mode == "oneshot" or not os.path.exists(MEMORY):
        return dict(have), {}
    study = (json.load(open(MEMORY, encoding="utf-8")).get(mode) or {})
    need = {db: (study.get(db) or {}).get("megabytes") for db in have}
    budget, used, served, left = megabytes(mem_limit), 0.0, {}, {}
    for db in sorted(have, key=lambda d: (need[d] is None, need[d] or 0, d)):
        mb = need[db]
        if mb is None:
            served[db] = have[db]          # not in the study: served, its need unknown
            continue
        if used + mb <= budget:
            served[db], used = have[db], used + mb
        else:
            left[db] = (f"needs {mb:,.0f} MB to open in this shape, which would take the Dolt server past its "
                        f"{mem_limit} limit ({used:,.0f} MB already committed); DOLT_MEM=... raises the limit, "
                        f"SERVE_DATABASES=all ignores it")
    return served, left


def rel(path):
    return "./" + os.path.relpath(path, ROOT)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serve", choices=MODES)
    ap.add_argument("--databases", help='space-separated names, or "all"')
    ap.add_argument("--dolt-mem")
    ap.add_argument("--doltgres-mem")
    a = ap.parse_args()
    env = dotenv()
    mode = setting("DOLTSAMPLES_SERVE", a.serve, env, "oneshot")
    if mode not in MODES:
        sys.exit(f"DOLTSAMPLES_SERVE must be one of {', '.join(MODES)}, not {mode!r}")
    wanted = setting("DOLTSAMPLES_SERVE_DATABASES", a.databases, env, "")
    mem = {"dolt": setting("DOLTSAMPLES_DOLT_MEM", a.dolt_mem, env, DEFAULT_MEM["dolt"]),
           "doltgres": setting("DOLTSAMPLES_DOLTGRES_MEM", a.doltgres_mem, env, DEFAULT_MEM["doltgres"])}

    serve = {"mode": mode, "label": LABEL[mode], "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "engines": {}}
    for engine in ("dolt", "doltgres", "doltlite"):
        have = present(engine, mode)
        served, left = choose(engine, mode, have, wanted, mem.get(engine, ""))
        serve["engines"][engine] = {"directory": rel(mode_dir(engine, mode)), "databases": sorted(served),
                                    "left_out": left, "mem_limit": mem.get(engine)}
        serve["engines"][engine]["paths"] = {db: rel(p) for db, p in served.items()}

    # neutral bases, created as this user before Docker can create them as root
    for base in ("dolt-serve", "doltgres-serve", "doltlite-serve"):
        os.makedirs(os.path.join(DATA, base), exist_ok=True)
    e = serve["engines"]
    lines = ["# Generated by scripts/stack_config.py on every `make up` -- do not edit.",
             f"# Serving the {mode} loads ({LABEL[mode]}); compose merges this into compose.yaml.",
             "services:",
             "  dolt:", f"    mem_limit: {mem['dolt']}", "    volumes:", "      - ./data/dolt-serve:/var/lib/dolt"]
    lines += [f"      - {p}:/var/lib/dolt/{db}" for db, p in sorted(e["dolt"]["paths"].items())]
    lines += ["  doltgres:", f"    mem_limit: {mem['doltgres']}", "    volumes:", "      - ./data/doltgres-serve:/var/lib/doltgres"]
    lines += [f"      - {p}:/var/lib/doltgres/{db}" for db, p in sorted(e["doltgres"]["paths"].items())]
    # DoltgreSQL's own `postgres` database, which its entrypoint creates only into an empty data
    # directory and which the health check, the account step and psql's default connect to: served
    # from whichever mode directory has one (the one-commit loads made it first)
    for m in [mode] + MODES:
        pg_own = os.path.join(mode_dir("doltgres", m), "postgres")
        if os.path.isdir(os.path.join(pg_own, ".dolt")):
            lines.append(f"      - {rel(pg_own)}:/var/lib/doltgres/postgres")
            break
    lines += ["  doltlite:", "    volumes:", "      - ./data/doltlite-serve:/data"]
    lines += [f"      - {p}:/data/{db}.doltlite" for db, p in sorted(e["doltlite"]["paths"].items())]
    lines += ["  workbench:", "    volumes:", "      - ./docker/workbench/store:/app/graphql-server/store",
              "      - ./data/doltlite-serve:/data/doltlite"]
    lines += [f"      - {p}:/data/doltlite/{db}.doltlite" for db, p in sorted(e["doltlite"]["paths"].items())]
    with open(OVERRIDE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    demo, admin = env.get("DEMO_PASSWORD") or os.environ.get("DEMO_PASSWORD", "demo"), \
        env.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "admin")
    first = (e["dolt"]["databases"] or ["sakila"])[0]
    first_pg = (e["doltgres"]["databases"] or ["sakila"])[0]
    store = [
        {"name": "dolt-megasamples (read-only)", "connectionUrl": f"mysql://demo:{demo}@dolt:3306/{first}",
         "type": "mysql", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
        {"name": "dolt-megasamples (full access)", "connectionUrl": f"mysql://admin:{admin}@dolt:3306/{first}",
         "type": "mysql", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
        {"name": "DoltgreSQL (read-only)", "connectionUrl": f"postgresql://demo:{demo}@doltgres:5432/{first_pg}",
         "type": "postgres", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
        {"name": "DoltgreSQL (full access)", "connectionUrl": f"postgresql://admin:{admin}@doltgres:5432/{first_pg}",
         "type": "postgres", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
    ] + [{"name": f"DoltLite {db}", "connectionUrl": f"file:///data/doltlite/{db}.doltlite",
          "type": "sqlite", "isDolt": True, "hideDoltFeatures": False, "useSSL": False}
         for db in e["doltlite"]["databases"]]
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    json.dump(store, open(STORE, "w", encoding="utf-8"))
    os.makedirs(os.path.dirname(SERVE), exist_ok=True)
    json.dump(serve, open(SERVE, "w", encoding="utf-8"), indent=1, sort_keys=True)

    print(f"  . serving the {mode} loads ({LABEL[mode]}): Dolt {len(e['dolt']['databases'])}, "
          f"DoltgreSQL {len(e['doltgres']['databases'])}, DoltLite {len(e['doltlite']['databases'])} database(s); "
          f"{len(store)} Workbench connections; {os.path.relpath(OVERRIDE, ROOT)} and {os.path.relpath(SERVE, ROOT)} written")
    for engine, v in e.items():
        for db, why in sorted(v["left_out"].items()):
            print(f"  ! {engine}: {db} not served: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
