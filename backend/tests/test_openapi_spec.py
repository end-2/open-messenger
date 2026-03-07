from __future__ import annotations

from pathlib import Path

import yaml


def test_openapi_yaml_documents_expected_contract() -> None:
    document = yaml.safe_load(Path("docs/openapi.yaml").read_text(encoding="utf-8"))

    assert document["openapi"] == "3.1.0"
    assert document["info"]["title"] == "Open Messenger API"
    assert document["info"]["version"] == "v0.1"

    security_schemes = document["components"]["securitySchemes"]
    assert set(security_schemes) == {"BearerToken", "AdminToken"}

    paths = document["paths"]
    assert "/v1/channels" in paths
    assert "/v1/messages:batchCreate" in paths
    assert "/compat/slack/chat.postMessage" in paths
    assert "/admin/v1/tokens/{token_id}/rotate" in paths
    assert "/admin/v1/channels/{channel_id}" in paths

    assert paths["/v1/channels"]["get"]["security"] == [{"BearerToken": []}]
    assert paths["/v1/channels"]["post"]["security"] == [{"BearerToken": []}]
    assert paths["/admin/v1/users"]["post"]["security"] == [{"AdminToken": []}]
    assert paths["/admin/v1/channels/{channel_id}"]["delete"]["security"] == [{"AdminToken": []}]
    assert paths["/compat/slack/chat.postMessage"]["post"]["security"] == [{"BearerToken": []}]
    assert "security" not in paths["/compat/telegram/bot{bot_token}/sendMessage"]["post"]

    assert (
        paths["/metrics"]["get"]["responses"]["200"]["content"]["text/plain"]["schema"]["type"]
        == "string"
    )
    assert (
        paths["/v1/events/stream"]["get"]["responses"]["200"]["content"]["text/event-stream"][
            "schema"
        ]["type"]
        == "string"
    )
    assert (
        paths["/v1/files/{file_id}"]["get"]["responses"]["200"]["content"][
            "application/octet-stream"
        ]["schema"]["format"]
        == "binary"
    )
