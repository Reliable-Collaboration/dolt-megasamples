#!/usr/bin/env python3
"""The complete state of the experiment, with every number labelled by unit and by what it measures.

  python3 scripts/summary.py [--disk] [--time] [--memory] [--grid]

Written because progress reports drifted into quoting bare figures -- "9.4 GB", "2.6x", "4.6 GB" --
where the reader had to infer whether a number was disk or memory, and if memory, which of several
different measurements. There are four distinct quantities in this experiment and they are easy to
confuse:

  disk on disk        bytes the stored database occupies, `du -sb`, excluding `.dolt/stats`
  load time           wall-clock seconds for the load itself, excluding dump, transform, measurement
  settle time         wall-clock seconds for the commit and `dolt gc` that follow the load
  peak load memory    the highest anonymous memory the worker held during the load, from the
                      container's cgroup (`memory.stat` anon), sampled every 2 seconds. Anonymous
                      memory, not total: the cgroup limit also counts page cache, but the kernel
                      reclaims cache under pressure and cannot reclaim anon, so anon is what decides
                      whether a process is killed.
  open memory         the smallest container memory *limit* under which the finished database could
                      be opened and queried at all. A different question from peak load memory, and
                      for a database with millions of commits the answer is much larger.

Every table below names its unit in the header. Nothing here is typed by hand; it is read from
build/progress.json, build/trace/*.json and build/memory.json.
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT  # noqa: E402

BUILD = os.path.join(ROOT, "build")
TESTS = [
    ("mysql", False, "MySQL extended INSERTs"),
    ("mysql_rowwise", False, "MySQL 1 INSERT/row"),
    ("dolt_oneshot", False, "Dolt 1 commit/database"),
    ("dolt_rowinsert", False, "Dolt 1 INSERT/row"),
    ("dolt_rowcommit", False, "Dolt 1 commit/row"),
    ("mysql_rowwise", True, "MySQL 1 INSERT/row, indexes kept"),
    ("dolt_rowinsert", True, "Dolt 1 INSERT/row, indexes kept"),
    ("dolt_rowcommit", True, "Dolt 1 commit/row, indexes kept"),
]
SHORT = ["myExt", "myRow", "dolt1", "doltRI", "doltRC", "myRow!", "doltRI!", "doltRC!"]


def load(name):
    p = os.path.join(BUILD, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def units():
    return load("progress.json").get("units", {})


def rows_per_db():
    rows = {}
    for mode in load("memory.json").values():
        for db, r in mode.items():
            if r.get("rows"):
                rows[db] = r["rows"]
    return rows


def cell(u, phase, db, inline):
    return u.get(f"{phase}/{db}" + ("/inline" if inline else ""), {})


def peak_load_memory():
    """Highest anonymous memory seen during each traced load, in bytes."""
    out = {}
    d = os.path.join(BUILD, "trace")
    if not os.path.isdir(d):
        return out
    for name in os.listdir(d):
        if not name.startswith("rowcommit-") or not name.endswith(".json"):
            continue
        t = json.load(open(os.path.join(d, name), encoding="utf-8"))
        peaks = [s.get("memory_anon_bytes") or 0 for s in t.get("samples") or []]
        if peaks:
            out[t.get("database") or name[10:-5]] = max(peaks)
    return out


def mb(n):
    return f"{n / 1e6:,.0f}" if n else "—"


def mins(n):
    return f"{n / 60:,.1f}" if n else "—"


def table_disk(u, rows, dbs):
    print("\nDISK ON DISK — megabytes (MB) occupied by the stored database, `du -sb`\n")
    print(f"{'database':20}{'rows':>10}  " + "".join(f"{s:>9}" for s in SHORT))
    for db in dbs:
        cells = [mb(cell(u, p, db, i).get("bytes")) for p, i, _ in TESTS]
        print(f"{db:20}{rows.get(db, 0):>10,}  " + "".join(f"{c:>9}" for c in cells))
    tot = [sum((cell(u, p, db, i).get("bytes") or 0) for db in dbs) for p, i, _ in TESTS]
    print(f"{'TOTAL':20}{sum(rows.get(d, 0) for d in dbs):>10,}  "
          + "".join(f"{mb(t):>9}" for t in tot))
    base = tot[0]
    if base:
        print(f"{'x MySQL extended':20}{'':>10}  "
              + "".join(f"{(f'{t / base:.2f}x' if t else '—'):>9}" for t in tot))


def table_time(u, rows, dbs):
    print("\nTIME — minutes of wall clock, load plus the commit and gc that follow it\n")
    print(f"{'database':20}{'rows':>10}  " + "".join(f"{s:>9}" for s in SHORT))
    for db in dbs:
        cells = []
        for p, i, _ in TESTS:
            v = cell(u, p, db, i)
            s = (v.get("seconds") or 0) + (v.get("settle_seconds") or 0)
            cells.append(mins(s) if v.get("status") == "done" else
                         ("RUN" if v.get("status") == "running" else "—"))
        print(f"{db:20}{rows.get(db, 0):>10,}  " + "".join(f"{c:>9}" for c in cells))
    tot = []
    for p, i, _ in TESTS:
        tot.append(sum(((cell(u, p, db, i).get("seconds") or 0)
                        + (cell(u, p, db, i).get("settle_seconds") or 0)) for db in dbs))
    print(f"{'TOTAL':20}{'':>10}  " + "".join(f"{mins(t):>9}" for t in tot))
    print(f"{'TOTAL hours':20}{'':>10}  "
          + "".join(f"{(f'{t / 3600:.1f}' if t else '—'):>9}" for t in tot))


def table_memory(u, rows, dbs, peaks, mem):
    print("\nMEMORY — two different quantities, both in gigabytes (GB)\n")
    print("  peak load RAM : highest anonymous memory the worker held while loading, cgroup anon")
    print("  open RAM      : smallest container memory limit under which the finished database")
    print("                  could be opened and queried at all\n")
    print(f"{'database':20}{'rows':>10}{'commits':>12}"
          f"{'peak load RAM':>15}{'open RAM':>11}{'disk MB':>10}")
    print(f"{'':20}{'(count)':>10}{'(count)':>12}{'(GB, 1 commit/row)':>15}"[:73])
    rc = mem.get("rowcommit") or {}
    for db in dbs:
        v = cell(u, "dolt_rowcommit", db, False)
        pk = peaks.get(db)
        om = (rc.get(db) or {}).get("megabytes")
        print(f"{db:20}{rows.get(db, 0):>10,}{(rc.get(db) or {}).get('commits') or 0:>12,}"
              f"{(f'{pk / 1e9:.1f}' if pk else '—'):>15}"
              f"{(f'{om / 1024:.2f}' if om else '>8'):>11}"
              f"{mb(v.get('bytes')):>10}")


def inline_factor(u, phase):
    """Measured inline/deferred time ratio for a phase, from the pairs that have both."""
    pairs = []
    for k, v in u.items():
        if not k.endswith("/inline") or v.get("status") != "done":
            continue
        ph, db = k.split("/")[0], k.split("/")[1]
        if ph != phase:
            continue
        d = u.get(f"{ph}/{db}", {})
        if d.get("status") == "done" and d.get("seconds"):
            pairs.append(((v.get("seconds") or 0) + (v.get("settle_seconds") or 0))
                         / ((d.get("seconds") or 0) + (d.get("settle_seconds") or 0)))
    return sum(pairs) / len(pairs) if pairs else 1.0


def table_outstanding(u, rows, dbs):
    """What is still to run, and how long it should take.

    Estimated from each database's own deferred timing for the same test, scaled by the
    inline/deferred ratio measured on the databases that have already done both -- rather than from
    a single corpus-wide rate, which hides that a database's cost depends on its schema as much as
    its row count."""
    print("\nOUTSTANDING — what has not finished, and the estimated wall-clock minutes for each\n")
    running, pending = [], []
    for db in dbs:
        for ph, inline, lbl in TESTS:
            v = cell(u, ph, db, inline)
            if v.get("status") == "done":
                continue
            d = cell(u, ph, db, False)
            base = (d.get("seconds") or 0) + (d.get("settle_seconds") or 0)
            est = base * (inline_factor(u, ph) if inline else 1.0)
            if v.get("status") == "running":
                elapsed = time.time() - (v.get("started") or time.time())
                running.append((db, lbl, elapsed, est))
            else:
                pending.append((db, lbl, est))
    if running:
        print(f"  {'RUNNING':10}{'database':20}{'test':34}"
              f"{'elapsed min':>12}{'est total min':>14}{'est left min':>13}")
        for db, lbl, el, est in running:
            print(f"  {'':10}{db:20}{lbl:34}{el / 60:>12.1f}{est / 60:>14.1f}"
                  f"{max(0, est - el) / 60:>13.1f}")
    if pending:
        print(f"\n  {'NOT STARTED':10}{'database':20}{'test':34}{'est min':>12}")
        for db, lbl, est in pending:
            print(f"  {'':10}{db:20}{lbl:34}{est / 60:>12.1f}")
    total = sum(max(0, e - el) for _, _, el, e in running) + sum(e for _, _, e in pending)
    print(f"\n  {len(running)} running, {len(pending)} not started; "
          f"estimated {total / 3600:.1f} hours of wall clock remaining")
    print("  Estimates scale each database's own deferred time by the measured inline/deferred")
    print("  ratio for that test: " + ", ".join(
        f"{lbl.split(',')[0]} {inline_factor(u, ph):.2f}x"
        for ph, inline, lbl in TESTS if inline))


def table_grid(u, rows, dbs):
    print("\nCOMPLETION — every database against every test\n")
    print(f"{'database':20}{'rows':>10}  " + "".join(f"{s:>9}" for s in SHORT))
    n_done = n_run = n_todo = 0
    for db in dbs:
        cells = []
        for p, i, _ in TESTS:
            st = cell(u, p, db, i).get("status")
            cells.append({"done": "done", "running": "RUNNING", "error": "FAILED"}.get(st, "-"))
            n_done += st == "done"
            n_run += st == "running"
            n_todo += st is None
        print(f"{db:20}{rows.get(db, 0):>10,}  " + "".join(f"{c:>9}" for c in cells))
    print(f"\n  {n_done} done, {n_run} running, {n_todo} not started, of {len(dbs) * len(TESTS)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for f in ("disk", "time", "memory", "grid", "outstanding"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    show_all = not any((a.disk, a.time, a.memory, a.grid, a.outstanding))

    u, rows, mem = units(), rows_per_db(), load("memory.json")
    peaks = peak_load_memory()
    dbs = sorted(rows, key=lambda d: -rows[d])
    print("  ".join(f"{s}={lbl}" for s, (_, _, lbl) in zip(SHORT, TESTS)).replace("  ", "\n  "))
    if show_all or a.grid:
        table_grid(u, rows, dbs)
    if show_all or a.disk:
        table_disk(u, rows, dbs)
    if show_all or a.time:
        table_time(u, rows, dbs)
    if show_all or a.memory:
        table_memory(u, rows, dbs, peaks, mem)
    if show_all or a.outstanding:
        table_outstanding(u, rows, dbs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
