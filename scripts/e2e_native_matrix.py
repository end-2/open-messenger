#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.e2e_matrix_lib import run_matrix_scenario


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the multi-user Open Messenger E2E matrix."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPEN_MESSENGER_E2E_BASE_URL", "http://127.0.0.1:18000"),
        help="Base URL for the Open Messenger API.",
    )
    parser.add_argument(
        "--admin-token",
        default=os.environ.get("OPEN_MESSENGER_E2E_ADMIN_TOKEN", "dev-admin-token"),
        help="Admin token for bootstrap operations.",
    )
    args = parser.parse_args()

    try:
        run_matrix_scenario(args.base_url, args.admin_token)
    except Exception as exc:  # noqa: BLE001
        print(f"E2E matrix failed: {exc}", file=sys.stderr)
        return 1

    print("E2E matrix passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
