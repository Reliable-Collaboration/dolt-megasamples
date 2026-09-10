# DoltgreSQL 1.3.1: a CHECK constraint calling regexp_like refuses every row

*Found on DoltgreSQL 1.3.1, the version dolt-megasamples pins by image digest (`sha256:6c85cb1f35be…`). It was the newest release on 2026-09-10; no newer release has been tried.*

Record: `knowledge/tools/doltgresql-1-3-1.md`.

**Steps:**

```sql
CREATE TABLE c1 (id int NOT NULL, z character(5),
  CONSTRAINT c1_chk CHECK (regexp_like((z)::text, '^[0-9]+$'::text)));
INSERT INTO c1 VALUES (1, '12345');
```

**Result:** `CREATE TABLE` is accepted and the `INSERT` answers `at or near "as": syntax error`; `COPY` into the table answers the same. `CAST(z AS text)` fails the same way; `regexp_like(z, '^[0-9]+$')` without the casts works and is enforced (a non-matching value is refused). Checks of other shapes with casts -- `(x)::text = ANY (ARRAY[...])`, `(q)::integer > 0`, `upper((r)::text) = 'G'` -- work. Expected: PostgreSQL accepts and enforces all of them.

**Where it may come from** (a reading of the v1.3.1 source, not run): doltgresql has no `regexp_like` of its own, so go-mysql-server's is used; its `String()` prints its cast argument with the alias (`sql/expression/function/regexp_like.go` lines 132-138), the check is stored in that form (`sql/plan/alter_check.go` line 172), and parsing it back on `INSERT` fails at `as`. This looks like the same alias printing as the generated-column report.

**Why it matters:** the `pubs` sample's four regex checks, as pg_dump writes them, make their tables unwritable on restore.
