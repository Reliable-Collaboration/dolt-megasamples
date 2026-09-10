# DoltgreSQL 1.3.1: a table with a STORED generated column accepts one alteration, then refuses every row

*Found on DoltgreSQL 1.3.1, the version dolt-megasamples pins by image digest (`sha256:6c85cb1f35be…`). It was the newest release on 2026-09-10; no newer release has been tried.*

Record: `knowledge/tools/doltgresql-1-3-1.md`, `knowledge/questions/doltgresql-generated-column-alteration.md`.

**Steps** (psql against `dolthub/doltgresql:1.3.1`, digest `sha256:6c85cb1f35beabf47f094336a420255130b841b1645f36d79ef046276af36851`):

```sql
CREATE TABLE g2 (id int NOT NULL, a numeric(19,4), b smallint,
                 c numeric(38,6) GENERATED ALWAYS AS (COALESCE(a * (b)::numeric, 0.0)) STORED);
ALTER TABLE ONLY g2 ADD CONSTRAINT g2_pkey PRIMARY KEY (id);   -- accepted
INSERT INTO g2 VALUES (1, 2.5, 4, DEFAULT);
```

**Result:** `ERROR: Invalid default value for '(coalesce("a" * "b"::NUMERIC as a * b::NUMERIC,0.0))': at or near "as": syntax error`. The same error answers any later `CREATE INDEX`, `COPY` or `ALTER TABLE` on the table; adding a foreign key answers `receiveMessage recovered panic: Invalid default value ...`. Without the `ALTER`, the `INSERT` succeeds and the column is computed (10.000000). The order of the two alterations does not matter, nor does the cast (`COALESCE(a * b, 0.0)` fails the same way). Expected: PostgreSQL 18.6 accepts all of it.

**Why it matters:** pg_dump writes every primary key as an `ALTER TABLE ... ADD CONSTRAINT` after `CREATE TABLE`, so any dumped table with a stored generated column becomes unwritable after restore.
