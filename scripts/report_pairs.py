#!/usr/bin/env python3
"""The tables of the PostgreSQL/DoltgreSQL and SQLite/DoltLite pairs, from build/results.json.

Read by scripts/render.py through its block registry; nothing here is written by hand. Every
table is one population per row: a test with no result shows an em dash, and a totals row covers
only the databases that have every test.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import human  # noqa: E402
from pairs import LABEL, PHASES  # noqa: E402
from report import cell, secs  # noqa: E402

TITLES = {"pg": ("PostgreSQL", "DoltgreSQL"), "lite": ("SQLite", "DoltLite")}
SHORT = {"postgres": "1. PostgreSQL<br>COPY", "postgres_rowwise": "2. PostgreSQL<br>1 INSERT/row",
         "doltgres_oneshot": "3. DoltgreSQL<br>1 commit/db", "doltgres_rowinsert": "4. DoltgreSQL<br>1 INSERT/row",
         "doltgres_rowcommit": "5. DoltgreSQL<br>1 commit/row",
         "sqlite": "1. SQLite<br>one transaction", "sqlite_rowwise": "2. SQLite<br>1 INSERT/row",
         "doltlite_oneshot": "3. DoltLite<br>1 commit/db", "doltlite_rowinsert": "4. DoltLite<br>1 INSERT/row",
         "doltlite_rowcommit": "5. DoltLite<br>1 commit/row"}


def units(results, pair):
    """{db: {phase: unit}} for the pair, with the source row count."""
    out = {}
    for db in sorted(results):
        m = (results[db].get("pairs") or {}).get(pair) or {}
        if not m:
            continue
        rows = ((results[db].get("pairs") or {}).get("source_rows") or {}).get(pair) or 0
        out[db] = dict(m, __rows=rows)
    return out


def size_time(u, base):
    if not u or not u.get("disk_bytes"):
        return "—"
    b = u["disk_bytes"]
    if base and base.get("disk_bytes") and u is not base:
        return f"{cell(b, base['disk_bytes'])}<br>{secs(u.get('total_seconds'))}"
    return f"{human(b)}<br>{secs(u.get('total_seconds') if u is not base else u.get('load_seconds'))}"


def pair_table(results, pair, suffix=""):
    phases = PHASES[pair]
    data = units(results, pair)
    if not data:
        return f"*No {' / '.join(TITLES[pair])} unit has been measured yet.*"
    keys = [phases[0]] + [ph + suffix for ph in phases[1:]]
    L = ["| database | rows | " + " | ".join(SHORT[ph] for ph in phases) + " |",
         "|---|---:|" + "---:|" * len(phases)]
    for db in sorted(data, key=lambda d: -data[d]["__rows"]):
        m = data[db]
        base = m.get(phases[0]) or {}
        L.append(f"| `{db}` | {m['__rows']:,} | " + " | ".join(size_time(m.get(k), base) for k in keys) + " |")
    full = [db for db in data if all((data[db].get(k) or {}).get("disk_bytes") for k in keys)]
    if full:
        b = {k: sum(data[db][k]["disk_bytes"] for db in full) for k in keys}
        t = {k: sum((data[db][k].get("total_seconds" if k != phases[0] else "load_seconds") or 0) for db in full)
             for k in keys}
        b0, t0 = b[keys[0]], max(t[keys[0]], 0.1)
        cells = [f"**{human(b0)}<br>{secs(t0)}**"] + [
            f"**{b[k] / b0:.2f}×<br>{t[k] / t0:.0f}× time**" for k in keys[1:]]
        L.append(f"| **all {len(full)} with every test** | **{sum(data[db]['__rows'] for db in full):,}** | "
                 + " | ".join(cells) + " |")
    if len(full) < len(data):
        missing = sorted(db for db in data if db not in full)
        L.append(f"\n*Each cell is disk then time; a versioned cell also gives the size as a multiple of test 1. "
                 f"{len(data) - len(full)} database(s) do not yet have every test and are excluded from the "
                 f"totals row: " + ", ".join(f"`{d}`" for d in missing) + ".*")
    return "\n".join(L)


def inline_table(results, pair):
    phases = PHASES[pair]
    data = units(results, pair)
    rows = [db for db in data if any(data[db].get(ph + "_inline") for ph in phases[1:])]
    if not rows:
        return f"*The inline policy has not been measured for the {' / '.join(TITLES[pair])} pair yet.*"
    per_row = phases[1:]
    L = ["| database | " + " | ".join(f"{SHORT[ph]}<br>deferred → inline" for ph in per_row) + " |",
         "|---|" + "---:|" * len(per_row)]
    for db in sorted(rows, key=lambda d: -data[d]["__rows"]):
        m = data[db]
        cells = []
        for ph in per_row:
            d, i = m.get(ph) or {}, m.get(ph + "_inline") or {}
            if not d.get("disk_bytes") and not i.get("disk_bytes"):
                cells.append("—")
                continue
            cells.append(f"{human(d['disk_bytes']) if d.get('disk_bytes') else '—'} → "
                         f"{human(i['disk_bytes']) if i.get('disk_bytes') else '—'}<br>"
                         f"{secs(d.get('total_seconds')) if d else '—'} → {secs(i.get('total_seconds')) if i else '—'}")
        L.append(f"| `{db}` | " + " | ".join(cells) + " |")
    return "\n".join(L)


def refusals(results):
    L = []
    for pair in PHASES:
        data = units(results, pair)
        for db in sorted(data):
            for ph in PHASES[pair] + [x + "_inline" for x in PHASES[pair]]:
                u = data[db].get(ph)
                if not u:
                    continue
                items = list(u.get("refused_objects") or [])
                if u.get("indexes_refused"):
                    items.append(f"{len(u['indexes_refused'])} index(es) refused: " + ", ".join(u["indexes_refused"]))
                if items:
                    L.append(f"* `{db}`, {LABEL[ph.replace('_inline', '')]}"
                             f"{' (inline)' if ph.endswith('_inline') else ''}: " + "; ".join(items))
    dropped = {}
    for pair in PHASES:
        for db, m in units(results, pair).items():
            for ph, u in m.items():
                if isinstance(u, dict) and u.get("indexes_dropped"):
                    dropped[db] = u["indexes_dropped"]
    if dropped:
        L.append("\nDropped by the dialect before any load, on both engines of the pair (the GIN indexes and the "
                 "indexes of the generated-column tables): "
                 + "; ".join(f"`{db}`: {', '.join(v)}" for db, v in sorted(dropped.items())) + ".")
    return "\n".join(L) if L else "*No unit has recorded a refusal.*"


def memory_table(results, pair):
    phases = PHASES[pair]
    data = units(results, pair)
    rows = [db for db in data if any((data[db].get(ph) or {}).get("memory_anon_peak_bytes") for ph in phases)]
    if not rows:
        return f"*No memory peak recorded for the {' / '.join(TITLES[pair])} pair yet.*"
    L = ["| database | rows | " + " | ".join(SHORT[ph] for ph in phases) + " |",
         "|---|---:|" + "---:|" * len(phases)]
    for db in sorted(rows, key=lambda d: -data[d]["__rows"]):
        m = data[db]
        cells = [human(m[ph]["memory_anon_peak_bytes"]) if (m.get(ph) or {}).get("memory_anon_peak_bytes") else "—"
                 for ph in phases]
        L.append(f"| `{db}` | {m['__rows']:,} | " + " | ".join(cells) + " |")
    return "\n".join(L)
