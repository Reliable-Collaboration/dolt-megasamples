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

  headline              both axes totalled, every load of every pair, as a ratio of the baseline
  sizes-by-engine       every database in every engine, the standard load
  history-cost          what a commit per row costs against the bulk load, database by database
  index-policy-summary  what maintaining the indexes costs, one dot per engine and load
  index-policy-<pair>   the same, database by database, with the indexes dropped and maintained
  memory-by-history     what each Dolt engine needs to open a store, against its commits
  disk-by-database      what each database costs on disk in all five loads, one panel per pair
  time-by-database      the same in time

One colour per engine (the Okabe-Ito palette, distinguishable under every common colour-vision
deficiency) and one marker per load shape, the same in every figure; a title states what the figure
shows, computed from the same measurements it draws.
"""
import json, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
from matplotlib.ticker import FuncFormatter   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "docs", "img")
MB = 1024 * 1024

INK, GRID = "#22252a", "#cfd4dc"


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
    return f"{v:g}".rstrip("0").rstrip(".")


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
    path = path or os.path.join(ROOT, "build", "results.json")
    if not os.path.exists(path):
        return {}          # nothing measured yet: every figure says so and skips
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------- the code ---
# One colour code for the whole document: hue is the engine family, on the Okabe-Ito palette, which
# stays distinguishable under the three common colour-vision deficiencies. A load shape is never a
# hue: it is the panel a figure puts it in, or the marker.
from loads import PAIRS, PAIR_ORDER, SHAPES, SHAPE_LABELS, complete, measure, rows_of, test_of  # noqa: E402

ENGINE = {"MySQL": "#0072B2", "PostgreSQL": "#56B4E9", "SQLite": "#E69F00",
          "Dolt": "#009E73", "DoltgreSQL": "#D55E00", "DoltLite": "#CC79A7"}
BASELINE_OF = {p: PAIRS[p]["baseline"] for p in PAIR_ORDER}
DOLT_OF = {p: PAIRS[p]["engine"] for p in PAIR_ORDER}
MARKER = {"bulk": "o", "rowwise": "o", "oneshot": "o", "rowinsert": "D", "rowcommit": "s"}


def engine_of(pair, shape):
    return BASELINE_OF[pair] if shape in ("bulk", "rowwise") else DOLT_OF[pair]


def colour(pair, shape):
    return ENGINE[engine_of(pair, shape)]


def times(v):
    return f"{v:.2f}×" if v < 10 else f"{v:,.0f}×"


def order(results):
    return sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0))


def totals(results, pair, axis):
    """{shape: total} over the databases the pair has every load for, and how many."""
    dbs = complete(results, pair)
    return {sh: sum(measure(results[d], pair, test_of(pair, sh), axis) or 0 for d in dbs) for sh in SHAPES}, dbs


def dot_axes(ax, title, xlabel, pad=14, unit=None):
    style(ax, title, xlabel, pad=pad)
    ax.set_xscale("log")
    log_axis(ax, "x")
    if unit:
        unit_ticks(ax, unit)
    ax.grid(axis="y", visible=False)


# Tick positions in the units a reader uses. Sizes are plotted in mebibytes and times in seconds;
# a decade axis labelled "10,000" makes the reader convert before the chart means anything.
BYTE_TICKS = [(2 ** -6, "16 KiB"), (2 ** -4, "64 KiB"), (0.25, "256 KiB"), (1, "1 MiB"), (4, "4 MiB"), (16, "16 MiB"),
              (64, "64 MiB"), (256, "256 MiB"), (1024, "1 GiB"), (4096, "4 GiB"), (16384, "16 GiB"),
              (65536, "64 GiB"), (262144, "256 GiB"), (1048576, "1 TiB")]
TIME_TICKS = [(0.1, "0.1 s"), (1, "1 s"), (10, "10 s"), (60, "1 min"), (600, "10 min"), (3600, "1 h"),
              (36000, "10 h"), (360000, "100 h")]


def unit_ticks(ax, unit, which="x"):
    ticks = BYTE_TICKS if unit == "bytes" else TIME_TICKS
    axis = ax.xaxis if which == "x" else ax.yaxis
    lo, hi = (ax.get_xlim() if which == "x" else ax.get_ylim())
    chosen = [(v, l) for v, l in ticks if lo <= v <= hi]
    if len(chosen) < 2:  # a narrow axis (a preview of one database) takes the nearest tick either side
        below = [(v, l) for v, l in ticks if v < lo]
        above = [(v, l) for v, l in ticks if v > hi]
        chosen = below[-1:] + chosen + above[:1]
        if len(chosen) < 2:
            return           # the decade labels stay
        (ax.set_xlim if which == "x" else ax.set_ylim)(min(lo, chosen[0][0]), max(hi, chosen[-1][0]))
    if len(chosen) > 7:  # a wide axis keeps every other tick, so the labels stay evenly spaced
        chosen = chosen[1::2] if len(chosen) % 2 == 0 else chosen[::2]
    axis.set_major_locator(plt.FixedLocator([v for v, _ in chosen]))
    axis.set_major_formatter(FuncFormatter(lambda v, _: dict(chosen).get(v, "")))
    axis.set_minor_formatter(FuncFormatter(lambda *_: ""))


def name_extremes(ax, points, fmt, k=2, fontsize=7):
    """Label the k largest and k smallest values of a dot series with their database name."""
    if not points:
        return
    ranked = sorted(points, key=lambda p: p[0])
    for x, y, name in dict.fromkeys(ranked[:k] + ranked[-k:]):   # a short series is not named twice
        ax.annotate(f"{name} {fmt(x)}", (x, y), textcoords="offset points", xytext=(6, 0), va="center",
                    ha="left", fontsize=fontsize, color=INK, alpha=.9)


# ---------------------------------------------------------------------------- F1 headline ---
def fig_headline(results):
    """The finding in one figure: for each way of writing the rows, each Dolt engine's total against
    its baseline in bulk, as a dot on a log axis with the reference line at 1. Position, not length,
    carries the value, which is what a log scale needs."""
    if not results:
        print("  ! headline skipped: nothing measured yet")
        return
    shapes = ["rowwise", "oneshot", "rowinsert", "rowcommit"]
    names = {"rowwise": "the baseline itself,\none INSERT per row", "oneshot": "one commit\nper database",
             "rowinsert": "one INSERT per row,\none commit", "rowcommit": "one commit\nper row"}
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6), sharey=True)
    ratio = {}
    for ax, axis in zip(axes, ("bytes", "seconds")):
        for k, pair in enumerate(PAIR_ORDER):
            tot, dbs = totals(results, pair, axis)
            if not dbs:
                continue
            base = tot["bulk"] or 1
            for i, sh in enumerate(shapes):
                v = tot[sh] / base
                ratio[(axis, pair, sh)] = v
                y = len(shapes) - 1 - i + (1 - k) * 0.22
                ax.scatter([v], [y], s=64, color=colour(pair, sh), marker=MARKER[sh], zorder=3,
                           edgecolor="white", linewidth=.8)
                ax.annotate(times(v), (v, y), textcoords="offset points", xytext=(7, 0), va="center", ha="left",
                            fontsize=7.5, color=INK)
        ax.axvline(1.0, color=INK, linewidth=1, linestyle="--")
        ax.set_yticks(range(len(shapes)), [names[sh] for sh in reversed(shapes)], fontsize=8.5)
        dot_axes(ax, "disk" if axis == "bytes" else "time to load",
                 "as a multiple of the same engine's baseline loaded in bulk (log scale; 1 = the baseline)")
        lo, hi = ax.get_xlim()
        ax.set_xlim(lo, hi * 3)
    drawn = [p for p in PAIR_ORDER if ("bytes", p, "rowcommit") in ratio]
    rc = [ratio[("bytes", p, "rowcommit")] for p in drawn]
    rt = [ratio[("seconds", p, "rowcommit")] for p in drawn if ("seconds", p, "rowcommit") in ratio]
    where = "in every engine" if len(drawn) == len(PAIR_ORDER) else f"in {len(drawn)} of the {len(PAIR_ORDER)} engines"
    title = (f"A commit per row costs {min(rc):.0f} to {max(rc):.0f} times the baseline's disk and "
             f"{min(rt):,.0f} to {max(rt):,.0f} times its time, {where}") if rc and rt else "What each Dolt engine costs"
    fig.suptitle(title, fontsize=12.5, fontweight="bold", color=INK, x=.01, ha="left", y=1.04)
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=ENGINE[e], markersize=8)
               for e in [DOLT_OF[p] for p in drawn] + [BASELINE_OF[p] for p in drawn]]
    fig.legend(handles, [f"{DOLT_OF[p]} against {BASELINE_OF[p]}" for p in drawn] + [f"{BASELINE_OF[p]} itself" for p in drawn],
               fontsize=8, frameon=False, ncol=6, loc="lower center", bbox_to_anchor=(0.5, -0.06))
    cov = "; ".join(f"{DOLT_OF[p]}: {len(complete(results, p))} of {len(results)} databases" for p in PAIR_ORDER)
    once = ", ".join(f"{times(ratio[('bytes', p, 'oneshot')])} {BASELINE_OF[p]}'s" for p in drawn if ("bytes", p, "oneshot") in ratio)
    rw = [ratio[("seconds", p, "rowwise")] for p in drawn if ("seconds", p, "rowwise") in ratio]
    fig.text(.01, -0.14, f"Totals over the databases each pair has every load for ({cov}). "
             + (f"Loaded once and committed once, a Dolt engine's store is {once}; " if once else "")
             + (f"writing one row at a time costs a baseline {times(min(rw))} to {times(max(rw))} its bulk load in time "
                "before any Dolt engine is involved." if rw else ""),
             fontsize=7.5, color=INK, alpha=.85, wrap=True)
    fig.tight_layout()
    save(fig, "headline.png")


# ------------------------------------------------------------------- F2 every database, every engine ---
def fig_sizes_by_engine(results):
    """One row per database, a dot per engine on a shared log axis, one panel per run: the standard
    load and the one-INSERT-per-row load in all six engines, the commit-per-row load in the three Dolt
    engines -- every engine and every run on one page."""
    if not results:
        print("  ! sizes-by-engine skipped: nothing measured yet")
        return
    dbs = order(results)
    fig, axes = plt.subplots(1, 3, figsize=(18, 0.42 * len(dbs) + 2.6), sharey=True, gridspec_kw={"width_ratios": [1.15, 1, 1]})
    panels = [(axes[0], [(p, "bulk") for p in PAIR_ORDER] + [(p, "oneshot") for p in PAIR_ORDER],
               "the standard load:\nthe baselines in bulk, the Dolt engines with one commit"),
              (axes[1], [(p, "rowwise") for p in PAIR_ORDER] + [(p, "rowinsert") for p in PAIR_ORDER],
               "one INSERT per row:\nthe baselines and, with one commit, the Dolt engines"),
              (axes[2], [(p, "rowcommit") for p in PAIR_ORDER], "one commit per row:\nthe three Dolt engines")]
    for ax, cols, title in panels:
        for pair, sh in cols:
            xs, ys = [], []
            for i, d in enumerate(dbs):
                v = measure(results[d], pair, test_of(pair, sh), "bytes")
                if v:
                    xs.append(v / MB)
                    ys.append(len(dbs) - 1 - i)
            ax.scatter(xs, ys, s=40, color=colour(pair, sh), marker=MARKER[sh], zorder=3, edgecolor="white", linewidth=.6,
                       label=f"{engine_of(pair, sh)}")
        for i in range(len(dbs)):
            ax.axhline(len(dbs) - 1 - i, color=GRID, linewidth=.5, alpha=.6, zorder=1)
        dot_axes(ax, title, "on disk (log scale)", pad=34, unit="bytes")
        ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    axes[0].set_yticks(range(len(dbs)), [f"{d}  {results[d].get('rows_mysql', 0):,}" for d in dbs][::-1], fontsize=7.5)
    tot = {p: totals(results, p, "bytes") for p in PAIR_ORDER}
    sub = ", ".join(f"{times(tot[p][0]['oneshot'] / tot[p][0]['bulk'])} {BASELINE_OF[p]}'s" for p in PAIR_ORDER if tot[p][0]["bulk"])
    cov = "; ".join(f"{DOLT_OF[p]}: {len(tot[p][1])} of {len(results)}" for p in PAIR_ORDER if tot[p][0]["bulk"])
    fig.suptitle(f"Loaded once and committed once, a Dolt engine's store is {sub}, in total" if sub
                 else "Every database in every engine, one panel per run",
                 fontsize=12.5, fontweight="bold", color=INK, x=.01, ha="left", y=1.0)
    fig.text(.01, -0.01, "Databases in order of rows. A missing dot is a load with no result; DoltLite's uncollected store "
             "is absent here and shown at its working footprint in the tables."
             + (f" The title's totals are over the databases each pair has every load for ({cov})." if cov else ""),
             fontsize=7.5, color=INK, alpha=.8)
    fig.tight_layout()
    save(fig, "sizes-by-engine.png")


# -------------------------------------------------------------------------- F3 the cost of history ---
def fig_history_cost(results):
    """Each database's commit-per-row store and load against its baseline in bulk, three engines on a
    row, the reference line at 1, the extremes named: a deviation figure, which is what a ratio is."""
    dbs = order(results)
    if not any(measure(results[d], p, test_of(p, "rowcommit"), "bytes") and measure(results[d], p, test_of(p, "bulk"), "bytes")
               for d in dbs for p in PAIR_ORDER):
        print("  ! history-cost skipped: no commit-per-row load has been measured beside its baseline")
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 0.42 * len(dbs) + 2.4), sharey=True)
    span = {}
    for ax, axis in zip(axes, ("bytes", "seconds")):
        pts_all, per_pair = [], {}
        for pair in PAIR_ORDER:
            xs, ys, pts = [], [], []
            for i, d in enumerate(dbs):
                base = measure(results[d], pair, test_of(pair, "bulk"), axis)
                v = measure(results[d], pair, test_of(pair, "rowcommit"), axis)
                if base and v:
                    xs.append(v / base)
                    ys.append(len(dbs) - 1 - i)
                    pts.append((v / base, len(dbs) - 1 - i, d))
            ax.scatter(xs, ys, s=40, color=colour(pair, "rowcommit"), marker="s", zorder=3, edgecolor="white", linewidth=.6,
                       label=f"{DOLT_OF[pair]} against {BASELINE_OF[pair]}")
            pts_all += pts
            per_pair[pair] = pts
        span[axis] = (min(x for x, _, _ in pts_all), max(x for x, _, _ in pts_all)) if pts_all else (0, 0)
        for i in range(len(dbs)):
            ax.axhline(len(dbs) - 1 - i, color=GRID, linewidth=.5, alpha=.6, zorder=1)
        ax.axvline(1.0, color=INK, linewidth=1, linestyle="--")
        for pair, pts in per_pair.items():   # the largest and the smallest ratio of each engine, named
            name_extremes(ax, pts, times, k=1)
        dot_axes(ax, "disk" if axis == "bytes" else "time to load",
                 "one commit per row, as a multiple of the same engine's baseline in bulk (log scale)", pad=30)
        ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))
        lo, hi = ax.get_xlim()
        ax.set_xlim(lo, hi * 4)
    axes[0].set_yticks(range(len(dbs)), [f"{d}  {results[d].get('rows_mysql', 0):,}" for d in dbs][::-1], fontsize=7.5)
    fig.suptitle((f"Keeping a commit per row costs from {times(span['bytes'][0])} to {times(span['bytes'][1])} the disk of the "
                  f"same database loaded in bulk" + (f", and {times(span['seconds'][0])} to {times(span['seconds'][1])} the time"
                                                     if span["seconds"][1] else ""))
                 if span["bytes"][1] else "What a commit per row costs against the bulk load",
                 fontsize=12, fontweight="bold", color=INK, x=.01, ha="left", y=1.0)
    fig.text(.01, -0.01, "Databases in order of rows; each engine's largest and smallest ratio are named. DoltLite's "
             "uncollected store is absent here and shown at its working footprint in the tables.", fontsize=7.5, color=INK, alpha=.8)
    fig.tight_layout()
    save(fig, "history-cost.png")


# ------------------------------------------------------------------------ F4 index policy, summary ---
POLICY_NONE = "#c9c7c2"   # a change within half a percent either way: the bar has no direction to show


def policy_change(r, pair, shape, axis):
    a = measure(r, pair, test_of(pair, shape), axis, "deferred")
    b = measure(r, pair, test_of(pair, shape), axis, "inline")
    return 100.0 * (b - a) / a if a and b else None


def fig_index_policy_summary(results):
    """What keeping the indexes during a row-by-row load costs, the median change over the databases,
    every engine on one axis: the README's figure. The per-database figures are in the report."""
    if not results:
        print("  ! index-policy-summary skipped: nothing measured yet")
        return
    import statistics
    shapes = ["rowwise", "rowinsert", "rowcommit"]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.2), sharey=True)
    median = {}
    for ax, axis in zip(axes, ("bytes", "seconds")):
        for k, pair in enumerate(PAIR_ORDER):
            for i, sh in enumerate(shapes):
                vals = [policy_change(results[d], pair, sh, axis) for d in results]
                vals = [v for v in vals if v is not None]
                if not vals:
                    continue
                med = statistics.median(vals)
                median[(axis, pair, sh)] = med
                y = len(shapes) - 1 - i + (1 - k) * 0.22
                ax.plot([min(vals), max(vals)], [y, y], color=colour(pair, sh), linewidth=1.2, alpha=.45, zorder=2)
                ax.scatter([med], [y], s=64, color=colour(pair, sh), marker=MARKER[sh], zorder=3, edgecolor="white", linewidth=.8)
                ax.annotate(f"{med:+.0f}%", (med, y), textcoords="offset points", xytext=(8, 0), ha="left", va="center", fontsize=7, color=INK)
        ax.axvline(0, color=INK, linewidth=1)
        ax.set_yticks(range(len(shapes)), [SHAPE_LABELS[sh].replace("the baseline, ", "the baseline,\n") for sh in reversed(shapes)], fontsize=8.5)
        style(ax, "disk" if axis == "bytes" else "time to load",
              "% change with the indexes kept (dot: the median database; line: the range)")
        ax.grid(axis="y", visible=False)
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=ENGINE[e], markersize=8) for e in ENGINE]
    fig.legend(handles, list(ENGINE), fontsize=8, frameon=False, ncol=6, loc="lower center", bbox_to_anchor=(0.5, -0.05))
    rcs = [median[("bytes", p, "rowcommit")] for p in PAIR_ORDER if ("bytes", p, "rowcommit") in median]
    bls = [median[("bytes", p, "rowwise")] for p in PAIR_ORDER if ("bytes", p, "rowwise") in median]
    fig.suptitle((f"Maintaining the indexes on a commit-per-row load costs {min(rcs):.0f}% to {max(rcs):.0f}% more disk at the median "
                  f"database" + (f"; on the baselines' row-by-row load, {min(bls):+.0f}% to {max(bls):+.0f}%" if bls else ""))
                 if rcs else "What maintaining the indexes costs",
                 fontsize=12, fontweight="bold", color=INK, x=.01, ha="left", y=1.04)
    fig.tight_layout()
    save(fig, "index-policy-summary.png")


def fig_index_policy(results, pair="dolt"):
    """What keeping the indexes costs, database by database, for one pair: diverging bars against a
    zero line, which is the form a change from a reference takes. In the report."""
    meta = PAIRS[pair]
    shapes = ["rowwise", "rowinsert", "rowcommit"]
    dbs = order(results)
    if not any(measure(results[d], pair, test_of(pair, sh), "bytes", "inline") for d in dbs for sh in shapes):
        print(f"  ! index-policy-{pair} skipped: no load has been measured with indexes left inline")
        return
    fig, axes = plt.subplots(2, 3, figsize=(14, 0.34 * len(dbs) + 3.2), sharey=True)
    for col, sh in enumerate(shapes):
        for row, (axis, unit) in enumerate((("bytes", "disk"), ("seconds", "time"))):
            ax = axes[row][col]
            vals, ys, cols = [], [], []
            for i, d in enumerate(dbs):
                pct = policy_change(results[d], pair, sh, axis)
                if pct is not None:
                    vals.append(pct)
                    ys.append(len(dbs) - 1 - i)
                    cols.append(colour(pair, sh) if abs(pct) > 0.5 else POLICY_NONE)
            if vals:
                ax.barh(ys, vals, 0.66, color=cols)
                for yy, vv in sorted(zip(ys, vals), key=lambda z: -abs(z[1]))[:2]:
                    if abs(vv) >= 1:
                        ax.annotate(f"{vv:+.0f}%", (vv, yy), textcoords="offset points", xytext=(4 if vv >= 0 else -4, 0),
                                    va="center", ha="left" if vv >= 0 else "right", fontsize=7.5, color=INK, fontweight="bold")
                if max(abs(v) for v in vals) < 1:
                    ax.set_xlim(-1, 1)
            ax.axvline(0, color=INK, linewidth=1.1)
            ax.set_xlabel(f"% change in {unit} when the indexes are kept", color=INK, fontsize=8.5)
            ax.set_title(meta["labels"][test_of(pair, sh)] if row == 0 else "", color=INK, fontsize=11, pad=10, loc="left", fontweight="bold")
            ax.tick_params(colors=INK, labelsize=7)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(GRID)
            ax.grid(axis="x", color=GRID, linewidth=.6, alpha=.7)
            ax.set_axisbelow(True)
            if col == 0:
                ax.set_yticks(range(len(dbs)), [f"{d}  {results[d].get('rows_mysql', 0):,}" for d in dbs][::-1], fontsize=6.5)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (ENGINE[BASELINE_OF[pair]], ENGINE[DOLT_OF[pair]], POLICY_NONE)]
    axes[0][0].legend(handles, [BASELINE_OF[pair], DOLT_OF[pair], "within half a percent either way"],
                      fontsize=8, frameon=False, ncol=3, loc="lower left", bbox_to_anchor=(0.0, 1.16))
    fig.suptitle(f"What maintaining the indexes during a row-by-row load costs, {meta['title']}, database by database",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.0)
    fig.tight_layout()
    save(fig, f"index-policy-{pair}.png")


# ------------------------------------------------------------------------ F5 memory tracks commits ---
MEMORY_JSON = os.path.join(ROOT, "build", "memory.json")
MEMORY_PAIRS_JSON = os.path.join(ROOT, "build", "memory_pairs.json")


def memory_points(results):
    """{(engine, mode): [(rows, commits, megabytes or None, db, ladder top)]} from the three memory studies."""
    pts = {}
    if os.path.exists(MEMORY_JSON):
        data = json.load(open(MEMORY_JSON, encoding="utf-8"))
        for mode in ("oneshot", "rowcommit"):
            pts[("Dolt", mode)] = [(r.get("rows"), r.get("commits"), r.get("megabytes"), db, r.get("ladder_top_mb") or 16384)
                                   for db, r in (data.get(mode) or {}).items() if r.get("rows")]
    if os.path.exists(MEMORY_PAIRS_JSON):
        data = json.load(open(MEMORY_PAIRS_JSON, encoding="utf-8"))
        for engine, pair, test in (("DoltgreSQL", "pg", "doltgres"), ("DoltLite", "lite", "doltlite")):
            for mode in ("oneshot", "rowcommit"):
                out = []
                for db, r in ((data.get(test) or {}).get(mode) or {}).items():
                    unit = ((results.get(db, {}).get("pairs") or {}).get(pair) or {}).get(f"{test}_{mode}") or {}
                    rows = rows_of(results.get(db, {}), pair)
                    if rows:
                        out.append((rows, unit.get("commits"), r.get("megabytes"), db, r.get("ladder_top_mb") or 16384))
                pts[(engine, mode)] = out
    return pts


def fig_memory(results):
    """What each Dolt engine needs to open a stored database and count its largest table, against rows
    and against commits: the memory studies. A point is the smallest container ceiling a query
    survived, an upper bound at the ladder's granularity; an open marker with an arrow is a store the
    study could not open at the top of its ladder."""
    pts = memory_points(results)
    if not pts:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), sharey=True)
    unopened = False
    for ax, xi, xlabel in ((axes[0], 0, "rows in the database"), (axes[1], 1, "commits in the store")):
        for (engine, mode), series in pts.items():
            xs = [(p[xi], p[2], p[3], p[4]) for p in series if p[xi]]
            ax.scatter([x for x, y, _, _ in xs if y], [y for x, y, _, _ in xs if y], s=40, color=ENGINE[engine],
                       marker=MARKER["oneshot" if mode == "oneshot" else "rowcommit"],
                       label=f"{engine}, {'one commit per database' if mode == 'oneshot' else 'one commit per row'}",
                       zorder=3, edgecolor="white", linewidth=.6, alpha=.9)
            for x, _, name, top in [p for p in xs if not p[1]]:   # drawn at the top of the ladder it failed on
                unopened = True
                ax.scatter([x], [top], s=52, facecolors="none", edgecolors=ENGINE[engine], marker="s", linewidth=1.4, zorder=3)
                ax.annotate("", xy=(x, top * 1.9), xytext=(x, top * 1.05), arrowprops=dict(arrowstyle="-|>", color=ENGINE[engine], linewidth=1.2))
            if xi == 1 and mode == "rowcommit":
                for x, y, name, _ in sorted([p for p in xs if p[1]], key=lambda p: -p[1])[:1]:
                    ax.annotate(f"{name}", (x, y), textcoords="offset points", xytext=(-8, -10), ha="right", fontsize=7.5, color=ENGINE[engine])
        ax.set_xscale("log")
        ax.set_yscale("log")
        log_axis(ax, "x")
        log_axis(ax, "y")
        style(ax, "", xlabel)
        unit_ticks(ax, "bytes", which="y")
        ax.grid(axis="y", color=GRID, linewidth=.6, alpha=.7)
    axes[0].set_ylabel("memory the store needed to open and count (log scale)", color=INK, fontsize=9)
    axes[0].legend(fontsize=7.5, frameon=False, loc="upper left", ncol=2)
    # the title is what the study measured: the same database, the same rows, opened with one commit and
    # with a commit per row -- the largest ratio between the two, and in how many engines it exceeds one
    # a one-commit store's need is an upper bound at the ladder's first rung, so the ratio to the same
    # database's commit-per-row store is a lower bound: "at least", engine by engine
    worst = {}
    for engine in sorted({e for e, _ in pts}):
        once = {p[3]: p[2] for p in pts.get((engine, "oneshot"), []) if p[2]}
        each = {p[3]: p[2] for p in pts.get((engine, "rowcommit"), []) if p[2]}
        ratios = [each[d] / once[d] for d in once if d in each]
        if ratios:
            worst[engine] = max(ratios)
    fig.suptitle(f"Opening a commit-per-row store needs at least {min(worst.values()):.0f}× to {max(worst.values()):.0f}× the memory "
                 f"of the same database with one commit ({', '.join(f'{e} {v:.0f}×' for e, v in worst.items())})"
                 if worst else "What each Dolt engine needs to open a store",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.02)
    fig.text(.02, -0.08,
             "Left: at the same row count the one-commit and the one-commit-per-row stores of the same database need very different\n"
             "memory. Right: against commits the two forms fall on one rising relationship within each engine. A point is the\n"
             "smallest container memory limit a query survived, an upper bound at the ladder's granularity."
             + ("\nAn open square with an arrow is a store the study could not open at the top of its ladder, drawn at that top." if unopened else ""),
             fontsize=8, color=INK, alpha=.85, linespacing=1.5)
    fig.tight_layout()
    save(fig, "memory-by-history.png")


# ------------------------------------------------------------ the report's per-database figures ---
def fig_by_database(results, axis, name, xlabel):
    """Every database, every load, every pair, as dots on one shared log axis per pair: the report's
    full view. Hue is the engine, the marker is the load shape."""
    if not results:
        print(f"  ! {name} skipped: nothing measured yet")
        return
    dbs = order(results)
    fig, axes = plt.subplots(1, 3, figsize=(18, 0.42 * len(dbs) + 2.6), sharey=True)
    for ax, pair in zip(axes, PAIR_ORDER):
        for sh in SHAPES:
            xs, ys = [], []
            for i, d in enumerate(dbs):
                v = measure(results[d], pair, test_of(pair, sh), axis)
                if v:
                    xs.append(v / (MB if axis == "bytes" else 1))
                    ys.append(len(dbs) - 1 - i)
            ax.scatter(xs, ys, s=34, color=colour(pair, sh), marker=MARKER[sh], zorder=3, edgecolor="white", linewidth=.6,
                       label=PAIRS[pair]["labels"][test_of(pair, sh)])
        for i in range(len(dbs)):
            ax.axhline(len(dbs) - 1 - i, color=GRID, linewidth=.5, alpha=.6, zorder=1)
        dot_axes(ax, PAIRS[pair]["title"], xlabel, pad=44, unit=axis)
        ax.legend(fontsize=6.8, frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    axes[0].set_yticks(range(len(dbs)), [f"{d}  {results[d].get('rows_mysql', 0):,}" for d in dbs][::-1], fontsize=7.5)
    fig.suptitle(("Disk used" if axis == "bytes" else "Time to load") + " by every database in every load of every pair",
                 fontsize=12.5, fontweight="bold", color=INK, x=.01, ha="left", y=1.0)
    fig.tight_layout()
    save(fig, name)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    out = IMG if src is None else os.path.join(ROOT, "build", "img-preview")
    globals()["IMG"] = out
    os.makedirs(out, exist_ok=True)
    if src:
        print(f"  ! rendering from {src}, so figures go to {os.path.relpath(out, ROOT)}/ and not docs/img/")
    results = load(src)
    fig_headline(results)
    fig_sizes_by_engine(results)
    fig_history_cost(results)
    fig_index_policy_summary(results)
    for pair in PAIR_ORDER:
        fig_index_policy(results, pair)
    fig_memory(results)
    fig_by_database(results, "bytes", "disk-by-database.png", "on disk (log scale)")
    fig_by_database(results, "seconds", "time-by-database.png", "time to load (log scale)")
    for pair in PAIR_ORDER:
        for axis in ("bytes", "seconds"):
            gaps = {sh: sum(1 for d in results if measure(results[d], pair, test_of(pair, sh), axis)) for sh in SHAPES}
            gaps = {sh: c for sh, c in gaps.items() if c < len(results)}
            if gaps:
                print(f"  ! {pair} {axis}: incomplete — " + ", ".join(f"{sh} {c}/{len(results)}" for sh, c in gaps.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
