from __future__ import annotations

from pathlib import Path

import yaml

from app.main import create_app
from app.openapi import build_openapi_document


def main() -> None:
    app = create_app()
    document = build_openapi_document(app)
    output_path = Path("docs/openapi.yaml")
    output_path.write_text(
        yaml.safe_dump(
            document,
            sort_keys=False,
            allow_unicode=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
