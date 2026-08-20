"""Verify that raw developer projections are controlled by server environment only."""

from __future__ import annotations

import os
from unittest.mock import patch

from tools.verify_utils import isolated_workspace


def main() -> None:
    from fastapi.testclient import TestClient
    from novelforge.api.app import create_app

    with isolated_workspace("novelforge_developer_projection_"):
        with TestClient(create_app()) as client:
            with patch.dict(os.environ, {"NOVELFORGE_DEVELOPER_MODE": "0"}, clear=False):
                disabled = client.get("/api/v1/settings/developer")
                assert disabled.status_code == 200
                assert disabled.json()["data"] == {"enabled": False, "projections": []}
            with patch.dict(os.environ, {"NOVELFORGE_DEVELOPER_MODE": "1"}, clear=False):
                enabled = client.get("/api/v1/settings/developer")
                assert enabled.status_code == 200
                assert enabled.json()["data"]["enabled"] is True
                assert "raw_json" in enabled.json()["data"]["projections"]
    print("developer projection guard verification: ok")


if __name__ == "__main__":
    main()
