SHELL := /bin/bash
VENV_DIR ?= .venv
PYTHON ?= python3
PIP := $(VENV_DIR)/bin/pip
PYTEST := $(VENV_DIR)/bin/pytest
UVICORN := $(VENV_DIR)/bin/uvicorn

# Detect host OS and architecture for Go cross-compilation
_UNAME_S := $(shell uname -s)
_UNAME_M := $(shell uname -m)
ifeq ($(_UNAME_S),Darwin)
  GO_OS := darwin
else
  GO_OS := linux
endif
ifeq ($(_UNAME_M),arm64)
  GO_ARCH := arm64
else ifeq ($(_UNAME_M),aarch64)
  GO_ARCH := arm64
else
  GO_ARCH := amd64
endif

.PHONY: help venv install run build build-go-cli test e2e test-docker e2e-docker test-frontend-docker test-frontend-cli-docker test-frontend-cli-golang-docker up down fullstack-up fullstack-down deploy-single-config deploy-staging-config deploy-prod-config clean

help:
	@echo "Available targets:"
	@echo "  venv         Create local virtual environment"
	@echo "  install      Install Python dependencies in venv"
	@echo "  run          Run API server locally"
	@echo "  build        Build the TypeScript frontend CLI binary in Docker"
	@echo "  build-go-cli Build the Go CLI binary in Docker for the current host OS/arch"
	@echo "  test         Run unit tests in local venv"
	@echo "  e2e          Run all end-to-end API checks locally, including the multi-user scenario (starts temporary API server)"
	@echo "  test-docker  Run unit tests in Docker"
	@echo "  e2e-docker   Run all end-to-end API checks in Docker, including the multi-user scenario"
	@echo "  test-frontend-docker  Run frontend unit test in Docker"
	@echo "  test-frontend-cli-docker  Run frontend CLI unit test in Docker"
	@echo "  test-frontend-cli-golang-docker  Run Go CLI unit tests in Docker"
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

build:
	mkdir -p frontend-cli/build
	docker run --rm -v "$$PWD":/workspace -w /workspace/frontend-cli node:22-alpine sh -lc "npm install --no-save --no-package-lock esbuild@0.25.10 pkg@5.8.1 && npx esbuild src/cli-main.ts --bundle --platform=node --target=node18 --format=cjs --outfile=build/cli.cjs && npx pkg build/cli.cjs --targets node18-linux-x64 --output build/open-messenger-cli && rm -rf node_modules build/cli.cjs"

build-go-cli:
	@echo "Building Go CLI for $(GO_OS)/$(GO_ARCH)..."
	mkdir -p frontend-cli-golang/build
	docker run --rm -v "$$PWD/frontend-cli-golang":/workspace -w /workspace \
		-e GOOS=$(GO_OS) -e GOARCH=$(GO_ARCH) -e CGO_ENABLED=0 \
		golang:1.22-alpine go build -o build/open-messenger-cli-go .
	@echo "Binary written to frontend-cli-golang/build/open-messenger-cli-go"

test: install
	PYTHONPATH=backend $(PYTEST) -q backend/tests

e2e: install
	@set -euo pipefail; \
	LOG_FILE=.pytest_cache/e2e-local-api.log; \
	mkdir -p .pytest_cache; \
	PYTHONPATH=backend $(UVICORN) app.main:app --host 127.0.0.1 --port 18000 > "$$LOG_FILE" 2>&1 & \
	API_PID=$$!; \
	trap 'kill $$API_PID >/dev/null 2>&1 || true' EXIT; \
	$(VENV_DIR)/bin/python scripts/e2e_native_api.py --base-url http://127.0.0.1:18000; \
	PYTHONPATH=backend $(VENV_DIR)/bin/python scripts/e2e_native_matrix.py --base-url http://127.0.0.1:18000

test-docker:
	docker compose --profile test run --rm --build test

e2e-docker:
	@set -euo pipefail; \
	docker compose up --build -d api redis mysql; \
	docker compose --profile test build e2e; \
	trap 'docker compose down --volumes --remove-orphans' EXIT; \
	docker compose --profile test run --rm e2e

test-frontend-docker:
	docker run --rm -v "$$PWD":/workspace -w /workspace/frontend node:22-alpine npm test

test-frontend-cli-docker:
	docker run --rm -v "$$PWD":/workspace -w /workspace/frontend-cli node:22-alpine npm test

test-frontend-cli-golang-docker:
	docker run --rm -v "$$PWD/frontend-cli-golang":/workspace -w /workspace golang:1.22-alpine go test ./...

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
