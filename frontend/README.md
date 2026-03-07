# Open Messenger Frontend

This frontend is a lightweight TypeScript BFF and browser console for the documented Open Messenger flows.

## Scope

- Inspect `/v1/info` service metadata
- Bootstrap a user and plaintext token through `/admin/v1/users` and `/admin/v1/tokens`, with the token shown first and additional details available in a popup on demand
- Open a dedicated chat page for channel creation, room history, message posting, thread replies, and event streaming
- Load existing channels and room history from the server
- Render sender display names in the transcript and thread view when the backend provides them
- Keep the thread sidebar hidden until a message opens it, with a conventional chat-room style sidebar, transcript, and composer layout
- Keep the main room transcript focused on root-level room messages while thread replies stay in the thread sidebar, and avoid exposing internal IDs in the room UI
- Align messages from the current bearer token on the right side while keeping sender identity at the top-left of each message card, and keep thread actions compact
- Enter the chat page from the main page after supplying or reusing a saved token, instead of editing the token inside the chat room
- Validate the token before entering `/chat`, and redirect direct `/chat` visits back to `/` when no valid token is available
- Subscribe to the backend SSE event stream through the frontend proxy
- Keep the live event stream control as a simple on/off toggle in the left sidebar footer

## Run

```bash
cd frontend
npm run dev
```

Environment variables:

- `FRONTEND_PORT`: browser UI port, default `3001`
- `OPEN_MESSENGER_API_BASE_URL`: backend base URL, default `http://127.0.0.1:8000`
- `OPEN_MESSENGER_ADMIN_API_TOKEN`: admin token used by the bootstrap form, default `dev-admin-token`

Open `http://127.0.0.1:3001` after the backend API is available.

- `/`: service snapshot and user/token bootstrap
- `/chat`: channel and message console with a room-style layout, authenticated sender display, and a dedicated thread panel; token entry happens on `/`

## Docker

From the repository root:

```bash
make fullstack-up
```

This starts the frontend container on `http://127.0.0.1:3001` and points it at the Dockerized backend API on `http://api:8000`.

Stop it with:

```bash
make fullstack-down
```

## Test

```bash
cd frontend
npm test
```

The test suite uses Node.js 22 built-in test runner with `--experimental-strip-types`, so no frontend build or dependency install step is required.
