#!/usr/bin/env python3
"""Draw the results. Reads build/results.json, writes PNGs into docs/img/.

  .venv/bin/python scripts/charts.py

matplotlib, deliberately: a Python library like the rest of the pipeline, no browser or JavaScript
toolchain, and it writes a PNG that can be committed and shown inline in a README. A chart that
needs a build step to look at is a chart nobody looks at.

**Every figure covers every test and every database.** An earlier version drew each figure over
whichever databases happened to have that measurement, so one chart covered 21 databases, another 11
and a third 9, under titles that did not say so — bars of different populations standing side by
side. Now the database list is the same everywhere, a test with no result for a database leaves a
visible gap, and each figure states its coverage. If a bar is missing, the measurement is missing,
and that is the honest thing for the picture to say.

The figures, each covering every pair -- MySQL and Dolt, PostgreSQL and DoltgreSQL, SQLite and
DoltLite -- and every database:

  cost-by-mode         both axes totalled, one bar per load, one row of panels per pair
  disk-by-database     what each database costs on disk in all five loads, one panel per pair
  time-by-database     the same in time
  ratio-by-database    disk as a ratio of the pair's own baseline, so the crossover is visible
  index-policy-<pair>  the row-by-row loads with the indexes dropped and with them maintained
  memory-by-history    what each Dolt engine needs to open a store, against rows and commits

Where a load was cheap enough to repeat, its bar carries a whisker spanning every sample. A bar
without one was measured once, which the figure says by leaving it off rather than by drawing a
whisker of zero length.
"""
import json, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "docs", "img")
MB = 1024 * 1024

INK, GRID = "#22252a", "#cfd4dc"
# the five loads, in the order they are always drawn
TESTS = ["mysql", "mysql_rowwise", "dolt_oneshot", "dolt_rowinsert", "dolt_rowcommit"]
# Categorical hues in fixed slot order, and they are checked rather than chosen by eye. The palette
# these replaced failed a colour-vision check outright: its green and its orange -- Dolt's one-commit
# and one-shot loads, drawn as adjacent bars -- came out 4.5 apart under protanopia, which is to say
# indistinguishable to a red-green colourblind reader looking at the two bars this chart exists to
# compare. These five pass every check; the three that sit under 3:1 against white are relieved by
# the report carrying every number as a table.
COLOURS = {"mysql": "#2a78d6", "mysql_rowwise": "#eb6834", "dolt_oneshot": "#1baf7a",
           "dolt_rowinsert": "#eda100", "dolt_rowcommit": "#e87ba4"}
LABELS = {"mysql": "MySQL — extended INSERTs",
          "mysql_rowwise": "MySQL — one INSERT per row",
          "dolt_oneshot": "Dolt — one commit per database",
          "dolt_rowinsert": "Dolt — one INSERT per row, one commit",
          "dolt_rowcommit": "Dolt — one commit per row"}
SHORT = {"mysql": "MySQL\nextended", "mysql_rowwise": "MySQL\n1 INSERT/row",
         "dolt_oneshot": "Dolt\n1 commit/db", "dolt_rowinsert": "Dolt\n1 INSERT/row",
         "dolt_rowcommit": "Dolt\n1 commit/row"}

# The same three row-by-row loads run a second time with every secondary index and constraint left
# in place for the whole load. They are a comparison of one variable against the five tests above,
# not five more tests, so they get their own figure instead of seven bars per database.
POLICY_TESTS = ["mysql_rowwise", "dolt_rowinsert", "dolt_rowcommit"]
# Diverging, because the question is a polarity: does keeping the indexes cost more or less than
# dropping them? Warm and cool poles with a neutral midpoint, so "no difference" reads as nothing.
POLICY_MORE, POLICY_LESS, POLICY_NONE = "#e34948", "#2a78d6", "#c9c7c2"


def bar_label(v):
    """A value written beside its bar: compact enough to fit, exact enough to be worth reading."""
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 10:
        return f"{v:.0f}"
    if v >= 1:
        return f"{v:.1f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def plain_number(v, _=None):
    """A tick label people read as a number.

    A log axis defaults to 10^3, 10^4 and so on, which is compact and which most readers have to
    convert in their heads before the chart means anything. These are quantities -- megabytes,
    seconds, rows -- so they are written as quantities, with thousands separators above one and
    without trailing zeros below it."""
    if v <= 0:
        return ""
    if v >= 1:
        return f"{v:,.0f}"
    return f"{v:g}".rstrip("0").rstrip(".") if v < 1 else f"{v:g}"


def log_axis(ax, which="x"):
    """Label a log axis with real numbers rather than powers of ten.

    Decades only. Labelling the 2x and 5x between them as well was the first attempt and it made the
    top of the scale unreadable -- "10,000 20,000 50,000 100,000" runs together in the width those
    four labels have. The values themselves go on the bars instead, which is what a reader wanting
    an exact figure is actually after."""
    axis = ax.xaxis if which == "x" else ax.yaxis
    axis.set_major_formatter(FuncFormatter(plain_number))
    axis.set_minor_formatter(FuncFormatter(lambda *_: ""))


def style(ax, title, xlabel, pad=12):
    ax.set_title(title, color=INK, fontsize=12, pad=pad, loc="left", fontweight="bold")
    ax.set_xlabel(xlabel, color=INK, fontsize=9)
    ax.tick_params(colors=INK, labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.grid(axis="x", color=GRID, linewidth=.6, alpha=.7)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(os.path.join(IMG, name), dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  . {os.path.relpath(os.path.join(IMG, name), ROOT)}")


def load(path=None):
    with open(path or os.path.join(ROOT, "build", "results.json"), encoding="utf-8") as fh:
        return json.load(fh)


def value(r, test, axis, policy="deferred"):
    """One measurement, or None. `axis` is 'bytes' or 'seconds'.

    `policy` picks between the row-by-row loads that dropped their secondary indexes for the load
    and the ones that kept them. It has no meaning for the one-shot loads, which are unaffected."""
    sfx = "_inline" if policy == "inline" else ""
    if test == "mysql":
        return r.get("mysql_disk_bytes") if axis == "bytes" else r.get("mysql_load_seconds")
    if test == "mysql_rowwise":
        return (r.get(f"mysql_rowwise_bytes{sfx}") if axis == "bytes"
                else r.get(f"mysql_rowwise_seconds{sfx}"))
    m = (r.get("modes", {}) or {}).get(test.replace("dolt_", "") + sfx, {}) or {}
    return m.get("disk_bytes") if axis == "bytes" else m.get("total_seconds")


def samples(r, test, axis, policy="deferred"):
    """Every repeat of one measurement, or None when it was measured once.

    A load cheap enough to repeat carries its own spread, and the figures draw it as a whisker. The
    expensive loads are single samples and get no whisker, which is the honest distinction: an
    unrepeated number is not a number that repeated well."""
    sfx = "_inline" if policy == "inline" else ""
    key = "bytes_all" if axis == "bytes" else "seconds_all"
    if test.startswith("dolt_"):
        m = (r.get("modes", {}) or {}).get(test.replace("dolt_", "") + sfx, {}) or {}
        got = m.get(key)
    else:
        spread = r.get("mysql_spread" if test == "mysql" else f"mysql_rowwise_spread{sfx}") or {}
        got = spread.get(key)
    return got if got and len(got) > 1 else None


def whisker(r, test, axis, policy, scale, centre):
    """(lower, upper) error-bar lengths around `centre`, or None."""
    xs = samples(r, test, axis, policy)
    if not xs:
        return None
    lo, hi = min(xs) / scale, max(xs) / scale
    return [[max(0.0, centre - lo)], [max(0.0, hi - centre)]]


def coverage(results, axis):
    """How many of the databases each test has a measurement for."""
    return {t: sum(1 for r in results.values() if value(r, t, axis)) for t in TESTS}


def caption(results, axis):
    cov = coverage(results, axis)
    n = len(results)
    missing = {t: n - c for t, c in cov.items() if c < n}
    if not missing:
        return f"all {n} databases, all five loads"
    return (f"{n} databases; a gap means that load has no result yet — "
            + ", ".join(f"{LABELS[t].split(' — ')[0]} {LABELS[t].split(' — ')[1]}: {cov[t]}/{n}"
                        for t in missing))


# ------------------------------------------------------------------- the three pairs ---
PAIR_TESTS = {"pg": ["postgres", "postgres_rowwise", "doltgres_oneshot", "doltgres_rowinsert", "doltgres_rowcommit"],
              "lite": ["sqlite", "sqlite_rowwise", "doltlite_oneshot", "doltlite_rowinsert", "doltlite_rowcommit"]}
PAIR_SHORT = {"postgres": "PostgreSQL\nCOPY", "postgres_rowwise": "PostgreSQL\n1 INSERT/row",
              "doltgres_oneshot": "DoltgreSQL\n1 commit/db", "doltgres_rowinsert": "DoltgreSQL\n1 INSERT/row",
              "doltgres_rowcommit": "DoltgreSQL\n1 commit/row",
              "sqlite": "SQLite\none transaction", "sqlite_rowwise": "SQLite\n1 INSERT/row",
              "doltlite_oneshot": "DoltLite\n1 commit/db", "doltlite_rowinsert": "DoltLite\n1 INSERT/row",
              "doltlite_rowcommit": "DoltLite\n1 commit/row"}
PAIR_TITLES = {"pg": "PostgreSQL and DoltgreSQL", "lite": "SQLite and DoltLite"}

# Every figure draws the three pairs the same way: five loads in the same order and the same colours
# -- the baseline in bulk, the baseline one row at a time, and the Dolt engine one commit per
# database, one INSERT per row, one commit per row -- so a colour means a shape wherever it appears.
PAIRS = {
    "dolt": {"title": "MySQL and Dolt", "tests": TESTS, "baseline": "mysql", "baseline_label": "the size MySQL uses",
             "labels": LABELS, "short": SHORT, "rows": lambda r: r.get("rows_mysql") or 0},
    "pg": {"title": PAIR_TITLES["pg"], "tests": PAIR_TESTS["pg"], "baseline": "postgres",
           "baseline_label": "the size PostgreSQL uses",
           "labels": {"postgres": "PostgreSQL — COPY", "postgres_rowwise": "PostgreSQL — one INSERT per row",
                      "doltgres_oneshot": "DoltgreSQL — one commit per database",
                      "doltgres_rowinsert": "DoltgreSQL — one INSERT per row, one commit",
                      "doltgres_rowcommit": "DoltgreSQL — one commit per row"},
           "short": {t: PAIR_SHORT[t] for t in PAIR_TESTS["pg"]},
           "rows": lambda r: ((r.get("pairs") or {}).get("source_rows") or {}).get("pg") or r.get("rows_mysql") or 0},
    "lite": {"title": PAIR_TITLES["lite"], "tests": PAIR_TESTS["lite"], "baseline": "sqlite",
             "baseline_label": "the size SQLite uses",
             "labels": {"sqlite": "SQLite — one transaction", "sqlite_rowwise": "SQLite — one INSERT per row",
                        "doltlite_oneshot": "DoltLite — one commit per database",
                        "doltlite_rowinsert": "DoltLite — one INSERT per row, one commit",
                        "doltlite_rowcommit": "DoltLite — one commit per row"},
             "short": {t: PAIR_SHORT[t] for t in PAIR_TESTS["lite"]},
             "rows": lambda r: ((r.get("pairs") or {}).get("source_rows") or {}).get("lite") or r.get("rows_mysql") or 0},
}
PAIR_ORDER = ["dolt", "pg", "lite"]


def colour_of(pair, test):
    """The colour of a load is its position in the pair's five, so the same shape has the same colour."""
    return COLOURS[TESTS[PAIRS[pair]["tests"].index(test)]]


def measure(r, pair, test, axis, policy="deferred"):
    """One measurement of any pair, or None: the settled size, or the load plus its settle step."""
    if pair == "dolt":
        return value(r, test, axis, policy)
    per_row = test != PAIRS[pair]["baseline"] and "oneshot" not in test
    key = test + ("_inline" if policy == "inline" and per_row else "")
    u = ((r.get("pairs") or {}).get(pair) or {}).get(key)
    if not u:
        return None
    if axis == "bytes":
        return u.get("disk_bytes")
    return u.get("load_seconds") if test in ("postgres", "sqlite") else u.get("total_seconds")


def spread(r, pair, test, axis, policy="deferred"):
    """Every repeat of a measurement, or None when it was measured once; the pairs' units are single samples."""
    return samples(r, test, axis, policy) if pair == "dolt" else None


def pair_coverage(results, pair, axis):
    return {t: sum(1 for r in results.values() if measure(r, pair, t, axis)) for t in PAIRS[pair]["tests"]}


def pair_caption(results, pair, axis):
    cov = pair_coverage(results, pair, axis)
    n = len(results)
    missing = {t: n - c for t, c in cov.items() if c < n}
    if not missing:
        return f"all {n} databases, all five loads"
    return (f"{n} databases; a gap means that load has no result — "
            + ", ".join(f"{PAIRS[pair]['labels'][t]}: {cov[t]}/{n}" for t in missing))


def order(results):
    return sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0))


def fig_by_database(results, axis, name, title, xlabel, scale):
    """One panel per pair, the same databases in the same order down every panel, five bars each:
    what every database costs in every load of every pair. Values sit past each bar because on a
    log axis the bar length deceives; the tables carry them all."""
    dbs = order(results)
    fig, axes = plt.subplots(1, 3, figsize=(19, 0.72 * len(dbs) + 2.6), sharey=True)
    h = 0.16
    for ax, pair in zip(axes, PAIR_ORDER):
        meta = PAIRS[pair]
        for k, t in enumerate(meta["tests"]):
            vals, ys, errs = [], [], []
            for i, d in enumerate(dbs):
                v = measure(results[d], pair, t, axis)
                if v:
                    vals.append(v / scale)
                    ys.append(i + (2 - k) * h)
                    xs = spread(results[d], pair, t, axis)
                    errs.append([[max(0.0, v / scale - min(xs) / scale)], [max(0.0, max(xs) / scale - v / scale)]]
                                if xs else None)
            if vals:
                ax.barh(ys, vals, h, label=meta["labels"][t], color=colour_of(pair, t))
                for yy, vv, e in zip(ys, vals, errs):
                    at = vv
                    if e:
                        ax.errorbar(vv, yy, xerr=e, fmt="none", ecolor=INK, elinewidth=.8, capsize=1.6, alpha=.85)
                        at = vv + e[1][0]
                    ax.annotate(bar_label(vv), (at, yy), textcoords="offset points", xytext=(3, 0),
                                va="center", ha="left", fontsize=5.4, color=INK, alpha=.85)
        ax.set_xscale("log")
        log_axis(ax, "x")
        style(ax, meta["title"], xlabel, pad=50)
        ax.legend(fontsize=7, frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.008))
        ax.text(0, -0.04, pair_caption(results, pair, axis), transform=ax.transAxes, fontsize=7, color=INK, alpha=.75)
    axes[0].set_yticks(range(len(dbs)), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs], fontsize=7)
    fig.suptitle(title, fontsize=13, fontweight="bold", color=INK, x=.01, ha="left", y=1.0)
    fig.tight_layout()
    save(fig, name)


def fig_ratio(results):
    """Disk as a ratio of the pair's own baseline loaded from the same dump, one panel per pair."""
    dbs = order(results)
    fig, axes = plt.subplots(1, 3, figsize=(19, 0.62 * len(dbs) + 2.6), sharey=True)
    h = 0.2
    for ax, pair in zip(axes, PAIR_ORDER):
        meta = PAIRS[pair]
        tests = [t for t in meta["tests"] if t != meta["baseline"]]
        for k, t in enumerate(tests):
            vals, ys = [], []
            for i, d in enumerate(dbs):
                base, v = measure(results[d], pair, meta["baseline"], "bytes"), measure(results[d], pair, t, "bytes")
                if base and v:
                    vals.append(v / base)
                    ys.append(i + (1.5 - k) * h)
            if vals:
                ax.barh(ys, vals, h, label=meta["labels"][t], color=colour_of(pair, t))
        ax.axvline(1.0, color=colour_of(pair, meta["baseline"]), linewidth=1.4, linestyle="--")
        ax.text(1.08, len(dbs) - .35, meta["baseline_label"], fontsize=7.5, color=colour_of(pair, meta["baseline"]))
        ax.set_xscale("log")
        log_axis(ax, "x")
        style(ax, meta["title"], "left of the line is smaller than the baseline; right is larger (log scale)", pad=44)
        if ax.containers:
            ax.legend(fontsize=7, frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.006))
        ax.text(0, -0.04, pair_caption(results, pair, "bytes"), transform=ax.transAxes, fontsize=7, color=INK, alpha=.75)
    axes[0].set_yticks(range(len(dbs)), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs], fontsize=7)
    fig.suptitle("Disk used, as a ratio of each pair's baseline loaded from the same dump",
                 fontsize=13, fontweight="bold", color=INK, x=.01, ha="left", y=1.0)
    fig.tight_layout()
    save(fig, "ratio-by-database.png")


def fig_cost_by_mode(results):
    """Totals on both axes, one row of two panels per pair, over the databases where every load of
    that pair has a result, so the five bars of a row stand for one population."""
    fig, axes = plt.subplots(3, 2, figsize=(11.5, 12.6))
    for row, pair in enumerate(PAIR_ORDER):
        meta = PAIRS[pair]
        tests = meta["tests"]
        dbs = [d for d, r in results.items()
               if all(measure(r, pair, t, "bytes") and measure(r, pair, t, "seconds") is not None for t in tests)]
        rows = sum(meta["rows"](results[d]) for d in dbs)
        for ax, axis in zip(axes[row], ("bytes", "seconds")):
            if not dbs:
                ax.axis("off")
                ax.text(0.01, 0.5, f"{meta['title']}: no database has every load of the pair yet", fontsize=10,
                        color=INK, va="center")
                continue
            vals = [sum(measure(results[d], pair, t, axis) or 0 for d in dbs) for t in tests]
            base = vals[0] or 1
            shown = [v / MB for v in vals] if axis == "bytes" else vals
            bars = ax.bar([meta["short"][t] for t in tests], shown, color=[colour_of(pair, t) for t in tests], width=.62)
            for b, v, raw in zip(bars, shown, vals):
                tag = "" if raw == vals[0] else (f"\n{raw / base:.2f}×" if raw / base < 10 else f"\n{raw / base:.0f}×")
                text = f"{v:,.0f} MB" if axis == "bytes" else (f"{v:,.0f}s" if v < 3600 else f"{v / 3600:,.1f}h")
                ax.text(b.get_x() + b.get_width() / 2, max(v, 1e-3) * 1.08, text + tag, ha="center", fontsize=7.5,
                        color=INK, fontweight="bold")
            ax.set_yscale("log")
            log_axis(ax, "y")
            ax.set_ylabel("mebibytes on disk" if axis == "bytes" else "seconds to load", color=INK, fontsize=8.5)
            style(ax, (f"{meta['title']} — {len(dbs)} of {len(results)} databases, {rows:,} rows\ndisk"
                       if axis == "bytes" else "\ntime"), "")
            ax.grid(axis="x", visible=False)
            ax.grid(axis="y", color=GRID, linewidth=.6, alpha=.7)
            ax.set_ylim(top=max(shown) * 8, bottom=max(min(x for x in shown if x > 0) / 4, 1e-3))
            ax.tick_params(axis="x", labelsize=7)
    fig.suptitle("What each load costs, every pair, against its own baseline",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.0)
    fig.tight_layout()
    save(fig, "cost-by-mode.png")


def fig_index_policy(results, pair="dolt"):
    """What keeping the indexes during the load costs, as a change from dropping them.

    The question is a polarity -- more or less -- so the form is a diverging bar against a zero
    line, and the colour is a diverging pair with a neutral midpoint rather than two arbitrary
    hues. Absolute sizes and times for both policies are in the report's tables; drawing them
    here as paired bars on a log axis made a 47% difference look like nothing at all, which is
    the opposite of what the figure is for.

    The one-shot loads are absent because the policy does not apply to them: mysqldump's extended
    INSERTs build an index over batches either way, and the two policies produced byte-identical
    files."""
    meta = PAIRS[pair]
    policy_tests = [t for t in meta["tests"] if t != meta["baseline"] and "oneshot" not in t]
    dbs = order(results)
    if not any(measure(results[d], pair, t, "bytes", "inline") for d in dbs for t in policy_tests):
        print(f"  ! index-policy-{pair} skipped: no load has been measured with indexes left inline")
        return

    fig, axes = plt.subplots(2, 3, figsize=(14, 0.34 * len(dbs) + 3.2), sharey=True)
    for col, t in enumerate(policy_tests):
        for row, (axis, unit) in enumerate((("bytes", "disk"), ("seconds", "time"))):
            ax = axes[row][col]
            vals, ys, cols = [], [], []
            for i, d in enumerate(dbs):
                a = measure(results[d], pair, t, axis, "deferred")
                b = measure(results[d], pair, t, axis, "inline")
                if a and b:
                    pct = 100.0 * (b - a) / a
                    vals.append(pct)
                    ys.append(len(dbs) - 1 - i)
                    cols.append(POLICY_MORE if pct > 0.5 else POLICY_LESS if pct < -0.5 else POLICY_NONE)
            if vals:
                ax.barh(ys, vals, 0.66, color=cols)
                for yy, vv in sorted(zip(ys, vals), key=lambda z: -abs(z[1]))[:2]:
                    if abs(vv) >= 1:
                        ax.annotate(f"{vv:+.0f}%", (vv, yy), textcoords="offset points",
                                    xytext=(4 if vv >= 0 else -4, 0), va="center",
                                    ha="left" if vv >= 0 else "right", fontsize=7.5, color=INK, fontweight="bold")
                if max(abs(v) for v in vals) < 1:
                    ax.set_xlim(-1, 1)
            ax.axvline(0, color=INK, linewidth=1.1)
            ax.set_xlabel(f"% change in {unit} when the indexes are kept", color=INK, fontsize=8.5)
            ax.set_title(meta["labels"][t] if row == 0 else "", color=INK, fontsize=11, pad=10, loc="left",
                         fontweight="bold")
            ax.tick_params(colors=INK, labelsize=7)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(GRID)
            ax.grid(axis="x", color=GRID, linewidth=.6, alpha=.7)
            ax.set_axisbelow(True)
            if col == 0:
                ax.set_yticks(range(len(dbs)), [f"{d}  {results[d].get('rows_mysql', 0):,}" for d in dbs][::-1],
                              fontsize=6.5)

    n = len(dbs)
    covered = {t: sum(1 for d in dbs if measure(results[d], pair, t, "bytes", "inline")
                      and measure(results[d], pair, t, "bytes", "deferred")) for t in policy_tests}
    gaps = ", ".join(f"{meta['labels'][t]}: {c}/{n}" for t, c in covered.items() if c < n)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (POLICY_MORE, POLICY_LESS, POLICY_NONE)]
    axes[0][0].legend(handles, ["keeping them costs more", "keeping them costs less", "no difference"],
                      fontsize=8, frameon=False, ncol=3, loc="lower left", bbox_to_anchor=(0.0, 1.16))
    fig.suptitle(f"What maintaining the indexes during a row-by-row load costs, {meta['title']} — "
                 f"all {n} databases, against dropping them and rebuilding at the end",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.0)
    fig.text(.02, -0.014,
             (f"a missing bar means that load has no result yet — {gaps}" if gaps
              else f"every database has both policies for all {len(policy_tests)} loads")
             + ".  Absolute sizes and times for both policies are tabulated in the README and REPORT.md.",
             fontsize=7.5, color=INK, alpha=.75)
    fig.tight_layout()
    save(fig, f"index-policy-{pair}.png")


MEMORY_JSON = os.path.join(ROOT, "build", "memory.json")
MEMORY_PAIRS_JSON = os.path.join(ROOT, "build", "memory_pairs.json")
MEM_SERIES = {"oneshot": ("#2a78d6", "one commit per database"),
              "rowcommit": ("#eb6834", "one commit per row")}
MEM_MARKERS = {"dolt": ("o", "Dolt"), "doltgres": ("s", "DoltgreSQL"), "doltlite": ("^", "DoltLite")}


def memory_points(results):
    """{(engine, mode): [(rows, commits, megabytes or None)]} from the three memory studies. Dolt's
    study records rows and commits itself; the pairs' study records the ceiling only, so their rows
    come from the export and their commits from the unit that wrote the store."""
    pts = {}
    if os.path.exists(MEMORY_JSON):
        data = json.load(open(MEMORY_JSON, encoding="utf-8"))
        for mode in MEM_SERIES:
            pts[("dolt", mode)] = [(r.get("rows"), r.get("commits"), r.get("megabytes"))
                                   for r in (data.get(mode) or {}).values() if r.get("rows")]
    if os.path.exists(MEMORY_PAIRS_JSON):
        data = json.load(open(MEMORY_PAIRS_JSON, encoding="utf-8"))
        for engine, pair, test in (("doltgres", "pg", "doltgres"), ("doltlite", "lite", "doltlite")):
            for mode in MEM_SERIES:
                out = []
                for db, r in ((data.get(engine) or {}).get(mode) or {}).items():
                    unit = ((results.get(db, {}).get("pairs") or {}).get(pair) or {}).get(f"{test}_{mode}") or {}
                    rows = PAIRS[pair]["rows"](results.get(db, {}))
                    if rows:
                        out.append((rows, unit.get("commits"), r.get("megabytes")))
                pts[(engine, mode)] = out
    return pts


def fig_memory(results):
    """How much memory each Dolt engine needs to open a stored database and count its largest table,
    against rows and against commits: Dolt, DoltgreSQL and DoltLite, each in its one-commit and its
    one-commit-per-row form. Each point is the smallest ceiling a query survived on a ladder of
    container memory limits -- an upper bound at the ladder's granularity, not a measured peak. An
    open marker with an arrow is a store the study could not open at the top of its ladder."""
    pts = memory_points(results)
    if not pts:
        return
    tops = []
    for path in (MEMORY_JSON, MEMORY_PAIRS_JSON):
        if os.path.exists(path):
            data = json.load(open(path, encoding="utf-8"))
            for m in data.values():
                for r in (m.values() if isinstance(m, dict) else []):
                    if isinstance(r, dict):
                        tops += [r.get("ladder_top_mb") for r in (r.values() if "megabytes" not in r else [r]) if isinstance(r, dict) and r.get("ladder_top_mb")]
    top = max(tops or [8192])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
    for ax, xi, xlabel in ((axes[0], 0, "rows in the database"), (axes[1], 1, "commits in the store")):
        for (engine, mode), series in pts.items():
            colour, shape = MEM_SERIES[mode]
            marker, name = MEM_MARKERS[engine]
            xs = [(p[xi], p[2]) for p in series if p[xi]]
            ax.scatter([x for x, y in xs if y], [y for x, y in xs if y], s=44, color=colour, marker=marker,
                       label=f"{name}, {shape}", zorder=3, edgecolor="white", linewidth=.7)
            for x, _ in [(x, y) for x, y in xs if not y]:
                ax.scatter([x], [top], s=54, facecolors="none", edgecolors=colour, marker=marker, linewidth=1.5, zorder=3)
                ax.annotate("", xy=(x, top * 1.9), xytext=(x, top * 1.05),
                            arrowprops=dict(arrowstyle="-|>", color=colour, linewidth=1.3))
        ax.set_xscale("log")
        ax.set_yscale("log")
        log_axis(ax, "x")
        log_axis(ax, "y")
        style(ax, "", xlabel)
        if ax is axes[0]:
            ax.set_ylabel("memory the store needed to open and count (MiB, log scale)", color=INK, fontsize=9)
        ax.grid(axis="y", color=GRID, linewidth=.6, alpha=.7)
    axes[0].legend(fontsize=8, frameon=False, loc="upper left", ncol=2)
    fig.suptitle("What each Dolt engine's memory tracks: not the rows, the commits",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.01)
    fig.text(.02, -0.13,
             "Left: at the same row count the one-commit and the one-commit-per-row stores need very different\n"
             "memory, so rows do not predict it. Right: within each engine the two forms fall on one relationship\n"
             "against commits. A point is the smallest container memory limit a query survived, an upper bound at\n"
             "the ladder's granularity; an open marker with an arrow is a store the study could not open at the top\n"
             "of its ladder, and a store with no commit count recorded appears on the left only.",
             fontsize=8, color=INK, alpha=.8, linespacing=1.5)
    fig.tight_layout()
    save(fig, "memory-by-history.png")


ENGINE_COLOURS = {"dolt": "#1baf7a", "pg": "#5b6ee1", "lite": "#c0392b"}


def fig_headline(results):
    """The finding in one picture: for each way of writing the rows, what each Dolt engine costs as a
    multiple of its own baseline loaded in bulk, in disk and in time, totalled over the databases
    the pair has every load for. The three engines stand side by side, which the per-pair figures
    cannot show. The baseline's own row-by-row load is drawn too, as the grey bar, because writing
    one row at a time is expensive before any Dolt engine is involved."""
    from loads import PAIR_ORDER as order_, PAIRS as pairs_, SHAPES, complete, measure, test_of
    shapes = ["rowwise", "oneshot", "rowinsert", "rowcommit"]
    names = {"rowwise": "the baseline,\none INSERT per row", "oneshot": "one commit\nper database",
             "rowinsert": "one INSERT per row,\none commit", "rowcommit": "one commit\nper row"}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))
    w = 0.26
    for ax, axis in zip(axes, ("bytes", "seconds")):
        for k, pair in enumerate(order_):
            dbs = complete(results, pair)
            if not dbs:
                continue
            base = sum(measure(results[d], pair, test_of(pair, "bulk"), axis) or 0 for d in dbs) or 1
            xs, ys, cols = [], [], []
            for i, shape in enumerate(shapes):
                v = sum(measure(results[d], pair, test_of(pair, shape), axis) or 0 for d in dbs) / base
                xs.append(i + (k - 1) * w)
                ys.append(v)
                cols.append("#b8bcc4" if shape == "rowwise" else ENGINE_COLOURS[pair])
            bars = ax.bar(xs, ys, w, color=cols, label=f"{pairs_[pair]['engine']} ({len(dbs)} of {len(results)} databases)")
            for b, v in zip(bars, ys):
                ax.text(b.get_x() + b.get_width() / 2, v * 1.12, f"{v:.2f}×" if v < 10 else f"{v:,.0f}×", ha="center",
                        fontsize=7, color=INK, fontweight="bold")
        ax.axhline(1.0, color=INK, linewidth=1, linestyle="--")
        ax.text(len(shapes) - 0.55, 1.12, "the baseline, loaded in bulk", fontsize=7.5, color=INK, ha="right")
        ax.set_yscale("log")
        log_axis(ax, "y")
        ax.set_xticks(range(len(shapes)), [names[sh] for sh in shapes], fontsize=8)
        ax.set_ylabel(("disk" if axis == "bytes" else "time to load") + ", as a multiple of the baseline in bulk (log scale)",
                      color=INK, fontsize=8.5)
        style(ax, "Disk" if axis == "bytes" else "Time", "")
        ax.grid(axis="x", visible=False)
        ax.grid(axis="y", color=GRID, linewidth=.6, alpha=.7)
        ax.set_ylim(top=max(ax.get_ylim()[1], 1) * 4)
    handles = [plt.Rectangle((0, 0), 1, 1, color=ENGINE_COLOURS[p]) for p in order_] + [plt.Rectangle((0, 0), 1, 1, color="#b8bcc4")]
    labels = [f"{pairs_[p]['engine']} against {pairs_[p]['baseline']}" for p in order_] + ["the baseline itself, one INSERT per row"]
    axes[0].legend(handles, labels, fontsize=8, frameon=False, loc="upper left")
    fig.suptitle("What a Dolt engine costs against the database it stands in for, every engine side by side",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.02)
    fig.text(.02, -0.06, "Totals over the databases each pair has every load for; the grey bar is the baseline's own row-by-row "
             "load, the cost of writing one row at a time before any Dolt engine is involved.",
             fontsize=7.5, color=INK, alpha=.8)
    fig.tight_layout()
    save(fig, "headline.png")


SIX = [("dolt", "bulk", "MySQL", "#2a78d6"), ("pg", "bulk", "PostgreSQL", "#6aa6e8"), ("lite", "bulk", "SQLite", "#a9cbf2"),
       ("dolt", "oneshot", "Dolt", "#1baf7a"), ("pg", "oneshot", "DoltgreSQL", "#5b6ee1"), ("lite", "oneshot", "DoltLite", "#c0392b")]


def fig_sizes_by_engine(results):
    """Every database down, every engine across, in two panels: the standard load in all six engines
    (the baselines in bulk, the Dolt engines with one commit), and the commit-per-row load in the
    three Dolt engines. The place to compare one database's size across engines, which the per-pair
    figures cannot show."""
    from loads import PAIR_ORDER as order_, PAIRS as pairs_, measure, test_of
    dbs = order(results)
    fig, axes = plt.subplots(1, 2, figsize=(15, 0.62 * len(dbs) + 2.6), sharey=True)
    panels = [(axes[0], SIX, "the standard load:\nthe baselines in bulk, the Dolt engines with one commit"),
              (axes[1], [(p, "rowcommit", pairs_[p]["engine"], c) for p, c in zip(order_, ("#1baf7a", "#5b6ee1", "#c0392b"))],
               "one commit per row:\nthe three Dolt engines")]
    for ax, cols, title in panels:
        h = 0.8 / len(cols)
        for k, (pair, shape, name, colour) in enumerate(cols):
            vals, ys = [], []
            for i, d in enumerate(dbs):
                v = measure(results[d], pair, test_of(pair, shape), "bytes")
                if v:
                    vals.append(v / MB)
                    ys.append(i + (len(cols) / 2 - 0.5 - k) * h)
            if vals:
                ax.barh(ys, vals, h, label=name, color=colour)
                for yy, vv in zip(ys, vals):
                    ax.annotate(bar_label(vv), (vv, yy), textcoords="offset points", xytext=(3, 0), va="center",
                                ha="left", fontsize=5.4, color=INK, alpha=.85)
        ax.set_xscale("log")
        log_axis(ax, "x")
        style(ax, title, "mebibytes on disk (log scale)", pad=40)
        ax.legend(fontsize=7, frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.004))
    axes[0].set_yticks(range(len(dbs)), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs], fontsize=7)
    fig.suptitle("Disk used by every database in every engine", fontsize=13, fontweight="bold", color=INK, x=.01, ha="left", y=1.0)
    fig.text(.01, -0.012, "A missing bar is a load with no result; a DoltLite store that could not be collected is absent here "
             "and shown at its working footprint in the tables.", fontsize=7.5, color=INK, alpha=.75)
    fig.tight_layout()
    save(fig, "sizes-by-engine.png")


def main():
    # Figures rendered from anything other than the real results file go somewhere else. Passing a
    # path is for checking a new figure against fabricated full coverage without waiting hours for a
    # run -- and doing exactly that overwrote docs/img and put two commits of synthetic charts into
    # the repository, presented as the experiment's results. The output directory follows the input
    # so that cannot happen again.
    src = sys.argv[1] if len(sys.argv) > 1 else None
    out = IMG if src is None else os.path.join(ROOT, "build", "img-preview")
    globals()["IMG"] = out
    os.makedirs(out, exist_ok=True)
    if src:
        print(f"  ! rendering from {src}, so figures go to "
              f"{os.path.relpath(out, ROOT)}/ and not docs/img/")
    results = load(src)
    fig_headline(results)
    fig_sizes_by_engine(results)
    fig_cost_by_mode(results)
    fig_by_database(results, "bytes", "disk-by-database.png",
                    "Disk used, every database, every load, every pair", "mebibytes on disk (log scale)", MB)
    fig_by_database(results, "seconds", "time-by-database.png",
                    "Time to load, every database, every load, every pair", "seconds (log scale)", 1)
    fig_ratio(results)
    for pair in PAIR_ORDER:
        fig_index_policy(results, pair)
    fig_memory(results)
    for pair in PAIR_ORDER:
        for axis in ("bytes", "seconds"):
            cov = pair_coverage(results, pair, axis)
            gaps = {t: c for t, c in cov.items() if c < len(results)}
            if gaps:
                print(f"  ! {pair} {axis}: incomplete — " + ", ".join(f"{t} {c}/{len(results)}" for t, c in gaps.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
