"""Candidate and conversation-group helpers for answer-context evidence output."""
# pylint: disable=too-many-branches,too-many-locals

from __future__ import annotations

from typing import Any

from ..attachment_record_semantics import enrich_attachment_record
from ..mcp_models import EmailAnswerContextInput
from .search_answer_context_candidate_common import candidate_summary
from .search_answer_context_evidence_helpers import (
    _ATTACHMENT_HEADER_RE,
    _attachment_extraction_state,
    _match_reason,
    _snippet,
)


def _known_attachment_profile(normalized: str, weak_reference_only: bool) -> dict[str, Any] | None:
    """Map normalized attachment extraction states to answer-evidence profiles."""
    if normalized in {"ocr_text_extracted", "ocr_extracted_text", "ocr_success"}:
        return {
            "extraction_state": "ocr_text_extracted",
            "text_available": True,
            "ocr_used": True,
            "failure_reason": None,
            "evidence_strength": "strong_text",
        }
    if normalized in {"text_extracted", "text"}:
        available = not weak_reference_only
        return {
            "extraction_state": "text_extracted" if available else "binary_only",
            "text_available": available,
            "ocr_used": False,
            "failure_reason": None if available else "no_text_extracted",
            "evidence_strength": "strong_text" if available else "weak_reference",
        }
    if normalized in {"ocr_failed", "ocr_failure"}:
        return {
            "extraction_state": "ocr_failed",
            "text_available": False,
            "ocr_used": True,
            "failure_reason": "ocr_failed",
            "evidence_strength": "weak_reference",
        }
    if normalized in {"extraction_failed", "text_extraction_failed"}:
        return {
            "extraction_state": "extraction_failed",
            "text_available": False,
            "ocr_used": False,
            "failure_reason": "extraction_failed",
            "evidence_strength": "weak_reference",
        }
    if normalized in {"binary_only", "image_embedding_only", "image_only_no_text"}:
        return {
            "extraction_state": "binary_only",
            "text_available": False,
            "ocr_used": normalized.startswith("ocr_"),
            "failure_reason": "no_text_extracted",
            "evidence_strength": "weak_reference",
        }
    return None


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

    known = _known_attachment_profile(normalized, weak_reference_only)
    if known is not None:
        return known
    state = normalized or "unknown"
    available = bool(normalized_snippet)
    return {
        "extraction_state": state,
        "text_available": available,
        "ocr_used": "ocr" in state,
        "failure_reason": None if available else "unknown",
        "evidence_strength": "strong_text" if available else "weak_reference",
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


def _attachment_filename(metadata: dict[str, Any], text: str) -> str:
    """Prefer attachment metadata and fall back to a parsed text header or a stable generic label."""
    filename = str(metadata.get("attachment_filename") or metadata.get("filename") or "")
    if filename:
        return filename
    match = _ATTACHMENT_HEADER_RE.match(text.strip())
    return match.group(1).strip() if match else "attachment"


def _attachment_info(
    metadata: dict[str, Any], record: dict[str, Any] | None, filename: str, profile: dict[str, Any]
) -> dict[str, Any]:
    """Merge record and retrieval metadata into the public attachment identity and extraction profile."""
    rec = record or {}
    support = rec.get("documentary_support", {})
    return {
        "filename": filename,
        "attachment_id": str(metadata.get("attachment_id") or rec.get("attachment_id") or ""),
        "mime_type": rec.get("mime_type"),
        "size": rec.get("size"),
        "content_sha256": str(metadata.get("content_sha256") or rec.get("content_sha256") or ""),
        "content_id": rec.get("content_id"),
        "is_inline": bool(rec.get("is_inline", False)) if record is not None else None,
        "locator_version": int(metadata.get("locator_version") or rec.get("locator_version") or 1),
        "text_locator": dict(rec.get("text_locator") or {}),
        "source_type_hint": rec.get("source_type_hint"),
        "format_profile": dict(support.get("format_profile", {})),
        "extraction_quality": dict(support.get("extraction_quality", {})),
        "review_recommendation": str(support.get("review_recommendation", "")),
        "text_preview": str(support.get("text_preview", "")),
        "spreadsheet_semantics": dict(rec.get("spreadsheet_semantics", {})),
        "calendar_semantics": dict(rec.get("calendar_semantics", {})),
        "weak_format_semantics": dict(rec.get("weak_format_semantics", {})),
        **profile,
    }


def _attachment_provenance(
    metadata: dict[str, Any], record: dict[str, Any] | None, result: Any, uid: str, filename: str, start: int, end: int
) -> dict[str, Any]:
    """Construct a stable attachment evidence handle with byte-range, hash, and locator provenance."""
    rec = record or {}
    return {
        "evidence_handle": f"attachment:{uid}:{filename}:{result.chunk_id}:{start}:{end}",
        "uid": uid,
        "chunk_id": result.chunk_id,
        "snippet_start": start,
        "snippet_end": end,
        "source_scope": str(metadata.get("source_scope") or "attachment_text"),
        "char_start": start,
        "char_end": end,
        "surface_hash": str(metadata.get("surface_hash") or ""),
        "attachment_id": str(metadata.get("attachment_id") or rec.get("attachment_id") or ""),
        "content_sha256": str(metadata.get("content_sha256") or rec.get("content_sha256") or ""),
        "locator_version": int(metadata.get("locator_version") or rec.get("locator_version") or 1),
        "attachment_filename": filename,
    }


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
    filename = _attachment_filename(metadata, result.text)
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
    attachment_info = _attachment_info(metadata, record, filename, evidence_profile)
    provenance = _attachment_provenance(metadata, record, result, uid, filename, snippet_start, snippet_end)
    return {
        **candidate_summary(
            metadata,
            result,
            rank=rank,
            uid=uid,
            snippet=snippet,
            match_reason=_match_reason(rank, params),
        ),
        "attachment": attachment_info,
        "provenance": provenance,
        "follow_up": {
            "tool": "email_deep_context",
            "uid": uid,
        },
    }


def _add_candidate_to_group(grouped: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> None:
    """Accumulate a candidate under its thread group while retaining its strongest evidence."""
    group_id = str(candidate.get("thread_group_id") or "")
    if not group_id:
        return
    score = float(candidate.get("score") or 0.0)
    uid = str(candidate.get("uid") or "")
    group = grouped.setdefault(
        group_id,
        {
            "conversation_id": str(candidate.get("conversation_id") or ""),
            "inferred_thread_id": str(candidate.get("inferred_thread_id") or ""),
            "thread_group_id": group_id,
            "thread_group_source": str(candidate.get("thread_group_source") or "canonical"),
            "top_uid": uid,
            "top_score": score,
            "matched_uids": [],
            "participants": [],
            "date_range": {},
            "message_count": 0,
        },
    )
    if uid and uid not in group["matched_uids"]:
        group["matched_uids"].append(uid)
    if score > float(group["top_score"]):
        group["top_score"] = score
        group["top_uid"] = uid


def _email_rows(value: Any) -> list[dict[str, Any]]:
    """Normalize absent database results to an empty row list."""
    return value if value else []


def _thread_emails_for_group(db: Any, group: dict[str, Any]) -> list[dict[str, Any]]:
    """Load canonical or inferred thread messages according to the group provenance."""
    if not db:
        return []
    if group["thread_group_source"] == "canonical" and hasattr(db, "get_thread_emails"):
        return _email_rows(db.get_thread_emails(str(group["conversation_id"] or "")))
    if group["thread_group_source"] == "inferred" and hasattr(db, "get_inferred_thread_emails"):
        return _email_rows(db.get_inferred_thread_emails(str(group["inferred_thread_id"] or "")))
    if hasattr(db, "get_thread_emails") and group["conversation_id"]:
        return _email_rows(db.get_thread_emails(str(group["conversation_id"] or "")))
    return []


def _finalize_group(db: Any, group: dict[str, Any]) -> None:
    """Enrich a conversation group with participants, message count, and date range when thread rows exist."""
    emails = _thread_emails_for_group(db, group)
    if not emails:
        group["message_count"] = len(group["matched_uids"])
        return
    group["participants"] = sorted({str(email.get("sender_email") or "") for email in emails if email.get("sender_email")})
    dates = sorted(str(email.get("date") or "")[:10] for email in emails if email.get("date"))
    group["message_count"] = len(emails)
    group["date_range"] = {"first": dates[0], "last": dates[-1]} if dates else {}


def _conversation_group_summaries(
    db: Any,
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Group ranked evidence into compact conversation summaries before answer rendering."""
    grouped: dict[str, dict[str, Any]] = {}
    for candidate in [*candidates, *attachment_candidates]:
        _add_candidate_to_group(grouped, candidate)
    for group in grouped.values():
        _finalize_group(db, group)

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
