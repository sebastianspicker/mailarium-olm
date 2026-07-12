"""Email browsing and export MCP tools."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

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

_DEEP_CONTEXT_EMAIL_FIELDS = {
    "uid",
    "message_id",
    "subject",
    "sender_name",
    "sender_email",
    "date",
    "folder",
    "email_type",
    "has_attachments",
    "attachment_count",
    "priority",
    "is_read",
    "conversation_id",
    "in_reply_to",
    "base_subject",
    "body_length",
    "body_text",
    "body_render_mode",
    "body_render_source",
    "thread_topic",
    "inference_classification",
    "is_calendar_message",
    "detected_language",
    "sentiment_label",
    "sentiment_score",
    "content_sha256",
    "body_kind",
    "body_empty_reason",
    "recovery_strategy",
    "recovery_confidence",
    "normalized_body_source",
    "body_normalization_version",
    "to",
    "cc",
    "bcc",
    "categories",
    "references",
    "attachments",
}


def _thread_graph_for_email(email: dict[str, Any]) -> dict[str, Any]:
    """Return canonical vs inferred thread graph fields for one email."""
    canonical = _canonical_thread_graph(email)
    inferred = _inferred_thread_graph(email)
    return {"canonical": canonical, "inferred": inferred}


def _canonical_thread_graph(email: dict[str, Any]) -> dict[str, Any]:
    references = _email_references(email)
    canonical: dict[str, Any] = {
        "conversation_id": str(email.get("conversation_id") or ""),
        "in_reply_to": str(email.get("in_reply_to") or ""),
        "references": [str(reference) for reference in references if reference],
    }
    canonical["has_thread_links"] = bool(canonical["conversation_id"] or canonical["in_reply_to"] or canonical["references"])
    return canonical


def _email_references(email: dict[str, Any]) -> list[Any]:
    references = email.get("references") or []
    if not references and email.get("references_json"):
        try:
            references = json.loads(str(email.get("references_json") or "[]"))
        except json.JSONDecodeError:
            references = []
    if not isinstance(references, list):
        return []
    return references


def _inferred_thread_graph(email: dict[str, Any]) -> dict[str, Any]:
    inferred: dict[str, Any] = {
        "parent_uid": str(email.get("inferred_parent_uid") or ""),
        "thread_id": str(email.get("inferred_thread_id") or ""),
        "reason": str(email.get("inferred_match_reason") or ""),
        "confidence": float(email.get("inferred_match_confidence") or 0.0),
    }
    inferred["has_parent_link"] = bool(inferred["parent_uid"] or inferred["thread_id"])
    return inferred


def _compact_email_for_deep_context(email: dict[str, Any]) -> dict[str, Any]:
    """Return a stable email payload without giant raw-body fields."""
    return {key: email.get(key) for key in _DEEP_CONTEXT_EMAIL_FIELDS if key in email}


def _estimated_json_chars(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")))


def _trim_text(value: Any, max_chars: int) -> str:
    collapsed = str(value or "")
    if len(collapsed) <= max_chars:
        return collapsed
    if max_chars <= 3:
        return collapsed[:max_chars]
    return collapsed[: max_chars - 3].rstrip() + "..."


def _compact_deep_context_payload(payload: dict[str, Any], *, budget: int) -> dict[str, Any]:
    """Drop low-priority deep-context sidecars before the generic JSON budget guard runs."""
    if budget <= 0 or _estimated_json_chars(payload) <= budget:
        return payload
    compacted = json.loads(json.dumps(payload, default=str))
    email = compacted.get("email")
    _compact_email_body_metadata(email)
    _compact_conversation_debug(compacted.get("conversation_debug"))
    if _estimated_json_chars(compacted) <= budget:
        return compacted
    _compact_thread_payload(compacted.get("thread"))
    if _estimated_json_chars(compacted) <= budget:
        return compacted
    _compact_evidence_payload(compacted.get("evidence"))
    if _estimated_json_chars(compacted) <= budget:
        return compacted
    if isinstance(email, dict):
        trimmed_email = {
            key: email.get(key)
            for key in (
                "uid",
                "subject",
                "sender_email",
                "sender_name",
                "date",
                "body_text",
                "body_total_chars",
                "body_render_mode",
                "body_render_source",
                "weak_message",
            )
            if key in email
        }
        compacted["email"] = trimmed_email
    for optional_key in ("conversation_debug", "sender", "evidence", "thread"):
        if _estimated_json_chars(compacted) <= budget:
            break
        compacted.pop(optional_key, None)
    return compacted


def _compact_email_body_metadata(email: Any) -> None:
    if isinstance(email, dict) and (body_text := str(email.get("body_text") or "")):
        email["body_total_chars"] = len(body_text)


def _compact_conversation_debug(debug: Any) -> None:
    if not isinstance(debug, dict) or not isinstance(debug.get("segments"), list) or not debug["segments"]:
        return
    segments = debug["segments"]
    debug["segment_sample"] = [
        {"ordinal": item.get("ordinal"), "segment_type": item.get("segment_type"), "source_surface": item.get("source_surface")}
        for item in segments[:3]
        if isinstance(item, dict)
    ]
    debug["segment_truncated_count"] = max(0, len(segments) - len(debug["segment_sample"]))
    debug.pop("segments", None)


def _compact_thread_payload(thread: Any) -> None:
    if not isinstance(thread, dict):
        return
    timeline = thread.get("timeline")
    if isinstance(timeline, list) and len(timeline) > 2:
        thread["timeline"] = timeline[:1] + timeline[-1:]
        thread["timeline_truncated_count"] = max(0, len(timeline) - len(thread["timeline"]))
    if summary := str(thread.get("summary") or ""):
        thread["summary"] = _trim_text(summary, 240)


def _compact_evidence_payload(evidence: Any) -> None:
    if not isinstance(evidence, dict) or not isinstance(evidence.get("items"), list):
        return
    items = evidence["items"]
    if len(items) > 8:
        evidence["items"] = items[:8]
        evidence["truncated_count"] = len(items) - len(evidence["items"])


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

        if params.format == "pdf" and not params.output_path:
            return json_error("pdf export requires output_path; omit output_path only for in-memory HTML export.")

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
            prepared = _prepare_deep_context_email(db, params, deps)
            if isinstance(prepared, str):
                return prepared
            email, result = prepared
            if params.include_thread:
                _add_deep_thread(result, email, db, deps)
            if params.include_evidence:
                _add_deep_evidence(result, db, params.uid)
            if params.include_sender_stats:
                _add_deep_sender(result, email, db)
            if params.include_conversation_debug:
                _add_deep_conversation_debug(result, email, db, params.uid)

            return json_response(
                _compact_deep_context_payload(result, budget=get_settings().mcp_max_json_response_chars),
                default=str,
            )

        return await run_with_db(deps, _work)


def _prepare_deep_context_email(db, params, deps) -> tuple[dict, dict] | str:
    email = db.get_email_full(params.uid)
    if not email:
        return json_error(f"Email not found: {params.uid}. Verify the UID is correct.")
    body_text, body_source = resolve_body_for_render(email, params.render_mode)
    email["body_text"] = deps.sanitize(body_text)
    email["body_render_mode"] = params.render_mode
    email["body_render_source"] = body_source
    weak_message = weak_message_semantics(email)
    if weak_message:
        email["weak_message"] = weak_message
    max_body = params.max_body_chars if params.max_body_chars is not None else get_settings().mcp_max_full_body_chars
    if max_body > 0:
        email["body_text"] = truncate_body(email["body_text"], max_body)
    result = {"email": _compact_email_for_deep_context(email)}
    if weak_message:
        result["email"]["weak_message"] = weak_message
    return email, result


def _add_deep_thread(result: dict, email: dict, db, deps) -> None:
    conversation_id = email.get("conversation_id", "")
    if not conversation_id:
        result["thread"] = {"note": "No conversation_id — standalone email."}
        return
    emails = db.get_thread_emails(conversation_id)
    thread = {
        "conversation_id": conversation_id,
        "email_count": len(emails),
        "participants": _unique_participants(emails),
        "date_range": _thread_date_range(emails),
    }
    if len(emails) > 1:
        from ..thread_summarizer import summarize_thread

        thread["summary"] = summarize_thread([_thread_summary_email(item, deps) for item in emails], max_sentences=5)
        thread["timeline"] = [_thread_timeline_email(item) for item in emails]
    result["thread"] = thread


def _thread_summary_email(email: dict, deps) -> dict[str, str]:
    return {
        "clean_body": deps.sanitize(email.get("body_text") or ""),
        "sender_email": email.get("sender_email", ""),
        "sender_name": email.get("sender_name", ""),
        "date": email.get("date", ""),
        "subject": email.get("subject", ""),
    }


def _thread_timeline_email(email: dict) -> dict[str, str]:
    return {"sender": email.get("sender_email", ""), "date": str(email.get("date", ""))[:10], "subject": email.get("subject", "")}


def _add_deep_evidence(result: dict, db, uid: str) -> None:
    items = db.list_evidence(email_uid=uid, limit=50).get("items", [])
    result["evidence"] = {"count": len(items), "items": [_deep_evidence_item(item) for item in items]}


def _deep_evidence_item(item: dict) -> dict[str, Any]:
    quote = item.get("key_quote") or ""
    return {
        "id": item.get("id"),
        "category": item.get("category"),
        "relevance": item.get("relevance"),
        "summary": item.get("summary", ""),
        "quote_preview": quote[:80] + "..." if len(quote) > 80 else quote,
    }


def _add_deep_sender(result: dict, email: dict, db) -> None:
    sender_email = email.get("sender_email", "")
    if not sender_email:
        return
    sender = {"email": sender_email}
    try:
        sender["top_contacts"] = db.top_contacts(sender_email, limit=5)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Failed to fetch top_contacts for %s", sender_email, exc_info=True)
    try:
        row = db.conn.execute("SELECT COUNT(*) AS c FROM emails WHERE sender_email = ?", (sender_email,)).fetchone()
        sender["total_emails_sent"] = row["c"]
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Failed to count emails for sender %s", sender_email, exc_info=True)
    result["sender"] = sender


def _add_deep_conversation_debug(result: dict, email: dict, db, uid: str) -> None:
    segments = email.get("segments")
    if segments is None:
        segments = db.conn.execute(
            """SELECT ordinal, segment_type, depth, text, source_surface, provenance_json
               FROM message_segments WHERE email_uid = ? ORDER BY ordinal ASC""",
            (uid,),
        ).fetchall()
    graph = _thread_graph_for_email(email)
    result["conversation_debug"] = {
        "segment_count": len(segments),
        "segments": [dict(segment) if not isinstance(segment, dict) else segment for segment in segments],
        "canonical_thread": graph["canonical"],
        "inferred_thread": graph["inferred"],
    }


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
