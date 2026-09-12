# DoltgreSQL 1.3.1: a named NOT NULL column constraint refuses the whole table

*Found on DoltgreSQL 1.3.1, the version dolt-megasamples measures, named by image digest (`sha256:6c85cb1f35be…`, `versions.json`). It was the newest release on 2026-09-10; v1.3.2 (2026-09-12) has not been tried.*

Record: `knowledge/tools/doltgresql-1-3-1.md`.

Reported upstream: https://github.com/dolthub/doltgresql/issues/3332 (2026-09-11), with the reproduction repository https://github.com/Reliable-Collaboration/repro-doltgresql-bug-named-not-null, which runs the failing SQL side by side with the reference engine. As read on 2026-09-12: fix pull request 3354 open, unmerged.

**Steps:**

```sql
CREATE TABLE t (
    id integer CONSTRAINT t_id_not_null NOT NULL,
    v text
);
```

**Result:** `non-foreign key column constraint names are not yet supported`, and the table is not created, so everything defined over it fails too. PostgreSQL 18 accepts it, and pg_dump 18 writes this form for every NOT NULL constraint whose name is not the generated one (the AdventureWorks sample has six, in three tables).

**Where it comes from** (read in the v1.3.1 source, not patched): `nodeColumnTableDef` in `server/ast/column_table_def.go` (lines 35-39) refuses a constraint name on `NOT NULL`, `DEFAULT` and `UNIQUE` alike. Accepting the name on `NOT NULL`, even without keeping it, would let such tables load.
