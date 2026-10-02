"""Remove what the build wrote: the stores and their records, and with --all the exports too.

  python3 -m doltsamples clean [--all]

The stores were written by containers, which on rootful Docker means by root, so they are removed
through a container. Refused while the stack is up, since it mounts them.
"""
import argparse, os, shutil, sys

from doltsamples.stack import CONTAINERS, SERVE
from doltsamples.util import BUILD, DATA, EXPORTS, STORES, lock, rel, remove_tree, run


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clean", description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="the exports from the corpus as well")
    a = ap.parse_args(argv)
    held, holder = lock("clean")
    if held is None:
        sys.exit(f"{holder} holds build/build.lock")
    up = set(run("docker", "ps", "--format", "{{.Names}}").stdout.split()) & set(CONTAINERS.values())
    if up:
        sys.exit(f"the stack is up ({', '.join(sorted(up))}); `make down` first")
    remove_tree(DATA)
    for path in (os.path.join(BUILD, "prepared"), STORES, SERVE):
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    print(f"  . removed {rel(DATA)}/, the prepared dumps and build/stores.json")
    if a.all:
        shutil.rmtree(EXPORTS, ignore_errors=True)
        print(f"  . removed {rel(EXPORTS)}/")
    return 0
