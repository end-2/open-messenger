# Deployment and Operations

## Local Development

Prerequisites:

- Python 3.12+
- Node.js 22+
- Docker Engine with the Compose plugin

Local Python environment:

1. Create and populate the virtual environment with `make install`.
2. Run backend unit tests with `make test`.
3. Run the backend server with `make run`.
4. Run end-to-end checks with `make e2e`.
5. Run the multi-user E2E matrix with `make e2e-matrix`.

Frontend workflows:

- Run the frontend console locally with `cd frontend && npm run dev`.
- Run frontend unit tests locally with `cd frontend && npm test`.

Optional runtime overrides:

- File-backed storage:
  `OPEN_MESSENGER_CONTENT_BACKEND=file OPEN_MESSENGER_METADATA_BACKEND=file OPEN_MESSENGER_STORAGE_DIR=data/storage make run`
- Redis and MySQL:
  `OPEN_MESSENGER_CONTENT_BACKEND=redis OPEN_MESSENGER_METADATA_BACKEND=mysql OPEN_MESSENGER_REDIS_URL=redis://localhost:6379/0 OPEN_MESSENGER_MYSQL_DSN=mysql+pymysql://app:app@localhost:3306/open_messenger make run`
- Local file storage:
  `OPEN_MESSENGER_FILE_STORAGE_BACKEND=local OPEN_MESSENGER_FILES_ROOT_DIR=data/files OPEN_MESSENGER_MAX_UPLOAD_MB=50 make run`
- Rate limiting:
  `OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS=10 OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS=60 make run`
  `OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS=0 make run`

## Container Workflows

Development and verification commands:

1. Start the deployment test stack with `make up`.
2. Start the application stack with `make fullstack-up`.
3. Run backend unit tests in Docker with `make test-docker`.
4. Run backend E2E checks in Docker with `make e2e-docker`.
5. Run the multi-user E2E matrix in Docker with `make e2e-matrix-docker`.
6. Run frontend unit tests in Docker with `make test-frontend-docker`.
7. Stop the deployment test stack with `make down`.
8. Stop the application stack with `make fullstack-down`.

Configuration previews:

- `make deploy-single-config`
- `make deploy-staging-config`
- `make deploy-prod-config`

## Deployment Profiles

### Single Instance

- Intended for one-node deployments with low operational overhead.
- Storage combination: `file + file`
- Compose bundle: `ops/deploy/docker-compose.single-instance.yml`
- Recommended environment template: `ops/deploy/env/staging.env.example`
- Included services: `frontend`, `api`, `prometheus`, `loki`, `promtail`, `tempo`, `grafana`

### Production

- Intended for horizontally scalable API deployments with shared infrastructure.
- Storage combination: `redis + mysql`
- Compose bundle: `ops/deploy/docker-compose.prod.yml`
- Recommended environment template: `ops/deploy/env/prod.env.example`
- Included services: `frontend`, `api`, `redis`, `mysql`, `prometheus`, `loki`, `promtail`, `tempo`, `grafana`

## Environment Templates

Maintained templates:

- `ops/deploy/env/dev.env.example`
- `ops/deploy/env/staging.env.example`
- `ops/deploy/env/prod.env.example`

Each template includes:

- frontend and API URLs
- storage backend selections
- file storage settings
- Redis and MySQL connection settings
- admin and token signing secrets
- rate limit configuration
- OTLP tracing configuration
- Grafana credentials

Copy the correct template into a private environment file before a real rollout and replace all placeholder secrets.

## Compose Examples

Single-instance rollout:

```bash
docker compose \
  --env-file ops/deploy/env/staging.env.example \
  -f ops/deploy/docker-compose.single-instance.yml \
  up -d
```

Production rollout:

```bash
docker compose \
  --env-file ops/deploy/env/prod.env.example \
  -f ops/deploy/docker-compose.prod.yml \
  up -d
```

## Smoke Checks

Application endpoints:

- `curl http://localhost:3001/healthz`
- `curl http://localhost:8000/healthz`
- `curl http://localhost:8000/readyz`
- `curl http://localhost:8000/metrics`
- `curl http://localhost:8000/v1/info`

Messaging and streaming checks:

- `curl -N http://localhost:8000/v1/events/stream -H "Authorization: Bearer <token>"`
- `curl -X POST http://localhost:8000/v1/channels -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"name":"general"}'`
- `curl -X POST http://localhost:8000/v1/channels/<channel_id>/threads -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"root_message_id":"<message_id>"}'`
- `curl -X POST http://localhost:8000/v1/messages:batchGet -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"message_ids":["<message_id>"]}'`
- `curl -X POST http://localhost:8000/v1/messages:batchCreate -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"items":[{"channel_id":"<channel_id>","text":"hello"}]}'`
- `curl http://localhost:8000/v1/threads/<thread_id>/context?limit=20 -H "Authorization: Bearer <token>"`
- `curl -X POST http://localhost:8000/admin/v1/users -H "Content-Type: application/json" -H "X-Admin-Token: dev-admin-token" -d '{"username":"alice"}'`

WebSocket check:

```bash
TOKEN="<token>" python - <<'PY'
import asyncio
import os
import websockets

async def main():
    token = os.environ["TOKEN"]
    async with websockets.connect(f"ws://localhost:8000/v1/events/ws?access_token={token}") as ws:
        await ws.send("ping")
        print(await ws.recv())

asyncio.run(main())
PY
```

## Monitoring Endpoints

- Frontend: `http://localhost:3001`
- API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Tempo: `http://localhost:3200`
- Grafana: `http://localhost:3000`

Default example Grafana credentials:

- Username: `admin`
- Password: `admin`

Replace example credentials before staging or production rollout.

## Rollback Procedure

1. Record the current image digest and target image digest before deployment.
2. Run `docker compose ... config` against the selected bundle to validate substitutions.
3. Deploy the new image and wait for `http://<host>:8000/readyz` to return `200`.
4. Wait for `http://<host>:3001/healthz` to return `200`.
5. If readiness, latency, or error rates regress, redeploy the previous image digest with the same environment file.
6. Confirm recovery through readiness probes, request metrics, and recent logs.
7. Preserve the failed image reference, logs, and environment diff for follow-up.

## Operations Runbook

Observe the deployment:

- Prometheus: inspect `open_messenger_http_requests_total` and `open_messenger_http_request_errors_total`
- Grafana: verify Prometheus, Loki, and Tempo data sources
- Loki: filter logs by `{compose_service="api"}`
- Tempo: confirm traces arrive when `OPEN_MESSENGER_TRACING_ENABLED=true`

Backup scope:

- Single instance: `api_storage`, `api_files`, `loki_data`, `tempo_data`, `grafana_data`
- Production: `mysql_data`, `loki_data`, `tempo_data`, `grafana_data`

Credential rotation:

- `OPEN_MESSENGER_ADMIN_API_TOKEN`
- `OPEN_MESSENGER_TOKEN_SIGNING_SECRET`
- MySQL credentials when used
- Redis credentials when used

Retention note:

- Loki and Tempo use local volumes in the provided bundles. Attach external storage or snapshot the volumes if longer retention is required.
