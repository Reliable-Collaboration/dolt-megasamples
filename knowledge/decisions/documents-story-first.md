---
type: Decision
title: The documents tell the finding first, in the reader's order, with one figure family
description: The rework of 2026-09-16 after the maintainer's review -- the README opens with the finding for all three pairs and follows it with the evidence in the order a reader asks, REPORT.md carries every table and figure, the figures are one family of dot plots with one colour per engine and one marker per load shape, and every title states what its figure shows, computed from the measurements it draws.
resource: /decisions/documents-story-first.md
tags:
- presentation
- figures
- readme
- decision
status: proposed
trust: verified
generated:
  by: claude-code/claude-fable-5-1
  at: "2026-09-16T15:30:00Z"
verified:
- by: claude-code/claude-fable-5-1
  at: "2026-09-16T15:30:00Z"
sources:
- resource: https://jfly.uni-koeln.de/color/
  title: Okabe and Ito, "Color Universal Design", the eight-colour palette the figures use
  accessed: "2026-09-16"
- resource: https://doi.org/10.1080/01621459.1984.10478080
  title: Cleveland and McGill 1984, "Graphical Perception" -- position on a common scale is read more accurately than length, the reason the figures are dot plots and not bars on log axes
  accessed: "2026-09-16"
- resource: https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary
  title: The Financial Times Visual Vocabulary -- which chart form fits which relationship (deviation, magnitude, correlation)
  accessed: "2026-09-16"
- resource: https://www.storytellingwithdata.com/
  title: Knaflic, "Storytelling with Data" -- the three-minute story, declarative titles, removing clutter
  accessed: "2026-09-16"
- resource: /decisions/pair-load-shapes-and-measurement.md
  title: The five load shapes and two index policies the figures draw
---

# Question

The maintainer's review of the README on 2026-09-16: it read as written for Dolt with the two further pairs added afterwards; the first table held MySQL and Dolt only, so Dolt could not be compared with DoltgreSQL; several figures omitted DoltgreSQL and DoltLite altogether; whole sections gave a size without saying which load or which engine; and there was no place to compare the size of a database across the six engines. The maintainer asked for research into data storytelling and visual presentation, and then for a draft to review. How should the documents be organised and drawn?

# Options considered

* **Keep the structure and add the pairs to every table.** Lost: the reader still meets the versions, the tests and the method before any finding, and three tables per fact keep the engines apart, which is what made looking for patterns between the products impossible.
* **One document carrying everything.** Lost: the README already ran past 600 lines with the evidence in it, and a reader who wants the answer does not get it on the first screen.
* **The finding first, then the evidence in the reader's order; the full evidence in its own document; one figure family.** Chosen. The principles read say the same thing from four directions: lead with the story and put the supporting detail behind it (Knaflic); a figure's title should state its finding; position on a common scale is read more accurately than length, so on a log axis a dot is honest where a bar is not (Cleveland and McGill); one colour per thing being compared, from a palette that survives every common colour-vision deficiency (Okabe and Ito); and a chart form chosen for the relationship it shows -- ratio to a baseline is a deviation, size across engines is a magnitude (the Visual Vocabulary).

# Evidence

The figures drawn on 2026-09-16 from the complete result sets (Dolt 2.3.2, DoltgreSQL 1.3.2, DoltLite 0.50.10), each title computed from the measurements it draws and each checked by eye for collisions and truncation: `headline` (every load of every pair as a ratio of its baseline, disk and time), `sizes-by-engine` (every database in all six engines, the standard load), `history-cost` (a commit per row against the bulk load, database by database), `index-policy-summary` and `index-policy-<pair>` (what maintaining the indexes costs), `memory-by-history` (what each Dolt engine needs to open a store, against its commits), `disk-by-database` and `time-by-database` (every load of every pair). The headline title that day read: "A commit per row costs 57 to 75 times the baseline's disk and 447 to 3,008 times its time, in every engine". Two figures were removed rather than redrawn, `cost-by-mode` and `ratio-by-database`, since the headline and the sizes figure show what they showed with the pairs in.

`make check` after the rework: every invariant checked, none failed, every document matching the measurements, the knowledge bundle canonical.

# Outcome

* **README.md** opens with the finding: the headline figure, the three things that hold across the three pairs, and two six-engine tables (disk and time, totalled over the databases each pair has every load for). Then, in the order a reader asks: how big every database is in every engine (one table, six engine columns); what history costs (a commit per row, disk and time, the three Dolt engines side by side); what keeping the indexes costs; what memory needs (the pairs' study and Dolt's three answers); whether each pair holds the same thing; what was measured (the versions and the five tests); what would make a reviewer hesitate; the machine; reproducing; running; layout; licence. The method's detail moved out.
* **REPORT.md** is new and generated from `docs/templates/REPORT.md`: the machine; every load of every database of every pair, one table per pair and the two by-database figures; the six-engine tables; what maintaining the indexes costs, database by database, with a figure per pair; what each engine refused; the loads' memory; the tests and how each load is performed and measured; and the MySQL/Dolt report in its own words, embedded as a block (`scripts/render.py`'s `embed_report`, which drops the file's own header, human note and machine table, carried once already). `scripts/report.py` no longer writes REPORT.md itself.
* **One figure family** in `scripts/charts.py`: one colour per engine (Okabe and Ito's palette: MySQL blue, PostgreSQL sky blue, SQLite orange, Dolt green, DoltgreSQL vermilion, DoltLite purple), one marker per load shape (a circle for the bulk and one-commit loads, a diamond for one INSERT per row, a square for a commit per row), dots on a common scale wherever the axis is logarithmic, a declarative title computed from the data on every figure, and the pair's coverage stated on each. `scripts/loads.py` is the one accessor the figures and the tables both read, so a number in a figure and the same number in a table come from one function.
* **What stays the same**: no number in either document is typed by a person; `make check` fails if a document disagrees with the measurements; JOURNAL.md keeps the method and the history of the work.

# Status

proposed (2026-09-16; a draft for the maintainer's review, built at the maintainer's request after the research; the maintainer has not yet reviewed it).
