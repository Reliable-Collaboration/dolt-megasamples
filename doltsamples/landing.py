"""The landing page: every database the stack serves, how to connect a tool of one's own, and the
consoles. Written by `make up` from build/serve.json into docker/console/index.html.
"""
import html, json, os

from doltsamples.config import HISTORY_LABEL
from doltsamples.stack import CONTAINERS, PASSWORDS, SERVE
from doltsamples.util import ROOT, human, load_json, versions

OUT = os.path.join(ROOT, "docker", "console", "index.html")
CATALOGUE = os.path.join(ROOT, "build", "catalogue.json")
CONSOLE_INFO = {
    "workbench": ("Dolt Workbench", "Dolt, DoltgreSQL and every DoltLite file",
                  "Branches, commits and diffs: the history the other consoles cannot show. Every server account "
                  "and every DoltLite file is a saved connection; pick one from its list."),
    "cloudbeaver": ("CloudBeaver", "Dolt and DoltgreSQL", "Open as a guest; both accounts of each engine are in the sidebar."),
    "dbgate": ("DbGate", "Dolt and DoltgreSQL", "The connections are preconfigured in the sidebar."),
    "adminer": ("Adminer", "Dolt and DoltgreSQL",
                "Its login form remains: system MySQL, server dolt, or system PostgreSQL, server doltgres, with either account."),
    "phpmyadmin": ("phpMyAdmin", "Dolt only", "Signed in already; the server menu switches account."),
}


def write():
    s = load_json(SERVE, {}) or {}
    stack, engines = s.get("stack") or {}, s.get("engines") or {}
    P, pw, consoles = stack.get("ports") or {}, stack.get("passwords") or {}, stack.get("consoles") or []
    # a password set in .env is named, not printed
    shown = {k: (v if v == PASSWORDS[k][1] else f"${PASSWORDS[k][0]}") for k, v in pw.items()}
    v = versions()
    catalogue = load_json(CATALOGUE, {}) or {}
    first = {e: (engines.get(e) or [{}])[0].get("name", "sakila") for e in ("dolt", "doltgres", "doltlite")}

    connect = []
    if engines.get("dolt"):
        connect.append((f"Dolt {v['dolt']['version']} (MySQL protocol)", [
            ("address", f"127.0.0.1 port {P['dolt']}"),
            ("accounts", f"demo / {shown['demo']} (read only) · admin / {shown['admin']} (all privileges) · root / {shown['dolt_root']}"),
            ("client", f"mysql -h 127.0.0.1 -P {P['dolt']} -u demo -p{shown['demo']} {first['dolt']}"),
            ("URL", f"mysql://demo:{shown['demo']}@127.0.0.1:{P['dolt']}/{first['dolt']}"),
            ("history", "SELECT * FROM dolt_log; SELECT * FROM dolt_diff('HEAD~1', 'HEAD', '<table>'); CALL dolt_checkout('-b', 'mine')")]))
    if engines.get("doltgres"):
        connect.append((f"DoltgreSQL {v['doltgres']['version']} (PostgreSQL protocol)", [
            ("address", f"127.0.0.1 port {P['doltgres']}"),
            ("accounts", f"demo / {shown['demo']} (reads every table) · admin / {shown['admin']} (superuser) · postgres / {shown['doltgres']}"),
            ("client", f"PGPASSWORD={shown['demo']} psql -h 127.0.0.1 -p {P['doltgres']} -U demo -d {first['doltgres']}"),
            ("URL", f"postgresql://demo:{shown['demo']}@127.0.0.1:{P['doltgres']}/{first['doltgres']}"),
            ("history", "SELECT * FROM dolt_log; SELECT dolt_checkout('-b', 'mine') — SQL only, there is no CLI")]))
    if engines.get("doltlite"):
        c = CONTAINERS["doltlite"]
        connect.append((f"DoltLite {v['doltlite']['version']} (files)", [
            ("files", f"/data/<name>.doltlite inside the {c} container; no accounts, no server"),
            ("open", f"docker exec -it {c} doltlite /data/{first['doltlite']}.doltlite"),
            ("copy one out", f"docker cp {c}:/data/{first['doltlite']}.doltlite ."),
            ("history", "SELECT * FROM dolt_log; SELECT dolt_commit('-Am', '...'); VACUUM collects garbage"),
            ("note", "a DoltLite file is not SQLite pages: the doltlite shell, libdoltlite and the Workbench open it; "
                     "sqlite3 and the other consoles cannot")]))

    links = "\n".join(
        f'  <a class="console" href="http://127.0.0.1:{P[c]}/"><b>{CONSOLE_INFO[c][0]}</b><em>{html.escape(CONSOLE_INFO[c][1])}</em>'
        f'<span>{html.escape(CONSOLE_INFO[c][2])}</span></a>' for c in CONSOLE_INFO if c in consoles)
    code = ("client", "URL", "open", "copy one out", "history")
    blocks = "\n".join(
        f'  <div class="engine"><h3>{html.escape(t)}</h3><table class="kv">'
        + "".join(f'<tr><th>{html.escape(k)}</th><td>{"<code>" + html.escape(x) + "</code>" if k in code else html.escape(x)}</td></tr>'
                  for k, x in rows) + "</table></div>" for t, rows in connect)
    rows = []
    for e, label in (("dolt", "Dolt"), ("doltgres", "DoltgreSQL"), ("doltlite", "DoltLite")):
        for st in sorted(engines.get(e) or [], key=lambda x: (x["database"], x["history"])):
            rows.append(f'  <tr><td>{label}</td><td><code>{html.escape(st["name"])}</code></td>'
                        f'<td class="what">{html.escape(catalogue.get(st["database"], ""))}</td>'
                        f'<td>{html.escape(HISTORY_LABEL[st["history"]])}</td>'
                        f'<td class="n">{(st.get("rows") or 0):,}</td><td class="n">{(st.get("commits") or 0):,}</td>'
                        f'<td class="n">{human(st.get("bytes") or 0)}</td></tr>')
    missing = s.get("missing") or []
    note = (f'<p class="note">{len(missing)} store(s) the configuration names are not served: '
            + "; ".join(html.escape(f"{m['engine']} {m['history']} {m['database']} ({m['why']})") for m in missing[:8])
            + ("…" if len(missing) > 8 else "") + "</p>") if missing else ""
    page = f"""<!doctype html>
<meta charset="utf-8"><title>dolt-megasamples</title>
<style>
 :root {{ color-scheme: light dark; --line:#8883; --fill:#69f; }}
 body {{ font:15px/1.5 system-ui,sans-serif; margin:0 auto; padding:2rem 1.25rem; max-width:72rem; }}
 h1 {{ margin:0 0 .25rem; }} h2 {{ margin:2rem 0 .5rem; font-size:1.15rem; }}
 p.lead {{ margin:0 0 1.5rem; opacity:.85; }} p.note {{ font-size:.9rem; opacity:.8; }}
 .consoles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(15rem,1fr)); gap:.75rem; }}
 a.console {{ display:block; padding:.75rem 1rem; border:1px solid var(--line); border-radius:.5rem; text-decoration:none; color:inherit; }}
 a.console:hover {{ border-color:var(--fill); }} a.console b, a.console em {{ display:block; }}
 a.console em {{ font-size:.85rem; opacity:.8; }} a.console span {{ font-size:.85rem; opacity:.7; }}
 .engines {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(20rem,1fr)); gap:.75rem; }}
 .engine {{ border:1px solid var(--line); border-radius:.5rem; padding:.5rem 1rem; min-width:0; }}
 .engine h3 {{ margin:.25rem 0 .5rem; font-size:1rem; }}
 table.kv {{ width:100%; table-layout:fixed; }}
 table.kv th {{ width:6.5rem; text-align:left; font-weight:600; padding:.1rem .6rem .1rem 0; vertical-align:top; font-size:.9rem; }}
 table.kv td {{ font-size:.9rem; padding:.1rem 0; overflow-wrap:anywhere; }}
 table.kv code {{ font-size:.85rem; white-space:pre-wrap; overflow-wrap:anywhere; }}
 table.db {{ border-collapse:collapse; width:100%; }}
 table.db th, table.db td {{ padding:.35rem .5rem; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }}
 table.db th.n, table.db td.n {{ text-align:right; white-space:nowrap; }} td.what {{ font-size:.85rem; opacity:.85; }}
 footer {{ margin-top:2rem; font-size:.85rem; opacity:.7; }}
</style>
<h1>dolt-megasamples</h1>
<p class="lead">The sample databases of <a href="https://github.com/Reliable-Collaboration/sql-megasamples">sql-megasamples</a>,
loaded into DoltHub's versioned engines with the history this checkout was configured to give them, and served beside
their consoles. Open one, look through its log, branch it, change it: that is what it is here for.</p>

<h2>Consoles</h2>
<div class="consoles">
{links}
</div>

<h2>Connect with your own tool</h2>
<div class="engines">
{blocks}
</div>

<h2>What is served</h2>
<table class="db">
<tr><th>engine</th><th>database</th><th>what it is</th><th>history</th><th class="n">rows</th><th class="n">commits</th><th class="n">size</th></tr>
{chr(10).join(rows)}
</table>
{note}
<footer>Written by <code>make up</code> from build/serve.json at {html.escape(s.get('written', ''))}. Every store was checked
against the corpus's row counts when it was built (build/stores.json).</footer>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"  . wrote {os.path.relpath(OUT, ROOT)} ({len(rows)} database(s))")
