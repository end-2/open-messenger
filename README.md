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

Start deployment test stack (API + Redis + MySQL + Prometheus + Loki + Tempo + Grafana):

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

Render deployment configs:

```bash
make deploy-single-config
make deploy-staging-config
make deploy-prod-config
```

Deployment profiles, environment templates, monitoring layout, and rollback/runbook steps are documented in [`docs/DEPLOY.md`](docs/DEPLOY.md).
The checked-in HTTP OpenAPI document is [`docs/openapi.yaml`](docs/openapi.yaml) and can be regenerated with `PYTHONPATH=backend .venv/bin/python scripts/generate_openapi.py`.

## API Smoke Check

After `make run` or `make up`:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl http://localhost:8000/metrics
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
curl "http://localhost:8000/v1/channels/<channel_id>/messages?limit=20&cursor=<next_cursor>" -H "Authorization: Bearer <token>"
```

Agent-friendly batch and context APIs:

```bash
curl -X POST http://localhost:8000/v1/messages:batchGet \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"message_ids":["<message_id_1>","<message_id_2>"]}'

curl -X POST http://localhost:8000/v1/messages:batchCreate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"items":[{"channel_id":"<channel_id>","text":"hello"},{"channel_id":"<channel_id>","text":"hello again","idempotency_key":"req-2"}]}'

curl "http://localhost:8000/v1/threads/<thread_id>/context?limit=20" \
  -H "Authorization: Bearer <token>"
```

Open the SSE event stream:

```bash
curl -N http://localhost:8000/v1/events/stream -H "Authorization: Bearer <token>"
```

Open the WebSocket event stream:

```bash
python - <<'PY'
import asyncio
import websockets

TOKEN = "<token>"

async def main():
    async with websockets.connect(f"ws://localhost:8000/v1/events/ws?access_token={TOKEN}") as ws:
        await ws.send("ping")
        print(await ws.recv())

asyncio.run(main())
PY
```

Compatibility endpoints:

```bash
curl -X POST http://localhost:8000/compat/slack/chat.postMessage -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"channel":"<channel_id>","text":"hello from slack"}'
curl -X POST http://localhost:8000/compat/telegram/bot<token>/sendMessage -H "Content-Type: application/json" -d '{"chat_id":"<channel_id>","text":"hello from telegram"}'
curl -X POST http://localhost:8000/compat/discord/channels/<channel_id>/messages -H "Content-Type: application/json" -H "Authorization: Bot <token>" -d '{"content":"hello from discord"}'
```

Upload and download a file:

```bash
curl -X POST http://localhost:8000/v1/files -H "Authorization: Bearer <token>" -F "file=@./README.md"
curl -L http://localhost:8000/v1/files/<file_id> -H "Authorization: Bearer <token>" -o downloaded.bin
```

Attach an uploaded file to a message:

```bash
curl -X POST http://localhost:8000/v1/channels/<channel_id>/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"text":"see attachment","attachments":["<file_id>"]}'
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
curl -X POST http://localhost:8000/admin/v1/tokens/<token_id>/rotate -H "X-Admin-Token: dev-admin-token"
curl -X DELETE http://localhost:8000/admin/v1/tokens/<token_id> -H "X-Admin-Token: dev-admin-token"
```

Tokens are persisted as SHA-256 hashes; the plaintext token is returned only once at creation time.
Rotation returns a new plaintext token once and immediately revokes the previous token.
Admin endpoints require `X-Admin-Token` that matches `OPEN_MESSENGER_ADMIN_API_TOKEN`.
Entity IDs use `<prefix>_<ULID>` format (for example `msg_01ARZ...`), and API timestamps are normalized ISO8601 UTC strings ending with `Z`.

Use JWT-like Bearer token on Native API requests:

```bash
curl http://localhost:8000/v1/channels/<channel_id> -H "Authorization: Bearer <token>"
```

The token uses JWT-like format (`header.payload.signature`) signed with `HS256`.

`POST /v1/channels/{channel_id}/messages` and `POST /v1/threads/{thread_id}/messages` support `idempotency_key`.
First request returns `201`, replay with the same key in the same channel/thread returns `200` and the original message.

`POST /v1/messages:batchGet` returns found messages in request order and collects misses in `not_found_ids`.
`POST /v1/messages:batchCreate` applies the same message contract in batch form, with `channel_id` required per item and item-level idempotency using `idempotency_key`.
`GET /v1/threads/{thread_id}/context` returns `thread`, `root_message`, `replies`, and `has_more_replies`.

`GET /v1/channels/{channel_id}/messages` uses cursor pagination.
`limit` defaults to `50` and is constrained to `1..200`.
Use the returned `next_cursor` as the next request's `cursor`.
When `next_cursor` is `null`, the client has reached the end of the channel message stream.

Errors are standardized as:

```json
{
  "code": "channel_not_found",
  "message": "Channel not found",
  "retryable": false
}
```

When request volume exceeds the configured window on `/v1` or `/admin/v1`, the API returns `429` with `code=rate_limited` and a `Retry-After` header. The limiter keys by bearer token, admin token, or client IP when no token is present. `/healthz`, `/readyz`, and `/metrics` are excluded.
Every HTTP response includes `X-Request-Id`. If the client sends `X-Request-Id`, the API preserves and propagates it; otherwise the API generates one. Application logs are emitted as JSON on stdout for collection by Loki.

`/v1/info` reports the configured backend names and selected store implementation classes.
`memory`, `file`, `redis`, `mysql`, and `local` file-binary storage are implemented.
Slack `thread_ts`, Telegram `reply_to_message_id`, and Discord `message_reference` are mapped onto internal thread/reply relationships through metadata-backed compatibility mappings.
`GET /v1/events/stream` provides an SSE feed with standard event payloads shaped as `event_id`, `type`, `occurred_at`, and `data`.
`GET /v1/events/ws` provides the same event payloads over WebSocket. The socket requires `messages:read` scope, accepts `Authorization: Bearer <token>` or `access_token` query authentication, and responds to `ping` with `{"type":"pong"}`.
Message attachments must reference existing file IDs returned by `POST /v1/files` or compatible upload endpoints.

## Storage Configuration

- `OPEN_MESSENGER_CONTENT_BACKEND`: `memory | file | redis`
- `OPEN_MESSENGER_METADATA_BACKEND`: `memory | file | mysql`
- `OPEN_MESSENGER_FILE_STORAGE_BACKEND`: `local`
- `OPEN_MESSENGER_STORAGE_DIR`: filesystem root used by `file` backends
- `OPEN_MESSENGER_FILES_ROOT_DIR`: filesystem root used by the `local` file storage backend
- `OPEN_MESSENGER_REDIS_URL`: Redis URL used by `redis` content backend
- `OPEN_MESSENGER_REDIS_CONTENT_KEY_PREFIX`: Redis key prefix for message content
- `OPEN_MESSENGER_MYSQL_DSN`: MySQL DSN used by `mysql` metadata backend
- `OPEN_MESSENGER_MYSQL_TABLE_PREFIX`: table prefix used by MySQL metadata tables
- `OPEN_MESSENGER_MAX_UPLOAD_MB`: max upload size in MB for `/v1/files`
- `OPEN_MESSENGER_ADMIN_API_TOKEN`: required value for `X-Admin-Token` on `/admin/v1/*`
- `OPEN_MESSENGER_TOKEN_SIGNING_SECRET`: signing secret for JWT-like token signature verification
- `OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS`: max requests per identity within the rate limit window
- `OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS`: sliding window size in seconds for rate limiting
- `OPEN_MESSENGER_TRACING_ENABLED`: enable OpenTelemetry trace export
- `OPEN_MESSENGER_TRACING_SERVICE_NAME`: logical service name attached to traces
- `OPEN_MESSENGER_OTLP_TRACES_ENDPOINT`: OTLP/HTTP trace export endpoint, for example `http://tempo:4318/v1/traces`

## Monitoring Stack

`docker compose` now includes the following observability services:

- Prometheus at `http://localhost:9090` scraping `/metrics`
- Loki at `http://localhost:3100` ingesting API container logs through Promtail
- Tempo at `http://localhost:3200` receiving OTLP traces from the API
- Grafana at `http://localhost:3000` with preprovisioned Prometheus, Loki, and Tempo datasources

Default Grafana credentials:

- username: `admin`
- password: `admin`

Useful Prometheus metrics:

- `open_messenger_http_request_duration_seconds`
- `open_messenger_http_requests_total`
- `open_messenger_http_request_errors_total`
- `open_messenger_message_events_total`
- `open_messenger_event_delivery_lag_seconds`
- `open_messenger_realtime_active_subscribers`
