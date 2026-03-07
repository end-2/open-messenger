# Low-Level Design

## Service Boundaries

The backend is organized around these responsibilities:

- Auth middleware validates bearer tokens, admin tokens, and request scopes.
- Channel services manage channel records and membership state.
- Message services create, list, update, and delete messages with idempotency support.
- Thread services map root messages to reply streams and provide context lookups.
- File services persist file metadata and binary payloads.
- Event services publish message and thread activity to SSE and WebSocket consumers.
- Compatibility adapters translate Slack, Telegram, and Discord request shapes into native service calls.

## Core Data Model

Primary entities:

- `User`
- `Token`
- `Channel`
- `ChannelMember`
- `Message`
- `Thread`
- `FileObject`
- `EventLog`

### Message Metadata

- `message_id`
- `channel_id`
- `thread_id`
- `sender_user_id`
- `content_ref`
- `attachments`
- `created_at`
- `updated_at`
- `deleted_at`
- `compat_origin`
- `idempotency_key`

### Thread Metadata

- `thread_id`
- `channel_id`
- `root_message_id`
- `reply_count`
- `last_message_at`

### File Metadata

- `file_id`
- `uploader_user_id`
- `filename`
- `mime_type`
- `size_bytes`
- `storage_backend`
- `storage_path`
- `sha256`

### Message Content

Message content is stored separately from metadata by `content_ref` and contains fields such as `text`, `blocks`, `mentions`, and `raw_payload`.

## Storage Contracts

### Message Content Store

Supported backends:

- `memory`
- `file`
- `redis`

Contract:

```python
class MessageContentStore(Protocol):
    async def put(self, content_id: str, payload: dict) -> None: ...
    async def get(self, content_id: str) -> dict | None: ...
    async def get_many(self, content_ids: list[str]) -> dict[str, dict]: ...
    async def delete(self, content_id: str) -> None: ...
```

### Metadata Store

Supported backends:

- `memory`
- `file`
- `mysql`

Contract:

```python
class MetadataStore(Protocol):
    async def create_message(self, msg: dict) -> dict: ...
    async def get_message(self, message_id: str) -> dict | None: ...
    async def get_messages(self, message_ids: list[str]) -> dict[str, dict]: ...
    async def get_users(self, user_ids: list[str]) -> dict[str, dict]: ...
    async def list_channel_messages(
        self, channel_id: str, cursor: str | None, limit: int
    ) -> list[dict]: ...
    async def create_channel(self, channel: dict) -> dict: ...
    async def delete_channel(self, channel_id: str) -> dict | None: ...
```

Expected backend combinations:

- Local development: `memory + memory`
- Single instance: `file + file`
- Shared runtime: `redis + mysql`

Read-heavy API paths should prefer the batch lookup methods above so channel listing, batch reads, and thread context responses do not devolve into per-message MySQL and Redis round-trips.

### File Binary Storage

- Default backend: `local`
- Root directory: `files_root_dir`
- Attachments are stored as `FileObject` references in message metadata.

## Authentication Model

Token types:

- `user_token`
- `bot_token`
- `service_token`

Request patterns:

- Native API: `Authorization: Bearer <token>`
- Admin API: separate admin token validation on `/admin/v1`

Token properties:

- JWT-like structure signed with configurable HMAC algorithms: `HS256`, `HS384`, or `HS512`
- Stored as hashes, not plaintext
- Scoped with values such as `channels:read`, `channels:write`, `messages:read`, `messages:write`, and `files:write`

Default token signing algorithm:

- `HS256`
- Chosen as the default because it keeps token size smallest while remaining in the same performance band as the other supported HMAC variants in the project benchmark.

## HTTP API Design

### Native API

Base path: `/v1`

For authenticated native message writes, the service derives `sender_user_id` from the bearer token subject rather than trusting a client-supplied sender field.
Message responses resolve sender identity fields from the stored user record and return `sender_username` and `sender_display_name` alongside `sender_user_id` when available.

Representative endpoints:

- `GET /channels`
- `POST /channels`
- `GET /channels/{channel_id}`
- `POST /channels/{channel_id}/messages`
- `GET /channels/{channel_id}/messages`
- `POST /channels/{channel_id}/threads`
- `POST /threads/{thread_id}/messages`
- `POST /files`
- `GET /files/{file_id}`
- `POST /messages:batchGet`
- `POST /messages:batchCreate`
- `GET /threads/{thread_id}/context`

### Admin API

Base path: `/admin/v1`

Representative endpoints:

- `POST /users`
- `DELETE /channels/{channel_id}`
- `POST /tokens`
- `DELETE /tokens/{token_id}`
- `POST /tokens/{token_id}/rotate`

### Compatibility API

Supported compatibility entry points:

- `POST /compat/slack/chat.postMessage`
- `POST /compat/slack/files.upload`
- `POST /compat/telegram/bot{token}/sendMessage`
- `POST /compat/telegram/bot{token}/sendDocument`
- `POST /compat/discord/channels/{channel_id}/messages`

## Pagination and Idempotency

Channel message listing uses cursor pagination with these rules:

- Results are ordered from oldest to newest.
- `limit` defaults to `50` and is constrained to `1..200`.
- `cursor` is the last `message_id` returned by the previous page.
- Responses return `items` and `next_cursor`.
- Thread replies remain part of the same channel stream ordering.

Message creation supports idempotency keys so retries can be handled safely, including within batch create requests.

## Realtime Events

Supported transports:

- `GET /v1/events/stream` for SSE
- `GET /v1/events/ws` for WebSocket

Current event types:

- `message.created`
- `message.updated`
- `message.deleted`
- `thread.created`
- `file.uploaded`

Example payload:

```json
{
  "event_id": "evt_01H...",
  "type": "message.created",
  "occurred_at": "2026-03-03T11:22:33Z",
  "data": {
    "channel_id": "ch_01H...",
    "message_id": "msg_01H..."
  }
}
```

## Agent-Oriented Behaviors

The native API is designed to be predictable for automation:

- Stable ULID-style identifiers
- ISO 8601 UTC timestamps
- Cursor-based list endpoints
- Structured error payloads
- Batch read and batch create APIs
- Thread context API
- SSE and WebSocket event streams

## Testing Focus

The codebase emphasizes:

- Shared contract tests for pluggable storage backends
- API integration tests for native and compatibility routes
- Token and scope enforcement tests
- E2E checks for primary messaging flows, including multi-user scope matrices and expected transcript verification

## Related References

- [HIGH_LEVEL_DESIGN.md](./HIGH_LEVEL_DESIGN.md)
- [DEPLOYMENT.md](./DEPLOYMENT.md)
- [openapi.yaml](./openapi.yaml)
