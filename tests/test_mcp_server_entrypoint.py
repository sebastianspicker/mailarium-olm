from __future__ import annotations

from unittest.mock import patch

import pytest


def test_missing_mcp_runtime_message_points_to_repo_venv() -> None:
    from src import mcp_server

    message = mcp_server._missing_mcp_runtime_message()

    assert ".venv/bin/python -m src.mcp_server" in message
    assert "mcp" in message


def test_main_exits_with_actionable_message_when_mcp_runtime_is_missing() -> None:
    from src import mcp_server

    with (
        patch.object(mcp_server, "_MCP_IMPORT_ERROR", ModuleNotFoundError("No module named 'mcp'")),
        patch.object(mcp_server, "_acquire_instance_lock") as mock_lock,
        patch.object(mcp_server, "_log_startup_info") as mock_log,
        patch.object(mcp_server.mcp, "run") as mock_run,
        pytest.raises(SystemExit) as exc,
    ):
        mcp_server.main([])

    assert ".venv/bin/python -m src.mcp_server" in str(exc.value)
    mock_lock.assert_not_called()
    mock_log.assert_not_called()
    mock_run.assert_not_called()
