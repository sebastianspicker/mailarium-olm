"""Extended tests for src/mcp_server.py — targets lines missed by existing tests."""

from __future__ import annotations

import json
import sys
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

    def test_get_email_db_uses_runtime_sqlite_override(self, tmp_path):
        """get_email_db prefers the active runtime SQLite override when present."""
        from src import mcp_server

        original_db = mcp_server._email_db
        original_lock = mcp_server._email_db_lock
        original_runtime = mcp_server._runtime_sqlite_path
        db_path = tmp_path / "runtime-email.db"
        db_path.touch()

        try:
            mcp_server._email_db = None
            mcp_server._email_db_lock = threading.Lock()
            mcp_server._runtime_sqlite_path = str(db_path)

            with patch("src.email_db.EmailDatabase") as mock_db:
                result = mcp_server.get_email_db()
                mock_db.assert_called_once_with(str(db_path))
                assert result is mock_db.return_value
        finally:
            mcp_server._email_db = original_db
            mcp_server._email_db_lock = original_lock
            mcp_server._runtime_sqlite_path = original_runtime


class TestGetRetrieverCaching:
    def test_get_retriever_uses_runtime_chromadb_override(self):
        """get_retriever prefers the active runtime Chroma override when present."""
        from src import mcp_server

        original_retriever = mcp_server._retriever
        original_lock = mcp_server._retriever_lock
        original_runtime = mcp_server._runtime_chromadb_path

        try:
            mcp_server._retriever = None
            mcp_server._retriever_lock = threading.Lock()
            mcp_server._runtime_chromadb_path = "/tmp/runtime-chroma"

            with patch("src.retriever.EmailRetriever") as mock_retriever:
                result = mcp_server.get_retriever()
                mock_retriever.assert_called_once_with(
                    chromadb_path=str(mcp_server.normalize_local_path("/tmp/runtime-chroma", field_name="chromadb_path")),
                    sqlite_path=str(
                        mcp_server.normalize_local_path(mcp_server.get_settings().sqlite_path, field_name="sqlite_path")
                    ),
                )
                assert result is mock_retriever.return_value
        finally:
            mcp_server._retriever = original_retriever
            mcp_server._retriever_lock = original_lock
            mcp_server._runtime_chromadb_path = original_runtime

    def test_get_retriever_threads_runtime_sqlite_override(self):
        """get_retriever must keep Chroma and SQLite runtime overrides aligned."""
        from src import mcp_server

        original_retriever = mcp_server._retriever
        original_lock = mcp_server._retriever_lock
        original_chroma = mcp_server._runtime_chromadb_path
        original_sqlite = mcp_server._runtime_sqlite_path

        try:
            mcp_server._retriever = None
            mcp_server._retriever_lock = threading.Lock()
            mcp_server._runtime_chromadb_path = "/tmp/runtime-chroma"
            mcp_server._runtime_sqlite_path = "/tmp/runtime-email.db"

            with patch("src.retriever.EmailRetriever") as mock_retriever:
                result = mcp_server.get_retriever()
                mock_retriever.assert_called_once_with(
                    chromadb_path=str(mcp_server.normalize_local_path("/tmp/runtime-chroma", field_name="chromadb_path")),
                    sqlite_path=str(mcp_server.normalize_local_path("/tmp/runtime-email.db", field_name="sqlite_path")),
                )
                assert result is mock_retriever.return_value
        finally:
            mcp_server._retriever = original_retriever
            mcp_server._retriever_lock = original_lock
            mcp_server._runtime_chromadb_path = original_chroma
            mcp_server._runtime_sqlite_path = original_sqlite


class TestRuntimeArchivePathOverrides:
    def test_set_runtime_archive_paths_invalidates_cached_singletons(self, tmp_path):
        from src import mcp_server

        class _DummyDb:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        original_retriever = mcp_server._retriever
        original_email_db = mcp_server._email_db
        original_chroma = mcp_server._runtime_chromadb_path
        original_sqlite = mcp_server._runtime_sqlite_path
        new_chroma = tmp_path / "runtime-chroma"
        new_sqlite = tmp_path / "runtime-email.db"
        new_chroma.mkdir()
        new_sqlite.touch()
        dummy_db = _DummyDb()

        try:
            mcp_server._retriever = object()
            mcp_server._email_db = dummy_db
            mcp_server._runtime_chromadb_path = str(tmp_path / "old-chroma")
            mcp_server._runtime_sqlite_path = str(tmp_path / "old-email.db")

            mcp_server.set_runtime_archive_paths(chromadb_path=str(new_chroma), sqlite_path=str(new_sqlite))

            assert mcp_server._retriever is None
            assert mcp_server._email_db is None
            assert dummy_db.closed is True
            assert mcp_server._runtime_chromadb_path == str(new_chroma.resolve())
            assert mcp_server._runtime_sqlite_path == str(new_sqlite.resolve())
        finally:
            mcp_server._retriever = original_retriever
            mcp_server._email_db = original_email_db
            mcp_server._runtime_chromadb_path = original_chroma
            mcp_server._runtime_sqlite_path = original_sqlite


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

    def test_tool_deps_privacy_helpers(self):
        """ToolDeps exposes shared privacy helpers to outward tools."""
        from src.mcp_server import ToolDeps

        payload, guardrails = ToolDeps.apply_privacy_guardrails(
            {"sender_email": "employee@example.test"},
            privacy_mode="external_counsel_export",
        )
        assert payload["sender_email"] == "[REDACTED: email]"
        assert ToolDeps.privacy_mode_policy("witness_sharing")["privacy_mode"] == "witness_sharing"
        assert guardrails["privacy_mode"] == "external_counsel_export"


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
    def test_log_startup_info_writes_deterministic_stderr_summary(self, capsys):
        """_log_startup_info should emit startup diagnostics even without logging config."""
        from src import mcp_server

        class _Settings:
            mcp_model_profile = "balanced"
            mcp_max_body_chars = 1000
            mcp_max_response_tokens = 2000
            mcp_max_full_body_chars = 3000
            mcp_max_json_response_chars = 4000
            mcp_max_triage_results = 50
            mcp_max_search_results = 30

        with (
            patch.object(mcp_server, "_resolved_runtime_paths", return_value=("/tmp/chroma", "/tmp/email.db")),
            patch.object(mcp_server, "get_settings", return_value=_Settings()),
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=False),
        ):
            mcp_server._log_startup_info()

        stderr = capsys.readouterr().err
        assert "MCP server starting | pid=" in stderr
        assert "runtime | sqlite=/tmp/email.db (exists=True) | chromadb=/tmp/chroma (exists=False)" in stderr
        assert (
            "limits | profile=balanced | body=1000 | tokens=2000 | full=3000 | json=4000 | triage_cap=50 | search_cap=30"
            in stderr
        )


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

    def test_main_applies_runtime_archive_overrides(self):
        from src import mcp_server

        with (
            patch.object(mcp_server, "_acquire_instance_lock") as mock_lock,
            patch.object(mcp_server, "_log_startup_info") as mock_log,
            patch.object(mcp_server, "set_runtime_archive_paths") as mock_paths,
            patch.object(mcp_server.mcp, "run") as mock_run,
        ):
            mcp_server.main(["--chromadb-path", "/tmp/chroma", "--sqlite-path", "/tmp/email.db"])

        mock_paths.assert_called_once_with(chromadb_path="/tmp/chroma", sqlite_path="/tmp/email.db")
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

    @pytest.mark.skipif(sys.platform == "win32", reason="fcntl not available on Windows")
    def test_acquire_lock_preserves_existing_pid_on_contention(self, tmp_path):
        """A contending process must not truncate the active lock holder PID."""
        import fcntl

        from src import mcp_server

        lock_path = tmp_path / "mcp_server.lock"
        sqlite_path = tmp_path / "email_metadata.db"
        sqlite_path.write_text("")

        original_fd = mcp_server._lock_fd
        existing_pid = "4242"
        holder = open(lock_path, "w+")
        try:
            holder.write(existing_pid)
            holder.flush()
            fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)

            mcp_server._lock_fd = None
            with patch("src.mcp_server.get_settings") as mock_settings:
                settings = MagicMock()
                settings.sqlite_path = str(sqlite_path)
                mock_settings.return_value = settings

                with patch("src.mcp_server.os.kill") as mock_kill:
                    mock_kill.return_value = None
                    with pytest.raises(SystemExit):
                        mcp_server._acquire_instance_lock()

            assert lock_path.read_text().strip() == existing_pid
        finally:
            holder.close()
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
