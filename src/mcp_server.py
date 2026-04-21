"""
MCP Server for Email RAG.

Exposes email search as tools that any MCP client can call directly.
Run with: python -m src.mcp_server

Example MCP client settings:
{
    "mcpServers": {
        "email_search": {
            "command": "/absolute/path/to/.venv/bin/python",
            "args": ["-m", "src.mcp_server"],
            "cwd": "/absolute/path/to/outlook-email-rag"
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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv

if TYPE_CHECKING:
    from .email_db import EmailDatabase
    from .retriever import EmailRetriever
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import get_settings
from .sanitization import sanitize_untrusted_text

logger = logging.getLogger(__name__)

load_dotenv()
# Clear any previously cached settings so they reflect the .env values
# loaded above (the lru_cache in get_settings() would otherwise return
# a stale Settings instance built before load_dotenv ran).
get_settings.cache_clear()

# ── Instance lock ─────────────────────────────────────────────

_lock_fd = None


def _acquire_instance_lock() -> None:
    """Acquire an exclusive file lock to prevent concurrent instances.

    Uses ``fcntl.flock`` (Unix) with ``LOCK_EX | LOCK_NB``.  On Windows
    (no ``fcntl``), logs a warning and continues without locking.
    """
    global _lock_fd
    try:
        import fcntl
    except ImportError:
        logger.warning("fcntl not available (Windows?) — skipping instance lock")
        return

    settings = get_settings()
    data_dir = Path(settings.sqlite_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "mcp_server.lock"

    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Lock held by another process — read existing PID for diagnostics
        try:
            existing_pid = lock_path.read_text().strip()
        except Exception:
            existing_pid = "unknown"

        # Check if the locking process is still alive.  A stale lock from
        # a crashed server should not block startup.
        stale = False
        if existing_pid and existing_pid != "unknown":
            try:
                os.kill(int(existing_pid), 0)  # signal 0 = existence check
            except (OSError, ValueError):
                stale = True

        if stale:
            logger.warning(
                "Stale lock from dead process (PID %s) — reclaiming lock.",
                existing_pid,
            )
            fd.close()
            fd = open(lock_path, "w")
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

    fd.write(str(os.getpid()))
    fd.flush()
    _lock_fd = fd
    atexit.register(_release_lock)


def _release_lock() -> None:
    global _lock_fd
    if _lock_fd is not None:
        try:
            _lock_fd.close()
        except Exception:
            logger.debug("Failed to close MCP server lock during shutdown", exc_info=True)
        _lock_fd = None


def _log_startup_info() -> None:
    """Log diagnostic info to stderr on startup."""
    settings = get_settings()
    sqlite_exists = os.path.exists(settings.sqlite_path)
    chromadb_exists = os.path.isdir(settings.chromadb_path)
    logger.info(
        "MCP server starting — PID=%d python=%s cwd=%s",
        os.getpid(),
        sys.executable,
        os.getcwd(),
    )
    logger.info(
        "  sqlite=%s (exists=%s) chromadb=%s (exists=%s)",
        settings.sqlite_path,
        sqlite_exists,
        settings.chromadb_path,
        chromadb_exists,
    )
    logger.info(
        "  profile=%s body=%d tokens=%d full=%d json=%d triage_cap=%d search_cap=%d",
        settings.mcp_model_profile,
        settings.mcp_max_body_chars,
        settings.mcp_max_response_tokens,
        settings.mcp_max_full_body_chars,
        settings.mcp_max_json_response_chars,
        settings.mcp_max_triage_results,
        settings.mcp_max_search_results,
    )


mcp = FastMCP("email_mcp")

_retriever = None
_retriever_lock = threading.Lock()


def _tool_annotations(title: str) -> ToolAnnotations:
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
    global _retriever
    if _retriever is not None:
        return _retriever
    with _retriever_lock:
        if _retriever is None:
            from .retriever import EmailRetriever

            _retriever = EmailRetriever()
    if _retriever is None:
        raise RuntimeError("Retriever initialization failed")
    return _retriever


# ── EmailDatabase helper ──────────────────────────────────────

_email_db = None
_email_db_lock = threading.Lock()

_DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available. Run ingestion first."})


def get_email_db() -> EmailDatabase | None:
    """Lazy singleton for the SQLite email database.

    Thread-safe via double-checked locking (same pattern as
    ``get_retriever``).  The returned ``EmailDatabase`` instance uses
    ``check_same_thread=False`` + WAL mode, which is safe for concurrent
    reads from multiple ``asyncio.to_thread`` workers.  Write operations
    (evidence_add, etc.) are serialized by SQLite's internal WAL locking.
    """
    global _email_db
    if _email_db is not None:
        return _email_db
    with _email_db_lock:
        if _email_db is None:
            from .email_db import EmailDatabase

            settings = get_settings()
            if Path(settings.sqlite_path).exists():
                _email_db = EmailDatabase(settings.sqlite_path)
    return _email_db


async def _offload(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous function in a thread to avoid blocking the event loop.

    ``asyncio.to_thread`` dispatches *fn* to the default thread-pool
    executor.  Each MCP tool call may run concurrently in a separate
    thread, so *fn* and the singletons it touches must be thread-safe.
    """
    if args or kwargs:
        import functools

        return await asyncio.to_thread(functools.partial(fn, *args, **kwargs))
    return await asyncio.to_thread(fn)


def _write_tool_annotations(title: str) -> ToolAnnotations:
    """Tool annotations for write operations."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )


def _idempotent_write_annotations(title: str) -> ToolAnnotations:
    """Tool annotations for idempotent write operations (report/export/ingest)."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


# ── Tool Module Registration ──────────────────────────────────


class ToolDeps:
    """Dependencies injected into tool modules to avoid circular imports."""

    @staticmethod
    def get_retriever() -> EmailRetriever:
        return get_retriever()

    @staticmethod
    def get_email_db() -> EmailDatabase | None:
        return get_email_db()

    offload = staticmethod(_offload)
    tool_annotations = staticmethod(_tool_annotations)
    write_tool_annotations = staticmethod(_write_tool_annotations)
    idempotent_write_annotations = staticmethod(_idempotent_write_annotations)
    DB_UNAVAILABLE = _DB_UNAVAILABLE
    sanitize = staticmethod(sanitize_untrusted_text)


from .tools import register_all  # noqa: E402

register_all(mcp, ToolDeps())


# ── Entry Point ────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the minimal MCP server CLI parser."""
    parser = argparse.ArgumentParser(
        prog="python -m src.mcp_server",
        description="Run the Email RAG MCP server over stdio.",
    )
    parser.add_argument("--version", action="version", version="0.1.0")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Startup routine: acquire lock, log diagnostics, then run the server."""
    _build_arg_parser().parse_args(argv)
    _acquire_instance_lock()
    _log_startup_info()
    mcp.run()


if __name__ == "__main__":
    main()
