#!/usr/bin/env python3
"""Write the Dolt Workbench's saved connections, so all four are a click away on first visit.

  python3 scripts/workbench_store.py

The Workbench's API keeps its saved connections in a JSON file, `store.json` under the directory
its README says to mount (`/app/graphql-server/store`); the image ships without one and creates
it when a connection is first added. This writes that file with the two accounts on Dolt and on
DoltgreSQL, passwords from the same environment variables the other consoles read, into
`docker/workbench/store/`, which compose mounts. `make up` runs it first; the file is generated
and not committed. The Workbench still keeps one *current* connection at a time, set when a
saved connection is clicked (or by its API), so a saved connection is a click, not a login.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT  # noqa: E402

OUT = os.path.join(ROOT, "docker", "workbench", "store", "store.json")


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
    ]


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(connections(), fh)
    print(f"  . wrote {os.path.relpath(OUT, ROOT)}: {len(connections())} saved connections for the Workbench")
    return 0


if __name__ == "__main__":
    sys.exit(main())
