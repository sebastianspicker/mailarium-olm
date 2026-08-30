"""
MCP Server for Mailarium.

Exposes email search as tools that any MCP client can call directly.
Run with: python -m mailarium.mcp_server

Example MCP client settings:
{
    "mcpServers": {
        "mailarium": {
            "command": "<repo-root>/.venv/bin/python",
            "args": ["-m", "mailarium.mcp_server"],
            "cwd": "<repo-root>"
        }
    }
}

IMPORTANT: Use absolute paths when your MCP client launches servers from a
different working directory.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import logging
import os
import sys
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO, cast

from dotenv import load_dotenv

from . import __version__

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.mailbox.mailbox_service import MailboxService
    from mailarium.retrieval.retriever import SearchEngine

try:
    from mcp.server.fastmcp import FastMCP as _FastMCP
    from mcp.types import ToolAnnotations as _MCPToolAnnotations

    _MCP_IMPORT_ERROR: ModuleNotFoundError | None = None
    FastMCP = cast(Any, _FastMCP)  # re-export of external class
    ToolAnnotations = cast(Any, _MCPToolAnnotations)
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in interpreter-specific entrypoint tests
    _MCP_IMPORT_ERROR = exc
    FastMCP = cast(Any, None)  # fallback when MCP is unavailable

    @dataclass
    class _FallbackToolAnnotations:
        # camelCase attributes are MCP protocol spec contract names.
        title: str
        readOnlyHint: bool
        destructiveHint: bool
        idempotentHint: bool
        openWorldHint: bool

    ToolAnnotations = cast(Any, _FallbackToolAnnotations)

from mailarium.platform.repo_paths import normalize_local_path, validate_runtime_path
from mailarium.platform.sanitization import (
    apply_privacy_guardrails,
    privacy_mode_policy,
    sanitize_untrusted_text,
)
from mailarium.runtime import ApplicationRuntime

from .config import clear_settings_cache, get_settings

logger = logging.getLogger(__name__)

load_dotenv()
# Clear any previously cached settings so they reflect the .env values
# loaded above instead of a stale Settings instance built before load_dotenv ran.
clear_settings_cache()


class McpRuntimeState:
    """Own one registered MCP server's runtime generation and path overrides.

    Offloaded tool work holds a lease for its complete blocking call.  A reset
    or path change therefore waits until the old generation is no longer in
    use before closing its resources.
    """

    def __init__(
        self,
        *,
        vector_index_path: str | None = None,
        sqlite_path: str | None = None,
        runtime_factory: Callable[..., ApplicationRuntime] = ApplicationRuntime,
    ) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._runtime_factory = runtime_factory
        self._vector_index_path = self._validated_override(vector_index_path, field_name="vector_index_path")
        self._sqlite_path = self._validated_override(sqlite_path, field_name="sqlite_path")
        self._runtime: ApplicationRuntime | None = None
        self._in_flight_leases = 0
        self._lease_local = threading.local()
        self._reset_pending = False
        self._closed = False

    @staticmethod
    def _validated_override(path: str | None, *, field_name: str) -> str | None:
        if path is None:
            return None
        return str(validate_runtime_path(path, field_name=field_name))

    def resolved_runtime_paths(self) -> tuple[str, str]:
        """Return active paths after applying this server's local overrides."""
        with self._condition:
            self._ensure_open()
            return self._resolved_runtime_paths_locked()

    def get_application_runtime(self) -> ApplicationRuntime:
        """Return the one runtime identity for the active generation."""
        with self._condition:
            self._ensure_open()
            if self._runtime is None:
                vector_index_path, sqlite_path = self._resolved_runtime_paths_locked()
                self._runtime = self._runtime_factory(
                    vector_index_path=vector_index_path,
                    sqlite_path=sqlite_path,
                )
            return self._runtime

    def get_retriever(self) -> Any:
        """Return the active generation's shared search engine."""
        return self.get_application_runtime().search_engine

    def get_archive_database(self) -> Any:
        """Return the active generation's archive database when it exists."""
        return self.get_application_runtime().archive_database

    def get_mailbox_service(self) -> Any:
        """Return the active generation's proposal-gated mailbox service."""
        return self.get_application_runtime().mailbox_service()

    @property
    def in_flight_leases(self) -> int:
        """Expose the current lease count for lifecycle diagnostics and tests."""
        with self._condition:
            return self._in_flight_leases

    @contextmanager
    def lease(self) -> Generator:
        """Keep the active generation open for one blocking operation."""
        with self._condition:
            self._ensure_open()
            self._in_flight_leases += 1
        self._lease_local.depth = getattr(self._lease_local, "depth", 0) + 1
        try:
            yield
        finally:
            self._lease_local.depth -= 1
            runtime: ApplicationRuntime | None = None
            with self._condition:
                self._in_flight_leases -= 1
                if self._in_flight_leases == 0 and self._reset_pending:
                    self._reset_pending = False
                    runtime = self._runtime
                    self._runtime = None
                self._condition.notify_all()
            self._close_runtime(runtime)

    async def offload(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run blocking MCP work in a leased worker thread."""

        def _run() -> Any:
            with self.lease():
                return fn(*args, **kwargs)

        return await asyncio.to_thread(_run)

    def set_archive_paths(
        self,
        *,
        vector_index_path: str | None = None,
        sqlite_path: str | None = None,
    ) -> bool:
        """Set validated overrides and replace the runtime after leases drain."""
        vector_override = self._validated_override(vector_index_path, field_name="vector_index_path")
        sqlite_override = self._validated_override(sqlite_path, field_name="sqlite_path")
        with self._condition:
            self._ensure_open()
            next_vector = self._vector_index_path if vector_index_path is None else vector_override
            next_sqlite = self._sqlite_path if sqlite_path is None else sqlite_override
            if next_vector == self._vector_index_path and next_sqlite == self._sqlite_path:
                return False
            runtime = self._detach_runtime_after_leases_locked()
            self._vector_index_path = next_vector
            self._sqlite_path = next_sqlite
        self._close_runtime(runtime)
        return True

    def reset_runtime_clients(self) -> None:
        """Discard the active runtime only after all offloaded calls complete."""
        with self._condition:
            self._ensure_open()
            if getattr(self._lease_local, "depth", 0):
                self._reset_pending = True
                return
            runtime = self._detach_runtime_after_leases_locked()
        self._close_runtime(runtime)

    def close(self) -> None:
        """Close this server state once; later calls are harmless."""
        with self._condition:
            if self._closed:
                return
            runtime = self._detach_runtime_after_leases_locked()
            self._closed = True
        self._close_runtime(runtime)

    def _resolved_runtime_paths_locked(self) -> tuple[str, str]:
        settings = get_settings()
        vector_index_path = self._vector_index_path or settings.vector_index_path
        sqlite_path = self._sqlite_path or settings.sqlite_path
        return (
            str(normalize_local_path(vector_index_path, field_name="vector_index_path")),
            str(normalize_local_path(sqlite_path, field_name="sqlite_path")),
        )

    def _detach_runtime_after_leases_locked(self) -> ApplicationRuntime | None:
        while self._in_flight_leases:
            self._condition.wait()
        runtime = self._runtime
        self._runtime = None
        return runtime

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("MCP runtime state is closed")

    @staticmethod
    def _close_runtime(runtime: ApplicationRuntime | None) -> None:
        if runtime is not None:
            runtime.close()


# ── Instance lock ─────────────────────────────────────────────

_lock_fd: TextIO | None = None  # module-level mutable singleton, not a constant


def _is_stale_lock_pid(existing_pid: str) -> bool:
    """Return whether a lock PID no longer identifies a live process."""
    if not existing_pid or existing_pid == "unknown":
        return False

    try:
        os.kill(int(existing_pid), 0)  # signal 0 = existence check
    except OSError, ValueError:
        return True
    return False


def _acquire_instance_lock(state: McpRuntimeState) -> None:
    """Acquire an exclusive file lock for one configured server state.

    Uses ``fcntl.flock`` (Unix) with ``LOCK_EX | LOCK_NB``. On platforms where
    ``fcntl`` is unavailable, log a warning and continue without locking.
    """
    global _lock_fd
    try:
        import fcntl
    except ImportError:
        logger.warning("fcntl is not available; continuing without an MCP instance lock.")
        return

    _vector_index_path, sqlite_path = state.resolved_runtime_paths()
    data_dir = Path(sqlite_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "mcp_server.lock"

    lock_path.touch(exist_ok=True)
    fd = open(lock_path, "r+", encoding="utf-8")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            fd.seek(0)
            existing_pid = fd.read().strip()
        except OSError, ValueError:
            existing_pid = "unknown"

        # Check if the locking process is still alive.  A stale lock from
        # a crashed server should not block startup.
        stale = _is_stale_lock_pid(existing_pid)

        if stale:
            logger.warning(
                "Stale lock from dead process (PID %s) - reclaiming lock.",
                existing_pid,
            )
            fd.close()
            fd = open(lock_path, "r+", encoding="utf-8")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                logger.error("Failed to reclaim stale lock.")
                fd.close()
                raise SystemExit(1) from None
        else:
            logger.error(
                "Another MCP server instance is already running (PID %s). Only one instance can access the database at a time.",
                existing_pid,
            )
            fd.close()
            raise SystemExit(1) from None

    fd.seek(0)
    fd.truncate()
    fd.write(str(os.getpid()))
    fd.flush()
    _lock_fd = fd
    atexit.register(_release_lock)


def _release_lock() -> None:
    """Manage lock for the runtime lifecycle."""
    global _lock_fd
    if _lock_fd is not None:
        try:
            _lock_fd.close()
        except OSError:
            logger.debug("Failed to close MCP server lock during shutdown", exc_info=True)
        _lock_fd = None


def _log_startup_info(state: McpRuntimeState) -> None:
    """Log diagnostic info to stderr on startup."""
    vector_index_path, sqlite_path = state.resolved_runtime_paths()
    settings = get_settings()
    sqlite_exists = os.path.exists(sqlite_path)
    vector_index_exists = os.path.isdir(vector_index_path)
    lines = [
        f"MCP server starting | pid={os.getpid()} | python={sys.executable} | cwd={os.getcwd()}",
        f"runtime | sqlite={sqlite_path} (exists={sqlite_exists}) "
        f"| vector_index={vector_index_path} (exists={vector_index_exists})",
        (
            f"limits | profile={settings.mcp_model_profile} | body={settings.mcp_max_body_chars} "
            f"| tokens={settings.mcp_max_response_tokens} | full={settings.mcp_max_full_body_chars} "
            f"| json={settings.mcp_max_json_response_chars} | triage_cap={settings.mcp_max_triage_results} "
            f"| search_cap={settings.mcp_max_search_results}"
        ),
    ]
    summary = "\n".join(lines)
    sys.stderr.write(summary + "\n")
    sys.stderr.flush()
    for line in lines:
        logger.info(line)


def _missing_mcp_runtime_message() -> str:
    """Explain how to start the server with an interpreter that provides FastMCP."""
    return (
        "The active Python interpreter does not have the 'mcp' package installed. "
        "Use '.venv/bin/python -m mailarium.mcp_server' or install this project's dependencies in the current interpreter."
    )


class _MissingFastMCP:
    """Fallback MCP runtime placeholder when the active interpreter lacks the mcp package."""

    def __init__(self, _name: str):
        self._name = _name

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Preserve import-time tool decoration until the missing runtime fails at startup."""

        def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return _decorator

    def run(self) -> None:
        """Fail explicitly when the optional MCP runtime is unavailable."""
        raise SystemExit(_missing_mcp_runtime_message())


def _tool_annotations(title: str) -> Any:
    """Standardized non-destructive MCP tool annotations."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


_DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available. Run ingestion first."})


def _write_tool_annotations(title: str) -> Any:
    """Tool annotations for write operations."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )


def _idempotent_write_annotations(title: str) -> Any:
    """Tool annotations for idempotent write operations (report/export/ingest)."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _remote_sync_annotations(title: str) -> Any:
    """Annotations for remote reads that mutate only canonical local state."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )


def _remote_execute_annotations(title: str) -> Any:
    """Annotations for proposal-bound remote mailbox mutations."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    )


def _sanitize_tool_text(text: str) -> str:
    """Sanitize tool text before exposing it."""
    return sanitize_untrusted_text(text)


# ── Tool Module Registration ──────────────────────────────────


class ToolDeps:
    """Dependencies injected into tool modules to avoid circular imports."""

    def __init__(self, state: McpRuntimeState) -> None:
        self._state = state

    def get_retriever(self) -> SearchEngine:
        """Expose the shared retriever to registered tool modules."""
        return cast(SearchEngine, self._state.get_retriever())

    def get_archive_database(self) -> ArchiveDatabase | None:
        """Expose the optional shared metadata database to registered tool modules."""
        return cast(ArchiveDatabase | None, self._state.get_archive_database())

    def get_mailbox_service(self) -> MailboxService | None:
        """Expose the shared proposal-gated mailbox service."""
        return cast(MailboxService | None, self._state.get_mailbox_service())

    def resolved_runtime_paths(self) -> tuple[str, str]:
        """Expose the active archive paths without coupling tools to this module."""
        return self._state.resolved_runtime_paths()

    def reset_runtime_clients(self) -> None:
        """Invalidate archive-backed runtime clients after a successful mutation."""
        self._state.reset_runtime_clients()

    async def offload(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run blocking tool work through this registration's leased state."""
        return await self._state.offload(fn, *args, **kwargs)

    tool_annotations = staticmethod(_tool_annotations)
    write_tool_annotations = staticmethod(_write_tool_annotations)
    idempotent_write_annotations = staticmethod(_idempotent_write_annotations)
    remote_sync_annotations = staticmethod(_remote_sync_annotations)
    remote_execute_annotations = staticmethod(_remote_execute_annotations)
    DB_UNAVAILABLE = _DB_UNAVAILABLE
    sanitize = staticmethod(_sanitize_tool_text)
    apply_privacy_guardrails = staticmethod(apply_privacy_guardrails)
    privacy_mode_policy = staticmethod(privacy_mode_policy)


def create_mcp_server(state: McpRuntimeState) -> Any:
    """Register one MCP server whose tools resolve through ``state``."""
    server = FastMCP("mailarium") if FastMCP is not None else _MissingFastMCP("mailarium")
    if FastMCP is not None:
        from mailarium.interfaces.mcp.tools import register_all

        register_all(cast(Any, server), ToolDeps(state))
    return server


# ── Entry Point ────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the stdio server CLI with process-local archive path overrides."""
    parser = argparse.ArgumentParser(
        prog="python -m mailarium.mcp_server",
        description="Run the Mailarium MCP server over stdio.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--vector-index-path", default=None, help="Custom USearch vector index path for this MCP server process.")
    parser.add_argument("--sqlite-path", default=None, help="Custom SQLite metadata path for this MCP server process.")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Startup routine: acquire lock, log diagnostics, then run the server."""
    args = _build_arg_parser().parse_args(argv)
    state = McpRuntimeState(
        vector_index_path=getattr(args, "vector_index_path", None),
        sqlite_path=getattr(args, "sqlite_path", None),
    )
    if _MCP_IMPORT_ERROR is not None:
        raise SystemExit(_missing_mcp_runtime_message()) from _MCP_IMPORT_ERROR
    try:
        _acquire_instance_lock(state)
        _log_startup_info(state)
        create_mcp_server(state).run()
    finally:
        state.close()
        _release_lock()


if __name__ == "__main__":
    main()
