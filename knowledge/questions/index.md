# questions

## Concepts
* [Does a later DoltgreSQL accept a second alteration of a table with a STORED generated column?](doltgresql-generated-column-alteration.md) - DoltgreSQL 1.3.1 accepts one ALTER TABLE or CREATE INDEX on such a table and refuses the next with a syntax error in its own re-serialised expression; whether a newer release fixes it decides whether adventureworks_lt's indexes can be carried.
* [Why does a PL/pgSQL trigger comparing NEW and OLD fields fail on DoltgreSQL at run time?](doltgresql-trigger-old-record.md) - The port's BEFORE UPDATE triggers are created but every UPDATE that fires one answers `record "old" has no field "*"`; the instance that stays up cannot take updates on those tables until this is understood.
* [What does DoltLite make durable per autocommitted statement?](doltlite-durability-per-statement.md) - sqlite_rowwise fsyncs on every statement by SQLite's default; DoltLite's README says nothing about it, and its file grew to 319 MB for 48,317 autocommitted statements before VACUUM, so the two per-row baselines may not be paying the same durability.
