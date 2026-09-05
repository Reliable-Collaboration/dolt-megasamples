#!/usr/bin/env python3
"""Draw the results. Reads build/results.json, writes PNGs into docs/img/.

  .venv/bin/python scripts/charts.py

matplotlib, deliberately: it is a Python library like the rest of the pipeline, it needs no browser
or JavaScript toolchain to render, and it writes a PNG that can be committed and shown inline in a
README on GitHub. A chart that needs a build step to look at is a chart nobody looks at.

Four figures, each answering one question:

  size-by-database     what does each database cost in each engine? (log scale: the databases span
                       three orders of magnitude, and a linear axis would show only the big ones)
  ratio-by-database    where is Dolt cheaper, and by how much? (the spread is the real finding)
  commit-granularity   what does history cost? one commit per database against one per row
  totals               the whole corpus in one picture, including what is not counted
"""
import json, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "docs", "img")
MB = 1024 * 1024

INK, GRID = "#22252a", "#cfd4dc"
COLOURS = {"mysql": "#4c72b0", "oneshot": "#dd8452", "rowinsert": "#55a868", "rowcommit": "#c44e52"}
LABELS = {"mysql": "MySQL 9.7.2", "oneshot": "Dolt — one commit per database",
          "rowinsert": "Dolt — one INSERT per row, one commit",
          "rowcommit": "Dolt — one commit per row"}


def style(ax, title, xlabel):
    ax.set_title(title, color=INK, fontsize=12, pad=12, loc="left", fontweight="bold")
    ax.set_xlabel(xlabel, color=INK, fontsize=9)
    ax.tick_params(colors=INK, labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.grid(axis="x", color=GRID, linewidth=.6, alpha=.7)
    ax.set_axisbelow(True)


def save(fig, name):
    path = os.path.join(IMG, name)
    fig.savefig(path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  . {os.path.relpath(path, ROOT)}")


def load():
    with open(os.path.join(ROOT, "build", "results.json"), encoding="utf-8") as fh:
        return json.load(fh)


def series(results, mode):
    return {db: (r.get("modes", {}).get(mode, {}) or {}).get("disk_bytes")
            for db, r in results.items()}


def fig_size_by_database(results):
    # Only the two modes that cover every database. Adding a mode measured on a subset would put
    # bars of different populations in one picture under a title claiming all 21.
    my = {db: r.get("mysql_disk_bytes") for db, r in results.items()}
    one = series(results, "oneshot")
    dbs = [d for d in sorted(my, key=lambda d: my[d] or 0) if my.get(d) and one.get(d)]

    fig, ax = plt.subplots(figsize=(9, 0.36 * len(dbs) + 1.6))
    h, y = 0.36, range(len(dbs))
    ax.barh([i + h / 2 for i in y], [my[d] / MB for d in dbs], h, label=LABELS["mysql"],
            color=COLOURS["mysql"])
    ax.barh([i - h / 2 for i in y], [one[d] / MB for d in dbs], h, label=LABELS["oneshot"],
            color=COLOURS["oneshot"])
    ax.set_yticks(list(y), dbs, fontsize=8)
    ax.set_xscale("log")
    style(ax, f"Disk used per database — all {len(dbs)}", "megabytes on disk (log scale)")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    save(fig, "size-by-database.png")


def fig_ratio(results):
    my = {db: r.get("mysql_disk_bytes") for db, r in results.items()}
    one = series(results, "oneshot")
    pairs = sorted(((one[d] / my[d], d) for d in my if my.get(d) and one.get(d)))
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(pairs) + 1.6))
    ratios = [p[0] for p in pairs]
    ax.barh(range(len(pairs)), ratios, 0.62, color=COLOURS["oneshot"])
    for i, (r, _) in enumerate(pairs):
        ax.text(r + .012, i, f"{r:.2f}×", va="center", fontsize=7.5, color=INK)
    ax.axvline(1.0, color=COLOURS["mysql"], linewidth=1.2, linestyle="--")
    ax.text(1.02, len(pairs) - .6, "same size as MySQL", fontsize=8, color=COLOURS["mysql"])
    ax.set_yticks(range(len(pairs)), [p[1] for p in pairs], fontsize=8)
    ax.set_xlim(0, max(1.12, max(ratios) * 1.18))
    style(ax, "Dolt ÷ MySQL, one commit per database",
          "smaller is less disk than MySQL for the same rows")
    save(fig, "ratio-by-database.png")


def fig_commit_granularity(results):
    my = {db: r.get("mysql_disk_bytes") for db, r in results.items()}
    one, row, com = series(results, "oneshot"), series(results, "rowinsert"), series(results, "rowcommit")
    dbs = [d for d in sorted(com, key=lambda d: results[d].get("rows_mysql") or 0) if com.get(d)]
    if not dbs:
        return
    fig, ax = plt.subplots(figsize=(10, 0.62 * len(dbs) + 1.8))
    h, y = 0.2, range(len(dbs))
    ax.barh([i + 1.5 * h for i in y], [my[d] / MB for d in dbs], h, label=LABELS["mysql"],
            color=COLOURS["mysql"])
    ax.barh([i + 0.5 * h for i in y], [one[d] / MB for d in dbs], h, label=LABELS["oneshot"],
            color=COLOURS["oneshot"])
    ax.barh([i - 0.5 * h for i in y], [(row.get(d) or 0) / MB for d in dbs], h,
            label=LABELS["rowinsert"], color=COLOURS["rowinsert"])
    ax.barh([i - 1.5 * h for i in y], [com[d] / MB for d in dbs], h, label=LABELS["rowcommit"],
            color=COLOURS["rowcommit"])
    for i, d in enumerate(dbs):
        ax.text(com[d] / MB * 1.15, i - 1.5 * h, f"{com[d] / one[d]:.0f}×",
                va="center", fontsize=7.5, color=COLOURS["rowcommit"], fontweight="bold")
    # both bounds, explicitly: on a log axis a bar starts at 0, which is -inf, so setting only the
    # right bound leaves the left one unscaled and every bar renders full width
    lo = min(min(one[d], my[d], com[d]) for d in dbs) / MB
    ax.set_xlim(lo / 3, max(com[d] for d in dbs) / MB * 3.2)
    ax.set_yticks(list(y), [f"{d}\n{results[d].get('rows_mysql', 0):,} rows" for d in dbs],
                  fontsize=7.5)
    ax.set_xscale("log")
    style(ax, "What history costs — the same rows, written four ways",
          "megabytes on disk (log scale).  × is the per-row-commit load against the one-commit load")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    save(fig, "commit-granularity.png")


def fig_totals(results):
    """MySQL against Dolt for every database. The other two modes are measured on subsets and are
    shown in commit-granularity.png, where the population is stated; putting them here would mean
    bars of different sizes standing under a title that claims all 21."""
    covered = [db for db, r in results.items()
               if r.get("mysql_disk_bytes") and (r.get("modes", {}).get("oneshot") or {}).get("disk_bytes")]
    my = sum(results[d]["mysql_disk_bytes"] for d in covered)
    one_total = sum(results[d]["modes"]["oneshot"]["disk_bytes"] for d in covered)
    rows_total = sum(results[d].get("rows_mysql") or 0 for d in covered)
    stats = sum((results[d].get("modes", {}).get("oneshot", {}) or {}).get("stats_bytes") or 0
                for d in covered)
    names = ["mysql", "oneshot"]
    vals = [my / MB, one_total / MB]
    tot = {"oneshot": one_total}

    fig, ax = plt.subplots(figsize=(7, 3.6))
    bars = ax.bar([LABELS[n].replace(" — ", "\n") for n in names], vals,
                  color=[COLOURS[n] for n in names], width=.55)
    ax.bar([LABELS["oneshot"].replace(" — ", "\n")], [stats / MB], bottom=[tot["oneshot"] / MB],
           color=COLOURS["oneshot"], alpha=.35, width=.55,
           label="server-collected statistics (not counted)")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.02, f"{v:,.0f} MB", ha="center", fontsize=9,
                color=INK, fontweight="bold")
    ax.text(1, (tot["oneshot"] + stats) / MB * 1.02, f"+{stats / MB:,.0f} MB stats", ha="center",
            fontsize=7.5, color=INK, alpha=.8)
    ax.text(0.5, max(vals) * .62, f"{one_total / my:.2f}×", ha="center", fontsize=22,
            color=INK, alpha=.35, fontweight="bold")
    ax.set_ylabel("megabytes on disk", color=INK, fontsize=9)
    style(ax, f"All {len(covered)} databases, {rows_total:,} rows", "")
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=.6, alpha=.7)
    ax.legend(fontsize=8, frameon=False)
    save(fig, "totals.png")


def main():
    os.makedirs(IMG, exist_ok=True)
    results = load()
    fig_size_by_database(results)
    fig_ratio(results)
    fig_commit_granularity(results)
    fig_totals(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
