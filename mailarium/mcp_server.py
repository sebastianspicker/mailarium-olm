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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO, cast

from dotenv import load_dotenv

from . import __version__

if TYPE_CHECKING:
    from .email_db import EmailDatabase
    from .mailbox_service import MailboxService
    from .retriever import EmailRetriever

try:
    from mcp.server.fastmcp import FastMCP as _FastMCP
    from mcp.types import ToolAnnotations as _MCPToolAnnotations

    _MCP_IMPORT_ERROR: ModuleNotFoundError | None = None
    FastMCP = cast(Any, _FastMCP)  # pylint: disable=invalid-name  # re-export of external class
    ToolAnnotations = cast(Any, _MCPToolAnnotations)
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in interpreter-specific entrypoint tests
    _MCP_IMPORT_ERROR = exc
    FastMCP = cast(Any, None)  # pylint: disable=invalid-name  # fallback when MCP is unavailable

    @dataclass
    class _FallbackToolAnnotations:  # pylint: disable=invalid-name
        # camelCase attributes are MCP protocol spec contract names.
        title: str
        readOnlyHint: bool
        destructiveHint: bool
        idempotentHint: bool
        openWorldHint: bool

    ToolAnnotations = cast(Any, _FallbackToolAnnotations)

from .config import clear_settings_cache, get_settings
from .repo_paths import normalize_local_path, validate_runtime_path
from .sanitization import (
    apply_privacy_guardrails,
    privacy_mode_policy,
    sanitize_untrusted_text,
)

logger = logging.getLogger(__name__)

load_dotenv()
# Clear any previously cached settings so they reflect the .env values
# loaded above instead of a stale Settings instance built before load_dotenv ran.
clear_settings_cache()

# ── Instance lock ─────────────────────────────────────────────

_lock_fd: TextIO | None = None  # module-level mutable singleton, not a constant


def _acquire_instance_lock() -> None:
    """Acquire an exclusive file lock to prevent concurrent instances.

    Uses ``fcntl.flock`` (Unix) with ``LOCK_EX | LOCK_NB``. On platforms where
    ``fcntl`` is unavailable, log a warning and continue without locking.
    """
    global _lock_fd  # pylint: disable=global-statement
    try:
        import fcntl
    except ImportError:
        logger.warning("fcntl is not available; continuing without an MCP instance lock.")
        return

    _vector_index_path, sqlite_path = _resolved_runtime_paths()
    data_dir = Path(sqlite_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "mcp_server.lock"

    lock_path.touch(exist_ok=True)
    fd = open(lock_path, "r+", encoding="utf-8")  # pylint: disable=consider-using-with
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
        stale = False
        if existing_pid and existing_pid != "unknown":
            try:
                os.kill(int(existing_pid), 0)  # signal 0 = existence check
            except OSError, ValueError:
                stale = True

        if stale:
            logger.warning(
                "Stale lock from dead process (PID %s) - reclaiming lock.",
                existing_pid,
            )
            fd.close()
            fd = open(lock_path, "r+", encoding="utf-8")  # pylint: disable=consider-using-with
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
    global _lock_fd  # pylint: disable=global-statement
    if _lock_fd is not None:
        try:
            _lock_fd.close()
        except OSError:
            logger.debug("Failed to close MCP server lock during shutdown", exc_info=True)
        _lock_fd = None


def _log_startup_info() -> None:
    """Log diagnostic info to stderr on startup."""
    vector_index_path, sqlite_path = _resolved_runtime_paths()
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


mcp = FastMCP("mailarium") if FastMCP is not None else _MissingFastMCP("mailarium")

_retriever = None  # pylint: disable=invalid-name  # lazy singleton, mutated at runtime
_retriever_lock = threading.Lock()
_runtime_vector_index_path: str | None = None
_runtime_sqlite_path: str | None = None


def _runtime_path_override_changed(path: str | None, *, field_name: str, current: str | None) -> tuple[str | None, bool]:
    """Validate supplied overrides and report whether they require client reinitialization."""
    if path is None:
        return current, False
    normalized = str(validate_runtime_path(path, field_name=field_name))
    return normalized, normalized != current


def _reset_runtime_clients() -> None:
    """Close and discard cached clients after runtime-path configuration changes."""
    global _email_db, _mailbox_service, _retriever  # pylint: disable=used-before-assignment,global-statement
    with _retriever_lock:
        _retriever = None
    with _mailbox_service_lock:
        _mailbox_service = None  # pylint: disable=used-before-assignment
    old_email_db = None
    with _email_db_lock:
        old_email_db = _email_db  # pylint: disable=used-before-assignment
        _email_db = None
    close = getattr(old_email_db, "close", None)
    if close is not None and callable(close):
        try:
            close()  # pylint: disable=not-callable
        except OSError:
            logger.debug("Failed to release file lock", exc_info=True)


def set_runtime_archive_paths(*, vector_index_path: str | None = None, sqlite_path: str | None = None) -> None:
    """Apply process-local archive overrides and reset stale database or retriever clients."""
    global _runtime_vector_index_path, _runtime_sqlite_path  # pylint: disable=global-statement
    new_vector_index_path, vector_index_changed = _runtime_path_override_changed(
        vector_index_path,
        field_name="vector_index_path",
        current=_runtime_vector_index_path,
    )
    new_sqlite_path, sqlite_changed = _runtime_path_override_changed(
        sqlite_path,
        field_name="sqlite_path",
        current=_runtime_sqlite_path,
    )
    if not (vector_index_changed or sqlite_changed):
        return
    _runtime_vector_index_path = new_vector_index_path
    _runtime_sqlite_path = new_sqlite_path
    _reset_runtime_clients()


def _resolved_runtime_paths() -> tuple[str, str]:
    """Resolve configured paths after applying validated process-local overrides."""
    settings = get_settings()
    vector_index_path = _runtime_vector_index_path or settings.vector_index_path
    sqlite_path = _runtime_sqlite_path or settings.sqlite_path
    return (
        str(normalize_local_path(vector_index_path, field_name="vector_index_path")),
        str(normalize_local_path(sqlite_path, field_name="sqlite_path")),
    )


def _tool_annotations(title: str) -> Any:
    """Standardized non-destructive MCP tool annotations."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def get_retriever() -> EmailRetriever:
    """Lazy singleton for the email retriever.

    Thread-safe via double-checked locking: the fast path reads
    ``_retriever`` without the lock (safe under CPython GIL since
    pointer reads are atomic).  The slow path acquires the lock and
    rechecks to prevent duplicate initialization.  Once initialized,
    the retriever is read-only and shared across all worker threads.
    """
    global _retriever  # pylint: disable=global-statement
    if _retriever is not None:
        return _retriever
    with _retriever_lock:
        if _retriever is None:
            from .retriever import EmailRetriever

            vector_index_path, sqlite_path = _resolved_runtime_paths()
            _retriever = EmailRetriever(
                vector_index_path=vector_index_path,
                sqlite_path=sqlite_path,
            )
    if _retriever is None:
        raise RuntimeError("Retriever initialization failed")
    return _retriever


# ── EmailDatabase helper ──────────────────────────────────────

_email_db = None  # pylint: disable=invalid-name  # lazy singleton, mutated at runtime
_email_db_lock = threading.Lock()
_mailbox_service = None  # pylint: disable=invalid-name
_mailbox_service_lock = threading.Lock()

_DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available. Run ingestion first."})


def get_email_db() -> EmailDatabase | None:
    """Lazy singleton for the SQLite email database.

    Thread-safe via double-checked locking (same pattern as
    ``get_retriever``).  The returned ``EmailDatabase`` instance uses
    ``check_same_thread=False`` + WAL mode, which is safe for concurrent
    reads from multiple ``asyncio.to_thread`` workers.  Write operations
    (evidence_add, etc.) are serialized by SQLite's internal WAL locking.
    """
    global _email_db  # pylint: disable=global-statement
    if _email_db is not None:
        return _email_db
    with _email_db_lock:
        if _email_db is None:
            from .email_db import EmailDatabase

            _vector_index_path, sqlite_path = _resolved_runtime_paths()
            if Path(sqlite_path).exists():
                _email_db = EmailDatabase(sqlite_path)
    return _email_db


def get_mailbox_service() -> MailboxService | None:
    """Return the shared mailbox service on the canonical SQLite connection."""
    global _mailbox_service  # pylint: disable=global-statement
    if _mailbox_service is not None:
        return _mailbox_service
    with _mailbox_service_lock:
        if _mailbox_service is None:
            db = get_email_db()
            if db is None:
                return None
            from .embedder import EmailEmbedder
            from .mailbox_service import MailboxService
            from .mailbox_store import MailboxStore

            vector_index_path, sqlite_path = _resolved_runtime_paths()
            _mailbox_service = MailboxService(
                MailboxStore(db.conn, operation_context=db.operation),
                db=db,
                embedder_factory=lambda: EmailEmbedder(
                    vector_index_path=vector_index_path,
                    sqlite_path=sqlite_path,
                ),
            )
    return _mailbox_service


async def _offload(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run blocking tool work off the event loop; callers must remain thread-safe."""
    if args or kwargs:
        import functools

        return await asyncio.to_thread(functools.partial(fn, *args, **kwargs))
    return await asyncio.to_thread(fn)


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

    @staticmethod
    def get_retriever() -> EmailRetriever:
        """Expose the shared retriever to registered tool modules."""
        return get_retriever()

    @staticmethod
    def get_email_db() -> EmailDatabase | None:
        """Expose the optional shared metadata database to registered tool modules."""
        return get_email_db()

    @staticmethod
    def get_mailbox_service() -> MailboxService | None:
        """Expose the shared proposal-gated mailbox service."""
        return get_mailbox_service()

    offload = staticmethod(_offload)
    tool_annotations = staticmethod(_tool_annotations)
    write_tool_annotations = staticmethod(_write_tool_annotations)
    idempotent_write_annotations = staticmethod(_idempotent_write_annotations)
    remote_sync_annotations = staticmethod(_remote_sync_annotations)
    remote_execute_annotations = staticmethod(_remote_execute_annotations)
    DB_UNAVAILABLE = _DB_UNAVAILABLE
    sanitize = staticmethod(_sanitize_tool_text)
    apply_privacy_guardrails = staticmethod(apply_privacy_guardrails)
    privacy_mode_policy = staticmethod(privacy_mode_policy)


if FastMCP is not None:
    from .tools import register_all

    register_all(cast(Any, mcp), ToolDeps())


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
    set_runtime_archive_paths(
        vector_index_path=getattr(args, "vector_index_path", None),
        sqlite_path=getattr(args, "sqlite_path", None),
    )
    if _MCP_IMPORT_ERROR is not None:
        raise SystemExit(_missing_mcp_runtime_message()) from _MCP_IMPORT_ERROR
    _acquire_instance_lock()
    _log_startup_info()
    mcp.run()


if __name__ == "__main__":
    main()
