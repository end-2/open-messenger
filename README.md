# Open Messenger

Open Messenger is a monorepo for a multi-channel messaging platform with a FastAPI backend and a Node.js TypeScript frontend console.

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

The examples below cover a minimal flow:

1. Create a user with the admin API.
2. Issue a bearer token for that user.
3. Create a channel.
4. Send a message.
5. Fetch messages from the channel.

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
      "username": "alice",
      "display_name": "Alice"
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

Send a message:

```bash
curl -sS -X POST "$API_URL/v1/channels/$CHANNEL_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "{
    \"text\": \"Hello from the README example\",
    \"sender_user_id\": \"$USER_ID\",
    \"idempotency_key\": \"readme-example-message-1\",
    \"metadata\": {
      \"source\": \"readme\"
    }
  }"
```

Fetch messages from the channel:

```bash
curl -sS "$API_URL/v1/channels/$CHANNEL_ID/messages?limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

## Documentation

Detailed design, implementation, deployment, and API contract references live under `docs/`:

- [High-level design](docs/HIGH_LEVEL_DESIGN.md)
- [Low-level design](docs/LOW_LEVEL_DESIGN.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [OpenAPI specification](docs/openapi.yaml)
