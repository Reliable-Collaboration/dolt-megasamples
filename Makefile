# dolt-megasamples: load the mysql-megasamples databases into Dolt and compare disk usage.
# Every target is a thin shim over a script in scripts/, so the experiment can be run without make.
PY ?= python3

.PHONY: help all run progress watch export load measure report charts environment method-checks experiment check up down status clean clean-data verify

help:
	@echo "make run        the whole experiment, timed: 5 loads x every database (hours)"
	@echo "make progress   what the run has done, is doing, and has left"
	@echo "make watch      the same, redrawn every minute"
	@echo "make all        the size-only pipeline: export -> load -> measure -> report"
	@echo "make export     mysqldump every database out of a running mysql-megasamples"
	@echo "make load       load those dumps into Dolt, commit and gc"
	@echo "make measure    size both engines and check they hold the same rows"
	@echo "make report     regenerate REPORT.md, the README tables and the figures"
	@echo "make charts     regenerate the figures only (matplotlib, in .venv)"
	@echo "make experiment the row-INSERT and per-row-commit loads, then the report"
	@echo "make check      fail if the report, the README table or a prose number is stale"
	@echo "make up         Dolt plus its four consoles (3307, 8090-8094)"
	@echo "make down       all of it down again"
	@echo "make status     what is running"
	@echo "make clean-data delete the Dolt data directory (written as root inside the container)"

# The experiment needs mysql-megasamples running: it is the source of every dump.
all: export load measure report

export:
	@$(PY) scripts/export_mysql.py
load:
	@$(PY) scripts/load_dolt.py
measure:
	@$(PY) scripts/measure.py
report: environment method-checks
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
run:
	@$(PY) scripts/run_all.py
progress:
	@$(PY) scripts/progress.py
watch:
	@$(PY) scripts/progress.py --watch

# The two extra loads: one INSERT per row, and one commit per row. Each writes into its own data
# directory, so the one-shot results they are compared against are never disturbed. The per-row
# commit load runs on the smallest databases only -- at the measured rate the full corpus would need
# tens of gigabytes and several hours, and the per-commit cost is already plain from these.
SMALL ?= oracle_hr pubs jaffle_shop smallsets northwind adventureworks_lt oracle_co oracle_oe chinook
MID   ?= dvdstore chicago_crimes
experiment:
	@$(PY) scripts/export_mysql.py --per-row $(foreach d,$(SMALL) $(MID),--only $(d))
	@$(PY) scripts/load_dolt.py  --mode rowinsert $(foreach d,$(SMALL) $(MID),--only $(d))
	@$(PY) scripts/measure.py    --mode rowinsert $(foreach d,$(SMALL) $(MID),--only $(d))
	@$(PY) scripts/load_dolt.py  --mode rowcommit --force $(foreach d,$(SMALL),--only $(d))
	@$(PY) scripts/measure.py    --mode rowcommit $(foreach d,$(SMALL),--only $(d))
	@$(MAKE) --no-print-directory report
check:
	@$(PY) scripts/report.py --check
	@$(PY) scripts/check_claims.py

up:
	@docker compose up -d
	@$(PY) scripts/console_page.py
	@docker compose restart console >/dev/null 2>&1 || true
	@echo "console at http://127.0.0.1:8090/  (phpMyAdmin 8091, Adminer 8092, DbGate 8093, CloudBeaver 8094)"
	@echo "Dolt on 127.0.0.1:3307 — mysql-megasamples keeps 3306 and 8080-8084"

down:
	@docker compose down

status:
	@docker ps --filter label=com.docker.compose.project=dolt-megasamples \
	  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true

# Dolt's container writes as root, so the host user cannot delete data/dolt directly -- `rm -rf`
# fails with "Permission denied" on every file and leaves the directory looking loaded. Removing it
# from inside a container is the only thing that works without sudo.
clean-data:
	@docker run --rm -v "$(PWD)/data:/data" --entrypoint sh \
	  dolthub/dolt-sql-server@sha256:38d5e900583267f35e36ad738e13f202e62860b351aa4c088dceaf7dbaed7ab6 \
	  -c 'rm -rf /data/dolt' 2>/dev/null || true
	@rm -rf data build/dumps/dolt build/results.json
	@echo "removed data/dolt, the transformed dumps and the measurements"

clean: clean-data
