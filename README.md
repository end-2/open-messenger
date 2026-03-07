# Open Messenger

Open Messenger is a monorepo for a multi-channel messaging platform with a FastAPI backend and a Node.js TypeScript frontend console. The chat console supports channel messaging, root-level thread creation, threaded replies, and live event inspection.

## Quick Start

Prerequisites:

- Python 3.12+
- Node.js 22+
- Docker Engine with the Compose plugin

Install the local Python environment:

```bash
make install
```

Run the API locally:

```bash
make run
```

Run local unit tests:

```bash
make test
cd frontend && npm test
```

Run end-to-end checks locally:

```bash
make e2e
```

Start the full application stack in Docker:

```bash
make fullstack-up
```

Run tests in Docker:

```bash
make test-docker
make test-frontend-docker
make e2e-docker
```

## Basic API Example

The examples below use only the required request fields and cover a minimal flow:

1. Create a user with the admin API.
2. Issue a bearer token for that user.
3. Create a channel.
4. Send a root message.
5. Fetch messages from the channel.
6. Create a thread from the root message.
7. Send a reply in the thread.
8. Fetch the thread context.

For native message endpoints, `sender_user_id` is derived from the authenticated bearer token user. Clients should not attempt to set the sender explicitly.

Assumptions:

- The API is running locally with `make run`.
- The default development admin token is `dev-admin-token`.
- `jq` is installed to extract IDs from JSON responses.

```bash
export API_URL="http://localhost:8000"
export ADMIN_TOKEN="dev-admin-token"
```

Create a user:

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
```

Issue a user token with channel and message scopes:

```bash
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
        \"messages:write\"
      ]
    }"
)

export ACCESS_TOKEN="$(echo "$TOKEN_JSON" | jq -r '.token')"
echo "$TOKEN_JSON"
```

Create a channel:

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
```

Send a root message:

```bash
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

Fetch messages from the channel:

```bash
curl -sS "$API_URL/v1/channels/$CHANNEL_ID/messages?limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Create a thread from the root message:

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
```

Send a reply in the thread:

```bash
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

## Documentation

Detailed design, implementation, deployment, and API contract references live under `docs/`:

- [High-level design](docs/HIGH_LEVEL_DESIGN.md)
- [Low-level design](docs/LOW_LEVEL_DESIGN.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [OpenAPI specification](docs/openapi.yaml)
