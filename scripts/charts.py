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
"""
import json, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "docs", "img")
MB = 1024 * 1024

INK, GRID = "#22252a", "#cfd4dc"
# the five loads, in the order they are always drawn
TESTS = ["mysql", "mysql_rowwise", "dolt_oneshot", "dolt_rowinsert", "dolt_rowcommit"]
COLOURS = {"mysql": "#4c72b0", "mysql_rowwise": "#8fa9d4", "dolt_oneshot": "#dd8452",
           "dolt_rowinsert": "#55a868", "dolt_rowcommit": "#c44e52"}
LABELS = {"mysql": "MySQL — extended INSERTs",
          "mysql_rowwise": "MySQL — one INSERT per row",
          "dolt_oneshot": "Dolt — one commit per database",
          "dolt_rowinsert": "Dolt — one INSERT per row, one commit",
          "dolt_rowcommit": "Dolt — one commit per row"}
SHORT = {"mysql": "MySQL\nextended", "mysql_rowwise": "MySQL\n1 INSERT/row",
         "dolt_oneshot": "Dolt\n1 commit/db", "dolt_rowinsert": "Dolt\n1 INSERT/row",
         "dolt_rowcommit": "Dolt\n1 commit/row"}


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
    print(f"  . {os.path.join('docs/img', name)}")


def load():
    with open(os.path.join(ROOT, "build", "results.json"), encoding="utf-8") as fh:
        return json.load(fh)


def value(r, test, axis):
    """One measurement, or None. `axis` is 'bytes' or 'seconds'."""
    if test == "mysql":
        return r.get("mysql_disk_bytes") if axis == "bytes" else r.get("mysql_load_seconds")
    if test == "mysql_rowwise":
        return r.get("mysql_rowwise_bytes") if axis == "bytes" else r.get("mysql_rowwise_seconds")
    m = (r.get("modes", {}) or {}).get(test.replace("dolt_", ""), {}) or {}
    return m.get("disk_bytes") if axis == "bytes" else m.get("total_seconds")


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
        vals, ys = [], []
        for i, d in enumerate(dbs):
            v = value(results[d], t, axis)
            if v:
                vals.append(v / scale)
                ys.append(i + (2 - k) * h)
        if vals:
            ax.barh(ys, vals, h, label=LABELS[t], color=COLOURS[t])
    ax.set_yticks(list(y), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs],
                  fontsize=7)
    ax.set_xscale("log")
    style(ax, title, xlabel, pad=30)
    ax.legend(fontsize=8, frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.005))
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
    ax.axvline(1.0, color=COLOURS["mysql"], linewidth=1.4, linestyle="--")
    ax.text(1.1, len(dbs) - .35, "the size MySQL uses", fontsize=8, color=COLOURS["mysql"])
    ax.set_yticks(list(y), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs],
                  fontsize=7)
    ax.set_xscale("log")
    style(ax, "Disk used, as a ratio of MySQL loaded from the same dump",
          "left of the line is smaller than MySQL; right of it is larger (log scale)", pad=30)
    ax.legend(fontsize=8, frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.005))
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
        ax.set_ylabel("megabytes on disk" if axis == "bytes" else "seconds to load",
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


def main():
    os.makedirs(IMG, exist_ok=True)
    results = load()
    by_database(results, "bytes", "disk-by-database.png",
                "Disk used, every database, every load", "megabytes on disk (log scale)", MB)
    by_database(results, "seconds", "time-by-database.png",
                "Time to load, every database, every load", "seconds (log scale)", 1)
    fig_ratio(results)
    fig_cost_by_mode(results)
    for axis in ("bytes", "seconds"):
        cov = coverage(results, axis)
        gaps = {t: c for t, c in cov.items() if c < len(results)}
        if gaps:
            print(f"  ! {axis}: incomplete — "
                  + ", ".join(f"{t} {c}/{len(results)}" for t, c in gaps.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
