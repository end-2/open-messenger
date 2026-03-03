# Local and Container Setup

This document describes reproducible setup and test execution for the current scaffold.

## Local Python Environment (venv)

1. Create and populate the virtual environment:
   - `make install`
2. Run backend unit tests:
   - `make test`
3. Run the API server:
   - `make run`

Optional: run with file-backed storage:
- `OPEN_MESSENGER_CONTENT_BACKEND=file OPEN_MESSENGER_METADATA_BACKEND=file OPEN_MESSENGER_STORAGE_DIR=data/storage make run`

## Docker Environment

1. Start deployment test stack:
   - `make up`
2. Run backend unit tests in a container:
   - `make test-docker`
3. Run frontend scaffold unit test in a container:
   - `make test-frontend-docker`
4. Stop the stack:
   - `make down`

## Smoke Checks

- `curl http://localhost:8000/healthz`
- `curl http://localhost:8000/v1/info`
- `curl -X POST http://localhost:8000/v1/channels -H "Content-Type: application/json" -d '{"name":"general"}'`
- `curl -X POST http://localhost:8000/v1/channels/<channel_id>/threads -H "Content-Type: application/json" -d '{"root_message_id":"<message_id>"}'`
- `curl -X POST http://localhost:8000/admin/v1/users -H "Content-Type: application/json" -H "X-Admin-Token: dev-admin-token" -d '{"username":"alice"}'`
