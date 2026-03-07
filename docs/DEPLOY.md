# Deployment Guide

This document turns the current runtime settings into deployable profiles and includes the monitoring stack used for operations.

## Profiles

### Single Instance

- Intended for one-node deployments and low operational overhead.
- Storage combination: `file + file`
- Monitoring included: Prometheus, Loki, Promtail, Tempo, Grafana
- Compose file: `ops/deploy/docker-compose.single-instance.yml`
- Recommended environment template: `ops/deploy/env/staging.env.example`

### Production

- Intended for horizontally scalable API nodes with shared metadata and content services.
- Storage combination: `redis + mysql`
- Monitoring included: Prometheus, Loki, Promtail, Tempo, Grafana
- Compose file: `ops/deploy/docker-compose.prod.yml`
- Recommended environment template: `ops/deploy/env/prod.env.example`

## Environment Templates

Maintained templates:

- `ops/deploy/env/dev.env.example`
- `ops/deploy/env/staging.env.example`
- `ops/deploy/env/prod.env.example`

Each template includes:

- storage backend selection
- file storage locations
- Redis and MySQL connection settings
- admin token and signing secret placeholders
- rate limit settings
- OTLP tracing settings for Tempo

Before a real deployment, copy the appropriate template to a private env file and replace all placeholder secrets.

## Config Preview

Render the maintained deployment bundles before rollout:

```bash
make deploy-single-config
make deploy-staging-config
make deploy-prod-config
```

The preview validates the Compose files and environment substitutions without starting containers.

## Compose Bundles

### Single Instance

Example:

```bash
docker compose \
  --env-file ops/deploy/env/staging.env.example \
  -f ops/deploy/docker-compose.single-instance.yml \
  up -d
```

Services started:

- `api`
- `prometheus`
- `loki`
- `promtail`
- `tempo`
- `grafana`

### Production

Example:

```bash
docker compose \
  --env-file ops/deploy/env/prod.env.example \
  -f ops/deploy/docker-compose.prod.yml \
  up -d
```

Services started:

- `api`
- `redis`
- `mysql`
- `prometheus`
- `loki`
- `promtail`
- `tempo`
- `grafana`

## Monitoring Endpoints

When the monitoring stack is enabled:

- API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Tempo: `http://localhost:3200`
- Grafana: `http://localhost:3000`

Default Grafana credentials in the examples:

- username: `admin`
- password: `admin`

Replace these values before staging or production rollout.

## Rollback Procedure

1. Record the current image digest and the target image digest before rollout.
2. Run `docker compose ... config` against the chosen deployment bundle to catch configuration drift.
3. Deploy the new image and wait for `http://<host>:8000/readyz` to return `200`.
4. If readiness, error-rate, or latency checks regress, redeploy the previous image digest with the same env file.
5. Confirm recovery through `/readyz`, Prometheus request/error metrics, and recent Loki logs.
6. Preserve the failed image reference, logs, and env diff for incident follow-up.

## Operations Runbook

Startup checks:

- `curl http://localhost:8000/healthz`
- `curl http://localhost:8000/readyz`
- `curl http://localhost:8000/metrics`
- `curl http://localhost:8000/v1/info`

Observe the deployment:

- Prometheus: inspect `open_messenger_http_requests_total` and `open_messenger_http_request_errors_total`
- Grafana: verify Prometheus, Loki, and Tempo datasources are healthy
- Loki: filter logs by `{compose_service="api"}`
- Tempo: confirm new traces arrive when `OPEN_MESSENGER_TRACING_ENABLED=true`

Stateful backup scope:

- single-instance profile: back up `api_storage`, `api_files`, `loki_data`, `tempo_data`, `grafana_data`
- production profile: back up `mysql_data`, `loki_data`, `tempo_data`, `grafana_data`

Credential rotation:

- rotate `OPEN_MESSENGER_ADMIN_API_TOKEN`
- rotate `OPEN_MESSENGER_TOKEN_SIGNING_SECRET`
- rotate MySQL and Redis credentials if used

Log retention note:

- Loki and Tempo use local volumes in these deployment bundles. Attach external storage or snapshot the volumes if longer retention is required.
