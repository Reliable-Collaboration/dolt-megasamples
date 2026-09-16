#!/usr/bin/env python3
"""The tables of the PostgreSQL/DoltgreSQL and SQLite/DoltLite pairs, from build/results.json.

Read by scripts/render.py through its block registry; nothing here is written by hand. Every
table is one population per row: a test with no result shows an em dash, and a totals row covers
only the databases that have every test.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import human, human_mb  # noqa: E402
from tables import TINT, grouped_table  # noqa: E402
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


def size_time(u, base, baseline=False):
    """A cell: the size, as a multiple of the bulk baseline where that is not the cell itself, then
    the time. A baseline load's time is its load time; a Dolt engine's is the load plus its settle
    step, the rule scripts/loads.py states."""
    t = u.get("load_seconds" if baseline else "total_seconds") if u else None
    if u and u.get("settled") is False and u.get("footprint_bytes"):
        return f"{shown(u)}<br>{seconds(t)}"
    if not u or not u.get("disk_bytes"):
        return "—"
    b = u["disk_bytes"]
    mark = UNSETTLED if u.get("settled") is False else ""
    if base and base.get("disk_bytes") and u is not base:
        return f"{cell(b, base['disk_bytes'])}{mark}<br>{seconds(t)}"
    return f"{human(b)}{mark}<br>{seconds(t)}"


def pair_table(results, pair, suffix=""):
    phases = PHASES[pair]
    data = units(results, pair)
    if not data:
        return f"*No {' / '.join(TITLES[pair])} unit has been measured yet.*"
    keys = [phases[0]] + [ph + suffix for ph in phases[1:]]
    rows = []
    for db in sorted(data, key=lambda d: -data[d]["__rows"]):
        m = data[db]
        base = m.get(phases[0]) or {}
        rows.append([f"`{db}`", f"{m['__rows']:,}"] + [size_time(m.get(k), base, baseline=k.replace(suffix, "") in phases[:2]) for k in keys])
    L = []
    full = [db for db in data if all((data[db].get(k) or {}).get("disk_bytes") for k in keys)
            and not any((data[db].get(k) or {}).get("settled") is False for k in keys)]
    if full:
        b = {k: sum(data[db][k]["disk_bytes"] for db in full) for k in keys}
        t = {k: sum((data[db][k].get("load_seconds" if k.replace(suffix, "") in phases[:2] else "total_seconds") or 0) for db in full)
             for k in keys}
        b0, t0 = b[keys[0]], max(t[keys[0]], 0.1)
        cells = [f"**{human(b0)}<br>{seconds(t0)}**"] + [
            f"**{b[k] / b0:.2f}×<br>{t[k] / t0:.0f}× time**" for k in keys[1:]]
        rows.append([f"**all {len(full)} with every test**", f"**{sum(data[db]['__rows'] for db in full):,}**"] + cells)
    baseline, engine = TITLES[pair]
    def sub(ph):   # "3. DoltgreSQL<br>1 commit/db" -> "3. 1 commit/db": the test number stays, the engine is the group
        num, rest = SHORT[ph].split("<br>")[0].split(". ", 1)[0], SHORT[ph].split("<br>")[1]
        return f"{num}. {rest}"
    groups = [(f"{baseline}<br><small>the baseline</small>", [(sub(ph), None) for ph in phases[:2]], None),
              (f"{engine}<br><small>the Dolt engine</small>",
               [(sub(ph), TINT["history"] if ph.endswith("rowcommit") else None) for ph in phases[2:]], TINT["commit"])]
    L.append(grouped_table([("database", "left"), ("rows", "right")], groups, rows))
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
            t = "load_seconds" if ph in phases[:2] else "total_seconds"   # the pair table's rule
            cells.append(f"{shown(d)} → {shown(i)}<br>"
                         f"{seconds(d.get(t)) if d else '—'} → {seconds(i.get(t)) if i else '—'}")
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
            for ph in PHASES[pair] + [x + "_inline" for x in PHASES[pair]]:
                u = data[db].get(ph)
                if not u:
                    continue
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
    ordering = {}
    for pair in PHASES:
        for db, m in units(results, pair).items():
            for ph, u in m.items():
                if isinstance(u, dict) and u.get("indexes_ordering_differs"):
                    ordering.setdefault((TITLES[pair][1], db), set()).update(u["indexes_ordering_differs"])
    if ordering:
        by_engine = {}
        for (engine, db), items in ordering.items():
            by_engine.setdefault(engine, []).append(f"`{db}` {len(items)}")
        L.append("\nRead back with a null ordering the source does not print, and otherwise identical -- recorded on the "
                 "unit as `indexes_ordering_differs`, not failed: "
                 + "; ".join(f"{engine}: {', '.join(sorted(v))} index(es)" for engine, v in sorted(by_engine.items())) + ".")
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


def refusals_summary(results):
    """One sentence for the README: how many views each engine refused, in how many databases, and
    why, counted from the units rather than typed. A refusal names its object ("VIEW: name: reason");
    a missing function is named by the engine ("function: 'x' not found"), anything else is counted
    as "other"."""
    import re
    counts = {}
    for pair in PHASES:
        data = units(results, pair)
        for db, m in data.items():
            seen = set()
            for ph, u in m.items():
                if not isinstance(u, dict):
                    continue
                for item in u.get("refused_objects") or []:
                    kind = item.split(":", 1)[0].strip().lower()
                    fn = re.search(r"function: '([^']+)' not found", item)
                    seen.add((kind, fn.group(1) if fn else "other", item))
                for item in u.get("indexes_refused") or []:
                    seen.add(("index", "other", item))
            engine = TITLES[pair][1]
            c = counts.setdefault(engine, {"dbs": set(), "kinds": {}})
            for kind, why, _ in seen:
                c["dbs"].add(db)
                c["kinds"].setdefault(kind, {}).setdefault(why, 0)
                c["kinds"][kind][why] += 1
    parts = []
    for engine in [TITLES[p][1] for p in PHASES]:
        c = counts.get(engine)
        if not c or not c["dbs"]:
            parts.append(f"{engine} refused nothing")
            continue
        kinds = []
        for kind, whys in sorted(c["kinds"].items()):
            n = sum(whys.values())
            reasons = [f"{k} over `{why}`" for why, k in sorted(whys.items()) if why != "other"]
            if whys.get("other"):
                reasons.append(f"{whys['other']} for {'other reasons' if whys['other'] > 1 else 'another reason'}")
            kinds.append(f"{n} {kind}{'s' if n != 1 else ''} in {len(c['dbs'])} database{'s' if len(c['dbs']) != 1 else ''}"
                         f" ({', '.join(reasons)})")
        parts.append(f"{engine} refused " + "; ".join(kinds))
    # the MySQL/Dolt pair: what the transform left out of Dolt's schema, from the report's own rows
    import report
    dolt = [i for i in report.rows(results) if (i["views_my"] - i["views_do"]) or (i["rout_my"] - i["rout_do"])]
    if dolt:
        views = sum(i["views_my"] - i["views_do"] for i in dolt)
        routines = sum(i["rout_my"] - i["rout_do"] for i in dolt)
        what = [f"{views} view{'s' if views != 1 else ''}" if views else "", f"{routines} routine{'s' if routines != 1 else ''}" if routines else ""]
        parts.append(f"Dolt's transform left out {' and '.join(w for w in what if w)} in {len(dolt)} database{'s' if len(dolt) != 1 else ''}"
                     " (cross-database views and stored routines it does not take, named in REPORT.md)")
    else:
        parts.append("Dolt's transform left nothing out")
    return "; ".join(parts) + "."


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
    from common import version_of
    stamped = study.get("_versions") or {}
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
    cells = [v for k, e in study.items() if not k.startswith("_") for m in e.values() for v in m.values()]
    tops = sorted({v.get("ladder_top_mb") for v in cells if v.get("ladder_top_mb")})
    exited = any(str(v.get("outcome", "")).startswith("exited") for v in cells)
    L.append("")
    note = (f"*Ceilings walked up to {', '.join(human_mb(t) for t in tops)}; a query that did not answer at the top is "
            f"\"could not open\" with what the probe saw.")
    if exited:
        note += (" `exited 1` is the image's entrypoint giving up after 300 s of start-up, not the memory ceiling: "
                 "DoltgreSQL scans every table when it opens a store, and a per-row-commit history of hundreds of "
                 "thousands of commits did not finish scanning in time.")
    stale = [f"{names[e]} (measured on {v}, the run is on {version_of(e)})" for e, v in sorted(stamped.items())
             if v != version_of(e)]
    if stale:
        note += " The study is not this run's for " + ", ".join(stale) + "; `make memory-pairs` measures it again."
    L.append(note + "*")
    return "\n".join(L)


# ------------------------------------------------------------- the findings, every engine at once ---
def findings_totals(results, axis):
    """Every engine side by side: each pair's five loads totalled over the databases where the pair
    has every load, as a size or a time and as a multiple of that pair's own baseline in bulk. The
    populations differ where a pair lacks a load of a database, so each column names its count."""
    from loads import PAIRS, PAIR_ORDER, SHAPES, SHAPE_LABELS, complete, rows_of
    cols, totals = [], {}
    for pair in PAIR_ORDER:
        dbs = complete(results, pair)
        rows = sum(rows_of(results[d], pair) for d in dbs)
        cols.append(f"{PAIRS[pair]['baseline']} / {PAIRS[pair]['engine']}<br>{len(dbs)} of {len(results)} databases, {rows:,} rows")
        totals[pair] = {shape: sum(measure_of(results[d], pair, shape, axis) or 0 for d in dbs) for shape in SHAPES}
    unit = "disk" if axis == "bytes" else "time to load"
    groups = [(c, [(unit, None), ("× baseline", TINT["ratio"])], None) for c in cols]
    rows = []
    for shape in SHAPES:
        who = "baseline" if shape in ("bulk", "rowwise") else "Dolt engine"
        row = [f"{SHAPE_LABELS[shape]} ({who})"]
        for pair in PAIR_ORDER:
            v, base = totals[pair][shape], totals[pair]["bulk"]
            if not base:            # a pair with no database complete: nothing to total, nothing to compare
                row += ["—", "—"]
                continue
            row.append(human(v) if axis == "bytes" else seconds(v))
            row.append("—" if shape == "bulk" else f"**{v / base:.2f}×**" if v / base < 10 else f"**{v / base:,.0f}×**")
        rows.append(row)
    return grouped_table([("load", "left")], groups, rows)


def measure_of(r, pair, shape, axis):
    from loads import measure, test_of
    return measure(r, pair, test_of(pair, shape), axis)


def sizes_all(results, axis="bytes"):
    """Every engine and every run in one grouped table: five column groups, one per run, the three
    engines of that run side by side under one label and one shade."""
    from loads import PAIRS, PAIR_ORDER, rows_of
    runs = [("bulk", "in bulk", "baseline", None), ("oneshot", "one commit per database", "engine", TINT["commit"]),
            ("rowwise", "one INSERT per row", "baseline", None), ("rowinsert", "one INSERT per row, one commit", "engine", TINT["commit"]),
            ("rowcommit", "one commit per row", "engine", TINT["history"])]
    groups = [(f"{label}<br><small>{'the baselines' if side == 'baseline' else 'the Dolt engines'}</small>",
               [(PAIRS[p][side], None) for p in PAIR_ORDER], tint) for _, label, side, tint in runs]
    rows = []
    for db in sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0)):
        r = results[db]
        row = [f"`{db}`", f"{rows_of(r):,}"]
        for sh, _, _, _ in runs:
            for p in PAIR_ORDER:
                v, mark = size_cell(r, p, sh)
                if axis == "seconds":
                    v = measure_of(r, p, sh, axis)
                row.append(((human(v) if axis == "bytes" else seconds(v)) + mark) if v is not None else "—")
        rows.append(row)
    return grouped_table([("database", "left"), ("rows", "right")], groups, rows)


def size_cell(r, pair, shape):
    """(bytes, mark) for one store: the measured size, or, for a store the engine could not collect,
    its working footprint marked †."""
    from loads import test_of
    v, mark = measure_of(r, pair, shape, "bytes"), ""
    if pair != "dolt":
        u = ((r.get("pairs") or {}).get(pair) or {}).get(test_of(pair, shape)) or {}
        if u.get("settled") is False and u.get("footprint_bytes"):
            v, mark = u["footprint_bytes"], UNSETTLED
    return v, mark


# ------------------------------------------------------------------ the served stack, for the README ---
def databases_table(results):
    """Every database with what it is (build/catalogue.json, copied from the corpus's own records by
    scripts/catalogue.py), its tables and rows. The sizes are their own block (sizes_all) so that
    neither table squeezes the other."""
    import json, os
    from common import ROOT
    from loads import PAIR_ORDER, PAIRS, rows_of
    try:
        what = json.load(open(os.path.join(ROOT, "build", "catalogue.json"), encoding="utf-8"))
    except (OSError, ValueError):
        what = {}
    order = sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0))
    L = ["| database | what it is | tables | rows |", "|---|---|---:|---:|"]
    for db in order:
        r = results[db]
        L.append(f"| `{db}` | {what.get(db, '')} | {r.get('tables') or 0:,} | {rows_of(r):,} |")
    return "\n".join(L)


def sizes_note(results):
    """One sentence under the disk grid: the largest database in the two Dolt shapes, so a reader does
    not take the served size for the only size."""
    from loads import PAIR_ORDER, PAIRS, rows_of
    order = sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0))
    big = results[order[0]]
    once = [size_cell(big, p, "oneshot") for p in PAIR_ORDER]
    each = [size_cell(big, p, "rowcommit") for p in PAIR_ORDER]
    if not (once[0][0] and each[0][0]):
        return ""
    others = "; ".join(f"{PAIRS[p]['engine']} {human(v)}{m}" for p, (v, m) in zip(PAIR_ORDER[1:], each[1:]) if v)
    return (f"*What a Dolt engine's store tracks is its commits, not its rows: `{order[0]}`, {rows_of(big):,} rows, is "
            f"{human(once[0][0])} in {PAIRS[PAIR_ORDER[0]]['engine']} with one commit and {human(each[0][0])} with a commit "
            f"per row" + (f" ({others})" if others else "") + ". The one-commit stores are what `make up` serves; "
            "[choosing what is served](#choosing-what-is-served) says how to serve the others.*")


def connect_table():
    """How to reach each served engine, in the words the landing page uses (scripts/console_page.py),
    so the README and the page cannot disagree about a port, an account or a client line."""
    import console_page
    code = {"client", "URL", "JDBC", "open", "copy one out"}
    import html
    engines = [(title.split(" (")[0], dict(rows)) for title, rows in console_page.CONNECT]
    keys = []
    for _, rows in engines:
        keys += [k for k in rows if k not in keys]
    L = ["| | " + " | ".join(name for name, _ in engines) + " |", "|---|" + "---|" * len(engines)]
    for k in keys:
        cells = []
        for _, rows in engines:
            v = rows.get(k)
            cells.append(("`" + v + "`" if k in code else html.escape(v, quote=False)) if v else "—")
        L.append(f"| {k} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def consoles_table():
    """The consoles as the landing page lists them, most coverage first, with the index page on top."""
    import console_page, html
    P = console_page.P
    L = ["| | address | browses | notes |", "|---|---|---|---|",
         f"| **console index** | **<http://127.0.0.1:{P['console']}/>** | every engine | **start here**: how to connect your own "
         "tool, the consoles by what each can open, and every database with what it is and its size in each engine, "
         "generated from the measurements and the running stack |"]
    for name, port, cover, note in console_page.CONSOLES:
        L.append(f"| {name} | <http://127.0.0.1:{port}/> | {cover} | {html.escape(note, quote=False)} |")
    return "\n".join(L)


def memory_grid(results):
    """Every database down, the three Dolt engines across, each with the store of one commit and the
    store of a commit per row: the smallest container memory limit at which the engine opened the
    stored database and counted its largest table, from the two memory studies (build/memory.json for
    Dolt, build/memory_pairs.json for DoltgreSQL and DoltLite). A dash is a shape not measured; "did
    not open" is a store that failed at the top of its ladder."""
    import json, os
    from common import ROOT, human_mb
    from loads import PAIR_ORDER, PAIRS, rows_of
    studies = {}
    p = os.path.join(ROOT, "build", "memory.json")
    if os.path.exists(p):
        studies["Dolt"] = {k: v for k, v in json.load(open(p, encoding="utf-8")).items() if not k.startswith("_")}
    p = os.path.join(ROOT, "build", "memory_pairs.json")
    if os.path.exists(p):
        pairs = json.load(open(p, encoding="utf-8"))
        studies["DoltgreSQL"] = pairs.get("doltgres") or {}
        studies["DoltLite"] = pairs.get("doltlite") or {}
    engines = [PAIRS[pr]["engine"] for pr in PAIR_ORDER if PAIRS[pr]["engine"] in studies]
    if not engines:
        return "*No memory study yet (`make memory-pairs`, `scripts/memory_profile.py`).*"

    def cell(engine, mode, db):
        c = (studies[engine].get(mode) or {}).get(db)
        if not c:
            return "—"
        if c.get("megabytes"):
            return human_mb(c["megabytes"])
        return f"did not open at {human_mb(c['ladder_top_mb'])}" if c.get("ladder_top_mb") else "did not open"

    groups = [(engine, [("one commit", None), ("one commit per row", TINT["history"])], TINT["commit"]) for engine in engines]
    rows = []
    for db in sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0)):
        rows.append([f"`{db}`", f"{rows_of(results[db]):,}"]
                    + [cell(engine, mode, db) for engine in engines for mode in ("oneshot", "rowcommit")])
    return grouped_table([("database", "left"), ("rows", "right")], groups, rows)
