# dolt-megasamples: load the mysql-megasamples databases into Dolt and compare disk usage.
# Every target is a thin shim over a script in scripts/, so the experiment can be run without make.
PY ?= python3

.PHONY: help all export load measure report check up down status clean clean-data verify

help:
	@echo "make all        the whole experiment: export -> load -> measure -> report"
	@echo "make export     mysqldump every database out of a running mysql-megasamples"
	@echo "make load       load those dumps into Dolt, commit and gc"
	@echo "make measure    size both engines and check they hold the same rows"
	@echo "make report     regenerate REPORT.md and the README results table"
	@echo "make check      fail if REPORT.md or the README is stale"
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
report:
	@$(PY) scripts/report.py
	@$(PY) scripts/console_page.py
check:
	@$(PY) scripts/report.py --check

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
