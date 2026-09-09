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

Four figures:

  disk-by-database   what each database costs on disk, in all five loads
  time-by-database   what each database costs in time, in all five loads
  ratio-by-database  the same as a ratio against MySQL, so the crossover is visible
  cost-by-mode       both axes totalled, one bar per load
  index-policy       the row-by-row loads with the indexes dropped and with them maintained

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


def by_database(results, axis, name, title, xlabel, scale):
    dbs = sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0))
    fig, ax = plt.subplots(figsize=(10, 0.78 * len(dbs) + 2.2))
    h, y = 0.16, range(len(dbs))
    for k, t in enumerate(TESTS):
        vals, ys, errs = [], [], []
        for i, d in enumerate(dbs):
            v = value(results[d], t, axis)
            if v:
                vals.append(v / scale)
                ys.append(i + (2 - k) * h)
                errs.append(whisker(results[d], t, axis, "deferred", scale, v / scale))
        if vals:
            ax.barh(ys, vals, h, label=LABELS[t], color=COLOURS[t])
            for yy, vv, e in zip(ys, vals, errs):
                at = vv
                if e:
                    ax.errorbar(vv, yy, xerr=e, fmt="none", ecolor=INK, elinewidth=.8,
                                capsize=1.6, alpha=.85)
                    at = vv + e[1][0]      # past the upper whisker, not through it
                # The value itself, past the end of the bar. On a log axis the bar length is the
                # only cue to magnitude and it is a deceptive one -- a bar twice as long is ten
                # times the number -- so the figure is written out rather than left to be read off
                # a compressed scale.
                ax.annotate(bar_label(vv), (at, yy), textcoords="offset points", xytext=(4, 0),
                            va="center", ha="left", fontsize=5.6, color=INK, alpha=.85)
    ax.set_yticks(list(y), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs],
                  fontsize=7)
    ax.set_xscale("log")
    log_axis(ax, "x")
    style(ax, title, xlabel, pad=46)
    ax.legend(fontsize=8, frameon=False, ncol=3, loc="lower center",
              bbox_to_anchor=(0.5, 1.012))
    ax.text(0, -0.055, caption(results, axis), transform=ax.transAxes, fontsize=7.5,
            color=INK, alpha=.75)
    save(fig, name)


def fig_ratio(results):
    dbs = sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0))
    tests = [t for t in TESTS if t != "mysql"]
    fig, ax = plt.subplots(figsize=(10, 0.68 * len(dbs) + 2.2))
    h, y = 0.2, range(len(dbs))
    for k, t in enumerate(tests):
        vals, ys = [], []
        for i, d in enumerate(dbs):
            base, v = results[d].get("mysql_disk_bytes"), value(results[d], t, "bytes")
            if base and v:
                vals.append(v / base)
                ys.append(i + (1.5 - k) * h)
        if vals:
            ax.barh(ys, vals, h, label=LABELS[t], color=COLOURS[t])
    drew = bool(ax.containers)
    ax.axvline(1.0, color=COLOURS["mysql"], linewidth=1.4, linestyle="--")
    ax.text(1.1, len(dbs) - .35, "the size MySQL uses", fontsize=8, color=COLOURS["mysql"])
    ax.set_yticks(list(y), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs],
                  fontsize=7)
    ax.set_xscale("log")
    log_axis(ax, "x")
    style(ax, "Disk used, as a ratio of MySQL loaded from the same dump",
          "left of the line is smaller than MySQL; right of it is larger (log scale)", pad=30)
    if drew:
        ax.legend(fontsize=8, frameon=False, ncol=2, loc="lower center",
                  bbox_to_anchor=(0.5, 1.005))
    ax.text(0, -0.05, caption(results, "bytes"), transform=ax.transAxes, fontsize=7.5,
            color=INK, alpha=.75)
    save(fig, "ratio-by-database.png")


def fig_cost_by_mode(results):
    """Totals on both axes, over the databases where every load has a result, so the five bars
    stand for one population."""
    dbs = [d for d, r in results.items()
           if all(value(r, t, "bytes") and value(r, t, "seconds") is not None for t in TESTS)]
    if not dbs:
        print("  ! cost-by-mode skipped: no database has every measurement yet")
        return
    rows = sum(results[d].get("rows_mysql") or 0 for d in dbs)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    for ax, axis in zip(axes, ("bytes", "seconds")):
        vals = [sum(value(results[d], t, axis) or 0 for d in dbs) for t in TESTS]
        base = vals[0]
        shown = [v / MB for v in vals] if axis == "bytes" else vals
        bars = ax.bar([SHORT[t] for t in TESTS], shown, color=[COLOURS[t] for t in TESTS], width=.62)
        for b, v, raw in zip(bars, shown, vals):
            tag = "" if raw == base else (f"\n{raw / base:.2f}×" if raw / base < 10
                                          else f"\n{raw / base:.0f}×")
            text = f"{v:,.0f} MB" if axis == "bytes" else (f"{v:,.0f}s" if v < 3600
                                                           else f"{v / 3600:,.1f}h")
            ax.text(b.get_x() + b.get_width() / 2, v * 1.08, text + tag, ha="center", fontsize=8,
                    color=INK, fontweight="bold")
        ax.set_yscale("log")
        log_axis(ax, "y")
        ax.set_ylabel("mebibytes on disk" if axis == "bytes" else "seconds to load",
                      color=INK, fontsize=9)
        style(ax, "Disk" if axis == "bytes" else "Time", "")
        ax.grid(axis="x", visible=False)
        ax.grid(axis="y", color=GRID, linewidth=.6, alpha=.7)
        ax.set_ylim(top=max(shown) * 8)
        ax.tick_params(axis="x", labelsize=7.5)
    fig.suptitle(f"What each load costs — {len(dbs)} of {len(results)} databases, "
                 f"{rows:,} rows, against MySQL",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.03)
    fig.tight_layout()
    save(fig, "cost-by-mode.png")


def fig_index_policy(results):
    """What keeping the indexes during the load costs, as a change from dropping them.

    The question is a polarity -- more or less -- so the form is a diverging bar against a zero
    line, and the colour is a diverging pair with a neutral midpoint rather than two arbitrary
    hues. Absolute sizes and times for both policies are in the report's tables; drawing them
    here as paired bars on a log axis made a 47% difference look like nothing at all, which is
    the opposite of what the figure is for.

    The one-shot loads are absent because the policy does not apply to them: mysqldump's extended
    INSERTs build an index over batches either way, and the two policies produced byte-identical
    files."""
    dbs = sorted(results, key=lambda d: -(results[d].get("rows_mysql") or 0))
    if not any(value(results[d], t, "bytes", "inline") for d in dbs for t in POLICY_TESTS):
        print("  ! index-policy skipped: no load has been measured with indexes left inline")
        return

    fig, axes = plt.subplots(2, 3, figsize=(14, 0.34 * len(dbs) + 3.2), sharey=True)
    for col, t in enumerate(POLICY_TESTS):
        for row, (axis, unit) in enumerate((("bytes", "disk"), ("seconds", "time"))):
            ax = axes[row][col]
            vals, ys, cols = [], [], []
            for i, d in enumerate(dbs):
                a = value(results[d], t, axis, "deferred")
                b = value(results[d], t, axis, "inline")
                if a and b:
                    pct = 100.0 * (b - a) / a
                    vals.append(pct)
                    ys.append(len(dbs) - 1 - i)
                    cols.append(POLICY_MORE if pct > 0.5 else
                                POLICY_LESS if pct < -0.5 else POLICY_NONE)
            if vals:
                ax.barh(ys, vals, 0.66, color=cols)
                # Label only the extremes, so the eye goes to the result rather than to 126 numbers,
                # and offset them in points rather than in data units. A panel where every value is
                # zero -- which is exactly what Dolt's one-INSERT-per-row disk does -- autoscales to
                # a range of hundredths, and a label offset by 1.5 *data* units then sits thirty
                # axis-widths off the plot. `bbox_inches="tight"` duly grew the canvas to include
                # it, turning a 14-inch figure into a 50-inch one.
                for yy, vv in sorted(zip(ys, vals), key=lambda z: -abs(z[1]))[:2]:
                    if abs(vv) >= 1:
                        ax.annotate(f"{vv:+.0f}%", (vv, yy), textcoords="offset points",
                                    xytext=(4 if vv >= 0 else -4, 0), va="center",
                                    ha="left" if vv >= 0 else "right",
                                    fontsize=7.5, color=INK, fontweight="bold")
                # a panel with nothing to show should look like nothing, not like noise magnified
                if max(abs(v) for v in vals) < 1:
                    ax.set_xlim(-1, 1)
            ax.axvline(0, color=INK, linewidth=1.1)
            ax.set_xlabel(f"% change in {unit} when the indexes are kept", color=INK, fontsize=8.5)
            ax.set_title(LABELS[t] if row == 0 else "", color=INK, fontsize=11,
                         pad=10, loc="left", fontweight="bold")
            ax.tick_params(colors=INK, labelsize=7)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(GRID)
            ax.grid(axis="x", color=GRID, linewidth=.6, alpha=.7)
            ax.set_axisbelow(True)
            if col == 0:
                ax.set_yticks(range(len(dbs)),
                              [f"{d}  {results[d].get('rows_mysql', 0):,}" for d in dbs][::-1],
                              fontsize=6.5)

    n = len(dbs)
    covered = {t: sum(1 for d in dbs if value(results[d], t, "bytes", "inline")
                      and value(results[d], t, "bytes", "deferred")) for t in POLICY_TESTS}
    gaps = ", ".join(f"{LABELS[t]}: {c}/{n}" for t, c in covered.items() if c < n)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in
               (POLICY_MORE, POLICY_LESS, POLICY_NONE)]
    axes[0][0].legend(handles,
                      ["keeping them costs more", "keeping them costs less", "no difference"],
                      fontsize=8, frameon=False, ncol=3, loc="lower left",
                      bbox_to_anchor=(0.0, 1.16))
    fig.suptitle("What maintaining the indexes during a row-by-row load costs — "
                 f"all {n} databases, against dropping them and rebuilding at the end",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.0)
    fig.text(.02, -0.014,
             (f"a missing bar means that pair has no result yet — {gaps}" if gaps
              else f"every database has both policies for all {len(POLICY_TESTS)} loads")
             + ".  Absolute sizes and times for both policies are tabulated in REPORT.md.",
             fontsize=7.5, color=INK, alpha=.75)
    fig.tight_layout()
    save(fig, "index-policy.png")


MEMORY_JSON = os.path.join(ROOT, "build", "memory.json")
MEM_SERIES = {"oneshot": ("#2a78d6", "3 commits per database"),
              "rowcommit": ("#eb6834", "one commit per row")}


def fig_memory():
    """How much memory Dolt needs to open a database, against rows and against commits.

    Two panels, because the point is which of the two predicts it. The same 21 databases are stored
    both ways -- identical rows, identical schema, differing only in how much history they carry --
    so at a given row count the two series show what history costs, and at a given commit count they
    show whether anything else matters.

    Each point is the smallest ceiling a query survived on a ladder of container memory limits, so
    it is an upper bound at the ladder's granularity rather than a measured peak. An open marker
    with an arrow is a database still killed at the top of the ladder."""
    if not os.path.exists(MEMORY_JSON):
        return
    data = json.load(open(MEMORY_JSON, encoding="utf-8"))
    if not any(m in data for m in MEM_SERIES):
        return
    top = max((r.get("ladder_top_mb") or 8192) for m in data.values() for r in m.values())

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), sharey=True)
    for ax, xkey, xlabel in ((axes[0], "rows", "rows in the database"),
                             (axes[1], "commits", "commits in the repository")):
        for mode, (colour, label) in MEM_SERIES.items():
            pts = [(r.get(xkey), r.get("megabytes"))
                   for r in (data.get(mode) or {}).values() if r.get(xkey)]
            ax.scatter([x for x, y in pts if y], [y for x, y in pts if y], s=46, color=colour,
                       label=label, zorder=3, edgecolor="white", linewidth=.8)
            for x, _ in [(x, y) for x, y in pts if not y]:
                ax.scatter([x], [top], s=52, facecolors="none", edgecolors=colour,
                           linewidth=1.6, zorder=3)
                ax.annotate("", xy=(x, top * 1.9), xytext=(x, top * 1.05),
                            arrowprops=dict(arrowstyle="-|>", color=colour, linewidth=1.4))
                ax.text(x, top * 2.1, f"still killed\nat {top // 1024} GB", ha="center",
                        fontsize=7.5, color=colour, fontweight="bold")
        ax.set_xscale("log")
        ax.set_yscale("log")
        log_axis(ax, "x")
        log_axis(ax, "y")
        style(ax, "", xlabel)
        if ax is axes[0]:
            ax.set_ylabel("memory the database needed (MiB, log scale)", color=INK, fontsize=9)
        ax.grid(axis="y", color=GRID, linewidth=.6, alpha=.7)
    axes[0].legend(fontsize=9, frameon=False, loc="upper left")
    fig.suptitle("What Dolt's memory tracks: not the rows, the commits",
                 fontsize=12, fontweight="bold", color=INK, x=.02, ha="left", y=1.01)
    # Wrapped by hand. A single long line of figure text is included in the tight bounding box at
    # its full width, which turns a 12-inch figure into a 27-inch one.
    fig.text(.02, -0.16,
             "Left: at the same row count the two forms need very different memory, so rows do not\n"
             "predict it — the 3.9M-row database sits at the floor with 3 commits and will not open\n"
             "in 8 GB with one commit per row. Right: both forms fall on one relationship, so\n"
             "commits do predict it; that database is absent here only because reading its commit\n"
             "count requires opening it. Each point is the smallest container memory limit a query\n"
             "survived — an upper bound at the ladder's granularity, not a measured peak.",
             fontsize=8, color=INK, alpha=.8, linespacing=1.5)
    fig.tight_layout()
    save(fig, "memory-by-history.png")


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
    by_database(results, "bytes", "disk-by-database.png",
                "Disk used, every database, every load", "mebibytes on disk (log scale)", MB)
    by_database(results, "seconds", "time-by-database.png",
                "Time to load, every database, every load", "seconds (log scale)", 1)
    fig_ratio(results)
    fig_cost_by_mode(results)
    fig_index_policy(results)
    fig_memory()
    for axis in ("bytes", "seconds"):
        cov = coverage(results, axis)
        gaps = {t: c for t, c in cov.items() if c < len(results)}
        if gaps:
            print(f"  ! {axis}: incomplete — "
                  + ", ".join(f"{t} {c}/{len(results)}" for t, c in gaps.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
