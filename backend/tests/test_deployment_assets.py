from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _parse_env_template(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def test_environment_templates_cover_dev_staging_and_prod() -> None:
    required_keys = {
        "OPEN_MESSENGER_ENVIRONMENT",
        "OPEN_MESSENGER_CONTENT_BACKEND",
        "OPEN_MESSENGER_METADATA_BACKEND",
        "OPEN_MESSENGER_STORAGE_DIR",
        "OPEN_MESSENGER_FILES_ROOT_DIR",
        "OPEN_MESSENGER_ADMIN_API_TOKEN",
        "OPEN_MESSENGER_TOKEN_SIGNING_SECRET",
        "OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS",
        "OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS",
        "OPEN_MESSENGER_TRACING_ENABLED",
        "OPEN_MESSENGER_TRACING_SERVICE_NAME",
        "OPEN_MESSENGER_OTLP_TRACES_ENDPOINT",
        "GF_SECURITY_ADMIN_USER",
        "GF_SECURITY_ADMIN_PASSWORD",
    }

    for name in ("dev", "staging", "prod"):
        values = _parse_env_template(ROOT / "ops" / "deploy" / "env" / f"{name}.env.example")
        assert required_keys.issubset(values)

    prod_values = _parse_env_template(ROOT / "ops" / "deploy" / "env" / "prod.env.example")
    assert prod_values["OPEN_MESSENGER_CONTENT_BACKEND"] == "redis"
    assert prod_values["OPEN_MESSENGER_METADATA_BACKEND"] == "mysql"
    assert {"MYSQL_ROOT_PASSWORD", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"}.issubset(
        prod_values
    )


def test_config_yaml_profiles_include_tracing_and_rate_limit_settings() -> None:
    config_text = (ROOT / "config.yaml").read_text(encoding="utf-8")

    assert "rate_limit_max_requests: 60" in config_text
    assert "rate_limit_max_requests: 120" in config_text
    assert "rate_limit_max_requests: 300" in config_text
    assert "tracing_enabled: true" in config_text
    assert "otlp_traces_endpoint: http://tempo:4318/v1/traces" in config_text


def test_single_instance_deploy_bundle_uses_file_backends_and_monitoring() -> None:
    compose_text = (
        ROOT / "ops" / "deploy" / "docker-compose.single-instance.yml"
    ).read_text(encoding="utf-8")

    assert "OPEN_MESSENGER_CONTENT_BACKEND: ${OPEN_MESSENGER_CONTENT_BACKEND:-file}" in compose_text
    assert "OPEN_MESSENGER_METADATA_BACKEND: ${OPEN_MESSENGER_METADATA_BACKEND:-file}" in compose_text
    assert "prometheus:" in compose_text
    assert "loki:" in compose_text
    assert "promtail:" in compose_text
    assert "tempo:" in compose_text
    assert "grafana:" in compose_text
    assert "api_storage:" in compose_text
    assert "api_files:" in compose_text


def test_prod_deploy_bundle_uses_redis_mysql_and_monitoring() -> None:
    compose_text = (ROOT / "ops" / "deploy" / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )

    assert "OPEN_MESSENGER_CONTENT_BACKEND: ${OPEN_MESSENGER_CONTENT_BACKEND:-redis}" in compose_text
    assert "OPEN_MESSENGER_METADATA_BACKEND: ${OPEN_MESSENGER_METADATA_BACKEND:-mysql}" in compose_text
    assert "redis:" in compose_text
    assert "mysql:" in compose_text
    assert "prometheus:" in compose_text
    assert "loki:" in compose_text
    assert "tempo:" in compose_text
    assert "grafana:" in compose_text


def test_deploy_document_covers_profiles_monitoring_and_rollback() -> None:
    deploy_doc = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")

    assert "Single Instance" in deploy_doc
    assert "Production" in deploy_doc
    assert "Prometheus" in deploy_doc
    assert "Grafana" in deploy_doc
    assert "Rollback Procedure" in deploy_doc
    assert "Operations Runbook" in deploy_doc
