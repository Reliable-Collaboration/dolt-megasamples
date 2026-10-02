"""The served stack: compose.yaml written from dolt-megasamples.yaml and the stores that are built.

  python3 -m doltsamples compose       write compose.yaml, the Workbench's connections and build/serve.json
  python3 -m doltsamples up            the same, then `docker compose up -d` and the landing page
  python3 -m doltsamples down | status | urls

compose.yaml is generated, like sql-megasamples' own: only the engines that have stores and the
consoles that can read them are in it, with the ports and memory limits the configuration names, so
`docker compose` works on its own afterwards. Each built store is mounted where its server looks for
a database, under its served name -- `sakila` for the single history, `sakila_per_row` for the
per-row one -- over a neutral base directory per engine (data/serve/<engine>). Everything binds to
127.0.0.1, one range above sql-megasamples' ports (3306, 5432, 8080-8084), so both can run at once.

Accounts are sql-megasamples': `demo` reads everything, `admin` can do anything. Their passwords
(DEMO_PASSWORD, ADMIN_PASSWORD, and DOLT_ROOT_PASSWORD, DOLTGRES_PASSWORD for the engines' own
superusers) come from `.env` when it sets them, and the init services apply them on every `up`.
"""
import copy, json, os, sys, time
from urllib.parse import quote

import yaml

from doltsamples import build
from doltsamples.config import CONSOLE_ENGINES, ENGINES, served_name
from doltsamples.util import (BUILD, DATA, ROOT, TRANSIENT, ensure_dir, lite_image, load_json, lock_held, now, rel, run,
                              save_json, versions)

COMPOSE = os.path.join(ROOT, "compose.yaml")
SERVE = os.path.join(BUILD, "serve.json")
STORE = os.path.join(ROOT, "docker", "workbench", "store", "store.json")
NETWORK = "dolt-megasamples_default"
CONTAINERS = {"dolt": "doltsamples-dolt", "doltgres": "doltsamples-doltgres", "doltlite": "doltsamples-doltlite",
              "workbench": "doltsamples-workbench", "landing": "doltsamples-console"}
PASSWORDS = {"demo": ("DEMO_PASSWORD", "demo"), "admin": ("ADMIN_PASSWORD", "admin"),
             "doltgres": ("DOLTGRES_PASSWORD", "doltsamples"), "dolt_root": ("DOLT_ROOT_PASSWORD", "root")}
# the image the Dolt accounts are applied with: Dolt's own image ships no MySQL client, and the
# corpus's image (a prerequisite, and the source of every Dolt export) does
MYSQL_CLIENT = os.environ.get("MEGASAMPLES_MYSQL_IMAGE", "sql-megasamples-mysql:dev")
# the consoles' images, by digest
IMAGES = {"landing": "nginx@sha256:3bcf852aed06467cf075c6105892e4d5a6ebbbafa0ce22d35062db9e90ddef4c",
          "phpmyadmin": "phpmyadmin@sha256:20fa6f724ba77d41abc25b1aeb4d97692ce344c7ace305594e57c5893f60f0f7",
          "adminer": "adminer@sha256:f1e2ba27b10a565ac77b2d8555d803be4ddb3232f4216dcf0ea85bcd8f2f1343",
          "dbgate": "dbgate/dbgate@sha256:14fce4ece52df514e0d320dc82cbfbca5e8f18f98464a6389b1c126f783a6b7e",
          "workbench": "dolthub/dolt-workbench@sha256:acba96fe224c7be44ce1c5f283691230608fdf917167e4e5548f6669f2c23855",
          "cloudbeaver": "dbeaver/cloudbeaver@sha256:3b4bf82287cf4febe0d335873f1346a01100f3951d266cd6a78c27fe30429cbc"}


def dotenv():
    """KEY=VALUE lines of .env, parsed the way compose parses them."""
    out, path = {}, os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] in "'\"" and v[-1] == v[0]:
                    v = v[1:-1]
                elif " #" in v:
                    v = v.split(" #", 1)[0].rstrip()
                out[k.strip()] = v
    return out


def passwords():
    env = dotenv()
    return {k: os.environ.get(var) or env.get(var) or default for k, (var, default) in PASSWORDS.items()}


def settings():
    """What the last `up` resolved -- ports, containers, passwords -- for the check and the page."""
    s = load_json(SERVE, {}) or {}
    return s.get("stack") or {}


# ---------------------------------------------------------------------------- what is served ---
def served(cfg):
    """{engine: [{name, database, history, path, ...record}]} for every wanted store that is built,
    and [(engine, history, db, why)] for those that are not."""
    recs, v = build.records(), versions()
    out, missing = {e: [] for e in ENGINES}, []
    for e, h, db in cfg.wanted():
        rec = recs.get(build.key(e, h, db))
        path = build.store_path(e, h, db)
        if not rec or rec.get("status") != "done" or not os.path.exists(path):
            why = ("its build failed: " + rec["error"][:100]) if rec and rec.get("error") else "not built (make build)"
            missing.append((e, h, db, why))
            continue
        if rec.get("version") != v[e]["version"]:
            missing.append((e, h, db, f"built with {e} {rec.get('version')}, not {v[e]['version']} (make build)"))
            continue
        out[e].append({"name": served_name(db, h), "database": db, "history": h, "path": path,
                       "rows": rec.get("rows"), "commits": rec.get("commits"), "bytes": rec.get("bytes"),
                       "refused": rec.get("refused_count", 0)})
    return out, missing


# ---------------------------------------------------------------------------------- compose ---
def healthcheck(test, start=None):
    h = {"test": ["CMD-SHELL", test], "interval": "5s", "timeout": "10s", "retries": 30}
    if start:
        h["start_period"] = start
    return h


def compose(cfg, stores, pw):
    v, P = versions(), cfg.ports
    engines = [e for e in ENGINES if stores[e]]
    consoles = [c for c in cfg.served_consoles() if c == "landing" or set(engines) & set(CONSOLE_ENGINES[c])]
    healthy = lambda *names: {n: {"condition": "service_healthy"} for n in names if n in engines}
    svc = {}
    if "dolt" in engines:
        svc["dolt"] = {
            "image": v["dolt"]["image"], "container_name": CONTAINERS["dolt"], "mem_limit": cfg.memory["dolt"],
            "ports": [f"127.0.0.1:{P['dolt']}:3306"],
            "environment": {"DOLT_ROOT_PASSWORD": "${DOLT_ROOT_PASSWORD:-root}", "DOLT_ROOT_HOST": "%"},
            # the base directory, and each store at /var/lib/dolt/<served name>: the server serves every
            # repository one level under its data directory. No `command:` -- the image's entrypoint
            # starts `dolt sql-server` with its own --host, and flags added here clash with it.
            "volumes": ["./data/serve/dolt:/var/lib/dolt"]
                       + [f"./{rel(s['path'])}:/var/lib/dolt/{s['name']}" for s in stores["dolt"]],
            # the port, not the CLI: `dolt sql -q` answers from the data directory whether or not the
            # server listens, so a CLI healthcheck goes green before anything can connect
            "healthcheck": healthcheck("bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/3306' 2>/dev/null"),
            "restart": "unless-stopped"}
        # applies the two accounts on every `up` (the image's init hook fires only on an empty data
        # directory, and the stores are written before the server starts)
        svc["dolt-init"] = {
            "image": MYSQL_CLIENT, "container_name": "doltsamples-init", "mem_limit": "512m",
            "depends_on": healthy("dolt"), "volumes": ["./docker/dolt/init.sh:/init.sh:ro"],
            "entrypoint": ["sh", "/init.sh"], "restart": "no",
            "environment": {"DOLT_ROOT_PASSWORD": "${DOLT_ROOT_PASSWORD:-root}",
                            "DEMO_PASSWORD": "${DEMO_PASSWORD:-demo}", "ADMIN_PASSWORD": "${ADMIN_PASSWORD:-admin}"}}
    if "doltgres" in engines:
        svc["doltgres"] = {
            "image": v["doltgres"]["image"], "container_name": CONTAINERS["doltgres"], "mem_limit": cfg.memory["doltgres"],
            "ports": [f"127.0.0.1:{P['doltgres']}:5432"],
            # DoltgreSQL scans every table when it opens a store, and a per-row history of hundreds of
            # thousands of commits takes longer than the image's default 300 s to accept connections
            "environment": {"DOLTGRES_PASSWORD": "${DOLTGRES_PASSWORD:-doltsamples}", "DOLTGRES_SERVER_TIMEOUT": "1800"},
            "volumes": ["./data/serve/doltgres:/var/lib/doltgres"]
                       + [f"./{rel(s['path'])}:/var/lib/doltgres/{s['name']}" for s in stores["doltgres"]],
            "healthcheck": healthcheck("PGPASSWORD=$$DOLTGRES_PASSWORD psql -X -h 127.0.0.1 -U postgres -d postgres "
                                       "-tAc 'SELECT 1' >/dev/null 2>&1", start="1800s"),
            "restart": "unless-stopped"}
        svc["doltgres-init"] = {
            "image": v["doltgres"]["image"], "container_name": "doltsamples-doltgres-init", "mem_limit": "256m",
            "depends_on": healthy("doltgres"), "entrypoint": ["sh", "/init.sh"], "restart": "no",
            "volumes": ["./docker/doltgres/init.sh:/init.sh:ro", "./docker/doltgres/init.sql:/init.sql:ro"],
            "environment": {"DOLTGRES_PASSWORD": "${DOLTGRES_PASSWORD:-doltsamples}",
                            "DEMO_PASSWORD": "${DEMO_PASSWORD:-demo}", "ADMIN_PASSWORD": "${ADMIN_PASSWORD:-admin}"}}
    if "doltlite" in engines:
        # DoltLite has no server: the files, and the doltlite shell to open them
        # (`docker exec -it doltsamples-doltlite doltlite /data/sakila.doltlite`)
        svc["doltlite"] = {
            "image": lite_image(v), "container_name": CONTAINERS["doltlite"], "mem_limit": "512m",
            "volumes": ["./data/serve/doltlite:/data"]
                       + [f"./{rel(s['path'])}:/data/{s['name']}.doltlite" for s in stores["doltlite"]],
            "restart": "unless-stopped"}
    first = lambda e: (stores[e][0]["name"] if stores[e] else "")
    if "landing" in consoles:
        svc["console"] = {"image": IMAGES["landing"], "container_name": CONTAINERS["landing"], "mem_limit": "32m",
                          "ports": [f"127.0.0.1:{P['landing']}:80"],
                          "volumes": ["./docker/console:/usr/share/nginx/html:ro"], "restart": "unless-stopped"}
    if "phpmyadmin" in consoles:
        svc["phpmyadmin"] = {
            "image": IMAGES["phpmyadmin"], "container_name": "doltsamples-phpmyadmin", "mem_limit": "256m",
            "ports": [f"127.0.0.1:{P['phpmyadmin']}:80"],
            "environment": {"PMA_HOST": "dolt", "PMA_PORT": "3306", "UPLOAD_LIMIT": "256M",
                            "DEMO_PASSWORD": "${DEMO_PASSWORD:-demo}", "ADMIN_PASSWORD": "${ADMIN_PASSWORD:-admin}"},
            "volumes": ["./docker/phpmyadmin/config.user.inc.php:/etc/phpmyadmin/config.user.inc.php:ro"],
            "depends_on": healthy("dolt"), "restart": "unless-stopped"}
    if "adminer" in consoles:
        svc["adminer"] = {"image": IMAGES["adminer"], "container_name": "doltsamples-adminer", "mem_limit": "160m",
                          "ports": [f"127.0.0.1:{P['adminer']}:8080"],
                          "environment": {"ADMINER_DEFAULT_SERVER": "dolt" if "dolt" in engines else "doltgres"},
                          "depends_on": healthy("dolt", "doltgres"), "restart": "unless-stopped"}
    if "dbgate" in consoles:
        env, names = {}, []
        for key, engine, user, label in (("demo", "dolt", "demo", "Dolt (read-only)"), ("admin", "dolt", "admin", "Dolt (full access)"),
                                         ("pgdemo", "doltgres", "demo", "DoltgreSQL (read-only)"),
                                         ("pgadmin", "doltgres", "admin", "DoltgreSQL (full access)")):
            if engine not in engines:
                continue
            names.append(key)
            env.update({f"LABEL_{key}": label, f"SERVER_{key}": engine, f"PORT_{key}": "3306" if engine == "dolt" else "5432",
                        f"USER_{key}": user, f"PASSWORD_{key}": "${%s_PASSWORD:-%s}" % (user.upper(), user),
                        f"ENGINE_{key}": "mysql@dbgate-plugin-mysql" if engine == "dolt" else "postgres@dbgate-plugin-postgres"})
        svc["dbgate"] = {"image": IMAGES["dbgate"], "container_name": "doltsamples-dbgate", "mem_limit": "320m",
                         "ports": [f"127.0.0.1:{P['dbgate']}:3000"], "environment": {"CONNECTIONS": ",".join(names), **env},
                         "depends_on": healthy("dolt", "doltgres"), "restart": "unless-stopped"}
    if "workbench" in consoles:
        # Dolt's own console: branches, commits and diffs, which the others cannot show. Its connections
        # are saved in docker/workbench/store (written below); its GraphQL server runs in the container
        # and reaches the engines on the compose network, while the browser calls it on its own port.
        svc["workbench"] = {
            "image": IMAGES["workbench"], "container_name": CONTAINERS["workbench"], "mem_limit": "640m",
            "ports": [f"127.0.0.1:{P['workbench']}:3000", f"127.0.0.1:{P['workbench_api']}:9002"],
            "environment": {"GRAPHQLAPI_URL": f"http://127.0.0.1:{P['workbench_api']}/graphql"},
            "volumes": ["./docker/workbench/store:/app/graphql-server/store", "./data/serve/doltlite:/data/doltlite"]
                       + [f"./{rel(s['path'])}:/data/doltlite/{s['name']}.doltlite" for s in stores["doltlite"]],
            "depends_on": healthy("dolt", "doltgres"), "restart": "unless-stopped"}
    if "cloudbeaver" in consoles:
        svc["cloudbeaver"] = {
            "image": IMAGES["cloudbeaver"], "container_name": "doltsamples-cloudbeaver", "mem_limit": "640m",
            "ports": [f"127.0.0.1:{P['cloudbeaver']}:8978"],
            "environment": {"CB_SERVER_URL": f"http://127.0.0.1:{P['cloudbeaver']}",
                            "CLOUDBEAVER_APP_GRANT_CONNECTIONS_ACCESS_TO_ANONYMOUS_TEAM": "true",
                            "CLOUDBEAVER_APP_READ_ONLY_CONNECTION_INFO": "true",
                            "CLOUDBEAVER_SYSTEM_VARIABLES_RESOLVING_ENABLED": "true",
                            "DEMO_PASSWORD": "${DEMO_PASSWORD:-demo}", "ADMIN_PASSWORD": "${ADMIN_PASSWORD:-admin}"},
            "volumes": ["./docker/cloudbeaver/.cloudbeaver.auto.conf:/opt/cloudbeaver/conf/.cloudbeaver.auto.conf:ro",
                        "./build/cloudbeaver/initial-data-sources.conf:/opt/cloudbeaver/conf/initial-data-sources.conf:ro"],
            "depends_on": healthy("dolt", "doltgres"), "restart": "unless-stopped"}
    header = ("# Generated by `make compose` (python3 -m doltsamples compose) from dolt-megasamples.yaml and the\n"
              "# stores in build/stores.json -- do not edit; change the configuration and run it again.\n"
              f"# Written {now()}.\n")
    return header + yaml.safe_dump({"name": "dolt-megasamples", "services": svc}, sort_keys=False, width=200), consoles


def workbench_store(stores, pw):
    demo, admin = quote(pw["demo"], safe=""), quote(pw["admin"], safe="")
    out = []
    if stores["dolt"]:
        db = stores["dolt"][0]["name"]
        out += [{"name": "Dolt (read-only)", "connectionUrl": f"mysql://demo:{demo}@dolt:3306/{db}", "type": "mysql"},
                {"name": "Dolt (full access)", "connectionUrl": f"mysql://admin:{admin}@dolt:3306/{db}", "type": "mysql"}]
    if stores["doltgres"]:
        db = stores["doltgres"][0]["name"]
        out += [{"name": "DoltgreSQL (read-only)", "connectionUrl": f"postgresql://demo:{demo}@doltgres:5432/{db}", "type": "postgres"},
                {"name": "DoltgreSQL (full access)", "connectionUrl": f"postgresql://admin:{admin}@doltgres:5432/{db}", "type": "postgres"}]
    out += [{"name": f"DoltLite {s['name']}", "connectionUrl": f"file:///data/doltlite/{s['name']}.doltlite", "type": "sqlite"}
            for s in stores["doltlite"]]
    for c in out:
        c.update({"isDolt": True, "hideDoltFeatures": False, "useSSL": False})
    return out


def cloudbeaver_sources(stores):
    """docker/cloudbeaver/initial-data-sources.conf with only the served engines' connections, each opening
    the first database that engine serves (a connection that names a database the server lacks fails)."""
    src = json.load(open(os.path.join(ROOT, "docker", "cloudbeaver", "initial-data-sources.conf"), encoding="utf-8"))
    keep = {}
    for key, conn in src["connections"].items():
        engine = "dolt" if conn["configuration"]["host"] == "dolt" else "doltgres"
        if not stores[engine]:
            continue
        db = stores[engine][0]["name"]
        c = conn["configuration"]
        c["database"] = db
        c["url"] = c["url"].rsplit("/", 1)[0] + "/" + db
        keep[key] = conn
    src["connections"] = keep
    out = os.path.join(BUILD, "cloudbeaver", "initial-data-sources.conf")
    ensure_dir(os.path.dirname(out))
    json.dump(src, open(out, "w", encoding="utf-8"), indent=2)


def ensure_doltgres_catalog(password):
    """DoltgreSQL's own `postgres` database in the served base, created once by starting the image over
    the empty base: the image creates it only on an empty data directory, and the base is not empty
    once stores are mounted into it."""
    base = ensure_dir(os.path.join(DATA, "serve", "doltgres"))
    if os.path.isdir(os.path.join(base, "postgres", ".dolt")):
        return
    name = "doltsamples-doltgres-catalog"
    run("docker", "rm", "-f", name)
    p = run("docker", "run", "-d", "--name", name, "--label", TRANSIENT, "--memory", "1g",
            "-e", f"DOLTGRES_PASSWORD={password}", "-v", f"{base}:/var/lib/doltgres", versions()["doltgres"]["image"])
    if p.returncode != 0:
        sys.exit(f"could not initialise DoltgreSQL's catalog: {p.stderr.strip()[:200]}")
    try:
        ok = 0
        for _ in range(180):
            q = run("docker", "exec", "-e", f"PGPASSWORD={password}", name, "psql", "-X", "-h", "127.0.0.1",
                    "-U", "postgres", "-d", "postgres", "-tAc", "SELECT 1")
            ok = ok + 1 if q.returncode == 0 else 0
            if ok == 2:
                break
            time.sleep(1)
        run("docker", "stop", "-t", "30", name)
    finally:
        run("docker", "rm", "-f", name)


def clean_placeholders():
    """The empty mount points Docker leaves in the served bases for stores no longer served; only
    while the stack is down, when nothing is mounted over them."""
    up = set(run("docker", "ps", "--format", "{{.Names}}").stdout.split())
    if up & set(CONTAINERS.values()):
        return
    run("docker", "run", "--rm", "--label", TRANSIENT, "-v", f"{os.path.join(DATA, 'serve')}:/s", "--entrypoint", "sh",
        lite_image(), "-c", "for d in /s/dolt /s/doltgres /s/doltlite; do [ -d $d ] && "
                            "find $d -mindepth 1 -maxdepth 1 \\( -type d -empty -o -type f -size 0 -name '*.doltlite' \\) -delete; done; true")


def write(cfg):
    holder = lock_held()
    if holder:
        sys.exit(f"{holder} holds build/build.lock: a build is writing the stores. `make up` once it has finished.")
    stores, missing = served(cfg)
    pw = passwords()
    for base in ("dolt", "doltgres", "doltlite"):
        ensure_dir(os.path.join(DATA, "serve", base))
    clean_placeholders()
    if stores["doltgres"]:
        ensure_doltgres_catalog(pw["doltgres"])
    text, consoles = compose(cfg, stores, pw)
    with open(COMPOSE, "w", encoding="utf-8") as fh:
        fh.write(text)
    ensure_dir(os.path.dirname(STORE))
    json.dump(workbench_store(stores, pw), open(STORE, "w", encoding="utf-8"))
    cloudbeaver_sources(stores)
    stack = {"ports": cfg.ports, "containers": CONTAINERS, "network": NETWORK, "passwords": pw, "consoles": consoles}
    serve = {"written": now(), "stack": stack,
             "engines": {e: [{k: s[k] for k in s if k != "path"} | {"store": rel(s["path"])} for s in stores[e]] for e in ENGINES},
             "missing": [{"engine": e, "history": h, "database": db, "why": why} for e, h, db, why in missing]}
    save_json(SERVE, serve)
    n = {e: len(stores[e]) for e in ENGINES}
    print(f"  . compose.yaml: Dolt {n['dolt']}, DoltgreSQL {n['doltgres']}, DoltLite {n['doltlite']} database(s); "
          f"consoles: {', '.join(consoles) or 'none'}")
    for e, h, db, why in missing:
        print(f"  ! {e} {h} {db}: not served, {why}")
    return serve


def up(cfg):
    serve = write(cfg)
    if not any(serve["engines"].values()):
        sys.exit("nothing is built yet: `make export` and `make build` first")
    p = run("docker", "compose", "up", "-d", "--remove-orphans", capture_output=False)
    if p.returncode != 0:
        return p.returncode
    from doltsamples import landing
    landing.write()
    urls()
    return 0


def down():
    if not os.path.exists(COMPOSE):
        print("no compose.yaml: nothing was brought up from this checkout")
        return 0
    return run("docker", "compose", "down", capture_output=False).returncode


def status():
    return run("docker", "ps", "--filter", "label=com.docker.compose.project=dolt-megasamples",
               "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}", capture_output=False).returncode


def urls():
    s = load_json(SERVE, {}) or {}
    P, consoles = (s.get("stack") or {}).get("ports") or {}, (s.get("stack") or {}).get("consoles") or []
    e = s.get("engines") or {}
    if "landing" in consoles:
        print(f"\n  open http://127.0.0.1:{P['landing']}/ -- every database served, how to connect, and the consoles")
    if e.get("dolt"):
        print(f"  Dolt        127.0.0.1:{P['dolt']}  (MySQL protocol; demo/admin)  {len(e['dolt'])} database(s)")
    if e.get("doltgres"):
        print(f"  DoltgreSQL  127.0.0.1:{P['doltgres']}  (PostgreSQL protocol; demo/admin)  {len(e['doltgres'])} database(s)")
    if e.get("doltlite"):
        print(f"  DoltLite    docker exec -it {CONTAINERS['doltlite']} doltlite /data/<name>.doltlite  {len(e['doltlite'])} file(s)")
    for c in consoles:
        if c != "landing":
            print(f"  {c:<11} http://127.0.0.1:{P[c]}/")
    return 0
