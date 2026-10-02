"""Copy each database's one-line description from the corpus into build/catalogue.json, for the
landing page's "what it is" column. Run by `make export`.

sql-megasamples says what each dataset is in the dataset's own research record
(`datasets/<name>/dataset.yaml` names the record and may carry a `blurb`; the record's front matter
carries `description`),
and its catalogue and landing page cut that description back to the clause that says what the
thing is. This does the same cut, with the same rules, so the README's and landing page's "what it
is" column here reads as it does there and cannot be written by hand.
"""
import json, os, sys

import yaml

from doltsamples.util import ROOT

OUT = os.path.join(ROOT, "build", "catalogue.json")
SPLITS = ("; ", " - ", " — ")   # the corpus's megasamples/catalogue.py: never ". " (cuts at "incl.")


def shorten(full, floor=40, ceiling=150):
    head = full
    for sep in SPLITS:
        candidate = head.split(sep)[0].strip()
        if len(candidate) >= floor:
            head = candidate
    if len(head) > ceiling:
        cut = head.rfind(", ", 0, ceiling)
        if cut > floor:
            head = head[:cut]
    if head.count("(") > head.count(")"):
        opened = head.rfind("(")
        if opened > floor:
            head = head[:opened].rstrip()
    return head.rstrip(" .,;-")     # the corpus's set


def front_matter(path):
    """The record's YAML front matter as a dict, the way the corpus reads it."""
    text = open(path, encoding="utf-8").read()
    parts = text.split("---", 2)
    try:
        return yaml.safe_load(parts[1]) or {} if len(parts) > 2 else {}
    except yaml.YAMLError:
        return {}


def write(corpus):
    datasets = os.path.join(corpus, "datasets")
    if not os.path.isdir(datasets):
        print(f"  ! no corpus checkout at {corpus}; the landing page will not say what each database is")
        return
    by_database = {}
    for name in sorted(os.listdir(datasets)):
        y = os.path.join(datasets, name, "dataset.yaml")
        if not os.path.exists(y):
            continue
        try:
            spec = yaml.safe_load(open(y, encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            sys.exit(f"{y}: {e}")
        if spec.get("append"):          # a folder that adds tables to another dataset's database, not a database
            continue
        db, record = str(spec.get("database") or name), str(spec.get("record") or "")
        # `blurb:` in dataset.yaml wins, as it does in the corpus, where the record's description was
        # written for the research trail rather than for readers
        blurb = str(spec.get("blurb") or "").strip()
        if blurb:
            by_database[db] = blurb
        elif record and os.path.exists(os.path.join(corpus, record)):
            by_database[db] = shorten(str(front_matter(os.path.join(corpus, record)).get("description") or "").strip())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(by_database, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
