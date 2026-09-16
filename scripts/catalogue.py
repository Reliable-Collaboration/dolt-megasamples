#!/usr/bin/env python3
"""Copy each database's one-line description from the corpus into build/catalogue.json.

  MEGASAMPLES_DIR=../sql-megasamples python3 scripts/catalogue.py      (make catalogue)

sql-megasamples says what each dataset is in the dataset's own research record
(`datasets/<name>/dataset.yaml` names the record and may carry a `blurb`; the record's front matter
carries `description`),
and its catalogue and landing page cut that description back to the clause that says what the
thing is. This does the same cut, with the same rules, so the README's and landing page's "what it
is" column here reads as it does there and cannot be written by hand. The result is committed, so
a clone without the corpus beside it renders the same words.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MEGASAMPLES_DIR, ROOT, load_results  # noqa: E402

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
    return head.rstrip(" ,;")


def front_matter(path):
    text = open(path, encoding="utf-8").read()
    parts = text.split("---", 2)
    return parts[1] if len(parts) > 2 else ""


def field(block, name):
    m = re.search(rf"^{name}:\s*(.+?)\s*$", block, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    return v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'" else v


def main():
    datasets = os.path.join(MEGASAMPLES_DIR, "datasets")
    if not os.path.isdir(datasets):
        sys.exit(f"no corpus checkout at {MEGASAMPLES_DIR} (set MEGASAMPLES_DIR); build/catalogue.json left as it is")
    by_database = {}
    for name in sorted(os.listdir(datasets)):
        y = os.path.join(datasets, name, "dataset.yaml")
        if not os.path.exists(y):
            continue
        block = open(y, encoding="utf-8").read()
        db, record = field(block, "database") or name, field(block, "record")
        # `blurb:` in dataset.yaml wins, as it does in the corpus, where the record's description was
        # written for the research trail rather than for readers
        blurb = field(block, "blurb")
        if blurb:
            by_database[db] = blurb
        elif record and os.path.exists(os.path.join(MEGASAMPLES_DIR, record)):
            by_database[db] = shorten(field(front_matter(os.path.join(MEGASAMPLES_DIR, record)), "description"))
    out = {db: by_database.get(db, "") for db in sorted(load_results())}
    missing = [db for db, v in out.items() if not v]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print(f"  . wrote {os.path.relpath(OUT, ROOT)} ({len(out) - len(missing)} of {len(out)} databases described"
          + (f"; no record for {', '.join(missing)}" if missing else "") + ")")


if __name__ == "__main__":
    main()
