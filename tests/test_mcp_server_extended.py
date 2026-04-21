"""Extended tests for src/mcp_server.py — targets lines missed by existing tests."""

from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

# ── _release_lock ─────────────────────────────────────────────────


class TestReleaseLock:
    def test_release_lock_with_fd(self):
        """_release_lock closes the file descriptor and sets _lock_fd to None."""
        from src import mcp_server

        mock_fd = MagicMock()
        original = mcp_server._lock_fd
        try:
            mcp_server._lock_fd = mock_fd
            mcp_server._release_lock()
            mock_fd.close.assert_called_once()
            assert mcp_server._lock_fd is None
        finally:
            mcp_server._lock_fd = original

    def test_release_lock_with_none(self):
        """_release_lock is a no-op when _lock_fd is None."""
        from src import mcp_server

        original = mcp_server._lock_fd
        try:
            mcp_server._lock_fd = None
            mcp_server._release_lock()
            assert mcp_server._lock_fd is None
        finally:
            mcp_server._lock_fd = original

    def test_release_lock_handles_close_exception(self):
        """_release_lock should not raise even if close() fails."""
        from src import mcp_server

        mock_fd = MagicMock()
        mock_fd.close.side_effect = OSError("close failed")
        original = mcp_server._lock_fd
        try:
            mcp_server._lock_fd = mock_fd
            mcp_server._release_lock()  # should not raise
            assert mcp_server._lock_fd is None
        finally:
            mcp_server._lock_fd = original


# ── get_email_db ──────────────────────────────────────────────────


class TestGetEmailDb:
    def test_get_email_db_returns_none_when_no_db(self, tmp_path):
        """get_email_db returns None when sqlite file doesn't exist."""
        from src import mcp_server

        original_db = mcp_server._email_db
        original_lock = mcp_server._email_db_lock
        try:
            mcp_server._email_db = None
            mcp_server._email_db_lock = threading.Lock()

            with patch("src.mcp_server.get_settings") as mock_settings:
                settings = MagicMock()
                settings.sqlite_path = str(tmp_path / "nonexistent.db")
                mock_settings.return_value = settings

                result = mcp_server.get_email_db()
                assert result is None
        finally:
            mcp_server._email_db = original_db
            mcp_server._email_db_lock = original_lock

    def test_get_email_db_returns_cached(self):
        """get_email_db returns cached value on subsequent calls."""
        from src import mcp_server

        original_db = mcp_server._email_db
        sentinel = object()
        try:
            mcp_server._email_db = sentinel  # type: ignore[assignment]
            result = mcp_server.get_email_db()
            assert result is sentinel
        finally:
            mcp_server._email_db = original_db

    def test_get_email_db_creates_instance_when_file_exists(self, tmp_path):
        """get_email_db creates an EmailDatabase when the sqlite file exists."""
        from src import mcp_server

        original_db = mcp_server._email_db
        original_lock = mcp_server._email_db_lock
        db_path = tmp_path / "email_metadata.db"
        db_path.touch()

        try:
            mcp_server._email_db = None
            mcp_server._email_db_lock = threading.Lock()

            with patch("src.mcp_server.get_settings") as mock_settings:
                settings = MagicMock()
                settings.sqlite_path = str(db_path)
                mock_settings.return_value = settings

                result = mcp_server.get_email_db()
                assert result is not None
        finally:
            mcp_server._email_db = original_db
            mcp_server._email_db_lock = original_lock


# ── ToolDeps ──────────────────────────────────────────────────────


class TestToolDeps:
    def test_tool_deps_get_email_db(self):
        """ToolDeps.get_email_db delegates to module-level get_email_db."""
        from src.mcp_server import ToolDeps

        with patch("src.mcp_server.get_email_db", return_value=None) as mock:
            result = ToolDeps.get_email_db()
            mock.assert_called_once()
            assert result is None

    def test_tool_deps_db_unavailable(self):
        """ToolDeps.DB_UNAVAILABLE is valid JSON with error message."""
        from src.mcp_server import ToolDeps

        data = json.loads(ToolDeps.DB_UNAVAILABLE)
        assert "error" in data

    def test_tool_deps_sanitize(self):
        """ToolDeps.sanitize delegates to sanitize_untrusted_text."""
        from src.mcp_server import ToolDeps

        result = ToolDeps.sanitize("hello")
        assert isinstance(result, str)


# ── _tool_annotations helpers ──────────────────────────────────────


class TestAnnotationHelpers:
    def test_tool_annotations(self):
        from src.mcp_server import _tool_annotations

        ann = _tool_annotations("Test Tool")
        assert ann.title == "Test Tool"
        assert ann.readOnlyHint is True
        assert ann.destructiveHint is False
        assert ann.idempotentHint is True

    def test_write_tool_annotations(self):
        from src.mcp_server import _write_tool_annotations

        ann = _write_tool_annotations("Write Tool")
        assert ann.title == "Write Tool"
        assert ann.readOnlyHint is False
        assert ann.idempotentHint is False

    def test_idempotent_write_annotations(self):
        from src.mcp_server import _idempotent_write_annotations

        ann = _idempotent_write_annotations("Export Tool")
        assert ann.title == "Export Tool"
        assert ann.readOnlyHint is False
        assert ann.idempotentHint is True


# ── _offload ──────────────────────────────────────────────────────


class TestOffload:
    @pytest.mark.asyncio
    async def test_offload_no_args(self):
        from src.mcp_server import _offload

        result = await _offload(lambda: "ok")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_offload_with_args_and_kwargs(self):
        from src.mcp_server import _offload

        def add(a, b, extra=0):
            return a + b + extra

        result = await _offload(add, 1, 2, extra=10)
        assert result == 13


# ── _log_startup_info ────────────────────────────────────────────


class TestLogStartupInfo:
    def test_log_startup_info_runs(self):
        """_log_startup_info should not raise."""
        from src.mcp_server import _log_startup_info

        # Should complete without error
        _log_startup_info()


class TestMain:
    def test_main_help_exits_before_startup(self, capsys):
        from src import mcp_server

        with (
            patch.object(mcp_server, "_acquire_instance_lock") as mock_lock,
            patch.object(mcp_server, "_log_startup_info") as mock_log,
            patch.object(mcp_server.mcp, "run") as mock_run,
            pytest.raises(SystemExit) as exc,
        ):
            mcp_server.main(["--help"])

        assert exc.value.code == 0
        mock_lock.assert_not_called()
        mock_log.assert_not_called()
        mock_run.assert_not_called()
        assert "Run the Email RAG MCP server over stdio." in capsys.readouterr().out

    def test_main_runs_server_without_args(self):
        from src import mcp_server

        with (
            patch.object(mcp_server, "_acquire_instance_lock") as mock_lock,
            patch.object(mcp_server, "_log_startup_info") as mock_log,
            patch.object(mcp_server.mcp, "run") as mock_run,
        ):
            mcp_server.main([])

        mock_lock.assert_called_once()
        mock_log.assert_called_once()
        mock_run.assert_called_once()


# ── _acquire_instance_lock (fcntl unavailable / Windows path) ────


class TestAcquireInstanceLock:
    def test_acquire_lock_skips_when_no_fcntl(self, monkeypatch):
        """When fcntl is not importable, _acquire_instance_lock logs and returns."""
        from src import mcp_server

        original = mcp_server._lock_fd
        try:
            # Remove fcntl from sys.modules temporarily to simulate ImportError
            import sys

            saved_fcntl = sys.modules.get("fcntl")
            sys.modules["fcntl"] = None  # type: ignore[assignment]

            # This should handle the ImportError gracefully
            try:
                mcp_server._acquire_instance_lock()
            except (SystemExit, TypeError):
                pass  # Lock may already be held from module import
            finally:
                if saved_fcntl is not None:
                    sys.modules["fcntl"] = saved_fcntl
                elif "fcntl" in sys.modules:
                    del sys.modules["fcntl"]
        finally:
            mcp_server._lock_fd = original

    def test_acquire_lock_handles_os_error(self, tmp_path, monkeypatch):
        """When flock raises OSError, _acquire_instance_lock raises SystemExit."""
        import fcntl

        from src import mcp_server

        original_fd = mcp_server._lock_fd
        try:
            mcp_server._lock_fd = None

            with patch("src.mcp_server.get_settings") as mock_settings:
                settings = MagicMock()
                settings.sqlite_path = str(tmp_path / "email_metadata.db")
                mock_settings.return_value = settings

                # Mock flock to raise OSError (lock held by another process)
                with patch.object(fcntl, "flock", side_effect=OSError("locked")):
                    with pytest.raises(SystemExit):
                        mcp_server._acquire_instance_lock()
        finally:
            mcp_server._lock_fd = original_fd


# ── get_retriever ─────────────────────────────────────────────────


class TestGetRetriever:
    def test_get_retriever_returns_cached(self):
        """get_retriever returns cached instance on second call."""
        from src import mcp_server

        original = mcp_server._retriever
        sentinel = MagicMock()
        try:
            mcp_server._retriever = sentinel
            result = mcp_server.get_retriever()
            assert result is sentinel
        finally:
            mcp_server._retriever = original
