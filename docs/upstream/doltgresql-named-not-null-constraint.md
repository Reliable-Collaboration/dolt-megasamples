# DoltgreSQL 1.3.1: a named NOT NULL column constraint refuses the whole table

*Found on DoltgreSQL 1.3.1, the version dolt-megasamples pins by image digest (`sha256:6c85cb1f35be…`). It was the newest release on 2026-09-10; no newer release has been tried.*

Record: `knowledge/tools/doltgresql-1-3-1.md`.

**Steps:**

```sql
CREATE TABLE t (
    id integer CONSTRAINT t_id_not_null NOT NULL,
    v text
);
```

**Result:** `non-foreign key column constraint names are not yet supported`, and the table is not created, so everything defined over it fails too. PostgreSQL 18 accepts it, and pg_dump 18 writes this form for every NOT NULL constraint whose name is not the generated one (the AdventureWorks sample has six, in three tables).

**Where it comes from** (read in the v1.3.1 source, not patched): `nodeColumnTableDef` in `server/ast/column_table_def.go` (lines 35-39) refuses a constraint name on `NOT NULL`, `DEFAULT` and `UNIQUE` alike. Accepting the name on `NOT NULL`, even without keeping it, would let such tables load.
