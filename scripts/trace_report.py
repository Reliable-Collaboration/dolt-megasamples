#!/usr/bin/env python3
"""Read a load's memory and disk trace, and say where it is heading.

  python3 scripts/trace_report.py [--only employees] [--mode rowcommit]

`run_all.py` samples memory and disk between chunks of a per-row-commit load, so a long load leaves
a curve of what it cost as history accumulated. This turns that curve into the two things worth
knowing before committing hours to a bigger one:

  * **where the ceiling is reached.** Fit the recent part of the curve and extrapolate to the
    container's memory limit. That gives a row count at which the load would be killed -- which is a
    prediction, and is reported as one, with the fit it rests on.
  * **whether the growth is still linear.** Fit the first half and the second half separately and
    compare the slopes. Memory that grows linearly with history can be planned for; memory whose
    slope is itself rising cannot, and the point where the two diverge is the useful part of the
    measurement.

Only anonymous memory is fitted. The cgroup limit counts page cache too, but the kernel reclaims
cache under pressure and cannot reclaim anon, so anon is what decides whether a process is killed.
"""
import argparse, glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human  # noqa: E402

TRACE_DIR = os.path.join(ROOT, "build", "trace")


def fit(points):
    """Least squares slope and intercept of y against x. Returns None for fewer than two points."""
    pts = [(x, y) for x, y in points if x is not None and y is not None]
    if len(pts) < 2:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    denom = sum((x - mx) ** 2 for x, _ in pts)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in pts) / denom
    return slope, my - slope * mx


def r_squared(points, model):
    pts = [(x, y) for x, y in points if x is not None and y is not None]
    slope, intercept = model
    my = sum(y for _, y in pts) / len(pts)
    ss_tot = sum((y - my) ** 2 for _, y in pts)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in pts)
    return 1 - ss_res / ss_tot if ss_tot else 1.0


def describe(path):
    t = json.load(open(path, encoding="utf-8"))
    samples = t.get("samples") or []
    limit = t.get("limit_bytes")
    name = f"{t.get('mode')}/{t.get('database')}"
    print(f"\n  {name}: {len(samples)} sample(s)"
          + (f", container limit {human(limit)}" if limit else ""))
    if len(samples) < 3:
        print("    too few samples to say anything yet")
        return

    last = samples[-1]
    # The final chunk is usually a short one, and its process therefore holds less than a full
    # chunk's worth. Including it drags every slope towards zero -- on a small database it inverts
    # the sign outright. Samples whose row span is well under the typical one are left out of the
    # fits and kept in the reported totals.
    spans = [b["rows"] - a["rows"] for a, b in zip(samples, samples[1:])]
    typical = sorted(spans)[len(spans) // 2] if spans else 0
    full = [samples[0]] + [b for a, b in zip(samples, samples[1:])
                           if not typical or (b["rows"] - a["rows"]) >= typical * 0.75]
    if len(full) < 3:
        full = samples
    anon = [(s["rows"], s.get("memory_anon_bytes")) for s in full]
    disk = [(s["rows"], s.get("disk_bytes")) for s in full]
    if len(full) != len(samples):
        print(f"    {len(samples) - len(full)} short final chunk(s) excluded from the fits")
    print(f"    at {last['rows']:,} rows: "
          f"{human(last.get('memory_anon_bytes') or 0)} anon, "
          f"{human(last.get('disk_bytes') or 0)} on disk, "
          f"{last['seconds'] / 60:.0f} min elapsed")

    d = fit(disk)
    if d:
        print(f"    disk grows {human(d[0])} per row (R²={r_squared(disk, d):.3f})")

    # is the growth still linear? compare the halves rather than trusting one fit over everything
    half = len(anon) // 2
    early, late = fit(anon[:half]), fit(anon[half:])
    whole = fit(anon)
    if early and late and early[0] > 0:
        change = 100 * (late[0] - early[0]) / early[0]
        verdict = ("still linear" if abs(change) < 25 else
                   "bending upwards" if change > 0 else "flattening")
        print(f"    anon slope: {human(early[0])}/row over the first half, "
              f"{human(late[0])}/row over the second — {verdict} ({change:+.0f}%)")
    if whole:
        print(f"    anon fit over everything: {human(whole[0])} per row "
              f"(R²={r_squared(anon, whole):.3f})")

    # where does it hit the ceiling?
    model = late or whole
    if model and limit and model[0] > 0:
        rows_at_limit = (limit - model[1]) / model[0]
        if rows_at_limit > last["rows"]:
            print(f"    extrapolating the recent slope, anon reaches the "
                  f"{human(limit)} limit at about {rows_at_limit:,.0f} rows "
                  f"({rows_at_limit / last['rows']:.1f}× where it is now)")
        else:
            print("    the recent slope already puts it at the limit; "
                  "treat any further extrapolation as unsupported")
        print("    that is a projection from a straight line, not a measurement: if the slope is "
              "bending upwards the true figure is lower")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append")
    ap.add_argument("--mode", action="append")
    a = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(TRACE_DIR, "*.json")))
    if a.only:
        paths = [p for p in paths if any(f"-{d}.json" in p for d in a.only)]
    if a.mode:
        paths = [p for p in paths if any(os.path.basename(p).startswith(m + "-") for m in a.mode)]
    if not paths:
        print(f"  no traces in {os.path.relpath(TRACE_DIR, ROOT)}; "
              "they are written by the per-row-commit loads")
        return 0
    for p in paths:
        describe(p)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
