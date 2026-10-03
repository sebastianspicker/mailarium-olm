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
import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from dotenv import load_dotenv

from mailarium import __version__

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.mailbox.service import MailboxService
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

from mailarium.interfaces.mcp.instance_lock import acquire_instance_lock, release_instance_lock
from mailarium.interfaces.mcp.runtime_state import McpRuntimeState
from mailarium.platform.sanitization import (
    apply_privacy_guardrails,
    privacy_mode_policy,
    sanitize_untrusted_text,
)
from mailarium.platform.settings import clear_settings_cache, get_settings

logger = logging.getLogger(__name__)


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
        return cast("SearchEngine", self._state.get_retriever())

    def get_archive_database(self) -> ArchiveDatabase | None:
        """Expose the optional shared metadata database to registered tool modules."""
        return cast("ArchiveDatabase | None", self._state.get_archive_database())

    def get_mailbox_service(self) -> MailboxService | None:
        """Expose the shared proposal-gated mailbox service."""
        return cast("MailboxService | None", self._state.get_mailbox_service())

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
    """Startup routine: load ``.env``, acquire lock, log diagnostics, then run the server."""
    load_dotenv()
    # Clear any previously cached settings so they reflect the .env values
    # loaded above instead of a stale Settings instance built before load_dotenv ran.
    clear_settings_cache()
    args = _build_arg_parser().parse_args(argv)
    state = McpRuntimeState(
        vector_index_path=getattr(args, "vector_index_path", None),
        sqlite_path=getattr(args, "sqlite_path", None),
    )
    if _MCP_IMPORT_ERROR is not None:
        raise SystemExit(_missing_mcp_runtime_message()) from _MCP_IMPORT_ERROR
    try:
        acquire_instance_lock(state)
        _log_startup_info(state)
        create_mcp_server(state).run()
    finally:
        state.close()
        release_instance_lock()
