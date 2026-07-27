"""Package entry-point delegation to the MCP server main function."""

from __future__ import annotations

import runpy
from unittest.mock import patch


def test_main_module_importable() -> None:
    """mailarium.__main__ must be importable without side effects when main() is mocked."""
    with patch("mailarium.mcp_server.main") as mock_main:
        # Running as a module calls main(); patch it to avoid server startup.
        runpy.run_module("mailarium", run_name="__main__", alter_sys=False)
        mock_main.assert_called_once()


def test_main_module_calls_mcp_server_main() -> None:
    """Verify the module-level call reaches mcp_server.main."""
    calls: list[str] = []

    def _fake_main() -> None:
        calls.append("called")

    with patch("mailarium.mcp_server.main", _fake_main):
        runpy.run_module("mailarium", run_name="__main__", alter_sys=False)

    assert calls == ["called"]
