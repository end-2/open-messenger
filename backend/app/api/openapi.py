from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI


_TAG_METADATA = [
    {"name": "System", "description": "Health, readiness, metrics, and service metadata."},
    {"name": "Native API", "description": "Primary Open Messenger HTTP API under `/v1`."},
    {"name": "Admin API", "description": "Administrative endpoints under `/admin/v1`."},
    {
        "name": "Compatibility API",
        "description": "Slack, Telegram, and Discord compatibility endpoints.",
    },
]


def _normalize_schema_values(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "contentMediaType":
                continue
            normalized[key] = _normalize_schema_values(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_schema_values(item) for item in value]
    return value


def _tags_for_path(path: str) -> list[str]:
    if path in {"/healthz", "/readyz", "/metrics"} or path == "/v1/info":
        return ["System"]
    if path.startswith("/admin/v1"):
        return ["Admin API"]
    if path.startswith("/compat/"):
        return ["Compatibility API"]
    return ["Native API"]


def _security_for_path(path: str) -> list[dict[str, list[str]]] | None:
    if path.startswith("/admin/v1"):
        return [{"AdminToken": []}]
    if path.startswith("/compat/slack") or path.startswith("/compat/discord"):
        return [{"BearerToken": []}]
    if path.startswith("/v1/") and path not in {"/v1/info"}:
        return [{"BearerToken": []}]
    return None


def build_openapi_document(app: FastAPI) -> dict[str, Any]:
    schema = _normalize_schema_values(deepcopy(app.openapi()))
    schema["info"]["description"] = (
        "HTTP API specification for Open Messenger. "
        "The WebSocket endpoint `/v1/events/ws` is not included because OpenAPI covers HTTP operations only."
    )
    schema["servers"] = [
        {"url": "http://localhost:8000", "description": "Local development"},
    ]
    schema["tags"] = _TAG_METADATA

    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["BearerToken"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT-like",
        "description": (
            "Use `Authorization: Bearer <token>` for Native API requests. "
            "Compatibility endpoints that reuse bearer auth may also accept `Authorization: Bot <token>`."
        ),
    }
    security_schemes["AdminToken"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Admin-Token",
        "description": "Administrative token required by `/admin/v1/*` endpoints.",
    }

    for name, component_schema in components.get("schemas", {}).items():
        if not name.startswith("Body_"):
            continue
        properties = component_schema.get("properties", {})
        for upload_field in ("file", "document"):
            upload_schema = properties.get(upload_field)
            if isinstance(upload_schema, dict):
                upload_schema.pop("format", None)

    for path, methods in schema.get("paths", {}).items():
        for operation in methods.values():
            operation["tags"] = _tags_for_path(path)
            security = _security_for_path(path)
            if security is not None:
                operation["security"] = security

    stream_response = schema["paths"]["/v1/events/stream"]["get"]["responses"]["200"]
    stream_response["content"] = {"text/event-stream": {"schema": {"type": "string"}}}

    metrics_response = schema["paths"]["/metrics"]["get"]["responses"]["200"]
    metrics_response["content"] = {"text/plain": {"schema": {"type": "string"}}}

    file_response = schema["paths"]["/v1/files/{file_id}"]["get"]["responses"]["200"]
    file_response["content"] = {
        "application/octet-stream": {
            "schema": {
                "type": "string",
                "format": "binary",
            }
        }
    }

    return schema
