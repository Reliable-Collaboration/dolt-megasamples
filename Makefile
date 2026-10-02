# dolt-megasamples: the sql-megasamples databases in Dolt, DoltgreSQL and DoltLite, with the history you
# choose, served beside their consoles. Every target is one command of the doltsamples package, so
# `python3 -m doltsamples <command>` does the same without make.

# the package's one dependency (PyYAML) lives in .venv, made with uv when it is here, else with venv and pip
PY := .venv/bin/python
MS := $(PY) -m doltsamples

.PHONY: help run export build status up down ps test compose list versions update lite-image clean clean-all okf-check screenshots

help:
	@echo "make run         export from sql-megasamples, then build every store dolt-megasamples.yaml asks for"
	@echo "make up          write compose.yaml from the configuration and start the stack; then open http://127.0.0.1:8090/"
	@echo "make test        prove the running stack answers: both accounts, every store's rows and history, every console"
	@echo "make down        stop it"
	@echo ""
	@echo "make export      the dumps out of a built sql-megasamples (build/exports/)       ARGS=\"--only sakila\""
	@echo "make build       every configured store, checked against the corpus (data/)    ARGS=\"--only sakila --force\""
	@echo "make status      what the configuration asks for beside what is built"
	@echo "make list        the databases the configuration names, per engine and history"
	@echo "make compose     write compose.yaml without starting anything"
	@echo "make ps          what is running"
	@echo "make versions    each engine here beside its newest release"
	@echo "make update      move the engines to their newest release (then make lite-image, make build)"
	@echo "make lite-image  build the DoltLite image from its checksummed release packages"
	@echo "make clean       remove the stores and their records; make clean-all removes the exports too"
	@echo "make screenshots retake the README's pictures from the running stack (docs/screenshots/)"

$(PY):
	@uv venv -q .venv 2>/dev/null || python3 -m venv .venv
	@uv pip install -q --python $(PY) -e . 2>/dev/null || $(PY) -m pip install -q -e .
	@echo "  . .venv ready"

run: $(PY)
	@$(MS) run
export: $(PY)
	@$(MS) export $(ARGS)
build: $(PY)
	@$(MS) build $(ARGS)
status list compose ps versions test: $(PY)
	@$(MS) $@
up: $(PY)
	@$(MS) up
down: $(PY)
	@$(MS) down
update: $(PY)
	@$(MS) update $(ENGINE)
lite-image: $(PY)
	@$(MS) lite-image --record
clean: $(PY)
	@$(MS) clean
clean-all: $(PY)
	@$(MS) clean --all

# the README's pictures, retaken from the running stack in the Playwright image on the host's network
# (the Workbench's page calls its API at the address the host publishes). The pictures are written as
# the caller: the caller's uid on rootful Docker, container root on a rootless engine, which maps to the caller.
WRITER = $(shell docker info -f '{{json .SecurityOptions}}' 2>/dev/null | grep -q rootless && echo 0:0 || echo $$(id -u):$$(id -g))
PER_ROW = $(shell $(PY) -c "import json; e=json.load(open('build/serve.json'))['engines']['dolt']; print(next((s['name'] for s in e if s['history'] == 'per-row'), ''))" 2>/dev/null)
screenshots:
	@docker run --rm --network host --user "$(WRITER)" -e HOME=/tmp -e WORKBENCH_DB="$(PER_ROW)" -v "$(CURDIR)/docs/screenshots:/out" \
	  mcr.microsoft.com/playwright/python:v1.49.1-noble sh -c "pip install -q --user playwright==1.49.1 && python3 /out/capture.py"

# the knowledge bundle's checker (knowledge/)
okf-check: $(PY)
	@$(PY) scripts/okf_check.py --bundle knowledge && $(PY) scripts/okf_fix_quotes.py --bundle knowledge --check
