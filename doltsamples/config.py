"""dolt-megasamples.yaml: which engines, which databases with which history, which consoles.

Read by every command. Without the file, the built-in default applies: the 21 core databases in all
three engines with one commit each, and every console.

    corpus: ../sql-megasamples        # the sql-megasamples checkout the data comes from
    engines:
      dolt:
        single: core                  # one commit holding the whole database
        per-row: [sakila, chinook]    # one commit per row; served as sakila_per_row, chinook_per_row
      doltgres:
        single: core
      doltlite:
        single: core
    consoles: [landing, workbench, phpmyadmin, adminer, dbgate, cloudbeaver]
    ports: {dolt: 3307, doltgres: 5433, landing: 8090, ...}
    memory: {dolt: 2g, doltgres: 2g, build: 12g}

A database list is a selector the corpus understands -- core, quick, all, a tier -- or a list of
names. A database may sit under both histories; the two are served side by side.
"""
import os, subprocess, sys

import yaml

from doltsamples.util import ROOT, default_build_memory

PATH = os.path.join(ROOT, "dolt-megasamples.yaml")
ENGINES = ("dolt", "doltgres", "doltlite")
HISTORIES = ("single", "per-row")
HISTORY_LABEL = {"single": "one commit for the whole database", "per-row": "one commit per row"}
CONSOLES = ("landing", "workbench", "phpmyadmin", "adminer", "dbgate", "cloudbeaver")
# which consoles can browse which engines; a console is started only if an engine it reads is served
CONSOLE_ENGINES = {"landing": ENGINES, "workbench": ENGINES, "phpmyadmin": ("dolt",), "adminer": ("dolt", "doltgres"),
                   "dbgate": ("dolt", "doltgres"), "cloudbeaver": ("dolt", "doltgres")}
PORTS = {"dolt": 3307, "doltgres": 5433, "landing": 8090, "phpmyadmin": 8091, "adminer": 8092,
         "dbgate": 8093, "cloudbeaver": 8094, "workbench": 8095, "workbench_api": 9002}
MEMORY = {"dolt": "2g", "doltgres": "2g"}
DEFAULT = {"engines": {e: {"single": "core"} for e in ENGINES}, "consoles": list(CONSOLES)}


def served_name(db, history):
    """The name a store is served under: the database's own for one commit, `<db>_per_row` for the
    per-row history, so both can be served by one server at once."""
    return db if history == "single" else f"{db}_per_row"


class Config:
    def __init__(self, raw, path=None):
        self.path = path
        self.raw = raw or {}
        corpus = self.raw.get("corpus") or os.environ.get("MEGASAMPLES_DIR") or os.path.join("..", "sql-megasamples")
        self.corpus = os.path.normpath(os.path.join(ROOT, os.path.expanduser(corpus)))
        self.engines = {}
        for engine, spec in (self.raw.get("engines") or {}).items():
            if engine not in ENGINES:
                sys.exit(f"{self.where()}: unknown engine {engine!r}; the engines are {', '.join(ENGINES)}")
            spec = spec or {}
            for key in spec:
                if key not in HISTORIES:
                    sys.exit(f"{self.where()}: {engine}: unknown history {key!r}; the histories are "
                             f"{', '.join(HISTORIES)}")
            self.engines[engine] = {h: spec[h] for h in HISTORIES if spec.get(h)}
        consoles = self.raw.get("consoles", list(CONSOLES))
        for c in consoles or []:
            if c not in CONSOLES:
                sys.exit(f"{self.where()}: unknown console {c!r}; the consoles are {', '.join(CONSOLES)}")
        self.consoles = [c for c in CONSOLES if c in (consoles or [])]
        self.ports = {**PORTS, **(self.raw.get("ports") or {})}
        mem = self.raw.get("memory") or {}
        self.memory = {**MEMORY, **{k: str(v) for k, v in mem.items()}}
        self.memory.setdefault("build", default_build_memory())
        self._resolved = {}

    def where(self):
        return os.path.relpath(self.path, ROOT) if self.path else "the built-in default"

    def databases(self, engine, history):
        """The database names a selector stands for, in the corpus's order."""
        key = (engine, history)
        if key not in self._resolved:
            sel = (self.engines.get(engine) or {}).get(history)
            self._resolved[key] = resolve(sel, self.corpus) if sel else []
        return self._resolved[key]

    def wanted(self):
        """[(engine, history, db)] for everything the configuration asks for."""
        return [(e, h, db) for e in ENGINES for h in HISTORIES for db in self.databases(e, h)]

    def served_consoles(self):
        engines = {e for e, _, _ in self.wanted()}
        return [c for c in self.consoles if engines & set(CONSOLE_ENGINES[c])]


def load(path=None):
    path = path or os.environ.get("DOLTSAMPLES_CONFIG") or PATH
    if os.path.exists(path):
        raw = yaml.safe_load(open(path, encoding="utf-8")) or {}
        return Config(raw, path)
    return Config(DEFAULT, None)


def corpus_cli(corpus, *args):
    """Run sql-megasamples' own CLI in its checkout (its virtualenv when it has one)."""
    py = os.path.join(corpus, ".venv", "bin", "python")
    cmd = [py if os.path.exists(py) else sys.executable, "-m", "megasamples", *args]
    p = subprocess.run(cmd, cwd=corpus, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": corpus})
    if p.returncode != 0:
        raise RuntimeError(f"sql-megasamples' CLI failed in {corpus}: {(p.stderr or p.stdout).strip()[-300:]}")
    return p.stdout


def database_of(corpus, dataset):
    """A dataset's database, and whether it only appends tables to another dataset's database."""
    path = os.path.join(corpus, "datasets", dataset, "dataset.yaml")
    try:
        cfg = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except OSError:
        return dataset, False
    return cfg.get("database") or dataset, bool(cfg.get("append"))


def resolve(selector, corpus):
    if isinstance(selector, str) and " " not in selector.strip() \
            and not os.path.isdir(os.path.join(corpus, "datasets", selector.strip())):
        if not os.path.isdir(os.path.join(corpus, "megasamples")):
            sys.exit(f"the selector {selector!r} needs the sql-megasamples checkout, which is not at {corpus}; "
                     f"clone it there, or set `corpus:` in dolt-megasamples.yaml")
        names = corpus_cli(corpus, "list", "--names", "--select", selector).split()
    elif isinstance(selector, str):
        names = selector.split()
    else:
        names = [str(n) for n in selector]
    out = []
    for name in names:
        db, append = database_of(corpus, name)
        if not append and db not in out:
            out.append(db)
    return out
