"""The commands. Each `make` target is one of these: `python3 -m doltsamples <command>`."""
import argparse, os, sys

from doltsamples import config as config_mod
from doltsamples.util import ROOT

USAGE = """python3 -m doltsamples <command>   (or the make target of the same name)

  run          export, lite-image, build: everything up to a stack that can start
  export       take the dumps out of a built sql-megasamples (build/exports/)
  build        build every store dolt-megasamples.yaml asks for (data/), checked against the corpus
  status       what the configuration asks for beside what is built
  up           write compose.yaml from the configuration and start the stack
  down         stop it
  ps           what is running
  test         prove the running stack answers: accounts, every store's rows and history, every console
  compose      write compose.yaml without starting anything
  list         the databases the configuration names, per engine and history
  versions     each engine here beside its newest release
  update       move the engines to their newest release (then: make lite-image, make build)
  lite-image   build the DoltLite image from its checksummed packages
  clean        remove the stores and exports (keeps the configuration)
"""


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m doltsamples", usage=USAGE, add_help=True)
    ap.add_argument("command", nargs="?", default="help")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd, rest = a.command, a.rest
    if cmd in ("help", "-h", "--help"):
        print(USAGE)
        return 0
    if cmd == "versions":
        from doltsamples import versions
        return versions.main(["--check"])
    if cmd == "update":
        from doltsamples import versions
        return versions.main(["--latest", *(rest[:1] or ["all"])])
    if cmd == "lite-image":
        from doltsamples import lite_image
        return lite_image.main(rest)
    cfg = config_mod.load()
    if cmd == "list":
        print(f"from {cfg.where()}; the corpus at {os.path.relpath(cfg.corpus, ROOT)}")
        for e in config_mod.ENGINES:
            for h in config_mod.HISTORIES:
                dbs = cfg.databases(e, h)
                if dbs:
                    print(f"  {e:<9} {h:<8} {len(dbs):>3}: {' '.join(dbs)}")
        print(f"  consoles: {', '.join(cfg.served_consoles()) or 'none'}")
        return 0
    if cmd == "export":
        p = argparse.ArgumentParser(prog="export")
        p.add_argument("--only", nargs="*")
        p.add_argument("--force", action="store_true")
        p.add_argument("--all", action="store_true", help="every database the corpus holds, not only those configured")
        o = p.parse_args(rest)
        from doltsamples import catalogue, corpus, lite_image
        from doltsamples.util import lite_image as tag, run
        if any(e == "doltlite" for e, _, _ in cfg.wanted()) or o.all:
            if run("docker", "image", "inspect", tag()).returncode != 0:
                lite_image.build()
        catalogue.write(cfg.corpus)
        return corpus.export(cfg, only=o.only, force=o.force, everything=o.all)
    if cmd == "build":
        p = argparse.ArgumentParser(prog="build")
        p.add_argument("--only", nargs="*")
        p.add_argument("--engine", choices=config_mod.ENGINES)
        p.add_argument("--force", action="store_true")
        o = p.parse_args(rest)
        from doltsamples import build
        return build.build(cfg, only=o.only, engine=o.engine, force=o.force)
    if cmd == "run":
        rc = main(["export"])
        return rc if rc else main(["build"])
    if cmd == "status":
        from doltsamples import build
        return build.status(cfg)
    if cmd in ("up", "compose", "down", "ps", "urls"):
        from doltsamples import stack
        return {"up": lambda: stack.up(cfg), "compose": lambda: (stack.write(cfg), 0)[1], "down": stack.down,
                "ps": stack.status, "urls": stack.urls}[cmd]()
    if cmd == "test":
        from doltsamples import check
        return check.main()
    if cmd == "clean":
        from doltsamples import clean
        return clean.main(rest)
    sys.exit(f"unknown command {cmd!r}\n\n{USAGE}")
