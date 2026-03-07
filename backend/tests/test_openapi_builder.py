from __future__ import annotations

from app.api.openapi import build_openapi_document
from app.main import create_app


def test_build_openapi_document_uses_api_module_location() -> None:
    app = create_app()

    document = build_openapi_document(app)

    assert document["info"]["title"] == "Open Messenger API"
    assert document["paths"]["/v1/channels"]["get"]["tags"] == ["Native API"]
    assert document["paths"]["/admin/v1/users"]["post"]["tags"] == ["Admin API"]
