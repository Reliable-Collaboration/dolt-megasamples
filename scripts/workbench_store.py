#!/usr/bin/env python3
"""Write the Dolt Workbench's saved connections: both accounts on Dolt and on DoltgreSQL, and one
per DoltLite file, so every database is a click away on first visit.

  python3 scripts/workbench_store.py

The Workbench's API keeps its saved connections in a JSON file, `store.json` under the directory
its README says to mount (`/app/graphql-server/store`); the image ships without one and creates
it when a connection is first added. This writes that file with the two accounts on Dolt and on
DoltgreSQL, passwords from the same environment variables the other consoles read, into
`docker/workbench/store/`, which compose mounts. The DoltLite files are one connection each: the
Workbench's bundled `@dolthub/doltlite` opens a file named by a `file://` URL inside its own
container, where compose mounts `data/doltlite-oneshot` at `/data/doltlite`. `make up` runs this
first; the file is generated and not committed. The Workbench still keeps one *current*
connection at a time, set when a saved connection is clicked (or by its API), so a saved
connection is a click, not a login.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT  # noqa: E402

OUT = os.path.join(ROOT, "docker", "workbench", "store", "store.json")
DOLTLITE = os.path.join(ROOT, "data", "doltlite-oneshot")   # mounted at /data/doltlite in the Workbench


def doltlite_files():
    if not os.path.isdir(DOLTLITE):
        return []
    return sorted(f for f in os.listdir(DOLTLITE) if f.endswith(".doltlite"))


def connections():
    demo = os.environ.get("DEMO_PASSWORD", "demo")
    admin = os.environ.get("ADMIN_PASSWORD", "admin")
    return [
        {"name": "dolt-megasamples (read-only)", "connectionUrl": f"mysql://demo:{demo}@dolt:3306/sakila",
         "type": "mysql", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
        {"name": "dolt-megasamples (full access)", "connectionUrl": f"mysql://admin:{admin}@dolt:3306/sakila",
         "type": "mysql", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
        {"name": "DoltgreSQL (read-only)", "connectionUrl": f"postgresql://demo:{demo}@doltgres:5432/sakila",
         "type": "postgres", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
        {"name": "DoltgreSQL (full access)", "connectionUrl": f"postgresql://admin:{admin}@doltgres:5432/sakila",
         "type": "postgres", "isDolt": True, "hideDoltFeatures": False, "useSSL": False},
    ] + [
        {"name": f"DoltLite {f[:-len('.doltlite')]}", "connectionUrl": f"file:///data/doltlite/{f}",
         "type": "sqlite", "isDolt": True, "hideDoltFeatures": False, "useSSL": False}
        for f in doltlite_files()
    ]


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(connections(), fh)
    print(f"  . wrote {os.path.relpath(OUT, ROOT)}: {len(connections())} saved connections for the Workbench "
          f"(4 server accounts, {len(doltlite_files())} DoltLite files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
