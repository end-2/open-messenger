# Local and Container Setup

This document describes reproducible setup and test execution for the current scaffold.

## Local Python Environment (venv)

1. Create and populate the virtual environment:
   - `make install`
2. Run backend unit tests:
   - `make test`
3. Run the frontend console:
   - `cd frontend && npm run dev`
4. Run frontend unit tests:
   - `cd frontend && npm test`
5. Run the API server:
   - `make run`
6. Run end-to-end API checks (starts temporary API server automatically):
   - `make e2e`
5. Optional: enable OTLP trace export to a local Tempo instance:
   - `OPEN_MESSENGER_TRACING_ENABLED=true OPEN_MESSENGER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces make run`

Optional: run with file-backed storage:
- `OPEN_MESSENGER_CONTENT_BACKEND=file OPEN_MESSENGER_METADATA_BACKEND=file OPEN_MESSENGER_STORAGE_DIR=data/storage make run`

Optional: run with redis/mysql-backed storage:
- `OPEN_MESSENGER_CONTENT_BACKEND=redis OPEN_MESSENGER_METADATA_BACKEND=mysql OPEN_MESSENGER_REDIS_URL=redis://localhost:6379/0 OPEN_MESSENGER_MYSQL_DSN=mysql+pymysql://app:app@localhost:3306/open_messenger make run`

Optional: customize file upload storage:
- `OPEN_MESSENGER_FILE_STORAGE_BACKEND=local OPEN_MESSENGER_FILES_ROOT_DIR=data/files OPEN_MESSENGER_MAX_UPLOAD_MB=50 make run`

Optional: tighten or disable rate limiting during local runs:
- `OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS=10 OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS=60 make run`
- `OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS=0 make run`

## Docker Environment

1. Start deployment test stack:
   - `make up`
   - This starts API, Redis, MySQL, Prometheus, Loki, Promtail, Tempo, and Grafana.
2. Run backend unit tests in a container:
   - `make test-docker`
3. Run backend end-to-end API checks in a container:
   - `make e2e-docker`
4. Run frontend unit tests in a container:
   - `make test-frontend-docker`
5. Stop the stack:
   - `make down`
6. Render deploy-ready Compose configs from the maintained templates:
   - `make deploy-single-config`
   - `make deploy-staging-config`
   - `make deploy-prod-config`

## Smoke Checks

- `curl http://localhost:8000/healthz`
- `curl http://localhost:8000/readyz`
- `curl http://localhost:8000/metrics`
- `curl http://localhost:8000/v1/info`
- `curl -N http://localhost:8000/v1/events/stream -H "Authorization: Bearer <token>"`
- `curl -X POST http://localhost:8000/v1/channels -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"name":"general"}'`
- `curl -X POST http://localhost:8000/v1/channels/<channel_id>/threads -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"root_message_id":"<message_id>"}'`
- `curl -X POST http://localhost:8000/v1/messages:batchGet -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"message_ids":["<message_id>"]}'`
- `curl -X POST http://localhost:8000/v1/messages:batchCreate -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"items":[{"channel_id":"<channel_id>","text":"hello"}]}'`
- `curl http://localhost:8000/v1/threads/<thread_id>/context?limit=20 -H "Authorization: Bearer <token>"`
- `curl -X POST http://localhost:8000/admin/v1/users -H "Content-Type: application/json" -H "X-Admin-Token: dev-admin-token" -d '{"username":"alice"}'`
- `curl http://localhost:8000/v1/channels/<channel_id> -H "Authorization: Bearer <token>"`

WebSocket smoke check:

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

Monitoring endpoints after `make up`:

- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Tempo: `http://localhost:3200`
- Grafana: `http://localhost:3000` (`admin` / `admin`)

Deployment profiles, environment templates, and rollback/runbook instructions are maintained in `docs/DEPLOY.md`.
