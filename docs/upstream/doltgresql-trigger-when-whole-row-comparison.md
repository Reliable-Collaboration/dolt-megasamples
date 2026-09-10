# DoltgreSQL 1.3.1: a trigger WHEN clause comparing whole rows refuses every UPDATE

*Found on DoltgreSQL 1.3.1, the version dolt-megasamples pins by image digest (`sha256:6c85cb1f35be…`). It was the newest release on 2026-09-10; no newer release has been tried.*

Record: `knowledge/tools/doltgresql-1-3-1.md`, `knowledge/questions/doltgresql-trigger-old-record.md`.

**Steps:**

```sql
CREATE TABLE actor (actor_id integer NOT NULL, first_name character varying(45) NOT NULL,
                    last_update timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL);
CREATE FUNCTION touch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW."last_update" IS NOT DISTINCT FROM OLD."last_update" THEN NEW."last_update" := CURRENT_TIMESTAMP; END IF;
  RETURN NEW;
END $$;
INSERT INTO actor VALUES (1, 'PENELOPE', '2006-02-15 04:34:33');
CREATE TRIGGER touch_upd BEFORE UPDATE ON actor FOR EACH ROW
  WHEN ((old.* IS DISTINCT FROM new.*)) EXECUTE FUNCTION touch();
UPDATE actor SET first_name = first_name WHERE actor_id = 1;
```

**Result:** the trigger is created, and the `UPDATE` answers `ERROR: record "old" has no field "*"`. The same body under `WHEN (old.first_name IS DISTINCT FROM new.first_name OR old.last_update IS DISTINCT FROM new.last_update)` works (an unchanged row leaves `last_update`, a changed one moves it), so the whole-row comparison in the `WHEN` clause is what is not evaluated. PostgreSQL accepts both forms and, for a no-op update, reports `UPDATE 1` where DoltgreSQL reports `UPDATE 0`.

**Where it may come from** (a reading of the v1.3.1 source, not run): the `WHEN` clause is compiled as a PL/pgSQL `RETURN` (`server/ast/create_trigger.go` lines 86-106), and variable substitution joins `old`, `.` and `*` into one name and then looks up a field called `*` (`server/plpgsql/statements.go` line 547, `server/plpgsql/interpreter_stack.go` lines 212-233).

**Why it matters:** `WHEN (old.* IS DISTINCT FROM new.*)` is the idiom for "only when the row changed" and pg_dump reproduces it verbatim.
