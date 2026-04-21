"""Email browsing and export MCP tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..config import get_settings
from ..formatting import resolve_body_for_render, truncate_body, weak_message_semantics
from ..mcp_models import (
    BrowseInput,
    EmailDeepContextInput,
    EmailExportInput,
)
from .utils import ToolDepsProto, json_error, json_response, run_with_db

logger = logging.getLogger(__name__)


def _thread_graph_for_email(email: dict[str, Any]) -> dict[str, Any]:
    """Return canonical vs inferred thread graph fields for one email."""
    references = email.get("references") or []
    if not references and email.get("references_json"):
        try:
            references = json.loads(str(email.get("references_json") or "[]"))
        except json.JSONDecodeError:
            references = []
    if not isinstance(references, list):
        references = []
    canonical: dict[str, Any] = {
        "conversation_id": str(email.get("conversation_id") or ""),
        "in_reply_to": str(email.get("in_reply_to") or ""),
        "references": [str(reference) for reference in references if reference],
    }
    canonical["has_thread_links"] = bool(canonical["conversation_id"] or canonical["in_reply_to"] or canonical["references"])
    inferred: dict[str, Any] = {
        "parent_uid": str(email.get("inferred_parent_uid") or ""),
        "thread_id": str(email.get("inferred_thread_id") or ""),
        "reason": str(email.get("inferred_match_reason") or ""),
        "confidence": float(email.get("inferred_match_confidence") or 0.0),
    }
    inferred["has_parent_link"] = bool(inferred["parent_uid"] or inferred["thread_id"])
    return {
        "canonical": canonical,
        "inferred": inferred,
    }


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register browse and export tools."""

    @mcp.tool(
        name="email_export",
        annotations=deps.idempotent_write_annotations("Export Email as HTML/PDF"),
    )
    async def email_export(params: EmailExportInput) -> str:
        """Export a single email or conversation thread as formatted HTML/PDF.

        Provide exactly one of uid (single email) or conversation_id (thread).
        """

        def _work(db):
            from ..email_exporter import EmailExporter

            exporter = EmailExporter(db)
            if params.uid:
                if params.output_path:
                    result = exporter.export_single_file(
                        params.uid,
                        params.output_path,
                        fmt=params.format,
                        render_mode=params.render_mode,
                    )
                else:
                    result = exporter.export_single_html(params.uid, render_mode=params.render_mode)
            else:
                if params.conversation_id is None:
                    return json_error("Provide either uid or conversation_id.")
                if params.output_path:
                    result = exporter.export_thread_file(
                        params.conversation_id,
                        params.output_path,
                        fmt=params.format,
                        render_mode=params.render_mode,
                    )
                else:
                    result = exporter.export_thread_html(params.conversation_id, render_mode=params.render_mode)
            return json_response(result)

        return await run_with_db(deps, _work)

    @mcp.tool(
        name="email_browse",
        annotations=deps.tool_annotations("Browse Emails / Categories / Calendar"),
    )
    async def email_browse(params: BrowseInput) -> str:
        """Browse emails, list categories, or browse calendar emails.

        Default: paginated email list. Set list_categories=True to get
        category counts. Set is_calendar=True to browse calendar/meeting emails.
        """

        def _work(db):
            # Category listing mode
            if params.list_categories:
                cats = db.category_counts()
                if not cats:
                    return json_response({"categories": [], "total": 0, "message": "No categories found in the archive."})
                return json_response({"categories": cats[: params.limit], "total": len(cats)})

            # Calendar browsing mode
            if params.is_calendar:
                emails = db.calendar_emails(
                    date_from=params.date_from,
                    date_to=params.date_to,
                    limit=params.limit,
                )
                return json_response({"emails": emails, "count": len(emails)})

            # Standard email browsing
            page = db.list_emails_paginated(
                offset=params.offset,
                limit=params.limit,
                folder=params.folder,
                sender=params.sender,
                category=params.category,
                sort_order=params.sort_order.upper(),
                date_from=params.date_from,
                date_to=params.date_to,
            )

            if params.include_body:
                max_chars = get_settings().mcp_max_body_chars
                uids = [e["uid"] for e in page["emails"]]
                full_map = db.get_emails_full_batch(uids)
                for email in page["emails"]:
                    full = full_map.get(email["uid"])
                    if full:
                        body_text, body_source = resolve_body_for_render(full, params.render_mode)
                        body = deps.sanitize(body_text)
                        email["body_text"] = truncate_body(body, max_chars)
                        email["body_render_mode"] = params.render_mode
                        email["body_render_source"] = body_source
                        weak_message = weak_message_semantics(full)
                        if weak_message:
                            email["weak_message"] = weak_message

            return json_response(page)

        return await run_with_db(deps, _work)

    # email_get_full removed — subsumed by email_deep_context(include_thread=False, ...)

    @mcp.tool(
        name="email_deep_context",
        annotations=deps.tool_annotations("Deep Email Analysis"),
    )
    async def email_deep_context(params: EmailDeepContextInput) -> str:
        """One-call deep analysis: full body + thread context + evidence + sender profile.

        Replaces 3-5 separate tool calls when investigating a specific email.
        Use after email_triage identifies emails of interest. Required before
        evidence_add to extract exact quotes from the full body text.
        """

        def _work(db):
            email = db.get_email_full(params.uid)
            if not email:
                return json_error(f"Email not found: {params.uid}. Verify the UID is correct.")
            # Sanitize untrusted email body content
            body_text, body_source = resolve_body_for_render(email, params.render_mode)
            email["body_text"] = deps.sanitize(body_text)
            email["body_render_mode"] = params.render_mode
            email["body_render_source"] = body_source
            weak_message = weak_message_semantics(email)
            if weak_message:
                email["weak_message"] = weak_message
            max_body = params.max_body_chars
            # When the caller didn't explicitly set max_body_chars (None sentinel),
            # honour the model-profile setting.
            if max_body is None:
                max_body = get_settings().mcp_max_full_body_chars
            if max_body > 0:
                email["body_text"] = truncate_body(
                    email["body_text"],
                    max_body,
                )
            result: dict = {"email": email}

            # Thread context
            if params.include_thread:
                conv_id = email.get("conversation_id", "")
                if conv_id:
                    thread_emails = db.get_thread_emails(conv_id)
                    thread: dict = {
                        "conversation_id": conv_id,
                        "email_count": len(thread_emails),
                        "participants": _unique_participants(thread_emails),
                        "date_range": _thread_date_range(thread_emails),
                    }
                    if len(thread_emails) > 1:
                        from ..thread_summarizer import summarize_thread

                        thread["summary"] = summarize_thread(
                            [
                                {
                                    "clean_body": deps.sanitize(e.get("body_text") or ""),
                                    "sender_email": e.get("sender_email", ""),
                                    "sender_name": e.get("sender_name", ""),
                                    "date": e.get("date", ""),
                                    "subject": e.get("subject", ""),
                                }
                                for e in thread_emails
                            ],
                            max_sentences=5,
                        )
                        thread["timeline"] = [
                            {
                                "sender": e.get("sender_email", ""),
                                "date": str(e.get("date", ""))[:10],
                                "subject": e.get("subject", ""),
                            }
                            for e in thread_emails
                        ]
                    result["thread"] = thread
                else:
                    result["thread"] = {"note": "No conversation_id — standalone email."}

            # Existing evidence from this email
            if params.include_evidence:
                ev = db.list_evidence(email_uid=params.uid, limit=50)
                items = ev.get("items", [])
                result["evidence"] = {
                    "count": len(items),
                    "items": [
                        {
                            "id": i.get("id"),
                            "category": i.get("category"),
                            "relevance": i.get("relevance"),
                            "summary": i.get("summary", ""),
                            "quote_preview": (
                                ((i.get("key_quote") or "")[:80] + "...")
                                if len(i.get("key_quote") or "") > 80
                                else (i.get("key_quote") or "")
                            ),
                        }
                        for i in items
                    ],
                }

            # Sender profile (pure SQLite, no networkx dependency)
            if params.include_sender_stats:
                sender_email = email.get("sender_email", "")
                if sender_email:
                    sender: dict = {"email": sender_email}
                    try:
                        sender["top_contacts"] = db.top_contacts(sender_email, limit=5)
                    except Exception:
                        logger.debug("Failed to fetch top_contacts for %s", sender_email, exc_info=True)
                    try:
                        row = db.conn.execute(
                            "SELECT COUNT(*) AS c FROM emails WHERE sender_email = ?",
                            (sender_email,),
                        ).fetchone()
                        sender["total_emails_sent"] = row["c"]
                    except Exception:
                        logger.debug("Failed to count emails for sender %s", sender_email, exc_info=True)
                    result["sender"] = sender

            if params.include_conversation_debug:
                segments = email.get("segments")
                if segments is None:
                    segments = db.conn.execute(
                        """SELECT ordinal, segment_type, depth, text, source_surface, provenance_json
                           FROM message_segments
                           WHERE email_uid = ?
                           ORDER BY ordinal ASC""",
                        (params.uid,),
                    ).fetchall()
                thread_graph = _thread_graph_for_email(email)
                inferred_thread = {
                    "parent_uid": thread_graph["inferred"]["parent_uid"],
                    "thread_id": thread_graph["inferred"]["thread_id"],
                    "reason": thread_graph["inferred"]["reason"],
                    "confidence": thread_graph["inferred"]["confidence"],
                }
                result["conversation_debug"] = {
                    "segment_count": len(segments),
                    "segments": [dict(segment) if not isinstance(segment, dict) else segment for segment in segments],
                    "canonical_thread": thread_graph["canonical"],
                    "inferred_thread": inferred_thread,
                }

            return json_response(result, default=str)

        return await run_with_db(deps, _work)


def _unique_participants(thread_emails: list[dict]) -> list[str]:
    """Extract unique sender emails from a thread, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for e in thread_emails:
        s = (e.get("sender_email") or "").strip().lower()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _thread_date_range(thread_emails: list[dict]) -> dict:
    """Extract first/last date strings from thread emails."""
    dates = [str(e.get("date", ""))[:10] for e in thread_emails if e.get("date")]
    return {"first": min(dates), "last": max(dates)} if dates else {}
