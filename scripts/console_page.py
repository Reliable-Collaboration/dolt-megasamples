#!/usr/bin/env python3
"""Generate the console landing page from the measurements.

  python3 scripts/console_page.py

The page is the experiment in one screen: every database with what it costs in each engine, how
to connect a tool of one's own to each engine that stays up (Dolt, DoltgreSQL, and the DoltLite
files), and the consoles with what each can open. It is generated from `build/results.json`, so
it shows what was measured and cannot drift from the report.
"""
import html, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, human, load_results  # noqa: E402
from pairs import DOLTGRES_VERSION, LITE_VERSION  # noqa: E402

OUT = os.path.join(ROOT, "docker", "console", "index.html")
# consoles in order of what they can open, most first
CONSOLES = [("CloudBeaver", 8094, "Dolt and DoltgreSQL",
             "Open as a guest; both accounts of both engines are in the sidebar."),
            ("DbGate", 8093, "Dolt and DoltgreSQL", "Four connections are preconfigured in the sidebar."),
            ("Dolt Workbench", 8095, "Dolt, DoltgreSQL and every DoltLite file",
             "Branches, commits and diffs — the part the others cannot show. Both accounts on both servers and "
             "each DoltLite file are saved connections: pick one from its list (it keeps one current connection at a time)."),
            ("Adminer", 8092, "Dolt and DoltgreSQL",
             "Its login form remains: system MySQL, server dolt — or system PostgreSQL, server doltgres — "
             "with either account."),
            ("phpMyAdmin", 8091, "Dolt only", "Signed in already; the server menu switches account.")]
# Adminer answers 403 to a login URL that names a username (its permanent-login guard, measured
# on the pinned image on 2026-09-10), so the links name the server only and the page above says
# which account to type.
DEEP = (("Adminer", "A", "http://127.0.0.1:8092/?server=dolt&db={db}"),
        ("Adminer on DoltgreSQL", "Aᴘ", "http://127.0.0.1:8092/?pgsql=doltgres&db={db}"),
        ("phpMyAdmin", "P", "http://127.0.0.1:8091/index.php?route=/database/structure&db={db}&server=1"))

CONNECT = [
    (f"Dolt (MySQL protocol)", [
        ("address", "127.0.0.1 port 3307"),
        ("accounts", "demo / demo (read only) · admin / admin (all privileges) · root / root"),
        ("client", "mysql -h 127.0.0.1 -P 3307 -u demo -pdemo sakila"),
        ("URL", "mysql://demo:demo@127.0.0.1:3307/sakila"),
        ("JDBC", "jdbc:mysql://127.0.0.1:3307/sakila"),
        ("version control", "dolt_log, dolt_diff and the rest are tables and procedures: SELECT * FROM dolt_log; CALL dolt_commit('-Am', '...')")]),
    (f"DoltgreSQL {DOLTGRES_VERSION} (PostgreSQL protocol)", [
        ("address", "127.0.0.1 port 5433"),
        ("accounts", "demo / demo (read only) · admin / admin (superuser) · postgres / doltsamples"),
        ("client", "PGPASSWORD=demo psql -h 127.0.0.1 -p 5433 -U demo -d sakila"),
        ("URL", "postgresql://demo:demo@127.0.0.1:5433/sakila"),
        ("JDBC", "jdbc:postgresql://127.0.0.1:5433/sakila"),
        ("version control", "SELECT * FROM dolt_log; SELECT dolt_commit('-Am', '...') — SQL only, there is no CLI"),
        ("note", "one database per dataset, each its own repository with one commit; some objects were not carried — the report says which")]),
    (f"DoltLite v{LITE_VERSION} (files)", [
        ("files", "/data/{database}.doltlite inside the doltsamples-doltlite container; no accounts, no server"),
        ("open", "docker exec -it doltsamples-doltlite doltlite /data/sakila.doltlite"),
        ("copy one out", "docker cp doltsamples-doltlite:/data/sakila.doltlite ."),
        ("version control", "SELECT * FROM dolt_log; SELECT dolt_commit('-Am', '...'); VACUUM is garbage collection"),
        ("console", "Dolt Workbench opens each file through its own DoltLite: pick the \"DoltLite <database>\" connection"),
        ("note", "a DoltLite file is not SQLite pages: sqlite3, Adminer, DbGate and CloudBeaver cannot open it; the doltlite "
                 "shell, libdoltlite and the Workbench can. One durable writer at a time.")]),
]


def sizes(r):
    """The one-commit size in each engine, or None where not measured."""
    one = (r.get("modes", {}) or {}).get("oneshot") or {}
    pairs = r.get("pairs") or {}
    return {"mysql": r.get("mysql_disk_bytes"), "dolt": one.get("disk_bytes"),
            "postgres": ((pairs.get("pg") or {}).get("postgres") or {}).get("disk_bytes"),
            "doltgres": ((pairs.get("pg") or {}).get("doltgres_oneshot") or {}).get("disk_bytes"),
            "sqlite": ((pairs.get("lite") or {}).get("sqlite") or {}).get("disk_bytes"),
            "doltlite": ((pairs.get("lite") or {}).get("doltlite_oneshot") or {}).get("disk_bytes")}


def main():
    results = load_results()
    items = [(db, r, sizes(r)) for db, r in sorted(results.items())]
    items = [(db, r, s) for db, r, s in items if any(s.values())]
    if not items:
        sys.exit("no measurements yet; run `make measure`")
    base = [(db, r, s) for db, r, s in items if s["mysql"] and s["dolt"]]
    my = sum(s["mysql"] for _, _, s in base)
    do = sum(s["dolt"] for _, _, s in base)
    rc = [(s["dolt"], (r.get("modes", {}).get("rowcommit") or {}).get("disk_bytes")) for _, r, s in base]
    rc = [(a, b) for a, b in rc if a and b]
    granularity = ""
    if rc:
        mults = sorted(b / a for a, b in rc)
        granularity = (f' Committing one row at a time instead costs <b>{mults[0]:.0f}× to {mults[-1]:.0f}×</b> '
                       f'as much, measured on {len(rc)} of them — history is the expensive part, not the rows. '
                       f'See <code>REPORT.md</code>.')
    have_pg = any(s["doltgres"] for _, _, s in items)
    have_lite = any(s["doltlite"] for _, _, s in items)

    links = "\n".join(
        f'      <a class="console" href="http://127.0.0.1:{port}/"><b>{name}</b><em>{html.escape(cover)}</em>'
        f'<span>{html.escape(note)}</span></a>' for name, port, cover, note in CONSOLES)
    connect = "\n".join(
        f'      <div class="engine"><h3>{html.escape(title)}</h3><table class="kv">'
        + "".join(f'<tr><th>{html.escape(k)}</th><td>{"<code>" + html.escape(v) + "</code>" if k in ("client", "URL", "JDBC", "open", "copy one out") else html.escape(v)}</td></tr>'
                  for k, v in rows) + '</table></div>' for title, rows in CONNECT)

    head = ['<th>database</th><th class="n">rows</th><th class="n">MySQL</th><th class="n">Dolt</th><th class="n">ratio</th><th></th>']
    if have_pg:
        head.append('<th class="n">PostgreSQL</th><th class="n">DoltgreSQL</th>')
    if have_lite:
        head.append('<th class="n">SQLite</th><th class="n">DoltLite</th>')
    cards = []

    def fmt(v):
        return human(v) if v else "—"

    for db, r, s in sorted(items, key=lambda x: -(x[2]["mysql"] or x[2]["postgres"] or x[2]["sqlite"] or 0)):
        opens = "".join(
            f'<a class="go" title="Open {db} in {n}" href="{html.escape(u.format(db=db))}">{c}</a>'
            for n, c, u in DEEP if (s["doltgres"] or "DoltgreSQL" not in n))
        ratio = (s["dolt"] / s["mysql"]) if s["mysql"] and s["dolt"] else None
        bar = min(100, ratio * 100) if ratio else 0
        row = (f'      <tr><td><code>{html.escape(db)}</code><span class="opens">{opens}</span></td>'
               f'<td class="n">{(r.get("rows_mysql") or 0):,}</td>'
               f'<td class="n">{fmt(s["mysql"])}</td><td class="n">{fmt(s["dolt"])}</td>'
               f'<td class="n">{f"{ratio:.2f}×" if ratio else "—"}</td>'
               f'<td><div class="bar"><i style="width:{bar:.1f}%"></i></div></td>')
        if have_pg:
            row += f'<td class="n">{fmt(s["postgres"])}</td><td class="n">{fmt(s["doltgres"])}</td>'
        if have_lite:
            row += f'<td class="n">{fmt(s["sqlite"])}</td><td class="n">{fmt(s["doltlite"])}</td>'
        cards.append(row + "</tr>")

    more = ""
    if have_pg or have_lite:
        more = (" The same rows were also loaded into PostgreSQL and DoltgreSQL, and into SQLite and DoltLite, "
                "each pair from its own dump, one commit per database; those sizes are in the last columns.")
    page = f"""<!doctype html>
<meta charset="utf-8"><title>dolt-megasamples</title>
<style>
 :root {{ color-scheme: light dark; --line:#8883; --fill:#69f; }}
 body {{ font:15px/1.5 system-ui,sans-serif; margin:0 auto; padding:2rem 1.25rem; max-width:72rem; }}
 h1 {{ margin:0 0 .25rem; }} h2 {{ margin:2rem 0 .5rem; font-size:1.15rem; }}
 p.lead {{ margin:0 0 1.5rem; opacity:.85; }}
 .consoles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(15rem,1fr)); gap:.75rem; }}
 a.console {{ display:block; padding:.75rem 1rem; border:1px solid var(--line); border-radius:.5rem; text-decoration:none; color:inherit; }}
 a.console:hover {{ border-color:var(--fill); }}
 a.console b {{ display:block; }} a.console em {{ display:block; font-size:.85rem; opacity:.8; }}
 a.console span {{ font-size:.85rem; opacity:.7; }}
 .engines {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(20rem,1fr)); gap:.75rem; }}
 .engine {{ border:1px solid var(--line); border-radius:.5rem; padding:.5rem 1rem; }}
 .engine h3 {{ margin:.25rem 0 .5rem; font-size:1rem; }}
 table.kv th {{ text-align:left; font-weight:600; padding:.1rem .6rem .1rem 0; white-space:nowrap; vertical-align:top; font-size:.9rem; }}
 table.kv td {{ font-size:.9rem; padding:.1rem 0; }} table.kv code {{ font-size:.85rem; }}
 table.db {{ border-collapse:collapse; width:100%; }}
 table.db th, table.db td {{ padding:.35rem .5rem; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }}
 table.db th.n, table.db td.n {{ text-align:right; white-space:nowrap; }}
 .bar {{ width:6rem; height:.5rem; background:var(--line); border-radius:.25rem; overflow:hidden; }}
 .bar i {{ display:block; height:100%; background:var(--fill); }}
 .opens a {{ font-size:.75rem; margin-left:.35rem; text-decoration:none; opacity:.6; }} .opens a:hover {{ opacity:1; }}
 footer {{ margin-top:2rem; font-size:.85rem; opacity:.7; }}
</style>
<h1>dolt-megasamples</h1>
<p class="lead">The sql-megasamples databases loaded into Dolt — and into DoltgreSQL and DoltLite — with what each costs
on disk beside the engine it mirrors. The Dolt column is the one-commit load, {do / my:.2f}× MySQL across
{len(base)} databases.{granularity}{more}</p>

<h2>Consoles, by what they can open</h2>
<div class="consoles">
{links}
</div>

<h2>Connect with your own tool</h2>
<div class="engines">
{connect}
</div>

<h2>Databases</h2>
<table class="db">
<tr>{''.join(head)}</tr>
{chr(10).join(cards)}
</table>
<footer>Sizes are the settled one-commit loads (after garbage collection or VACUUM); the report gives every shape.
A = open in Adminer, Aᴘ = in Adminer on DoltgreSQL, P = in phpMyAdmin. Generated by scripts/console_page.py.</footer>
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"  . wrote {os.path.relpath(OUT, ROOT)} ({len(items)} databases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
