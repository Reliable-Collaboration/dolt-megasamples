# DoltgreSQL 1.3.1: a named NOT NULL column constraint refuses the whole table

Record: `knowledge/tools/doltgresql-1-3-1.md`.

**Steps:**

```sql
CREATE TABLE t (
    id integer CONSTRAINT t_id_not_null NOT NULL,
    v text
);
```

**Result:** `non-foreign key column constraint names are not yet supported`, and the table is not created, so everything defined over it fails too. PostgreSQL 18 accepts it, and pg_dump 18 writes this form for every NOT NULL constraint whose name is not the generated one (the AdventureWorks sample has six, in three tables).
