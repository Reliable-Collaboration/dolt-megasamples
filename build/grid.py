#!/usr/bin/env python3
"""The whole experiment as a grid: every database against every test, done and outstanding."""
import json, os, sys
sys.path.insert(0, "scripts")
from common import ROOT

u = json.load(open(os.path.join(ROOT, "build", "progress.json"), encoding="utf-8"))["units"]
mem = json.load(open(os.path.join(ROOT, "build", "memory.json"), encoding="utf-8"))
rows = {}
for mode in mem.values():
    for db, r in mode.items():
        if r.get("rows"):
            rows[db] = r["rows"]

DEFERRED = ["mysql", "dolt_oneshot", "mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"]
INLINE = ["mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"]
HEAD = ["my", "d1", "myR", "dRI", "dRC", "myR!", "dRI!", "dRC!"]
# measured inline/deferred time ratios; rowcommit not yet complete, so its deferred time is used
FACTOR = {"mysql_rowwise": 1.024, "dolt_rowinsert": 1.150, "dolt_rowcommit": 1.0}


def unit(ph, db, inline):
    return u.get(f"{ph}/{db}" + ("/inline" if inline else ""), {})


def mark(v):
    s = v.get("status")
    return {"done": " ok ", "running": "RUN ", "error": "FAIL"}.get(s, "  . ")


dbs = sorted(rows, key=lambda d: -rows[d])
print(f"{'database':22}{'rows':>10}  " + "".join(f"{h:>5}" for h in HEAD))
print(f"{'':22}{'':>10}  " + "".join(f"{'':>5}" for h in HEAD))
pending_seconds, pending_n = 0.0, 0
for db in dbs:
    cells = []
    for ph in DEFERRED:
        cells.append(mark(unit(ph, db, False)))
    for ph in INLINE:
        v = unit(ph, db, True)
        cells.append(mark(v))
        if v.get("status") not in ("done", "running"):
            d = unit(ph, db, False)
            base = (d.get("seconds") or 0) + (d.get("settle_seconds") or 0)
            pending_seconds += base * FACTOR[ph]
            pending_n += 1
    print(f"{db:22}{rows[db]:>10,}  " + "".join(f"{c:>5}" for c in cells))

done = sum(1 for v in u.values() if v.get("status") == "done")
run = sum(1 for v in u.values() if v.get("status") == "running")
fail = sum(1 for v in u.values() if v.get("status") == "error")
print()
print("  my=MySQL extended  d1=Dolt 1 commit/db  myR=MySQL 1 INSERT/row")
print("  dRI=Dolt 1 INSERT/row  dRC=Dolt 1 commit/row   ! = indexes kept inline")
print()
print(f"  {done} done, {run} running, {fail} failed, {pending_n} not started, of 168 total")
print(f"  estimated time for the {pending_n} outstanding: {pending_seconds/3600:.1f} h")
