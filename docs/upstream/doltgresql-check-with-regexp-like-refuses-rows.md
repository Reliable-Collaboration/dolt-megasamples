# DoltgreSQL 1.3.1: a CHECK constraint calling regexp_like refuses every row

Record: `knowledge/tools/doltgresql-1-3-1.md`.

**Steps:**

```sql
CREATE TABLE c1 (id int NOT NULL, z character(5),
  CONSTRAINT c1_chk CHECK (regexp_like((z)::text, '^[0-9]+$'::text)));
INSERT INTO c1 VALUES (1, '12345');
```

**Result:** `CREATE TABLE` is accepted and the `INSERT` answers `at or near "as": syntax error`; `COPY` into the table answers the same. `CAST(z AS text)` fails the same way; `regexp_like(z, '^[0-9]+$')` without the casts works and is enforced (a non-matching value is refused). Checks of other shapes with casts -- `(x)::text = ANY (ARRAY[...])`, `(q)::integer > 0`, `upper((r)::text) = 'G'` -- work. Expected: PostgreSQL accepts and enforces all of them.

**Why it matters:** the `pubs` sample's four regex checks, as pg_dump writes them, make their tables unwritable on restore.
