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
- `scripts/e2e_native_api.py`: End-to-end Native API verification script

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

Run E2E checks locally (starts a temporary API server automatically):

```bash
make e2e
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

Run E2E checks inside Docker:

```bash
make e2e-docker
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
curl -X POST http://localhost:8000/v1/channels -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"name":"general"}'
curl http://localhost:8000/v1/channels/<channel_id> -H "Authorization: Bearer <token>"
```

Create and query messages:

```bash
curl -X POST http://localhost:8000/v1/channels/<channel_id>/messages -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"text":"hello"}'
curl "http://localhost:8000/v1/channels/<channel_id>/messages?limit=20" -H "Authorization: Bearer <token>"
```

Upload and download a file:

```bash
curl -X POST http://localhost:8000/v1/files -H "Authorization: Bearer <token>" -F "file=@./README.md"
curl -L http://localhost:8000/v1/files/<file_id> -H "Authorization: Bearer <token>" -o downloaded.bin
```

Create a thread from a root message and post a reply:

```bash
curl -X POST http://localhost:8000/v1/channels/<channel_id>/threads -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"root_message_id":"<message_id>"}'
curl -X POST http://localhost:8000/v1/threads/<thread_id>/messages -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"text":"thread reply"}'
```

Create an admin user and token:

```bash
curl -X POST http://localhost:8000/admin/v1/users -H "Content-Type: application/json" -H "X-Admin-Token: dev-admin-token" -d '{"username":"alice","display_name":"Alice"}'
curl -X POST http://localhost:8000/admin/v1/tokens -H "Content-Type: application/json" -H "X-Admin-Token: dev-admin-token" -d '{"user_id":"<user_id>","token_type":"bot_token","scopes":["messages:write"]}'
curl -X DELETE http://localhost:8000/admin/v1/tokens/<token_id> -H "X-Admin-Token: dev-admin-token"
```

Tokens are persisted as SHA-256 hashes; the plaintext token is returned only once at creation time.
Admin endpoints require `X-Admin-Token` that matches `OPEN_MESSENGER_ADMIN_API_TOKEN`.
Entity IDs use `<prefix>_<ULID>` format (for example `msg_01ARZ...`), and API timestamps are normalized ISO8601 UTC strings ending with `Z`.

Use JWT-like Bearer token on Native API requests:

```bash
curl http://localhost:8000/v1/channels/<channel_id> -H "Authorization: Bearer <token>"
```

The token uses JWT-like format (`header.payload.signature`) signed with `HS256`.

`POST /v1/channels/{channel_id}/messages` and `POST /v1/threads/{thread_id}/messages` support `idempotency_key`.
First request returns `201`, replay with the same key in the same channel/thread returns `200` and the original message.

Errors are standardized as:

```json
{
  "code": "channel_not_found",
  "message": "Channel not found",
  "retryable": false
}
```

`/v1/info` reports the configured backend names and selected store implementation classes.
`memory`, `file`, `redis`, and `mysql` backends are implemented.

## Storage Configuration

- `OPEN_MESSENGER_CONTENT_BACKEND`: `memory | file | redis`
- `OPEN_MESSENGER_METADATA_BACKEND`: `memory | file | mysql`
- `OPEN_MESSENGER_STORAGE_DIR`: filesystem root used by `file` backends
- `OPEN_MESSENGER_REDIS_URL`: Redis URL used by `redis` content backend
- `OPEN_MESSENGER_REDIS_CONTENT_KEY_PREFIX`: Redis key prefix for message content
- `OPEN_MESSENGER_MYSQL_DSN`: MySQL DSN used by `mysql` metadata backend
- `OPEN_MESSENGER_MYSQL_TABLE_PREFIX`: table prefix used by MySQL metadata tables
- `OPEN_MESSENGER_FILES_ROOT_DIR`: filesystem root used by `/v1/files` upload/download
- `OPEN_MESSENGER_MAX_UPLOAD_MB`: max upload size in MB for `/v1/files`
- `OPEN_MESSENGER_ADMIN_API_TOKEN`: required value for `X-Admin-Token` on `/admin/v1/*`
- `OPEN_MESSENGER_TOKEN_SIGNING_SECRET`: signing secret for JWT-like token signature verification
