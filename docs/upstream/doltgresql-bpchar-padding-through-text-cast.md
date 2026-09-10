# DoltgreSQL 1.3.1: a character(n) value keeps its padding through a cast to text

Record: `knowledge/tools/doltgresql-1-3-1.md`.

**Steps:**

```sql
CREATE TABLE c1 (id int NOT NULL, class character(2),
  CONSTRAINT c1_ck CHECK (((upper((class)::text) = ANY (ARRAY['L'::text, 'M'::text, 'H'::text])) OR (class IS NULL))));
INSERT INTO c1 VALUES (1, 'L ');
SELECT '[' || (class)::text || ']' FROM c1;
```

**Result:** the `INSERT` answers `Check constraint "c1_ck" violated`; with the check removed, the `SELECT` answers `[L ]`. PostgreSQL answers `[L]` (the cast from bpchar to text strips the padding) and accepts the row; `COPY` behaves the same way on both. `rtrim((class)::text)` restores PostgreSQL's behaviour on DoltgreSQL.

**Why it matters:** pg_dump writes `character(n)` values padded, and the AdventureWorks sample's `CHECK` constraints over `class`, `productline` and `style` refuse every row of `production_product` on restore.
