# Oracle Learning Lab: common tasks. `make help` lists them.
SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON  ?= .venv/bin/python
COMPOSE ?= docker compose

.PHONY: help venv lint test check secrets build up down logs ps sqlplus shell

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

venv: ## create .venv with the app and the dev tools
	python3 -m venv .venv && $(PYTHON) -m pip install -q -e '.[dev]'

lint: ## static checks (ruff, content structure)
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m oracle_lab validate --static

test: ## unit tests; database tests run when STUDY_DSN / STUDY_PASSWORD[_FILE] reach a database
	$(PYTHON) -m pytest -q

check: lint test ## lint and test

secrets: ## generate missing passwords in ./secrets
	scripts/init-secrets.sh

build: secrets ## build the all-in-one image (Oracle 19c + app)
	$(COMPOSE) build

up: secrets ## build and start the stack in the background
	$(COMPOSE) up -d --build
	@echo "First start creates the database (10-30 min): make logs. Then open http://127.0.0.1:$${LAB_PORT:-8071}"

down: ## stop the stack (data in ./data is kept)
	$(COMPOSE) down

logs: ## follow the container logs
	$(COMPOSE) logs -f lab

ps: ## container status and health
	$(COMPOSE) ps

sqlplus: ## SQL*Plus as the learning user inside the container (password: secrets/study_db_password)
	$(COMPOSE) exec lab bash -c 'sqlplus -L "$$STUDY_USER@$$STUDY_DSN"'

shell: ## a shell in the container
	$(COMPOSE) exec lab bash
