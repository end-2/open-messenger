# High-Level Design

## Purpose

Open Messenger provides a consistent messaging platform for browser clients, bots, and AI agents. The platform combines a native API with compatibility endpoints that cover the core messaging patterns of Slack, Telegram, and Discord.

## Product Goals

- Provide channel-based messaging with thread support.
- Expose a stable native API for applications and agents.
- Offer compatibility endpoints for common messaging workflows.
- Keep storage backends replaceable across local, file-backed, and shared infrastructure modes.
- Support local development, reproducible container execution, and production-oriented deployment profiles.

## Scope

Included in the current scope:

- API token authentication for users, bots, and services
- Channel creation, lookup, membership, and message flows
- Thread creation and threaded replies
- File upload, download, and message attachments
- Realtime delivery through SSE and WebSocket
- Storage abstraction for message content, metadata, and file binaries
- Compatibility adapters for core Slack, Telegram, and Discord message APIs

Out of scope for the current stage:

- End-to-end encryption
- Voice or video calls
- Fine-grained policy engines such as full RBAC or ABAC
- Multi-region active-active deployment

## System Context

Primary actors:

- Web users using the frontend console
- External clients using the native HTTP API
- AI agents using batch, context, and event-stream APIs
- Integrations calling compatibility endpoints
- Operators deploying and monitoring the service

## Architecture Overview

```text
[Browser / CLI / Agent / Integration]
                 |
                 v
      [HTTP API and Realtime Gateway]
       | Native API
       | Admin API
       | Compatibility API
                 |
                 v
           [Auth Middleware]
                 |
                 v
         [Messaging Application]
       | Channels
       | Messages
       | Threads
       | Files
       | Event fan-out
                 |
                 v
          [Storage Abstractions]
       | Content store
       | Metadata store
       | Binary file store
```

## Major Subsystems

### Frontend Console

The frontend provides a browser console for service inspection, token bootstrap, and interactive chat flows.

### API Layer

The backend is built with FastAPI and exposes:

- `/v1` for the native API
- `/admin/v1` for administrative token and user management
- `/compat/*` for compatibility endpoints
- `/v1/events/*` for realtime streaming

### Messaging Application

The application layer owns the messaging rules around channels, messages, threads, file attachments, idempotency, and event publication.

### Storage Layer

The service separates message content, metadata, and file binaries so deployments can swap implementations without rewriting the API surface.

## Deployment Modes

- Local development: `memory + memory`
- Single instance: `file + file`
- Shared production profile: `redis + mysql`

Detailed runtime, rollout, and operations guidance is documented in [DEPLOYMENT.md](./DEPLOYMENT.md).

## Documentation Map

- Use [LOW_LEVEL_DESIGN.md](./LOW_LEVEL_DESIGN.md) for data models, API behaviors, storage contracts, and implementation details.
- Use [DEPLOYMENT.md](./DEPLOYMENT.md) for local setup, container workflows, deployment profiles, monitoring, and rollback procedures.
- Use [openapi.yaml](./openapi.yaml) for the source-of-truth HTTP contract.
