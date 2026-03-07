SHELL := /bin/bash
VENV_DIR ?= .venv
PYTHON ?= python3
PIP := $(VENV_DIR)/bin/pip
PYTEST := $(VENV_DIR)/bin/pytest
UVICORN := $(VENV_DIR)/bin/uvicorn

.PHONY: help venv install run test e2e e2e-matrix test-docker e2e-docker e2e-matrix-docker test-frontend-docker test-frontend-cli-docker up down fullstack-up fullstack-down deploy-single-config deploy-staging-config deploy-prod-config clean

help:
	@echo "Available targets:"
	@echo "  venv         Create local virtual environment"
	@echo "  install      Install Python dependencies in venv"
	@echo "  run          Run API server locally"
	@echo "  test         Run unit tests in local venv"
	@echo "  e2e          Run end-to-end API checks locally (starts temporary API server)"
	@echo "  e2e-matrix   Run multi-user end-to-end matrix locally (starts temporary API server)"
	@echo "  test-docker  Run unit tests in Docker"
	@echo "  e2e-docker   Run end-to-end API checks in Docker"
	@echo "  e2e-matrix-docker Run multi-user end-to-end matrix in Docker"
	@echo "  test-frontend-docker  Run frontend unit test in Docker"
	@echo "  test-frontend-cli-docker  Run frontend CLI unit test in Docker"
	@echo "  up           Start deployment test stack (API, Redis, MySQL, Prometheus, Loki, Tempo, Grafana)"
	@echo "  down         Stop and remove deployment test stack"
	@echo "  fullstack-up Start frontend and backend application containers in Docker"
	@echo "  fullstack-down Stop and remove fullstack application containers"
	@echo "  deploy-single-config  Render single-instance deployment compose config"
	@echo "  deploy-staging-config Render staging deployment compose config"
	@echo "  deploy-prod-config    Render production deployment compose config"
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

e2e-matrix: install
	@set -euo pipefail; \
	LOG_FILE=.pytest_cache/e2e-matrix-local-api.log; \
	mkdir -p .pytest_cache; \
	PYTHONPATH=backend $(UVICORN) app.main:app --host 127.0.0.1 --port 18000 > "$$LOG_FILE" 2>&1 & \
	API_PID=$$!; \
	trap 'kill $$API_PID >/dev/null 2>&1 || true' EXIT; \
	PYTHONPATH=backend $(VENV_DIR)/bin/python scripts/e2e_native_matrix.py --base-url http://127.0.0.1:18000

test-docker:
	docker compose --profile test run --rm --build test

e2e-docker:
	@set -euo pipefail; \
	docker compose up --build -d api redis mysql; \
	trap 'docker compose down --volumes --remove-orphans' EXIT; \
	docker compose --profile test run --rm --build e2e

e2e-matrix-docker:
	@set -euo pipefail; \
	docker compose up --build -d api redis mysql; \
	trap 'docker compose down --volumes --remove-orphans' EXIT; \
	docker compose --profile test run --rm --build e2e-matrix

test-frontend-docker:
	docker run --rm -v "$$PWD":/workspace -w /workspace/frontend node:22-alpine npm test

test-frontend-cli-docker:
	docker run --rm -v "$$PWD":/workspace -w /workspace/frontend-cli node:22-alpine npm test

up:
	docker compose up --build -d api redis mysql prometheus loki promtail tempo grafana

down:
	docker compose down --volumes --remove-orphans

fullstack-up:
	docker compose up --build -d frontend api redis mysql tempo

fullstack-down:
	docker compose stop frontend api redis mysql tempo
	docker compose rm -f frontend api redis mysql tempo

deploy-single-config:
	docker compose --env-file ops/deploy/env/dev.env.example -f ops/deploy/docker-compose.single-instance.yml config

deploy-staging-config:
	docker compose --env-file ops/deploy/env/staging.env.example -f ops/deploy/docker-compose.single-instance.yml config

deploy-prod-config:
	docker compose --env-file ops/deploy/env/prod.env.example -f ops/deploy/docker-compose.prod.yml config

clean:
	rm -rf $(VENV_DIR) .pytest_cache
