"""Process-wide exclusive lock that keeps one MCP server per configured archive."""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from mailarium.interfaces.mcp.runtime_state import McpRuntimeState

logger = logging.getLogger(__name__)

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


def acquire_instance_lock(state: McpRuntimeState) -> None:
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
    atexit.register(release_instance_lock)


def release_instance_lock() -> None:
    """Manage lock for the runtime lifecycle."""
    global _lock_fd
    if _lock_fd is not None:
        try:
            _lock_fd.close()
        except OSError:
            logger.debug("Failed to close MCP server lock during shutdown", exc_info=True)
        _lock_fd = None
