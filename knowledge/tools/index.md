# tools

## Concepts
* [DoltgreSQL 1.3.1](doltgresql-1-3-1.md) - The PostgreSQL-compatible Dolt server the PostgreSQL pair measures, pinned by image digest, with what was verified by loading sakila into it before the experiment ran.
* [DoltLite v0.50.10](doltlite-0-50-10.md) - The DoltLite release the SQLite pair measures since 2026-09-12 (one version per result set; v0.50.9 before), built here into an image from its two checksummed Debian packages, with what was verified on it before the loads ran again -- above all that VACUUM now collects a per-row-commit file v0.50.9 answered "out of memory" on.
* [DoltLite v0.50.9](doltlite-0-50-9.md) - The SQLite fork with a versioned storage engine that the SQLite pair measured from 2026-09-10 to 2026-09-12 at v0.50.9, named by the checksums of its Debian packages and built here into an image from them, with what was verified by replaying sakila into it before the experiment ran; superseded by v0.50.10 on 2026-09-12, every DoltLite unit measured again.
* [PostgreSQL 18.6 as the baseline of the PostgreSQL pair](postgresql-18-6-baseline.md) - The image, data-directory layout, dump tool and client used for the PostgreSQL side of the pair, and how its size and readiness are read.
* [The sqlite3 shell 3.46.1 as the baseline of the SQLite pair](sqlite3-shell-3-46-1.md) - Debian 13's sqlite3 shell, which writes the dumps and is the stock engine beside DoltLite; what its .dump output looks like and how it behaves on errors.
