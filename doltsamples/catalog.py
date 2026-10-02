"""Reading a database back: rows per table, the index set and object counts, the same way from the
corpus's reference and from a Dolt engine's store, and comparing the two.

Shared by dolt-megasamples' build (every store is checked against the reference its export
recorded) and by dolt-unofficial-benchmarking, which reads the baselines the same way.
"""
import os, re, time

from doltsamples.dialects import doltgres as doltgres_dialect
from doltsamples.util import run

PW = "doltsamples"      # the postgres superuser's password in every DoltgreSQL container started here


def psql(container, db, sql, password=PW):
    """One query, tuples only, unaligned; the CompletedProcess."""
    return run("docker", "exec", "-e", f"PGPASSWORD={password}", container, "psql", "-X", "-h", "127.0.0.1",
               "-U", "postgres", "-d", db, "-tA", "-c", sql)


def psql_value(container, db, sql, password=PW):
    p = psql(container, db, sql, password)
    if p.returncode != 0:
        raise RuntimeError(f"{container}: {sql[:80]}: {(p.stderr or '').strip()[:200]}")
    return p.stdout.strip()


def psql_file(container, db, inside, password=PW):
    """Load a file the way both engines of the pair get it: quietly, output discarded, every
    error reported with its line, never stopping at the first one -- the row and index checks
    are the arbiter, and psql's per-line errors say exactly which object was refused."""
    return run("docker", "exec", "-e", f"PGPASSWORD={password}", container, "psql", "-X", "-h", "127.0.0.1",
               "-U", "postgres", "-d", db, "-q", "-o", "/dev/null", "-v", "ON_ERROR_STOP=0", "-f", inside)


PSQL_ERROR = re.compile(r"^psql:(?P<file>\S+?):(?P<line>\d+): (?P<level>ERROR|FATAL|PANIC):\s*(?P<msg>.*)$")


def psql_errors(p, prepared_text=None):
    """[{line, message, object}] for every ERROR psql reported while loading a file."""
    out, index = [], None
    for line in (p.stderr or "").splitlines():
        m = PSQL_ERROR.match(line.strip())
        if not m:
            continue
        entry = {"line": int(m.group("line")), "message": m.group("msg")[:200]}
        if prepared_text is not None:
            if index is None:
                # one pass over the file for every error of the load: a refused large table reports
                # an error per row, and splitting the file again for each stalled a unit for hours
                index = doltgres_dialect.block_index(prepared_text)
            t, name = doltgres_dialect.block_at(index, entry["line"])
            entry["object"] = f"{t}: {name}" if t else None
        out.append(entry)
    return out


def wait_pg(container, seconds=180, password=PW):
    """Ready means two consecutive answers over TCP a second apart: the image's entrypoint
    restarts the server once after initialising, and a single success can land before that."""
    ok = 0
    for _ in range(seconds):
        if psql(container, "postgres", "SELECT 1", password).returncode == 0:
            ok += 1
            if ok == 2:
                return True
        else:
            ok = 0
        time.sleep(1)
    raise RuntimeError(f"{container} did not answer within {seconds}s: "
                       + run("docker", "logs", "--tail", "5", container).stderr[-300:])



USER_SCHEMAS = "('pg_catalog', 'information_schema', 'pg_toast')"


def pg_catalog(container, db):
    """Rows per base table, the index set, and object counts -- read the same way from every
    PostgreSQL-speaking engine."""
    tables = [t for t in psql_value(
        container, db, "SELECT table_schema || '.' || table_name FROM information_schema.tables "
        f"WHERE table_type = 'BASE TABLE' AND table_schema NOT IN {USER_SCHEMAS} ORDER BY 1").splitlines()
        if t and not t.split(".", 1)[1].startswith("dolt_")]
    rows = {}
    for t in tables:
        s, n = t.split(".", 1)
        p = psql(container, db, f'SELECT COUNT(*) FROM "{s}"."{n}"')
        rows[t] = int(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip().isdigit() else None
    idx = psql_value(container, db, "SELECT schemaname || '.' || tablename || '|' || indexname || '|' || indexdef "
                     f"FROM pg_indexes WHERE schemaname NOT IN {USER_SCHEMAS} ORDER BY 1")
    indexes = sorted(" ".join(l.split()) for l in idx.splitlines() if l.strip())
    objects = {}
    for key, sql in (("views", f"SELECT COUNT(*) FROM pg_views WHERE schemaname NOT IN {USER_SCHEMAS}"),
                     ("triggers", "SELECT COUNT(*) FROM pg_trigger WHERE NOT tgisinternal"),
                     ("routines", "SELECT COUNT(*) FROM information_schema.routines "
                                  f"WHERE specific_schema NOT IN {USER_SCHEMAS}"),
                     ("foreign_keys", "SELECT COUNT(*) FROM information_schema.table_constraints "
                                      f"WHERE constraint_type = 'FOREIGN KEY' AND table_schema NOT IN {USER_SCHEMAS}")):
        p = psql(container, db, sql)
        objects[key] = int(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip().isdigit() else None
    return {"rows": rows, "indexes": indexes, "objects": objects}



def lite_sh(cmd, container):
    return run("docker", "exec", container, "sh", "-c", cmd)


def q(name):
    return '"' + name.replace('"', '""') + '"'


def lit(name):
    return "'" + name.replace("'", "''") + "'"


def lite_catalog(binary, inside_path, container, script_host, script_inside, tables=None):
    """Rows per table and the index set of one file, through the named shell.

    Two scripts: the first counts every table and lists its indexes, the second reads the columns
    of every index the first found. Written to a file and `.read`, so hundreds of tables cost two
    process starts, and an error on one statement is reported and does not stop the rest."""
    p = lite_sh(f"{binary} {inside_path} \"SELECT name FROM sqlite_schema WHERE sql LIKE 'CREATE VIRTUAL%' ORDER BY 1\"",
                container)
    virtual = [l for l in p.stdout.splitlines() if l.strip()]
    if tables is None:
        p = lite_sh(f"{binary} {inside_path} \"SELECT name FROM sqlite_schema WHERE type = 'table' "
                    f"AND name NOT LIKE 'sqlite_%' ORDER BY 1\"", container)
        # a virtual table's shadow tables hold its index pages, not data: the loads rebuild the
        # index, so its page layout is not expected to match and they are left out
        tables = [l for l in p.stdout.splitlines() if l.strip()
                  and not any(l.startswith(v + "_") for v in virtual)]
    lines = []
    for t in tables:
        lines += [f"SELECT '@rows', {lit(t)}, COUNT(*) FROM {q(t)};", f"SELECT '@table', {lit(t)};",
                  f"PRAGMA index_list({q(t)});"]
    rows, listed, errors = {}, {}, []
    out = _lite_script(binary, inside_path, lines, container, script_host, script_inside)
    current = None
    for line in out.stdout.splitlines():
        bits = line.split("|")
        if bits[0] == "@rows" and len(bits) == 3:
            rows[bits[1]] = int(bits[2]) if bits[2].isdigit() else None
        elif bits[0] == "@table":
            current = bits[1]
        elif current is not None and len(bits) >= 4 and bits[0].isdigit():
            listed[(current, bits[1])] = (bits[2], bits[3])        # unique, origin
    errors += [l for l in out.stderr.splitlines() if l.strip()]
    for t in tables:
        rows.setdefault(t, None)
    lines = []
    for (t, name) in listed:
        lines += [f"SELECT '@index', {lit(t)}, {lit(name)};", f"PRAGMA index_info({q(name)});"]
    cols, key = {}, None
    if lines:
        out = _lite_script(binary, inside_path, lines, container, script_host, script_inside)
        for line in out.stdout.splitlines():
            bits = line.split("|")
            if bits[0] == "@index" and len(bits) == 3:
                key = (bits[1], bits[2])
                cols[key] = []
            elif key is not None and len(bits) == 3 and bits[0].isdigit():
                cols[key].append(bits[2])
        errors += [l for l in out.stderr.splitlines() if l.strip()]
    indexes = sorted(f"{t}|{name}|unique={u}|origin={o}|{','.join(cols.get((t, name), []))}"
                     for (t, name), (u, o) in listed.items())
    p = lite_sh(f"{binary} {inside_path} \"SELECT type || '|' || COUNT(*) FROM sqlite_schema "
                f"WHERE name NOT LIKE 'sqlite_%' GROUP BY type\"", container)
    objects = {l.split("|")[0]: int(l.split("|")[1]) for l in p.stdout.splitlines() if "|" in l}
    p = lite_sh(f"{binary} {inside_path} \"SELECT COUNT(*) FROM sqlite_schema WHERE sql LIKE 'CREATE VIRTUAL%'\"", container)
    objects["virtual tables"] = int(p.stdout.strip()) if p.stdout.strip().isdigit() else None
    return {"rows": rows, "indexes": indexes, "objects": objects, "virtual_tables": virtual,
            "catalog_errors": errors[:10]}


def _lite_script(binary, inside_path, lines, container, script_host, script_inside):
    os.makedirs(os.path.dirname(script_host), exist_ok=True)
    with open(script_host, "w", encoding="utf-8") as fh:
        fh.write(".mode list\n" + "\n".join(lines) + "\n")
    return lite_sh(f"{binary} {inside_path} \".read {script_inside}\"", container)



IDX = re.compile(r"^create (unique )?index ([^\s(]+) on (?:only )?([^\s(]+) ?(?:using (\w+) ?)?\((.*)$")


def canonical_index(entry):
    """One PostgreSQL-pair index as both engines should agree on it.

    pg_indexes.indexdef is printed text, and the two engines print the same index differently:
    PostgreSQL quotes an identifier that is a keyword (`"position"`), DoltgreSQL does not. Comparing
    the text made every such difference a missing index plus an extra one. The definition is read
    back into its parts instead -- unique or not, the table, the method (btree when an engine leaves
    it out), the key list and whatever follows it -- with identifier quotes removed, whitespace
    collapsed and everything outside string literals case-folded. The name stays in the second field,
    where the refusal matching looks for it. SQLite-pair entries, already built from PRAGMA
    index_list and index_info, pass through unchanged."""
    parts = entry.split("|", 2)
    if len(parts) != 3 or not parts[2].lstrip().upper().startswith("CREATE"):
        return entry
    table, name, ddl = parts
    out, i, n = [], 0, len(ddl)
    while i < n:
        c = ddl[i]
        if c == "'":
            j = i + 1
            while j < n:
                if ddl[j] == "'":
                    if j + 1 < n and ddl[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append(ddl[i:j + 1])
            i = j + 1
            continue
        if c != '"':
            out.append(c.lower())
        i += 1
    text = re.sub(r"\s*([(),])\s*", r"\1", " ".join("".join(out).split()))
    table = table.replace('"', "").lower()
    m = IDX.match(text)
    if not m:
        return f"{table}|{name}|{text}"
    unique, _, on, method, rest = m.groups()
    return f"{table}|{name}|unique={bool(unique)}|on={on}|using={method or 'btree'}|({rest}"


def compare(ref, got, dropped=()):
    """What is short: a row-count message or None, and the index report."""
    short = None
    for t, want in ref["rows"].items():
        g = got["rows"].get(t)
        if want is None:   # the export could not count it: the reference is broken, and that is what to say
            short = f"{t}: the reference recorded no row count (the export's shell could not count it); export again"
            break
        if g != want:
            short = f"{t} has {g if g is not None else 'no'} rows, expected {want:,}"
            break
    dropped = set(dropped)
    want_idx = {canonical_index(i) for i in ref["indexes"] if i.split("|")[1] not in dropped}
    got_idx = {canonical_index(i) for i in got["indexes"]}
    missing, extra = want_idx - got_idx, got_idx - want_idx
    # DoltgreSQL 1.3.2 prints `nulls first` after a uuid column in pg_indexes.indexdef where PostgreSQL
    # prints nothing (adventureworks_lt's eight unique rowguid indexes, 2026-09-14; 1.3.1 printed none).
    # The index exists with the same columns, uniqueness and method, so it is not missing; the
    # difference in what the catalog says is kept under ordering_differs, not hidden.
    # the rule is exactly that finding: the source prints no null ordering and the engine prints one;
    # a source that names an ordering, or an engine that prints a different one, is a real difference
    strip = lambda e: re.sub(r" nulls (first|last)\b", "", e)
    differs = []
    for w in sorted(missing):
        if strip(w) != w:
            continue
        twin = next((g for g in extra if strip(g) == w and strip(g) != g), None)
        if twin is not None:
            missing.discard(w)
            extra.discard(twin)
            differs.append(f"{w.split('|')[1]}: expected {w.split('|', 2)[2]}, got {twin.split('|', 2)[2]}")
    report = {"missing": sorted(missing), "extra": sorted(extra),
              "dropped_by_dialect": sorted(dropped), "checked": len(want_idx)}
    if differs:
        report["ordering_differs"] = differs
    extra_tables = sorted(set(got["rows"]) - set(ref["rows"]))
    if extra_tables:
        report["extra_tables"] = extra_tables
    return short, report


