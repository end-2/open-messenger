# Frontend CLI

`frontend-cli` provides an interactive terminal client for the Open Messenger backend.

## Run locally

```bash
cd frontend-cli
npm install
npm run dev
```

Optional environment variables:

- `OPEN_MESSENGER_API_URL` defaults to `http://127.0.0.1:8000`
- `OPEN_MESSENGER_ADMIN_API_TOKEN` defaults to `dev-admin-token`
- `OPEN_MESSENGER_ACCESS_TOKEN` sets the initial bearer token

## Commands

- `help`
- `info`
- `bootstrap <username> [display-name]`
- `token <access-token>`
- `whoami`
- `create-channel <name>`
- `use-channel <channel-id>`
- `list [cursor]`
- `send <text>`
- `thread <root-message-id>`
- `reply <thread-id> <text>`
- `context <thread-id>`
- `exit`

## Test

```bash
cd frontend-cli
npm test
```
