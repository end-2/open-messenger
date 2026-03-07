# Open Messenger Frontend

This frontend is a lightweight TypeScript BFF and browser console for the documented Open Messenger flows.

## Scope

- Inspect `/v1/info` service metadata
- Bootstrap a user and plaintext token through `/admin/v1/users` and `/admin/v1/tokens`
- Create channels and post messages through the Native API
- Load channel messages
- Subscribe to the backend SSE event stream through the frontend proxy

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

## Test

```bash
cd frontend
npm test
```

The test suite uses Node.js 22 built-in test runner with `--experimental-strip-types`, so no frontend build or dependency install step is required.
