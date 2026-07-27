"""Fails the MCP entry point early with a repository-local setup message when its runtime dependency is absent."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest


def test_missing_mcp_runtime_message_points_to_repo_venv() -> None:
    from mailarium import mcp_server

    message = mcp_server._missing_mcp_runtime_message()

    assert ".venv/bin/python -m mailarium.mcp_server" in message
    assert "mcp" in message


def test_main_exits_with_actionable_message_when_mcp_runtime_is_missing() -> None:
    from mailarium import mcp_server

    with ExitStack() as patches:
        patches.enter_context(patch.object(mcp_server, "_MCP_IMPORT_ERROR", ModuleNotFoundError("No module named 'mcp'")))
        mock_lock = patches.enter_context(patch.object(mcp_server, "_acquire_instance_lock"))
        mock_log = patches.enter_context(patch.object(mcp_server, "_log_startup_info"))
        mock_run = patches.enter_context(patch.object(mcp_server.mcp, "run"))
        with pytest.raises(SystemExit) as exc:
            mcp_server.main([])

    assert ".venv/bin/python -m mailarium.mcp_server" in str(exc.value)
    mock_lock.assert_not_called()
    mock_log.assert_not_called()
    mock_run.assert_not_called()
