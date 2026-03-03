# Open Messenger

Baseline monorepo scaffold for the Open Messenger platform.

## Project Structure

- `backend/`: Python FastAPI API server
- `frontend/`: Node.js frontend placeholder structure
- `docs/`: Design and implementation tracking documents
- `Dockerfile`: API container image definition
- `docker-compose.yml`: Local deployment and containerized test environment
- `Makefile`: Common local workflow commands
- `config.yaml`: Baseline environment profile template

## Prerequisites

- Python 3.12+
- Docker Engine with Compose plugin

## Local Setup (venv)

```bash
make install
```

Run API locally:

```bash
make run
```

Run unit tests in local virtual environment:

```bash
make test
```

## Docker Setup

Start deployment test stack (API + Redis + MySQL):

```bash
make up
```

Stop stack:

```bash
make down
```

Run unit tests inside Docker for reproducibility:

```bash
make test-docker
```

Run frontend scaffold unit test in Docker:

```bash
make test-frontend-docker
```

## API Smoke Check

After `make run` or `make up`:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/v1/info
```

`/v1/info` reports the configured backend names and selected store implementation classes.
Currently, `memory` and `file` backends are implemented. `redis` and `mysql` remain placeholders.

## Storage Configuration

- `OPEN_MESSENGER_CONTENT_BACKEND`: `memory | file | redis`
- `OPEN_MESSENGER_METADATA_BACKEND`: `memory | file | mysql`
- `OPEN_MESSENGER_STORAGE_DIR`: filesystem root used by `file` backends
