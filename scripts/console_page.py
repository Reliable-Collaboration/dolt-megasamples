#!/usr/bin/env python3
"""Generate the Dolt console's landing page from the measurements.

  python3 scripts/console_page.py

The page is the experiment in one screen: every database with what it costs in each engine, links
into the four Dolt consoles, and a per-row link that opens one database directly in phpMyAdmin or
Adminer. It is generated from `build/results.json`, so it shows what was measured and cannot drift
from the report.
"""
import html, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human, load_results  # noqa: E402

OUT = os.path.join(ROOT, "docker", "console", "index.html")
CONSOLES = [("phpMyAdmin", 8091, "Signed in already; the server menu switches account."),
            ("Adminer", 8092, "Its login form remains; use either account below."),
            ("DbGate", 8093, "Both connections are preconfigured in the sidebar."),
            ("CloudBeaver", 8094, "Open as a guest; both connections are in the sidebar."),
            ("Dolt Workbench", 8095,
             "Branches, commits and diffs \u2014 the part the others cannot show. "
             "Connect once with mysql://admin:admin@dolt:3306/sakila")]
DEEP = (("phpMyAdmin", "P", "http://127.0.0.1:8091/index.php?route=/database/structure&db={db}&server=1"),
        ("Adminer", "A", "http://127.0.0.1:8092/?server=dolt&username=demo&db={db}"))


def main():
    results = load_results()
    for r in results.values():          # flatten the one-shot mode for this page's table
        one = (r.get("modes", {}) or {}).get("oneshot") or {}
        if one.get("disk_bytes"):
            r["dolt_disk_bytes"] = one["disk_bytes"]
    items = [(db, r) for db, r in sorted(results.items())
             if r.get("mysql_disk_bytes") and r.get("dolt_disk_bytes")]
    if not items:
        sys.exit("no measurements yet; run `make measure`")

    my = sum(r["mysql_disk_bytes"] for _, r in items)
    do = sum(r["dolt_disk_bytes"] for _, r in items)
    rows_total = sum(r.get("rows_mysql") or 0 for _, r in items)

    # The table below is the one-commit load. Saying so matters: the same rows committed one at a
    # time are 10x to 187x larger, and a page that showed only the flattering number would be
    # telling half the result.
    rc = [(db, r, (r.get("modes", {}).get("rowcommit") or {}).get("disk_bytes"))
          for db, r in items]
    rc = [(db, r, v) for db, r, v in rc if v]
    granularity = ""
    if rc:
        mults = sorted(v / r["dolt_disk_bytes"] for _, r, v in rc)
        granularity = (
            f' Committing one row at a time instead costs <b>{mults[0]:.0f}\u00d7 to '
            f'{mults[-1]:.0f}\u00d7</b> as much, measured on {len(rc)} of them \u2014 history is '
            f'the expensive part, not the rows. See <code>REPORT.md</code>.')

    links = "\n".join(
        f'      <a class="console" href="http://127.0.0.1:{port}/"><b>{name}</b>'
        f'<span>{html.escape(note)}</span></a>' for name, port, note in CONSOLES)

    cards = []
    for db, r in sorted(items, key=lambda x: -x[1]["mysql_disk_bytes"]):
        opens = "".join(
            f'<a class="go" title="Open {db} in {n}" href="{html.escape(u.format(db=db))}">{c}</a>'
            for n, c, u in DEEP)
        ratio = r["dolt_disk_bytes"] / r["mysql_disk_bytes"]
        bar = min(100, ratio * 100)
        cards.append(
            f'      <tr><td><code>{html.escape(db)}</code><span class="opens">{opens}</span></td>'
            f'<td class="n">{(r.get("rows_mysql") or 0):,}</td>'
            f'<td class="n">{human(r["mysql_disk_bytes"])}</td>'
            f'<td class="n">{human(r["dolt_disk_bytes"])}</td>'
            f'<td class="n">{ratio:.2f}×</td>'
            f'<td><div class="bar"><i style="width:{bar:.1f}%"></i></div></td></tr>')

    page = f"""<!doctype html>
<meta charset="utf-8"><title>dolt-megasamples</title>
<style>
 :root {{ color-scheme: light dark; --line:#8883; --fill:#69f; }}
 body {{ font:15px/1.5 system-ui,sans-serif; margin:0 auto; padding:2rem 1.25rem; max-width:64rem; }}
 h1 {{ font-size:1.5rem; margin:0 0 .25rem; }}
 p.sub {{ margin:0 0 1.5rem; opacity:.7; }}
 .headline {{ border:1px solid var(--line); border-radius:.5rem; padding:1rem 1.25rem; margin:0 0 1.5rem;
              font-size:1.05em; }}
 .headline b {{ font-size:1.3em; }}
 .consoles {{ display:grid; gap:.75rem; grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));
              margin-bottom:1.5rem; }}
 a.console {{ display:block; padding:.85rem 1rem; border:1px solid var(--line); border-radius:.5rem;
              text-decoration:none; color:inherit; }}
 a.console:hover {{ border-color:var(--fill); }}
 a.console span {{ display:block; font-size:.85em; opacity:.7; margin-top:.2rem; }}
 table {{ border-collapse:collapse; width:100%; font-size:.9em; }}
 th,td {{ text-align:left; padding:.35rem .6rem; border-bottom:1px solid var(--line); }}
 td.n, th.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
 .bar {{ background:#8882; border-radius:.2rem; height:.6rem; width:8rem; }}
 .bar i {{ display:block; height:100%; background:var(--fill); border-radius:.2rem; }}
 .opens {{ margin-left:.45rem; white-space:nowrap; }}
 a.go {{ display:inline-block; width:1.25rem; height:1.25rem; line-height:1.25rem; text-align:center;
         border:1px solid var(--line); border-radius:.25rem; font-size:.72em; font-weight:600;
         text-decoration:none; color:inherit; opacity:.65; margin-left:.15rem; }}
 a.go:hover {{ opacity:1; border-color:var(--fill); }}
 .creds {{ border:1px solid var(--line); border-radius:.5rem; padding:.75rem 1rem; margin:1.5rem 0;
           font-size:.9em; }}
 footer {{ margin-top:2rem; font-size:.85em; opacity:.7; }}
</style>

<h1>dolt-megasamples</h1>
<p class="sub">{len(items)} databases · {rows_total:,} rows · Dolt 2.3.2 on 127.0.0.1:3307</p>

<div class="headline">
  The same data in both engines: MySQL keeps it in <b>{human(my)}</b>, Dolt in <b>{human(do)}</b> —
  <b>{do / my:.2f}×</b>. Per database the ratio runs from
  {min(r["dolt_disk_bytes"] / r["mysql_disk_bytes"] for _, r in items):.2f}× to
  {max(r["dolt_disk_bytes"] / r["mysql_disk_bytes"] for _, r in items):.2f}×, which is the point of
  the experiment: the number is not one number.{granularity}
</div>

<div class="consoles">
{links}
</div>

<table>
  <caption style="text-align:left;font-size:.85em;opacity:.7;padding:.4rem 0">
    Each database loaded in a single Dolt commit.
  </caption>
  <thead><tr><th>database — <b>P</b> opens it in phpMyAdmin, <b>A</b> in Adminer</th>
  <th class="n">rows</th><th class="n">MySQL</th><th class="n">Dolt</th><th class="n">Dolt ÷ MySQL</th>
  <th></th></tr></thead>
  <tbody>
{chr(10).join(cards)}
  </tbody>
</table>

<div class="creds">
  <b>Two accounts</b>, the same as mysql-megasamples, on host <code>127.0.0.1</code> port
  <code>3307</code>.<br>
  <code>demo</code> / <code>demo</code> — read only. <code>admin</code> / <code>admin</code> — full
  privileges. Each console opens on the read-only one.
</div>

<footer>
  Generated by <code>scripts/console_page.py</code> from <code>build/results.json</code> — the same
  measurements as <code>REPORT.md</code>, so this page cannot disagree with the report. The MySQL
  side of the comparison lives in <code>mysql-megasamples</code> and serves 3306 and 8080–8084;
  nothing here uses those ports.
</footer>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print(f"  . wrote docker/console/index.html: {len(items)} databases, "
          f"MySQL {human(my)}, Dolt {human(do)}, {do / my:.2f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
