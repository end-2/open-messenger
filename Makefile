SHELL := /bin/bash
VENV_DIR ?= .venv
PYTHON ?= python3
PIP := $(VENV_DIR)/bin/pip
PYTEST := $(VENV_DIR)/bin/pytest
UVICORN := $(VENV_DIR)/bin/uvicorn

.PHONY: help venv install run test e2e test-docker e2e-docker test-frontend-docker up down clean

help:
	@echo "Available targets:"
	@echo "  venv         Create local virtual environment"
	@echo "  install      Install Python dependencies in venv"
	@echo "  run          Run API server locally"
	@echo "  test         Run unit tests in local venv"
	@echo "  e2e          Run end-to-end API checks locally (starts temporary API server)"
	@echo "  test-docker  Run unit tests in Docker"
	@echo "  e2e-docker   Run end-to-end API checks in Docker"
	@echo "  test-frontend-docker  Run frontend unit test in Docker"
	@echo "  up           Start deployment test stack (API, Redis, MySQL)"
	@echo "  down         Stop and remove deployment test stack"
	@echo "  clean        Remove local test artifacts"

venv:
	$(PYTHON) -m venv $(VENV_DIR)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run: install
	PYTHONPATH=backend $(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

test: install
	PYTHONPATH=backend $(PYTEST) -q backend/tests

e2e: install
	@set -euo pipefail; \
	LOG_FILE=.pytest_cache/e2e-local-api.log; \
	mkdir -p .pytest_cache; \
	PYTHONPATH=backend $(UVICORN) app.main:app --host 127.0.0.1 --port 18000 > "$$LOG_FILE" 2>&1 & \
	API_PID=$$!; \
	trap 'kill $$API_PID >/dev/null 2>&1 || true' EXIT; \
	$(VENV_DIR)/bin/python scripts/e2e_native_api.py --base-url http://127.0.0.1:18000

test-docker:
	docker compose --profile test run --rm --build test

e2e-docker:
	@set -euo pipefail; \
	docker compose up --build -d api redis mysql; \
	trap 'docker compose down --volumes --remove-orphans' EXIT; \
	docker compose --profile test run --rm --build e2e

test-frontend-docker:
	docker run --rm -v "$$PWD":/workspace -w /workspace node:22-alpine node --test frontend/src/index.test.js

up:
	docker compose up --build -d api redis mysql

down:
	docker compose down --volumes --remove-orphans

clean:
	rm -rf $(VENV_DIR) .pytest_cache
