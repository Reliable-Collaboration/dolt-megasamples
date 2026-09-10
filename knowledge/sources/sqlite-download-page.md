---
type: Source
title: SQLite download page (current release)
description: What the newest SQLite release was on 2026-09-10, read to compare with the SQLite version DoltLite reports as its base.
resource: https://sqlite.org/download.html
tags:
- sqlite
- upstream
status: stable
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-10T03:45:00Z"
sources:
- resource: https://sqlite.org/download.html
  title: SQLite Download Page
  accessed: "2026-09-10"
---

# What was read

The download page on 2026-09-10, looking for the autoconf tarball of the current release.

# Relevant excerpt

The current source tarball on the page is `2026/sqlite-autoconf-3530400.tar.gz`, i.e. SQLite 3.53.4 (paraphrase: only the file name was extracted from the page).

# What it was used to decide

`doltlite -version` reports `DoltLite v0.50.9 (SQLite 3.54.0, 64-bit)`: the fork tracks SQLite's trunk ahead of the newest release, so no stock `sqlite3` of the same version can be installed for the baseline. The baseline is Debian 13's `sqlite3` 3.46.1, and the version gap is recorded rather than hidden: [the sqlite3 shell 3.46.1](/tools/sqlite3-shell-3-46-1.md), [pair load shapes](/decisions/pair-load-shapes-and-measurement.md).
