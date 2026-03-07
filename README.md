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

## Documentation

Detailed design, implementation, deployment, and API contract references live under `docs/`:

- [High-level design](docs/HIGH_LEVEL_DESIGN.md)
- [Low-level design](docs/LOW_LEVEL_DESIGN.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [OpenAPI specification](docs/openapi.yaml)
