"""Candidate and conversation-group helpers for answer-context evidence output."""

from __future__ import annotations

from typing import Any

from ..attachment_record_semantics import enrich_attachment_record
from ..mcp_models import EmailAnswerContextInput
from .search_answer_context_evidence_helpers import (
    _ATTACHMENT_HEADER_RE,
    _attachment_extraction_state,
    _match_reason,
    _snippet,
)


def _attachment_evidence_profile(
    metadata: dict[str, Any],
    *,
    chunk_id: str = "",
    snippet: str = "",
) -> dict[str, Any]:
    """Return normalized attachment evidence semantics for answer-facing output."""
    extraction_state = _attachment_extraction_state(metadata, chunk_id=chunk_id) or ""
    normalized = extraction_state.strip().lower()
    normalized_snippet = " ".join((snippet or "").split())
    weak_reference_only = bool(_ATTACHMENT_HEADER_RE.match((snippet or "").strip())) and "\n" not in (snippet or "")

    if normalized in {"ocr_text_extracted", "ocr_extracted_text", "ocr_success"}:
        extraction_state = "ocr_text_extracted"
        text_available = True
        ocr_used = True
        failure_reason = None
        evidence_strength = "strong_text"
    elif normalized in {"text_extracted", "text"}:
        extraction_state = "binary_only" if weak_reference_only else "text_extracted"
        text_available = not weak_reference_only
        ocr_used = False
        failure_reason = None if text_available else "no_text_extracted"
        evidence_strength = "strong_text" if text_available else "weak_reference"
    elif normalized in {"ocr_failed", "ocr_failure"}:
        extraction_state = "ocr_failed"
        text_available = False
        ocr_used = True
        failure_reason = "ocr_failed"
        evidence_strength = "weak_reference"
    elif normalized in {"extraction_failed", "text_extraction_failed"}:
        extraction_state = "extraction_failed"
        text_available = False
        ocr_used = False
        failure_reason = "extraction_failed"
        evidence_strength = "weak_reference"
    elif normalized in {"binary_only", "image_embedding_only", "image_only_no_text"}:
        extraction_state = "binary_only"
        text_available = False
        ocr_used = normalized.startswith("ocr_")
        failure_reason = "no_text_extracted"
        evidence_strength = "weak_reference"
    else:
        extraction_state = normalized or "unknown"
        text_available = bool(normalized_snippet)
        ocr_used = "ocr" in extraction_state
        failure_reason = None if text_available else "unknown"
        evidence_strength = "strong_text" if text_available else "weak_reference"

    return {
        "extraction_state": extraction_state,
        "text_available": text_available,
        "ocr_used": ocr_used,
        "failure_reason": failure_reason,
        "evidence_strength": evidence_strength,
    }


def _attachment_record_for_candidate(db: Any, uid: str, filename: str) -> dict[str, Any] | None:
    """Return the matching attachment record for one candidate, if the DB exposes it."""
    if not db or not uid or not filename or not hasattr(db, "attachments_for_email"):
        return None
    attachments = db.attachments_for_email(uid)
    for attachment in attachments:
        if str(attachment.get("name") or "") == filename:
            return attachment
    return None


def _attachment_candidate(
    db: Any,
    result: Any,
    *,
    rank: int,
    params: EmailAnswerContextInput,
) -> dict[str, Any]:
    """Build one attachment evidence candidate from a search result."""
    metadata = result.metadata
    uid = str(metadata.get("uid", ""))
    filename = str(metadata.get("attachment_filename") or metadata.get("filename") or "")
    if not filename:
        header_match = _ATTACHMENT_HEADER_RE.match(result.text.strip())
        if header_match:
            filename = header_match.group(1).strip()
    if not filename:
        filename = "attachment"
    snippet = _snippet(result.text)
    snippet_start = int(metadata.get("char_start") or 0)
    snippet_end = int(metadata.get("char_end") or 0)
    if snippet_end <= snippet_start:
        snippet_end = snippet_start + len(snippet)
    record = _attachment_record_for_candidate(db, uid, filename)
    if isinstance(record, dict):
        record = enrich_attachment_record(
            record,
            title=str(metadata.get("subject", "")),
            snippet=snippet,
        )
    evidence_profile = _attachment_evidence_profile(metadata, chunk_id=result.chunk_id, snippet=result.text)
    attachment_info = {
        "filename": filename,
        "attachment_id": str(metadata.get("attachment_id") or (record or {}).get("attachment_id") or ""),
        "mime_type": (record or {}).get("mime_type"),
        "size": (record or {}).get("size"),
        "content_sha256": str(metadata.get("content_sha256") or (record or {}).get("content_sha256") or ""),
        "content_id": (record or {}).get("content_id"),
        "is_inline": bool((record or {}).get("is_inline", False)) if record is not None else None,
        "locator_version": int(metadata.get("locator_version") or (record or {}).get("locator_version") or 1),
        "text_locator": dict((record or {}).get("text_locator") or {}),
        "source_type_hint": (record or {}).get("source_type_hint"),
        "format_profile": dict((record or {}).get("documentary_support", {}).get("format_profile", {})),
        "extraction_quality": dict((record or {}).get("documentary_support", {}).get("extraction_quality", {})),
        "review_recommendation": str((record or {}).get("documentary_support", {}).get("review_recommendation", "")),
        "text_preview": str((record or {}).get("documentary_support", {}).get("text_preview", "")),
        "spreadsheet_semantics": dict((record or {}).get("spreadsheet_semantics", {})),
        "calendar_semantics": dict((record or {}).get("calendar_semantics", {})),
        "weak_format_semantics": dict((record or {}).get("weak_format_semantics", {})),
        **evidence_profile,
    }
    provenance = {
        "evidence_handle": f"attachment:{uid}:{filename}:{result.chunk_id}:{snippet_start}:{snippet_end}",
        "uid": uid,
        "chunk_id": result.chunk_id,
        "snippet_start": snippet_start,
        "snippet_end": snippet_end,
        "source_scope": str(metadata.get("source_scope") or "attachment_text"),
        "char_start": snippet_start,
        "char_end": snippet_end,
        "surface_hash": str(metadata.get("surface_hash") or ""),
        "attachment_id": str(metadata.get("attachment_id") or (record or {}).get("attachment_id") or ""),
        "content_sha256": str(metadata.get("content_sha256") or (record or {}).get("content_sha256") or ""),
        "locator_version": int(metadata.get("locator_version") or (record or {}).get("locator_version") or 1),
        "attachment_filename": filename,
    }
    return {
        "rank": rank,
        "uid": uid,
        "subject": metadata.get("subject", ""),
        "sender_email": metadata.get("sender_email", ""),
        "sender_name": metadata.get("sender_name", ""),
        "date": metadata.get("date", ""),
        "conversation_id": metadata.get("conversation_id", ""),
        "score": result.score,
        "snippet": snippet,
        "match_reason": _match_reason(rank, params),
        "attachment": attachment_info,
        "provenance": provenance,
        "follow_up": {
            "tool": "email_deep_context",
            "uid": uid,
        },
    }


def _conversation_group_summaries(
    db: Any,
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build ranked conversation-group summaries for the current answer bundle."""
    grouped: dict[str, dict[str, Any]] = {}
    ordered_candidates = [*candidates, *attachment_candidates]
    for candidate in ordered_candidates:
        thread_group_id = str(candidate.get("thread_group_id") or "")
        if not thread_group_id:
            continue
        conversation_id = str(candidate.get("conversation_id") or "")
        inferred_thread_id = str(candidate.get("inferred_thread_id") or "")
        thread_group_source = str(candidate.get("thread_group_source") or "canonical")
        group = grouped.get(thread_group_id)
        score = float(candidate.get("score") or 0.0)
        uid = str(candidate.get("uid") or "")
        if group is None:
            group = {
                "conversation_id": conversation_id,
                "inferred_thread_id": inferred_thread_id,
                "thread_group_id": thread_group_id,
                "thread_group_source": thread_group_source,
                "top_uid": uid,
                "top_score": score,
                "matched_uids": [],
                "participants": [],
                "date_range": {},
                "message_count": 0,
            }
            grouped[thread_group_id] = group
        if uid and uid not in group["matched_uids"]:
            group["matched_uids"].append(uid)
        if score > float(group["top_score"]):
            group["top_score"] = score
            group["top_uid"] = uid

    for group in grouped.values():
        thread_emails: list[dict[str, Any]] = []
        if db:
            if group["thread_group_source"] == "canonical" and hasattr(db, "get_thread_emails"):
                thread_emails = db.get_thread_emails(str(group["conversation_id"] or "")) or []
            elif group["thread_group_source"] == "inferred" and hasattr(db, "get_inferred_thread_emails"):
                thread_emails = db.get_inferred_thread_emails(str(group["inferred_thread_id"] or "")) or []
            elif hasattr(db, "get_thread_emails") and group["conversation_id"]:
                thread_emails = db.get_thread_emails(str(group["conversation_id"] or "")) or []
        if thread_emails:
            participants = sorted({str(email.get("sender_email") or "") for email in thread_emails if email.get("sender_email")})
            dates = sorted(str(email.get("date") or "")[:10] for email in thread_emails if email.get("date"))
            group["participants"] = participants
            group["message_count"] = len(thread_emails)
            if dates:
                group["date_range"] = {"first": dates[0], "last": dates[-1]}
            else:
                group["date_range"] = {}
        else:
            group["message_count"] = len(group["matched_uids"])

    conversation_groups = sorted(grouped.values(), key=lambda item: float(item["top_score"]), reverse=True)
    by_id = {group["thread_group_id"]: group for group in conversation_groups}
    return conversation_groups, by_id


def _attach_conversation_context(
    items: list[dict[str, Any]],
    conversation_group_by_id: dict[str, dict[str, Any]],
) -> None:
    """Attach current conversation summaries to evidence items."""
    for item in items:
        thread_group_id = str(item.get("thread_group_id") or "")
        if thread_group_id and thread_group_id in conversation_group_by_id:
            item["conversation_context"] = conversation_group_by_id[thread_group_id]
        else:
            item.pop("conversation_context", None)
