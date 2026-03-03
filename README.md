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

Create and query a channel:

```bash
curl -X POST http://localhost:8000/v1/channels -H "Content-Type: application/json" -d '{"name":"general"}'
curl http://localhost:8000/v1/channels/<channel_id>
```

Create and query messages:

```bash
curl -X POST http://localhost:8000/v1/channels/<channel_id>/messages -H "Content-Type: application/json" -d '{"text":"hello"}'
curl "http://localhost:8000/v1/channels/<channel_id>/messages?limit=20"
```

Create a thread from a root message and post a reply:

```bash
curl -X POST http://localhost:8000/v1/channels/<channel_id>/threads -H "Content-Type: application/json" -d '{"root_message_id":"<message_id>"}'
curl -X POST http://localhost:8000/v1/threads/<thread_id>/messages -H "Content-Type: application/json" -d '{"text":"thread reply"}'
```

Create an admin user and token:

```bash
curl -X POST http://localhost:8000/admin/v1/users -H "Content-Type: application/json" -H "X-Admin-Token: dev-admin-token" -d '{"username":"alice","display_name":"Alice"}'
curl -X POST http://localhost:8000/admin/v1/tokens -H "Content-Type: application/json" -H "X-Admin-Token: dev-admin-token" -d '{"user_id":"<user_id>","token_type":"bot_token","scopes":["messages:write"]}'
curl -X DELETE http://localhost:8000/admin/v1/tokens/<token_id> -H "X-Admin-Token: dev-admin-token"
```

Tokens are persisted as SHA-256 hashes; the plaintext token is returned only once at creation time.
Admin endpoints require `X-Admin-Token` that matches `OPEN_MESSENGER_ADMIN_API_TOKEN`.

`/v1/info` reports the configured backend names and selected store implementation classes.
Currently, `memory` and `file` backends are implemented. `redis` and `mysql` remain placeholders.

## Storage Configuration

- `OPEN_MESSENGER_CONTENT_BACKEND`: `memory | file | redis`
- `OPEN_MESSENGER_METADATA_BACKEND`: `memory | file | mysql`
- `OPEN_MESSENGER_STORAGE_DIR`: filesystem root used by `file` backends
- `OPEN_MESSENGER_ADMIN_API_TOKEN`: required value for `X-Admin-Token` on `/admin/v1/*`
