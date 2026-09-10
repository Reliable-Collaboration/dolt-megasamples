# decisions

## Concepts
* [Pin DoltgreSQL at 1.3.1 by digest, marked so it can be undone](doltgresql-version-pin.md) - Every DoltgreSQL number is measured against one build, named by image digest; the pin is marked in the two places it lives and undoing it is a one-line change plus a rerun.
* [For DoltLite, "the same file" is the dump replayed into a DoltLite-format database](doltlite-same-file.md) - What the SQLite/DoltLite pair loads on the DoltLite side, and why opening the stock SQLite file would have measured SQLite twice.
* [What the dialects change before a load, and what is recorded as refused instead](pair-dialect-rules.md) - The nine named rules of scripts/doltgres_dialect.py and scripts/doltlite_dialect.py, each found by refusal; the objects each engine still refuses, which the report counts; and the preflight table of the quick subset.
* [The load shapes, index policies and measurement rules of the two further pairs](pair-load-shapes-and-measurement.md) - The five shapes per pair, what the deferred and inline index policies mean for pg_dump and .dump output, and how disk, time and memory are read -- and where each departs from the MySQL/Dolt pair and why.
* [DoltgreSQL and DoltLite instances that stay up beside Dolt](stood-up-instances.md) - How the loaded databases are served after the experiment -- a DoltgreSQL server on 5433 with the two accounts, the DoltLite files with their shell, the consoles that can open them, and a landing page that says how to connect.
