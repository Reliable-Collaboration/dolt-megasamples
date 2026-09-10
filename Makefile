# dolt-megasamples: load the sql-megasamples databases into Dolt and compare disk usage.
# Every target is a thin shim over a script in scripts/, so the experiment can be run without make.
PY ?= python3

# Every target is phony. `docs` is the one that made this matter: a directory named docs/
# exists, so Make considered the target satisfied and silently skipped it -- both directly
# and as a prerequisite of `report`, which is why the documents stayed stale while every
# other step ran. Generated from the targets themselves so a new one cannot be forgotten.
.PHONY: all audit charts check clean clean-data collect docs down environment estimate experiment export help load measure measure-all method-checks preflight progress report run status summary trace up watch \
        export-postgres export-sqlite export-pairs lite-image preflight-pairs run-pg run-lite okf-check test-stack clean-pairs memory-pairs

help:
	@echo "make run        the whole experiment, timed: 5 loads x every database (hours)"
	@echo "make progress   what the run has done, is doing, and has left"
	@echo "make watch      the same, redrawn every minute"
	@echo "make all        the size-only pipeline: export -> load -> measure -> report"
	@echo "make export     mysqldump every database out of a running sql-megasamples MySQL"
	@echo "make load       load those dumps into Dolt, commit and gc"
	@echo "make measure    size both engines and check they hold the same rows"
	@echo "make report     regenerate REPORT.md, the README tables and the figures"
	@echo "make charts     regenerate the figures only (matplotlib, in .venv)"
	@echo "make collect    fold the timed run into build/results.json (make report does this)"
	@echo "make measure-all  row counts and index parity for every mode that was loaded"
	@echo "make preflight  load every schema into both engines before running the loads"
	@echo ""
	@echo "The PostgreSQL/DoltgreSQL and SQLite/DoltLite pairs (scripts/pairs.py):"
	@echo "make lite-image     build the DoltLite image from the pinned .deb packages (checksummed)"
	@echo "make export-pairs   pg_dump every database out of sql-megasamples PostgreSQL; copy and dump its SQLite files"
	@echo "make preflight-pairs  every schema into PostgreSQL, DoltgreSQL, SQLite and DoltLite; what each refuses"
	@echo "make run-pg | run-lite  the five timed loads of a pair (ARGS=\"--only sakila --indexes inline\")"
	@echo "make memory-pairs   what DoltgreSQL and DoltLite need to open each database in each shape (build/memory_pairs.json)"
	@echo "make okf-check      validate the knowledge bundle (knowledge/)"
	@echo "make test-stack     after make up: both accounts on Dolt and DoltgreSQL, the DoltLite files, every console"
	@echo "make audit      check the measurements against invariants that must hold"
	@echo "make docs       regenerate README.md and JOURNAL.md from docs/templates and build/"
	@echo "make trace      what the per-row-commit loads cost in memory as history accumulated"
	@echo "make estimate   project how long a full run takes, from measured rates"
	@echo "make summary    the whole experiment as labelled tables: disk, time, memory, progress"
	@echo "make experiment the row-INSERT and per-row-commit loads, then the report"
	@echo "make check      fail if the report, the README table or a prose number is stale"
	@echo "make up         Dolt, DoltgreSQL, the DoltLite files and the consoles (3307, 5433, 8090-8095)"
	@echo "                SERVE=rowcommit serves the one-commit-per-row loads (default oneshot; also rowinsert,"
	@echo "                rowinsert_inline, rowcommit_inline); SERVE_DATABASES=\"sakila chinook\" or all; DOLT_MEM=8g"
	@echo "make down       all of it down again"
	@echo "make status     what is running"
	@echo "make clean-data delete the Dolt data directory (written as root inside the container)"
	@echo "make clean-pairs delete the PostgreSQL, DoltgreSQL, SQLite and DoltLite stores of every shape (keeps the exports)"

# The experiment needs sql-megasamples' MySQL running: it is the source of every dump.
all: export load measure report

export:
	@$(PY) scripts/export_mysql.py
load:
	@$(PY) scripts/load_dolt.py
measure:
	@$(PY) scripts/measure.py

# Row counts and index parity for every mode that has a data directory, not just the one-shot load.
# run_all.py verifies row counts as each unit finishes; this is what puts the index comparison for
# each mode into results.json, including both index policies.
MEASURE_MODES = oneshot rowinsert rowcommit rowinsert_inline rowcommit_inline
measure-all:
	@for m in $(MEASURE_MODES); do \
	  test -d data/dolt$$(test $$m = oneshot || echo -$$m) && \
	    $(PY) scripts/measure.py --mode $$m || true; \
	done
# collect folds build/progress.json -- what the timed run actually did -- into build/results.json,
# which is what the report and the figures read. Nothing called it, so the documented path of
# `make run` then `make report` built the report from whatever results.json happened to hold, which
# after a `make clean-data` is nothing at all.
collect:
	@$(PY) scripts/collect.py
	@$(PY) scripts/collect_pairs.py

report: environment method-checks collect docs
	@$(PY) scripts/report.py
	@$(PY) scripts/console_page.py
	@$(MAKE) --no-print-directory charts

# The figures. matplotlib lives in .venv because it is this repository's only dependency; the rest
# of the pipeline runs on the system python and shells out to docker.
environment:
	@$(PY) scripts/environment.py >/dev/null && echo "  . recorded the machine into build/environment.json"
method-checks:
	@$(PY) scripts/method_checks.py

charts: .venv/bin/python
	@.venv/bin/python scripts/charts.py

.venv/bin/python:
	@uv venv .venv >/dev/null 2>&1 || python3 -m venv .venv
	@(uv pip install -q matplotlib >/dev/null 2>&1 || .venv/bin/pip install -q matplotlib)
	@echo "  . created .venv with matplotlib"

# The whole experiment, timed: five loads of every database across both engines, resumable and
# observable. Expect many hours -- the per-row-commit phase alone is most of it.
# Two minutes that can save six hours: load every schema, without its rows, into both engines and
# report anything either refuses -- especially anything only one of them refuses.
preflight:
	@$(PY) scripts/preflight.py

run: preflight
	@$(PY) scripts/run_all.py
progress:
	@$(PY) scripts/progress.py
watch:
	@$(PY) scripts/progress.py --watch

# The row-by-row loads used to run here over a hand-picked subset of the smallest databases, which
# is why earlier reports had holes in them. `make run` runs every phase over every database and
# records the timings as well, so that is the only supported way to produce the experiment now.
experiment:
	@echo "'make experiment' ran the row-by-row loads over a subset of the databases and left"
	@echo "the report with gaps in it. Use 'make run' instead -- every phase over every database,"
	@echo "timed and resumable -- and then 'make report'."
	@echo "For the index-maintenance comparison: python3 scripts/run_all.py --indexes inline"
	@false
# audit first: check_claims verifies the prose matches the measurements, but says nothing about
# whether the measurements are consistent with each other. The row count that broke this experiment
# passed every claim check, because the prose faithfully reported the wrong number.
# Every document is generated, so there is nothing hand-written left to pin to the measurements.
# audit.py checks the measurements against each other; render.py --check checks that the documents
# on disk are what those measurements produce.
docs:
	@$(PY) scripts/render.py

check:
	@$(PY) scripts/audit.py
	@$(PY) scripts/render.py --check
	@$(PY) scripts/report.py --check
	@$(MAKE) --no-print-directory okf-check

up:
	@docker image inspect doltsamples-doltlite:0.50.9 >/dev/null 2>&1 || $(MAKE) --no-print-directory lite-image
	@DOLTSAMPLES_SERVE="$(SERVE)" DOLTSAMPLES_SERVE_DATABASES="$(SERVE_DATABASES)" DOLTSAMPLES_DOLT_MEM="$(DOLT_MEM)" DOLTSAMPLES_DOLTGRES_MEM="$(DOLTGRES_MEM)" $(PY) scripts/stack_config.py
	@docker compose up -d
	@$(PY) scripts/console_page.py
	@docker compose restart console >/dev/null 2>&1 || true
	@echo "console at http://127.0.0.1:8090/  (phpMyAdmin 8091, Adminer 8092, DbGate 8093, CloudBeaver 8094, Workbench 8095)"
	@echo "Dolt on 127.0.0.1:3307, DoltgreSQL on 127.0.0.1:5433, DoltLite files in doltsamples-doltlite — sql-megasamples keeps 3306, 5432 and 8080-8084"

down:
	@docker compose down

status:
	@docker ps --filter label=com.docker.compose.project=dolt-megasamples \
	  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true

# Dolt's container writes as root, so the host user cannot delete data/dolt directly -- `rm -rf`
# fails with "Permission denied" on every file and leaves the directory looking loaded. Removing it
# from inside a container is the only thing that works without sudo.
# Every mode has its own directory -- data/dolt, data/dolt-rowinsert, data/dolt-rowcommit and the
# two _inline variants -- so the wildcard matters: deleting data/dolt alone left the row-by-row
# results in place and the next run measured them again.
clean-data:
	@docker run --rm -v "$(PWD)/data:/data" --entrypoint sh \
	  dolthub/dolt-sql-server@sha256:38d5e900583267f35e36ad738e13f202e62860b351aa4c088dceaf7dbaed7ab6 \
	  -c 'rm -rf /data/dolt /data/dolt-* /data/mysql' 2>/dev/null || true
	@rm -rf data build/dumps/dolt build/results.json build/progress.json
	@echo "removed every data/dolt* directory, the transformed dumps, the measurements and the run state"

# The two further pairs' stores and prepared dumps: written as root by the worker containers, so
# removed through one. The exports (build/dumps/postgres, build/dumps/sqlite), the measurements and
# the run state are kept; `make clean-data` is the one that removes everything.
clean-pairs:
	@docker run --rm -v "$(PWD)/data:/data" -v "$(PWD)/build/dumps:/dumps" --entrypoint sh \
	  doltsamples-doltlite:0.50.9 \
	  -c 'rm -rf /data/postgres-timing /data/doltgres-* /data/sqlite-* /data/doltlite-* /dumps/pairs' 2>/dev/null || true
	@echo "removed the PostgreSQL, DoltgreSQL, SQLite and DoltLite stores of every shape and the prepared dumps"

clean: clean-data

audit:
	@$(PY) scripts/audit.py

trace:
	@$(PY) scripts/trace_report.py

estimate:
	@$(PY) scripts/estimate.py

summary:
	@$(PY) scripts/summary.py

# ---------------------------------------------------------------- the two further pairs ---
lite-image:
	@$(PY) scripts/lite_image.py
export-postgres:
	@$(PY) scripts/export_postgres.py $(ARGS)
export-sqlite:
	@$(PY) scripts/export_sqlite.py $(ARGS)
export-pairs: export-postgres export-sqlite
preflight-pairs:
	@$(PY) scripts/preflight_pairs.py $(ARGS)
run-pg:
	@$(PY) scripts/run_pairs.py --pair pg $(ARGS)
run-lite:
	@$(PY) scripts/run_pairs.py --pair lite $(ARGS)
test-stack:
	@$(PY) scripts/stack_check.py
memory-pairs:
	@$(PY) scripts/memory_profile_pairs.py $(ARGS)
okf-check:
	@$(PY) scripts/okf_check.py --bundle knowledge && $(PY) scripts/okf_fix_quotes.py --bundle knowledge --check
