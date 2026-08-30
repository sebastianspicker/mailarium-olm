"""Attachment discovery MCP tools."""

from __future__ import annotations

from typing import Any

from ..mcp_models import EmailAttachmentsInput
from .utils import ToolDepsProto, json_error, json_response, run_with_db


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register attachment discovery tools."""

    @mcp.tool(
        name="email_attachments",
        annotations=deps.tool_annotations("Attachment Discovery"),
    )
    async def email_attachments(params: EmailAttachmentsInput) -> str:
        """Attachment discovery: list, search, or get statistics.

        mode='list': browse all attachments with filters and pagination.
        mode='search': find emails with matching attachments.
        mode='stats': aggregate statistics (counts, sizes, type distribution).
        """

        def _work(db: Any) -> str:
            if params.mode == "list":
                return json_response(
                    db.list_attachments(
                        filename=params.filename,
                        extension=params.extension,
                        mime_type=params.mime_type,
                        sender=params.sender,
                        limit=params.limit,
                        offset=params.offset,
                    )
                )
            if params.mode == "search":
                results = db.search_emails_by_attachment(
                    filename=params.filename,
                    extension=params.extension,
                    mime_type=params.mime_type,
                    limit=params.limit,
                )
                return json_response({"emails": results, "count": len(results)})
            if params.mode == "stats":
                return json_response(db.attachment_stats())
            return json_error(f"Invalid mode: {params.mode}. Use 'list', 'search', or 'stats'.")

        return await run_with_db(deps, _work)
