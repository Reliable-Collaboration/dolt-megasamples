# sources

## Concepts
* [The DoltgreSQL issues filed from this repository on 2026-09-11, and DoltHub's response](doltgresql-issues-filed-2026-09-11.md) - Fifteen issues on dolthub/doltgresql (3323 to 3337) and one comment on the existing issue 3113, each backed by a public reproduction repository under Reliable-Collaboration that runs the failing SQL side by side with PostgreSQL 18.6; as read on 2026-09-12, all are open and labelled "customer issue", eleven have a fix pull request open, and none is in a release.
* [DoltgreSQL README (dolthub/doltgresql, main)](doltgresql-readme.md) - The project's own description of what DoltgreSQL is, how data goes in, what it does not do, and its correctness and performance claims.
* [DoltgreSQL release v1.3.1 and its Docker image](doltgresql-release-v1-3-1.md) - The release current on 2026-09-10, its publication date, and the digest of the Docker Hub image the experiment pins.
* [DoltLite LICENSE.md](doltlite-license.md) - The licence terms of DoltLite -- Apache-2.0 for the DoltLite extensions over public-domain SQLite -- and why GitHub reports no licence.
* [DoltLite README (dolthub/doltlite, main)](doltlite-readme.md) - The project's own description of DoltLite, how it installs, how stock SQLite files are treated, where it departs from SQLite, and its beta status.
* [DoltLite release v0.50.10 and the garbage-collection fix for issue 2820](doltlite-release-v0-50-10.md) - The release published on 2026-09-11, one day after the pinned v0.50.9, which carries pull request 2836 -- the fix for the VACUUM "out of memory" failure this repository reported as issue 2820 -- and the checksums of its two Debian packages, downloaded so the pin can move if the maintainer asks.
* [DoltLite release v0.50.9 and its packages](doltlite-release-v0-50-9.md) - The release current on 2026-09-10, its assets, the checksums of the two Debian packages the experiment builds its image from, and the release cadence around it.
* [SQLite download page (current release)](sqlite-download-page.md) - What the newest SQLite release was on 2026-09-10, read to compare with the SQLite version DoltLite reports as its base.
