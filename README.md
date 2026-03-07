# Open Messenger

Open Messenger is a monorepo for a multi-channel messaging platform with a FastAPI backend, a Node.js TypeScript frontend console, and an interactive terminal CLI written in Go. The chat surfaces support channel messaging, file attachments, root-level thread creation, threaded replies, live event inspection, and sender display-name rendering.

## Quick Start

Prerequisites:

- Docker Engine with the Compose plugin
- `curl`
- `jq`

Start the full application stack:

```bash
make fullstack-up
```

Run only the backend locally with a custom admin token:

```bash
OPEN_MESSENGER_ADMIN_API_TOKEN="my-admin-token" make run
```

Services after startup:

```bash
export API_URL="http://localhost:8000"
export FRONTEND_URL="http://localhost:3001"
export ADMIN_TOKEN="dev-admin-token"
```

If you started the backend with a custom admin token, set `ADMIN_TOKEN` to the same value before running the admin API examples.

Smoke-check the stack:

```bash
curl -sS "$API_URL/healthz"
curl -sS "$FRONTEND_URL/healthz"
```

Create a user and token:

```bash
USER_JSON=$(
  curl -sS -X POST "$API_URL/admin/v1/users" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -d '{
      "username": "alice"
    }'
)

export USER_ID="$(echo "$USER_JSON" | jq -r '.user_id')"
echo "$USER_JSON"
TOKEN_JSON=$(
  curl -sS -X POST "$API_URL/admin/v1/tokens" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Token: $ADMIN_TOKEN" \
    -d "{
      \"user_id\": \"$USER_ID\",
      \"token_type\": \"user_token\",
      \"scopes\": [
        \"channels:read\",
        \"channels:write\",
        \"messages:read\",
        \"messages:write\",
        \"files:read\",
        \"files:write\"
      ]
    }"
)

export ACCESS_TOKEN="$(echo "$TOKEN_JSON" | jq -r '.token')"
echo "$TOKEN_JSON"
```

Create a channel and send a message:

```bash
CHANNEL_JSON=$(
  curl -sS -X POST "$API_URL/v1/channels" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{
      "name": "general"
    }'
)

export CHANNEL_ID="$(echo "$CHANNEL_JSON" | jq -r '.channel_id')"
echo "$CHANNEL_JSON"
ROOT_MESSAGE_JSON=$(
  curl -sS -X POST "$API_URL/v1/channels/$CHANNEL_ID/messages" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{
      "text": "Hello from the README example"
    }'
)

export ROOT_MESSAGE_ID="$(echo "$ROOT_MESSAGE_JSON" | jq -r '.message_id')"
echo "$ROOT_MESSAGE_JSON"
```

Read the channel:

```bash
curl -sS "$API_URL/v1/channels/$CHANNEL_ID/messages?limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Create a thread and read its context:

```bash
THREAD_JSON=$(
  curl -sS -X POST "$API_URL/v1/channels/$CHANNEL_ID/threads" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d "{
      \"root_message_id\": \"$ROOT_MESSAGE_ID\"
    }"
)

export THREAD_ID="$(echo "$THREAD_JSON" | jq -r '.thread_id')"
echo "$THREAD_JSON"
curl -sS -X POST "$API_URL/v1/threads/$THREAD_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "text": "This is a thread reply"
  }'
```

Fetch the thread context:

```bash
curl -sS "$API_URL/v1/threads/$THREAD_ID/context?limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Stop the stack:

```bash
make fullstack-down
```

## Testing

Local:

- `make install`
- `make test`
- `make e2e`

Docker:

- `make test-docker`
- `make test-frontend-docker`
- `make test-frontend-cli-docker`
- `make test-frontend-cli-golang-docker`
- `make e2e-docker`

`make e2e` and `make e2e-docker` both run the full native API end-to-end suite, including the multi-user scenario. The Docker E2E run also verifies that the native API scenario persisted the expected message content in Redis and the related metadata rows in MySQL.

## Make Targets

- `make fullstack-up`: start frontend, API, Redis, MySQL, and Tempo in Docker
- `make fullstack-down`: stop and remove the full application stack
- `make run`: run the API locally in the project `venv`
- `make build`: build the TypeScript CLI binary in Docker
- `make build-go-cli`: build the Go CLI binary in Docker for the current host OS and architecture
- `make up`: start the broader deployment test stack
- `make down`: stop and remove the deployment test stack

## Documentation

- [High-level design](docs/HIGH_LEVEL_DESIGN.md)
- [Low-level design](docs/LOW_LEVEL_DESIGN.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [OpenAPI specification](docs/openapi.yaml)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
