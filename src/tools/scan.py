"""Scan session management MCP tool for progressive multi-pass search."""

from __future__ import annotations

from typing import Any

from ..mcp_models import EmailScanInput
from .utils import ToolDepsProto, get_deps, json_error, json_response

# Thread-safety note: _deps is written once during single-threaded module
# registration at import time, then only read by tool handlers.
_deps: ToolDepsProto | None = None


def _d() -> ToolDepsProto:
    return get_deps(_deps)


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register scan session tool."""
    global _deps
    _deps = deps

    @mcp_instance.tool(
        name="email_scan",
        annotations=deps.write_tool_annotations("Scan Session Management"),
    )
    async def email_scan(params: EmailScanInput) -> str:
        """Manage progressive scan sessions for multi-pass investigation.

        action='status': view session stats (seen UIDs, candidate counts by label/phase).
        action='flag': flag UIDs as candidates with a label and phase marker.
        action='candidates': list flagged candidates, optionally filtered by label/phase.
        action='reset': clear session. Use scan_id='__all__' to clear all sessions.
        """
        from .. import scan_session

        if params.action == "status":
            status = scan_session.session_status(params.scan_id)
            if status is None:
                return json_error(f"No scan session found: {params.scan_id}")
            return json_response(status)

        if params.action == "flag":
            if not params.uids:
                return json_error("uids is required for action='flag'.")
            if not params.label:
                return json_error("label is required for action='flag'.")
            added, total = scan_session.flag_candidates(
                params.scan_id,
                uids=params.uids,
                label=params.label,
                phase=params.phase or 1,
                score=params.score or 0.0,
            )
            return json_response(
                {
                    "flagged": added,
                    "total_candidates": total,
                    "scan_id": params.scan_id,
                }
            )

        if params.action == "candidates":
            candidates = scan_session.get_candidates(
                params.scan_id,
                label=params.label,
                phase=params.phase,
            )
            return json_response(
                {
                    "candidates": candidates,
                    "count": len(candidates),
                    "scan_id": params.scan_id,
                }
            )

        if params.action == "reset":
            if params.scan_id == "__all__":
                count = scan_session.reset_all_sessions()
                return json_response({"reset": "all", "sessions_cleared": count})
            removed = scan_session.reset_session(params.scan_id)
            return json_response(
                {
                    "reset": params.scan_id,
                    "existed": removed,
                }
            )

        return json_error(f"Invalid action: {params.action}. Use 'status', 'flag', 'candidates', or 'reset'.")
