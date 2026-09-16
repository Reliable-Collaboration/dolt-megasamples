#!/usr/bin/env python3
"""The tables of the PostgreSQL/DoltgreSQL and SQLite/DoltLite pairs, from build/results.json.

Read by scripts/render.py through its block registry; nothing here is written by hand. Every
table is one population per row: a test with no result shows an em dash, and a totals row covers
only the databases that have every test.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import human, human_mb  # noqa: E402
from pairs import LABEL, PER_ROW, PHASES  # noqa: E402
from report import cell, secs  # noqa: E402


def seconds(v):
    """A pair unit's time. report.secs prints a dash for zero, which in these tables would read as not
    measured; every pair unit records its time, and one that rounds to zero took less than 0.05 s."""
    return "0.0 s" if v == 0 else secs(v)

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


UNSETTLED = " †"


def shown(u):
    """A unit's size as the tables print it: settled, or the uncollected footprint marked †."""
    if not u:
        return "—"
    if u.get("settled") is False and u.get("footprint_bytes"):
        return human(u["footprint_bytes"]) + UNSETTLED
    return human(u["disk_bytes"]) if u.get("disk_bytes") else "—"


def size_time(u, base):
    if u and u.get("settled") is False and u.get("footprint_bytes"):
        return f"{shown(u)}<br>{seconds(u.get('total_seconds'))}"
    if not u or not u.get("disk_bytes"):
        return "—"
    b = u["disk_bytes"]
    mark = UNSETTLED if u.get("settled") is False else ""
    if base and base.get("disk_bytes") and u is not base:
        return f"{cell(b, base['disk_bytes'])}{mark}<br>{seconds(u.get('total_seconds'))}"
    return f"{human(b)}{mark}<br>{seconds(u.get('total_seconds') if u is not base else u.get('load_seconds'))}"


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
    full = [db for db in data if all((data[db].get(k) or {}).get("disk_bytes") for k in keys)
            and not any((data[db].get(k) or {}).get("settled") is False for k in keys)]
    if full:
        b = {k: sum(data[db][k]["disk_bytes"] for db in full) for k in keys}
        t = {k: sum((data[db][k].get("total_seconds" if k != phases[0] else "load_seconds") or 0) for db in full)
             for k in keys}
        b0, t0 = b[keys[0]], max(t[keys[0]], 0.1)
        cells = [f"**{human(b0)}<br>{seconds(t0)}**"] + [
            f"**{b[k] / b0:.2f}×<br>{t[k] / t0:.0f}× time**" for k in keys[1:]]
        L.append(f"| **all {len(full)} with every test** | **{sum(data[db]['__rows'] for db in full):,}** | "
                 + " | ".join(cells) + " |")
    if len(full) < len(data):
        missing = sorted(db for db in data if db not in full)
        L.append(f"\n*Each cell is disk then time; a versioned cell also gives the size as a multiple of test 1. "
                 f"{len(data) - len(full)} database(s) do not yet have every test and are excluded from the "
                 f"totals row: " + ", ".join(f"`{d}`" for d in missing) + ".*")
    unsettled = sorted(f"`{db}` ({SHORT[k.replace('_inline', '')].replace('<br>', ', ')})"
                       for db in data for k in keys if (data[db].get(k) or {}).get("settled") is False)
    if unsettled:
        L.append(f"\n*† The store could not be garbage-collected, so this is the working footprint after the load, "
                 f"not a collected size, and it is left out of the totals row: " + ", ".join(unsettled) + ".*")
    return "\n".join(L)


def inline_table(results, pair):
    phases = PHASES[pair]
    data = units(results, pair)
    # the row-by-row shapes only: a one-commit load has no inline counterpart, and its column
    # could never fill
    per_row = [ph for ph in phases if ph in PER_ROW]
    rows = [db for db in data if any(data[db].get(ph + "_inline") for ph in per_row)]
    if not rows:
        return f"*The inline policy has not been measured for the {' / '.join(TITLES[pair])} pair yet.*"
    L = ["| database | " + " | ".join(f"{SHORT[ph]}<br>deferred → inline" for ph in per_row) + " |",
         "|---|" + "---:|" * len(per_row)]
    for db in sorted(rows, key=lambda d: -data[d]["__rows"]):
        m = data[db]
        cells = []
        for ph in per_row:
            d, i = m.get(ph) or {}, m.get(ph + "_inline") or {}
            if shown(d) == "—" and shown(i) == "—":
                cells.append("—")
                continue
            cells.append(f"{shown(d)} → {shown(i)}<br>"
                         f"{seconds(d.get('total_seconds')) if d else '—'} → {seconds(i.get('total_seconds')) if i else '—'}")
        L.append(f"| `{db}` | " + " | ".join(cells) + " |")
    if any(UNSETTLED in c for c in L):
        L.append("\n*† The store could not be garbage-collected, so the size is the working footprint after the load.*")
    return "\n".join(L)


def refusals(results):
    """What an engine refused, one line per database and distinct refusal, naming the loads it
    happened in -- the same view refused in all eight loads of a database is one line, not eight."""
    L = []
    for pair in PHASES:
        data = units(results, pair)
        for db in sorted(data):
            groups = {}
            loads = 0
            for ph in PHASES[pair] + [x + "_inline" for x in PHASES[pair]]:
                u = data[db].get(ph)
                if not u:
                    continue
                loads += 1
                items = list(u.get("refused_objects") or [])
                if u.get("indexes_refused"):
                    items.append(f"{len(u['indexes_refused'])} index(es) refused: " + ", ".join(u["indexes_refused"]))
                if items:
                    label = LABEL[ph.replace("_inline", "")] + (" (inline)" if ph.endswith("_inline") else "")
                    groups.setdefault(tuple(items), []).append(label)
            for items, where in groups.items():
                engine = where[0].split(",")[0]
                of_engine = sum(1 for ph in PHASES[pair] + [x + "_inline" for x in PHASES[pair]]
                                if data[db].get(ph) and LABEL[ph.replace("_inline", "")].startswith(engine))
                if len(where) == of_engine and of_engine > 1:
                    scope = f"every {engine} load"
                elif len(where) == 1:
                    scope = where[0]
                else:
                    scope = f"{engine}, {len(where)} of its {of_engine} loads (" + "; ".join(
                        w.split(", ", 1)[1] for w in where) + ")"
                L.append(f"* `{db}` -- {scope}: " + "; ".join(items))
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
    """Peak anonymous plus shared memory of each load's own container, through the load and its
    settle step."""
    phases = PHASES[pair]
    data = units(results, pair)
    rows = [db for db in data if any((data[db].get(ph) or {}).get("memory_peak_bytes") for ph in phases)]
    if not rows:
        return f"*No memory peak recorded for the {' / '.join(TITLES[pair])} pair yet.*"
    L = ["| database | rows | " + " | ".join(SHORT[ph] for ph in phases) + " |",
         "|---|---:|" + "---:|" * len(phases)]
    for db in sorted(rows, key=lambda d: -data[d]["__rows"]):
        m = data[db]
        cells = [human(m[ph]["memory_peak_bytes"]) if (m.get(ph) or {}).get("memory_peak_bytes") else "—"
                 for ph in phases]
        L.append(f"| `{db}` | {m['__rows']:,} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def versions_table():
    """Every engine this repository measures or serves, the one version its numbers belong to, since
    when, how the version is named, and what the image itself answers -- read from versions.json and
    build/environment.json, so the table cannot drift from what is measured. One version per result
    set (2026-09-12): a moved version means every unit of that engine is measured again."""
    import json, os, re
    from common import ROOT, VERSIONS
    env = {}
    path = os.path.join(ROOT, "build", "environment.json")
    if os.path.exists(path):
        env = (json.load(open(path, encoding="utf-8")).get("engines") or {})

    def short(image):
        name, _, digest = (image or "").partition("@")
        return f"`{name}@{digest[:19]}…`" if digest else (f"`{image}`" if image else "")

    def answered(text):
        return (text or "not recorded").replace("|", "\\|")

    dockerfile = open(os.path.join(ROOT, "docker", "doltlite", "Dockerfile"), encoding="utf-8").read()
    base = re.search(r"^FROM (\S+)", dockerfile, re.M)
    rows = [
        ("MySQL", "mysql", short(VERSIONS["mysql"]["image"]), env.get("mysql_version")),
        ("Dolt", "dolt", short(VERSIONS["dolt"]["image"]), env.get("dolt_version")),
        ("PostgreSQL", "postgres", short(VERSIONS["postgres"]["image"]), env.get("postgres_version")),
        ("DoltgreSQL", "doltgres", short(VERSIONS["doltgres"]["image"]), f"release {env.get('doltgres_version', 'not recorded')}"),
        ("SQLite shell", "sqlite", f"Debian 13's package in {short(base.group(1)) if base else '`debian:13-slim`'}",
         env.get("sqlite3_version")),
        ("DoltLite", "doltlite", ", ".join(f"`{pkg['name']}` sha256 `{pkg['sha256'][:12]}…`"
                                           for pkg in VERSIONS["doltlite"]["packages"]),
         env.get("doltlite_version")),
    ]
    L = ["| engine | version of this result set | since | named by | what the image answers |",
         "|---|---|---|---|---|"]
    for label, key, named, observed in rows:
        v = VERSIONS[key]
        L.append(f"| {label} | **{v['version']}** | {v['since']} | {named} | {answered(observed)} |")
    return "\n".join(L)



def memory_study_table():
    """What each engine of the pairs needs to open a stored shape and count its largest table -- the
    memory study of scripts/memory_profile_pairs.py (build/memory_pairs.json): per engine and shape,
    the largest and smallest ceiling that worked and which database set the top, and every store
    the study could not open, with the reason it recorded."""
    import json, os
    from common import ROOT
    path = os.path.join(ROOT, "build", "memory_pairs.json")
    if not os.path.exists(path):
        return "*No memory study of the pairs yet (`make memory-pairs`).*"
    study = json.load(open(path, encoding="utf-8"))
    names = {"doltgres": "DoltgreSQL", "doltlite": "DoltLite"}
    shapes = [("oneshot", "one commit per database"), ("rowinsert", "one INSERT per row, one commit"),
              ("rowinsert_inline", "the same, indexes inline"), ("rowcommit", "one commit per row"),
              ("rowcommit_inline", "the same, indexes inline")]
    L = ["| engine | stored shape | opens in | smallest | could not open |", "|---|---|---:|---:|---|"]
    for engine in ("doltgres", "doltlite"):
        for mode, label in shapes:
            dbs = (study.get(engine) or {}).get(mode) or {}
            if not dbs:
                continue
            ok = {db: v for db, v in dbs.items() if v.get("outcome") == "ok" and v.get("megabytes")}
            bad = {db: v for db, v in dbs.items() if v.get("outcome") != "ok"}
            top = max(ok.items(), key=lambda kv: kv[1]["megabytes"]) if ok else None
            opens = f"{human_mb(top[1]['megabytes'])} (`{top[0]}`)" if top else "—"
            least = human_mb(min(v['megabytes'] for v in ok.values())) if ok else "—"
            why = ", ".join(f"`{db}` ({v.get('outcome')})" for db, v in sorted(bad.items())) or "—"
            L.append(f"| {names[engine]} | {label} | {opens} | {least} | {why} |")
    tops = sorted({v.get("ladder_top_mb") for e in study.values() for m in e.values() for v in m.values() if v.get("ladder_top_mb")})
    exited = any(v.get("outcome") == "exited 1" for e in study.values() for m in e.values() for v in m.values())
    L.append("")
    note = (f"*Ceilings walked up to {', '.join(human_mb(t) for t in tops)}; a query that did not answer at the top is "
            f"\"could not open\" with what the probe saw.")
    if exited:
        note += (" `exited 1` is the image's entrypoint giving up after 300 s of start-up, not the memory ceiling: "
                 "DoltgreSQL scans every table when it opens a store, and a per-row-commit history of hundreds of "
                 "thousands of commits did not finish scanning in time.")
    L.append(note + "*")
    return "\n".join(L)


# ------------------------------------------------------------- the findings, every engine at once ---
def findings_totals(results, axis):
    """Every engine side by side: each pair's five loads totalled over the databases where the pair
    has every load, as a size or a time and as a multiple of that pair's own baseline in bulk. The
    populations differ where a pair lacks a load of a database, so each column names its count."""
    from loads import PAIRS, PAIR_ORDER, SHAPES, SHAPE_LABELS, complete, rows_of, test_of
    cols, totals = [], {}
    for pair in PAIR_ORDER:
        dbs = complete(results, pair)
        rows = sum(rows_of(results[d], pair) for d in dbs)
        cols.append(f"{PAIRS[pair]['baseline']} / {PAIRS[pair]['engine']}<br>{len(dbs)} of {len(results)} databases, {rows:,} rows")
        totals[pair] = {shape: sum(measure_of(results[d], pair, shape, axis) or 0 for d in dbs) for shape in SHAPES}
    unit = "disk" if axis == "bytes" else "time to load"
    L = [f"| load | " + " | ".join(f"{c} | × baseline" for c in cols) + " |",
         "|---|" + "---:|---:|" * len(cols)]
    for shape in SHAPES:
        cells = []
        for pair in PAIR_ORDER:
            v, base = totals[pair][shape], totals[pair]["bulk"] or 1
            text = human(v) if axis == "bytes" else seconds(v)
            cells.append(f"{text} | {'—' if shape == 'bulk' else f'**{v / base:.2f}×**' if v / base < 10 else f'**{v / base:,.0f}×**'}")
        who = "baseline" if shape in ("bulk", "rowwise") else "Dolt engine"
        L.append(f"| {SHAPE_LABELS[shape]} ({who}) | " + " | ".join(cells) + " |")
    return "\n".join(L)


def measure_of(r, pair, shape, axis):
    from loads import measure, test_of
    return measure(r, pair, test_of(pair, shape), axis)


def findings_by_database(results):
    """Every database down, every engine across, for the two loads that answer the question: the
    standard one-commit load (test 3 against test 1) and the commit-per-row load (test 5 against
    test 1), each as the size and as a multiple of that pair's baseline. † marks a store that could
    not be collected and is shown at its working footprint."""
    from loads import PAIRS, PAIR_ORDER, rows_of, test_of
    heads = []
    for pair in PAIR_ORDER:
        heads += [f"{PAIRS[pair]['baseline']}<br>bulk", f"{PAIRS[pair]['engine']}<br>1 commit/db", "×",
                  f"{PAIRS[pair]['engine']}<br>1 commit/row", "×"]
    L = ["| database | rows | " + " | ".join(heads) + " |", "|---|---:|" + "---:|" * len(heads)]
    for db in sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0)):
        r = results[db]
        cells = []
        for pair in PAIR_ORDER:
            base = measure_of(r, pair, "bulk", "bytes")
            for shape in ("oneshot", "rowcommit"):
                v = measure_of(r, pair, shape, "bytes")
                mark = ""
                if pair != "dolt":
                    u = ((r.get("pairs") or {}).get(pair) or {}).get(test_of(pair, shape)) or {}
                    if u.get("settled") is False and u.get("footprint_bytes"):
                        v, mark = u["footprint_bytes"], UNSETTLED
                if shape == "oneshot":
                    cells.append(human(base) if base else "—")
                cells.append((human(v) + mark) if v else "—")
                cells.append(f"{v / base:.2f}×" if (v and base and v / base < 10) else (f"{v / base:,.0f}×" if v and base else "—"))
        L.append(f"| `{db}` | {rows_of(r):,} | " + " | ".join(cells) + " |")
    return "\n".join(L)


ENGINE_COLUMNS = [("dolt", "bulk", "MySQL"), ("pg", "bulk", "PostgreSQL"), ("lite", "bulk", "SQLite"),
                  ("dolt", "oneshot", "Dolt"), ("pg", "oneshot", "DoltgreSQL"), ("lite", "oneshot", "DoltLite")]


def findings_sizes(results, shape, axis="bytes"):
    """Every database down and every engine across, for one way of writing the rows: the size (or
    the time) each engine ended with, so a database can be compared across all six engines at once.
    `shape` is 'oneshot' (the standard load: the baselines in bulk, the Dolt engines with one commit),
    'rowinsert' (one INSERT per row everywhere, one commit on the Dolt side), 'rowcommit' (one
    commit per row, which only the Dolt engines have) or 'all' (every engine and every run, fifteen
    columns grouped by run). † marks a store that could not be collected, shown at its working
    footprint."""
    from loads import PAIRS, PAIR_ORDER, rows_of, test_of
    if shape == "oneshot":
        cols = [(pair, "bulk", PAIRS[pair]["baseline"]) for pair in PAIR_ORDER] + \
               [(pair, "oneshot", PAIRS[pair]["engine"]) for pair in PAIR_ORDER]
    elif shape == "rowinsert":
        cols = [(pair, "rowwise", PAIRS[pair]["baseline"]) for pair in PAIR_ORDER] + \
               [(pair, "rowinsert", PAIRS[pair]["engine"]) for pair in PAIR_ORDER]
    elif shape == "rowcommit":
        cols = [(pair, "rowcommit", PAIRS[pair]["engine"]) for pair in PAIR_ORDER]
    else:  # every engine and every run, grouped by run so the same run's engines sit side by side
        short = {"bulk": "in bulk", "oneshot": "one commit", "rowwise": "one INSERT per row",
                 "rowinsert": "one INSERT per row, one commit", "rowcommit": "one commit per row"}
        cols = []
        for sh in ("bulk", "oneshot", "rowwise", "rowinsert", "rowcommit"):
            side = "baseline" if sh in ("bulk", "rowwise") else "engine"
            cols += [(pair, sh, f"{PAIRS[pair][side]}<br>{short[sh]}") for pair in PAIR_ORDER]
    L = ["| database | rows | " + " | ".join(name for _, _, name in cols) + " |", "|---|---:|" + "---:|" * len(cols)]
    for db in sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0)):
        r = results[db]
        cells = []
        for pair, sh, _ in cols:
            v = measure_of(r, pair, sh, axis)
            mark = ""
            if pair != "dolt" and axis == "bytes":
                u = ((r.get("pairs") or {}).get(pair) or {}).get(test_of(pair, sh)) or {}
                if u.get("settled") is False and u.get("footprint_bytes"):
                    v, mark = u["footprint_bytes"], UNSETTLED
            cells.append(((human(v) if axis == "bytes" else seconds(v)) + mark) if v else "—")
        L.append(f"| `{db}` | {rows_of(r):,} | " + " | ".join(cells) + " |")
    return "\n".join(L)
