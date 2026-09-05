#!/usr/bin/env python3
"""Measure both engines on disk, and check they are holding the same data.

  python3 scripts/measure.py [--only sakila]

For every database this records:

* **bytes on disk, per engine.** `du -sb` of the directory each engine keeps that database in --
  `/var/lib/mysql/<db>` for MySQL (InnoDB file-per-table gives one directory per schema) and
  `<data>/<db>` for Dolt. This is the number the experiment is about: what the engine actually costs
  on the filesystem, indexes, overhead and all.
* **what MySQL thinks it uses**, from `information_schema` (`data_length + index_length`). It is
  always smaller than the directory, because it does not count the tablespace's free pages, and the
  gap is worth showing rather than hiding.
* **rows, counted on both sides.** A size comparison between two databases holding different data
  would be meaningless, so every table is counted in MySQL and in Dolt and any disagreement is
  recorded. `COUNT(*)` is exact on both -- `table_rows` in `information_schema` is an InnoDB
  estimate and is not used.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, DOLT_IMAGE, DUMPS, MYSQL_CONTAINER, databases, dolt, human,  # noqa: E402
                    load_results, mysql, run, save_results)


def mysql_disk_bytes(db):
    p = run("docker", "exec", MYSQL_CONTAINER, "du", "-sb", f"/var/lib/mysql/{db}")
    return int(p.stdout.split()[0]) if p.returncode == 0 and p.stdout.split() else None


def dolt_disk_bytes(db):
    p = run("docker", "run", "--rm", "-v", f"{DATA}:/var/lib/dolt", "--entrypoint", "du",
            DOLT_IMAGE, "-sb", f"/var/lib/dolt/{db}")
    return int(p.stdout.split()[0]) if p.returncode == 0 and p.stdout.split() else None


def mysql_tables(db):
    return [r[0] for r in mysql(
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema='{db}' AND table_type='BASE TABLE' ORDER BY table_name")]


def mysql_rows(db, tables):
    if not tables:
        return 0, {}
    sql = " UNION ALL ".join(f"SELECT '{t}', COUNT(*) FROM `{db}`.`{t}`" for t in tables)
    per = {r[0]: int(r[1]) for r in mysql(sql)}
    return sum(per.values()), per


def dolt_rows(db, tables):
    if not tables:
        return 0, {}
    sql = " UNION ALL ".join(f"SELECT '{t}', COUNT(*) FROM `{t}`" for t in tables)
    p = dolt("--data-dir", "/var/lib/dolt", "--use-db", db, "sql", "-r", "csv", "-q", sql)
    if p.returncode != 0:
        return None, {}
    per = {}
    for line in p.stdout.splitlines():
        parts = line.rsplit(",", 1)
        if len(parts) == 2 and parts[1].strip().isdigit():
            per[parts[0].strip().strip('"')] = int(parts[1])
    return sum(per.values()), per


def object_counts(db):
    """Views and routines on each side.

    mysqldump wraps them in MySQL's version-gated comments (`/*!50001 CREATE ALGORITHM ... */`),
    which Dolt does not parse, so they can go missing while every row still loads. Their storage
    cost is a definition string, but a comparison that quietly dropped part of one database would
    not be worth publishing, so both sides are counted.
    """
    my_views = int(mysql(f"SELECT COUNT(*) FROM information_schema.views "
                         f"WHERE table_schema='{db}'")[0][0])
    my_routines = int(mysql(f"SELECT COUNT(*) FROM information_schema.routines "
                            f"WHERE routine_schema='{db}'")[0][0])
    p = dolt("--data-dir", "/var/lib/dolt", "--use-db", db, "sql", "-r", "csv", "-q",
             "SELECT (SELECT COUNT(*) FROM information_schema.views WHERE table_schema=DATABASE()), "
             "(SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema=DATABASE())")
    do_views = do_routines = None
    for line in p.stdout.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 2 and all(x.isdigit() for x in parts):
            do_views, do_routines = int(parts[0]), int(parts[1])
    return dict(views_mysql=my_views, views_dolt=do_views,
                routines_mysql=my_routines, routines_dolt=do_routines)


def measure(db, results):
    entry = results.setdefault(db, {})
    tables = mysql_tables(db)
    my_rows, my_per = mysql_rows(db, tables)
    do_rows, do_per = dolt_rows(db, tables)

    mismatched = sorted(t for t in tables if my_per.get(t) != do_per.get(t))
    entry["tables"] = len(tables)
    entry["rows_mysql"] = my_rows
    entry["rows_dolt"] = do_rows
    entry["row_mismatches"] = {t: {"mysql": my_per.get(t), "dolt": do_per.get(t)}
                               for t in mismatched[:20]}
    entry["mysql_disk_bytes"] = mysql_disk_bytes(db)
    entry["mysql_logical_bytes"] = int(mysql(
        f"SELECT COALESCE(SUM(data_length+index_length),0) FROM information_schema.tables "
        f"WHERE table_schema='{db}'")[0][0])
    entry["dolt_disk_bytes"] = dolt_disk_bytes(db)
    dump = os.path.join(DUMPS, f"{db}.sql")
    entry["dump_bytes"] = os.path.getsize(dump) if os.path.exists(dump) else None
    entry.update(object_counts(db))

    md, dd = entry["mysql_disk_bytes"], entry["dolt_disk_bytes"]
    ratio = f"{dd / md:5.2f}x" if md and dd else "    -"
    flag = "x" if mismatched else "."
    missing = ((entry["views_mysql"] - (entry["views_dolt"] or 0))
               + (entry["routines_mysql"] - (entry["routines_dolt"] or 0)))
    print(f"  {flag} {db:<24} MySQL {human(md or 0):>10}   Dolt {human(dd or 0):>10}   {ratio}"
          + (f"   {len(mismatched)} table(s) differ" if mismatched else "")
          + (f"   {missing} view/routine(s) missing in Dolt" if missing > 0 else ""))
    return entry


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append")
    a = ap.parse_args()

    results = load_results()
    names = a.only or [d for d in databases() if os.path.isdir(os.path.join(DATA, d))]
    print(f"measuring {len(names)} database(s)")
    for db in names:
        measure(db, results)
        save_results(results)

    bad = [d for d in names if results[d].get("row_mismatches")]
    my = sum(results[d].get("mysql_disk_bytes") or 0 for d in names)
    do = sum(results[d].get("dolt_disk_bytes") or 0 for d in names)
    print(f"\ntotal   MySQL {human(my)}   Dolt {human(do)}"
          + (f"   {do / my:.2f}x" if my else ""))
    if bad:
        print(f"row counts disagree in: {', '.join(bad)} — the comparison is not valid for those")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
