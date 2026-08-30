"""Candidate construction, provenance, and quote-attribution helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mailarium.model.attachment_record_semantics import enrich_attachment_record
from mailarium.model.data_shapes import as_dict
from mailarium.model.reply_context import extract_reply_context

from ..formatting import resolve_body_for_render
from .contracts import AnswerContextRequest
from .ranking import _result_competition_key, _support_type_for_result, _support_type_for_row

"""Shared public identity fields for answer-context evidence candidates."""


def candidate_summary(
    metadata: dict[str, Any],
    result: Any,
    *,
    rank: int,
    uid: str,
    snippet: str,
    match_reason: str,
) -> dict[str, Any]:
    """Project the common ranked email fields used by every evidence lane."""
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
        "match_reason": match_reason,
    }


"""Low-level evidence and retrieval helpers for answer-context rendering."""


_ATTACHMENT_HEADER_RE = re.compile(r'^\[Attachment:\s*(.+?)\s+from email\s+"', re.IGNORECASE)


def _snippet(text: str, *, max_chars: int = 280) -> str:
    """Return a compact single-line snippet for answer evidence."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _match_reason(rank: int, params: AnswerContextRequest) -> str:
    """Return a compact explanation for why a candidate was included."""
    parts = ["Top-ranked semantic match" if rank == 1 else "High-ranked semantic match"]
    if params.hybrid:
        parts.append("hybrid recall enabled")
    if params.rerank:
        parts.append("reranked for precision")
    return "; ".join(parts) + "."


def _find_snippet_bounds(body_text: str, snippet: str) -> tuple[int | None, int | None]:
    """Locate *snippet* in *body_text*, tolerating collapsed whitespace."""
    if not body_text or not snippet:
        return None, None
    exact_start = body_text.find(snippet)
    if exact_start >= 0:
        return exact_start, exact_start + len(snippet)

    body_chars: list[str] = []
    body_map: list[int] = []
    prev_space = False
    for idx, char in enumerate(body_text):
        if char.isspace():
            if prev_space:
                continue
            body_chars.append(" ")
            body_map.append(idx)
            prev_space = True
        else:
            body_chars.append(char)
            body_map.append(idx)
            prev_space = False
    normalized_body = "".join(body_chars)
    normalized_snippet = " ".join(snippet.split())
    collapsed_start = normalized_body.find(normalized_snippet)
    if collapsed_start < 0:
        return None, None
    start = body_map[collapsed_start]
    end = body_map[collapsed_start + len(normalized_snippet) - 1] + 1
    return start, end


def _verified_snippet_for_mode(body_text: str, retrieval_snippet: str) -> tuple[str, str, int | None, int | None]:
    """Return snippet, verification status, and bounds for the requested body text."""
    start, end = _find_snippet_bounds(body_text, retrieval_snippet)
    if start is not None and end is not None:
        return body_text[start:end], "exact", start, end
    fallback = _snippet(body_text) if body_text else retrieval_snippet
    if not fallback:
        fallback = retrieval_snippet
    start, end = _find_snippet_bounds(body_text, fallback)
    return fallback, "fallback", start, end


def _segment_ordinal_for_snippet(db: Any, uid: str, snippet: str) -> int | None:
    """Return the first segment ordinal containing *snippet*, if available."""
    conn = getattr(db, "conn", None)
    if conn is None:
        return None
    rows = conn.execute(
        """SELECT ordinal, text
           FROM message_segments
           WHERE email_uid = ?
           ORDER BY ordinal ASC""",
        (uid,),
    ).fetchall()
    normalized_snippet = " ".join(snippet.split())
    for row in rows:
        segment_text = row["text"] if not isinstance(row, dict) else row.get("text", "")
        if not segment_text:
            continue
        if snippet in segment_text or normalized_snippet in " ".join(segment_text.split()):
            ordinal = row["ordinal"] if not isinstance(row, dict) else row.get("ordinal")
            return int(ordinal) if ordinal is not None else None
    return None


def _is_attachment_result(metadata: dict[str, Any], *, chunk_id: str = "") -> bool:
    """Classify search results whose support originates from an attachment payload."""
    raw_flag = metadata.get("is_attachment")
    if isinstance(raw_flag, str):
        if raw_flag.lower() == "true":
            return True
    elif raw_flag:
        return True
    if metadata.get("attachment_filename"):
        return True
    if str(metadata.get("chunk_type") or "").lower() == "image":
        return True
    return "__att_" in chunk_id or "__img_" in chunk_id


def _attachment_extraction_state(metadata: dict[str, Any], *, chunk_id: str = "") -> str | None:
    """Return best-effort attachment extraction state from existing chunk metadata."""
    explicit = metadata.get("extraction_state")
    if explicit:
        return str(explicit).strip().lower()
    if str(metadata.get("chunk_type") or "").lower() == "image":
        return "image_embedding_only"
    if _is_attachment_result(metadata, chunk_id=chunk_id):
        return "text_extracted"
    return None


def _recipients_summary(full_email: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact visible-recipient summary for chronology and appendix views."""
    if not isinstance(full_email, dict):
        return {"status": "not_available"}

    visible_recipients: list[str] = []
    counts = {"to": 0, "cc": 0, "bcc": 0}
    for field in ("to", "cc", "bcc"):
        field_values = [str(value).strip().lower() for value in (full_email.get(field) or []) if value]
        counts[field] = len(field_values)
        for value in field_values:
            if value and value not in visible_recipients:
                visible_recipients.append(value)

    if not visible_recipients:
        return {
            "status": "empty",
            "to_count": counts["to"],
            "cc_count": counts["cc"],
            "bcc_count": counts["bcc"],
            "visible_recipient_count": 0,
            "visible_recipient_emails": [],
            "signature": "",
        }

    return {
        "status": "available",
        "to_count": counts["to"],
        "cc_count": counts["cc"],
        "bcc_count": counts["bcc"],
        "visible_recipient_count": len(visible_recipients),
        "visible_recipient_emails": visible_recipients,
        "signature": "|".join(visible_recipients),
    }


def _references_for_email(full_email: dict[str, Any] | None) -> list[str]:
    """Read message references from structured data or legacy JSON without propagating malformed values."""
    if not full_email:
        return []
    raw = full_email.get("references") or []
    if not raw and full_email.get("references_json"):
        import json

        try:
            raw = json.loads(str(full_email.get("references_json") or "[]"))
        except json.JSONDecodeError:
            raw = []
    return [str(item) for item in raw if item] if isinstance(raw, list) else []


def _thread_graph_for_email(
    full_email: dict[str, Any] | None,
    *,
    fallback_conversation_id: str = "",
) -> dict[str, Any] | None:
    """Return canonical vs inferred thread graph fields for one email."""
    if not full_email and not fallback_conversation_id:
        return None
    email = full_email or {}
    references = _references_for_email(full_email)
    conversation_id = _text(email.get("conversation_id") or fallback_conversation_id)
    in_reply_to = _text(email.get("in_reply_to"))
    canonical = {
        "conversation_id": conversation_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "has_thread_links": bool(conversation_id or in_reply_to or references),
    }
    inferred = {
        "parent_uid": _text(email.get("inferred_parent_uid")),
        "thread_id": _text(email.get("inferred_thread_id")),
        "reason": _text(email.get("inferred_match_reason")),
        "confidence": float(email.get("inferred_match_confidence") or 0.0),
    }
    inferred["has_parent_link"] = bool(inferred["parent_uid"] or inferred["thread_id"])
    return {
        "canonical": canonical,
        "inferred": inferred,
    }


def _thread_locator_for_candidate(
    candidate: dict[str, Any],
    full_email: dict[str, Any] | None,
) -> dict[str, str]:
    """Return the grouping locator for one candidate without conflating canonical and inferred ids."""
    canonical_conversation_id = str(candidate.get("conversation_id") or (full_email or {}).get("conversation_id") or "")
    inferred_thread_id = str((full_email or {}).get("inferred_thread_id") or "")
    if canonical_conversation_id:
        return {
            "conversation_id": canonical_conversation_id,
            "inferred_thread_id": inferred_thread_id,
            "thread_group_id": canonical_conversation_id,
            "thread_group_source": "canonical",
        }
    if inferred_thread_id:
        return {
            "conversation_id": "",
            "inferred_thread_id": inferred_thread_id,
            "thread_group_id": inferred_thread_id,
            "thread_group_source": "inferred",
        }
    return {
        "conversation_id": "",
        "inferred_thread_id": "",
        "thread_group_id": "",
        "thread_group_source": "",
    }


def _render_candidate_body(
    full_email: dict[str, Any], requested_mode: str, retrieval_snippet: str
) -> tuple[str, str, str, str, int | None, int | None]:
    """Render candidate body in the response format consumed by callers."""
    has_forensic = bool((full_email.get("forensic_body_text") or "").strip())
    if requested_mode == "forensic":
        mode = "forensic" if has_forensic else "retrieval"
        body, source = resolve_body_for_render(full_email, mode)
        snippet, status, start, end = _verified_snippet_for_mode(body, retrieval_snippet)
        verification = "forensic_exact" if status == "exact" and mode == "forensic" else "forensic_fallback_retrieval"
        return snippet, mode, source, verification, start, end
    if requested_mode == "hybrid" and has_forensic:
        body, source = resolve_body_for_render(full_email, "forensic")
        snippet, status, start, end = _verified_snippet_for_mode(body, retrieval_snippet)
        verification = "hybrid_verified_forensic" if status == "exact" else "hybrid_forensic_fallback"
        return snippet, "forensic", source, verification, start, end
    body, source = resolve_body_for_render(full_email, "retrieval")
    snippet, status, start, end = _verified_snippet_for_mode(body, retrieval_snippet)
    if requested_mode == "hybrid":
        return snippet, "retrieval", source, "hybrid_fallback_retrieval", start, end
    verification = "retrieval_exact" if status == "exact" else "retrieval_fallback"
    return snippet, "retrieval", source, verification, start, end


def _provenance_for_candidate(
    db: Any,
    uid: str,
    retrieval_snippet: str,
    *,
    metadata: dict[str, Any],
) -> tuple[str, str, str, str, dict[str, Any], dict[str, Any] | None]:
    """Resolve render provenance and a stable evidence handle for one candidate."""
    requested_mode = str(metadata.get("evidence_mode") or "retrieval")
    body_render_mode = "forensic" if requested_mode == "forensic" else "retrieval"
    body_render_source = str(metadata.get("body_render_source") or metadata.get("normalized_body_source") or "search_result_text")
    snippet = retrieval_snippet
    snippet_start: int | None = None
    snippet_end: int | None = None
    segment_ordinal: int | None = None
    verification_status = "retrieval"

    full_map = db.get_emails_full_batch([uid]) if db and uid and hasattr(db, "get_emails_full_batch") else {}
    full_email = full_map.get(uid) if isinstance(full_map, dict) else None
    if full_email:
        snippet, body_render_mode, body_render_source, verification_status, snippet_start, snippet_end = _render_candidate_body(
            full_email, requested_mode, retrieval_snippet
        )
        segment_ordinal = _segment_ordinal_for_snippet(db, uid, snippet)

    if snippet_start is None:
        snippet_start = 0
        snippet_end = len(snippet)

    handle = f"email:{uid}:{body_render_mode}:{body_render_source}:{snippet_start}:{snippet_end}"
    if segment_ordinal is not None:
        handle += f":{segment_ordinal}"

    provenance = {
        "evidence_handle": handle,
        "uid": uid,
        "body_render_mode": body_render_mode,
        "body_render_source": body_render_source,
        "snippet_start": snippet_start,
        "snippet_end": snippet_end,
        "segment_ordinal": segment_ordinal,
    }
    return snippet, body_render_mode, body_render_source, verification_status, provenance, full_email


"""Candidate and conversation-group helpers for answer-context evidence output."""


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
    params: AnswerContextRequest,
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


"""Quote attribution and candidate enrichment for answer-context payloads."""


_EMAIL_CANDIDATE_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_FROM_HEADER_RE = re.compile(r"(?im)^from:\s*(.+)$")


def _segment_rows_for_uid(db: Any, uid: str) -> list[dict[str, Any]]:
    """Return persisted conversation segments for one email, if available."""
    conn = getattr(db, "conn", None)
    if conn is None or not uid:
        return []
    rows = conn.execute(
        """SELECT ordinal, segment_type, depth, text, source_surface
           FROM message_segments
           WHERE email_uid = ?
           ORDER BY ordinal ASC""",
        (uid,),
    ).fetchall()
    return [dict(row) if not isinstance(row, dict) else row for row in rows]


def _normalize_attributed_email(value: str) -> str:
    """Return a best-effort normalized email address for attribution output."""
    normalized = value.strip().lower()
    if not normalized:
        return ""
    match = _EMAIL_CANDIDATE_RE.search(normalized)
    if match:
        return match.group(1).lower()
    return normalized


def _quoted_block_candidates(segment_text: str, authored_email: str) -> list[str]:
    """Return unique non-authored email candidates visible in one quoted block."""
    candidates: list[str] = []
    for match in _EMAIL_CANDIDATE_RE.finditer(segment_text or ""):
        email = _normalize_attributed_email(match.group(0))
        if not email or email == authored_email:
            continue
        if email not in candidates:
            candidates.append(email)
    return candidates


def _quoted_from_header_candidate(segment_text: str, authored_email: str) -> str:
    """Return one quoted speaker email from a visible ``From:`` header, if unambiguous."""
    match = _FROM_HEADER_RE.search(segment_text or "")
    if not match:
        return ""
    candidates = _quoted_block_candidates(match.group(1), authored_email)
    if len(candidates) == 1:
        return candidates[0]
    return ""


def _reply_context_identities(full_email: dict[str, Any] | None, authored_email: str) -> tuple[str, list[str]]:
    """Return normalized reply-context identities excluding the authored speaker."""
    normalized_authored_email = authored_email.strip().lower()
    reply_context_from = _normalize_attributed_email(str((full_email or {}).get("reply_context_from") or ""))
    reply_context_to = [
        _normalize_attributed_email(identity) for identity in ((full_email or {}).get("reply_context_to") or []) if identity
    ]
    identities = [
        identity for identity in [reply_context_from, *reply_context_to] if identity and identity != normalized_authored_email
    ]
    return reply_context_from, list(dict.fromkeys(identities))


def _quoted_reply_context_identities(segment_text: str, authored_email: str) -> list[str]:
    """Return unique quoted reply-context identities visible in one segment."""
    normalized_authored_email = authored_email.strip().lower()
    quoted_reply_context = extract_reply_context(segment_text, "", "reply")
    if not quoted_reply_context or not quoted_reply_context.from_email:
        return []
    quoted_from = _normalize_attributed_email(quoted_reply_context.from_email)
    quoted_to = [_normalize_attributed_email(identity) for identity in quoted_reply_context.to_emails]
    reply_context_identities = [
        identity for identity in [quoted_from, *quoted_to] if identity and identity != normalized_authored_email
    ]
    return list(dict.fromkeys(reply_context_identities))


def _quote_attribution_details(
    *,
    full_email: dict[str, Any] | None,
    authored_email: str,
    conversation_context: dict[str, Any] | None,
    segment_text: str = "",
) -> dict[str, Any]:
    """Return one normalized quote-attribution decision with explicit ambiguity state."""
    normalized_authored_email = authored_email.strip().lower()
    quoted_from_header = _quoted_from_header_candidate(segment_text, normalized_authored_email)
    quoted_reply_context_identities = _quoted_reply_context_identities(segment_text, normalized_authored_email)
    quoted_block_emails = _quoted_block_candidates(segment_text, normalized_authored_email)
    reply_context_from, reply_context_identities = _reply_context_identities(full_email, normalized_authored_email)

    if quoted_from_header:
        return _attribution_decision(quoted_from_header, "quoted_from_header", 0.85, "explicit_header")
    if len(quoted_reply_context_identities) == 1:
        return _quoted_reply_context_decision(quoted_reply_context_identities[0], reply_context_from)
    if len(quoted_block_emails) == 1:
        return _quoted_block_decision(quoted_block_emails[0], reply_context_from)
    if reply_context_from and not quoted_block_emails and not quoted_reply_context_identities:
        return _attribution_decision(
            reply_context_from,
            "reply_context_from",
            0.8,
            "reply_context_fallback",
            "Quoted ownership is inferred from the visible reply context because "
            "the quoted block has no explicit identity markers.",
            downgraded=True,
        )
    unique_alternatives = _conversation_alternatives(conversation_context, normalized_authored_email)
    if len(unique_alternatives) == 1:
        return _attribution_decision(
            unique_alternatives[0],
            "conversation_participant_exclusion",
            0.5,
            "participant_exclusion",
            "Quoted ownership is inferred only from the remaining conversation participants, so it should be read cautiously.",
            downgraded=True,
        )
    return _attribution_decision(
        "",
        "unresolved",
        0.0,
        "unresolved",
        "Quoted ownership remains unresolved because the visible reply chain includes multiple plausible speakers.",
        candidates=list(dict.fromkeys([*quoted_block_emails, *reply_context_identities])),
        downgraded=True,
    )


def _attribution_decision(
    speaker_email: str,
    source: str,
    confidence: float,
    status: str,
    reason: str = "",
    *,
    candidates: list[str] | None = None,
    downgraded: bool = False,
) -> dict[str, Any]:
    """Package speaker identity, provenance, confidence, downgrade state, and alternatives consistently."""
    return {
        "speaker_email": speaker_email,
        "source": source,
        "confidence": confidence,
        "quote_attribution_status": status,
        "quote_attribution_reason": reason,
        "candidate_emails": candidates if candidates is not None else [speaker_email],
        "downgraded_due_to_quote_ambiguity": downgraded,
    }


def _quoted_reply_context_decision(speaker_email: str, reply_context_from: str) -> dict[str, Any]:
    """Assign high-confidence quoted ownership when reply-context identity corroborates the speaker."""
    corroborated = bool(reply_context_from and reply_context_from == speaker_email)
    return _attribution_decision(
        speaker_email,
        "reply_context_from_corroborated" if corroborated else "quoted_block_reply_context",
        0.8 if corroborated else 0.72,
        "corroborated_reply_context",
    )


def _quoted_block_decision(speaker_email: str, reply_context_from: str) -> dict[str, Any]:
    """Calibrate quoted-block ownership lower unless reply context corroborates the sole candidate."""
    corroborated = bool(reply_context_from and reply_context_from == speaker_email)
    return _attribution_decision(
        speaker_email,
        "reply_context_from_corroborated" if corroborated else "quoted_block_email",
        0.78 if corroborated else 0.6,
        "corroborated_reply_context" if corroborated else "inferred_single_candidate",
        "" if corroborated else "Only one non-authored identity is visible in the quoted block, so ownership remains inferred.",
        downgraded=not corroborated,
    )


def _conversation_alternatives(conversation_context: dict[str, Any] | None, authored_email: str) -> list[str]:
    """Return unique normalized participants other than the message author as attribution alternatives."""
    participants = as_dict(conversation_context).get("participants", [])
    alternatives = [
        str(participant).strip().lower() for participant in participants if participant and participant != authored_email
    ]
    return list(dict.fromkeys(alternatives))


def _infer_quoted_speaker(
    *,
    full_email: dict[str, Any] | None,
    authored_email: str,
    conversation_context: dict[str, Any] | None,
    segment_text: str = "",
) -> tuple[str, str, float]:
    """Infer a likely quoted speaker and attribution provenance."""
    decision = _quote_attribution_details(
        full_email=full_email,
        authored_email=authored_email,
        conversation_context=conversation_context,
        segment_text=segment_text,
    )
    return (
        str(decision.get("speaker_email") or ""),
        str(decision.get("source") or "unresolved"),
        float(decision.get("confidence") or 0.0),
    )


def _speaker_attribution_for_candidate(
    db: Any,
    *,
    uid: str,
    conversation_id: str,
    sender_email: str,
    sender_name: str,
    conversation_context: dict[str, Any] | None,
    full_email: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build authored vs quoted speaker hints for one candidate."""
    segments = _segment_rows_for_uid(db, uid)
    if not segments:
        return None
    authored_email, authored_name = _canonical_sender_for_candidate(db, conversation_id, uid, sender_email, sender_name)
    return {
        "authored_speaker": {
            "email": authored_email,
            "name": authored_name,
            "source": "canonical_sender",
            "confidence": 1.0,
        },
        "quoted_blocks": _quoted_speaker_blocks(segments, full_email, sender_email, conversation_context),
    }


def _quoted_speaker_blocks(
    segments: list[dict[str, Any]],
    full_email: dict[str, Any] | None,
    sender_email: str,
    conversation_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract only quoted-reply and forwarded-message segments for speaker attribution."""
    quoted_blocks: list[dict[str, Any]] = []
    for segment in segments:
        segment_type = str(segment.get("segment_type") or "")
        if segment_type not in {"quoted_reply", "forwarded_message"}:
            continue
        quoted_blocks.append(_quoted_speaker_block(segment, segment_type, full_email, sender_email, conversation_context))
    return quoted_blocks


def _quoted_speaker_block(
    segment: dict[str, Any],
    segment_type: str,
    full_email: dict[str, Any] | None,
    sender_email: str,
    conversation_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combine segment location and calibrated quote attribution into one public speaker block."""
    quote_attribution = _quote_attribution_details(
        full_email=full_email,
        authored_email=sender_email,
        conversation_context=conversation_context,
        segment_text=str(segment.get("text") or ""),
    )
    return {
        "segment_ordinal": int(segment.get("ordinal") or 0),
        "segment_type": segment_type,
        "speaker_email": str(quote_attribution.get("speaker_email") or ""),
        "source": str(quote_attribution.get("source") or ""),
        "confidence": float(quote_attribution.get("confidence") or 0.0),
        "quote_attribution_status": str(quote_attribution.get("quote_attribution_status") or ""),
        "quote_attribution_reason": str(quote_attribution.get("quote_attribution_reason") or ""),
        "candidate_emails": list(quote_attribution.get("candidate_emails") or []),
        "downgraded_due_to_quote_ambiguity": bool(quote_attribution.get("downgraded_due_to_quote_ambiguity", True)),
        "text": str(segment.get("text") or ""),
    }


def _canonical_sender_for_candidate(
    db: Any, conversation_id: str, uid: str, sender_email: str, sender_name: str
) -> tuple[str, str]:
    """Recover the stored author identity from the canonical thread row when available."""
    authored_email = sender_email
    authored_name = sender_name
    if db and conversation_id and hasattr(db, "get_thread_emails"):
        thread_emails = db.get_thread_emails(conversation_id) or []
        for email in thread_emails:
            if str(email.get("uid") or "") != uid:
                continue
            authored_email = str(email.get("sender_email") or authored_email)
            authored_name = str(email.get("sender_name") or authored_name)
            break
    return authored_email, authored_name


"""Candidate-row builders for answer-context runtime payloads."""


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _strings(values: Any) -> list[str]:
    return [str(item) for item in (values or []) if item]


def _dicts(values: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (values or []) if isinstance(item, dict)]


def _row_rank_key(row: dict[str, Any], *, exact_wording: bool) -> tuple[float, float, str]:
    """Adapt a preloaded row to the same competition key used for retriever results."""
    proxy = type("_RowProxy", (), {"metadata": row, "score": float(row.get("score") or 0.0), "chunk_id": ""})()
    return _result_competition_key(proxy, exact_wording=exact_wording)


@dataclass(frozen=True)
class _RowContext:
    """Bundle one preloaded row with ranking and request-specific rendering state."""

    row: dict[str, Any]
    rank: int
    params: Any
    exact_wording: bool

    @property
    def uid(self) -> str:
        """Return the candidate message UID as normalized text."""
        return _text(self.row.get("uid"))

    @property
    def source_id(self) -> str:
        """Return explicit source identity, falling back to stable row identity."""
        return _text(self.row.get("source_id"), f"email:{self.uid}" if self.uid else _text(self.row.get("result_key")))

    @property
    def document_locator(self) -> dict[str, Any]:
        """Copy the locator so payload assembly cannot mutate the source row."""
        return dict(self.row.get("document_locator") or {})

    @property
    def provenance(self) -> dict[str, Any]:
        """Copy provenance so later packing cannot mutate the source row."""
        return dict(self.row.get("provenance") or {})


def _row_common(context: _RowContext, provenance: dict[str, Any]) -> dict[str, Any]:
    """Project shared rank, identity, score, snippet, and provenance fields for any preloaded candidate."""
    row = context.row
    return {
        "rank": context.rank,
        "uid": context.uid,
        "subject": row.get("subject", ""),
        "sender_email": row.get("sender_email", ""),
        "sender_name": row.get("sender_name", ""),
        "date": row.get("date", ""),
        "conversation_id": row.get("conversation_id", ""),
        "score": float(row.get("score") or 0.0),
        "snippet": row.get("snippet", ""),
        "match_reason": row.get("match_reason") or _match_reason(context.rank, context.params),
        "exact_wording_requested": context.exact_wording,
        "provenance": provenance,
        "score_kind": row.get("score_kind", "semantic"),
        "score_calibration": row.get("score_calibration", "calibrated"),
        "result_key": row.get("result_key", ""),
        "matched_query_lanes": _strings(row.get("matched_query_lanes")),
        "matched_query_queries": _strings(row.get("matched_query_queries")),
        "support_type": _support_type_for_row(row),
        "document_locator": context.document_locator,
        "source_reliability": dict(row.get("source_reliability") or {}),
        "candidate_related_source_ids": [
            str(item) for item in (row.get("candidate_related_source_ids") or []) if str(item).strip()
        ],
        "candidate_related_sources": _dicts(row.get("candidate_related_sources")),
        "follow_up": row.get("follow_up") or ({"tool": "email_deep_context", "uid": context.uid} if context.uid else {}),
    }


def _preloaded_attachment(context: _RowContext) -> dict[str, Any]:
    """Normalize a caller-supplied attachment row with a stable source ID and evidence handle."""
    row = context.row
    attachment = dict(row.get("attachment") or {})
    filename = _text(attachment.get("filename") or row.get("attachment_filename"), "attachment")
    attachment.setdefault("filename", filename)
    source_type_hint = _text(attachment.get("source_type_hint") or row.get("source_type"), "attachment")
    provenance = context.provenance
    provenance.setdefault(
        "evidence_handle",
        _text(
            context.document_locator.get("evidence_handle") or context.source_id, f"{source_type_hint}:{context.uid}:{filename}"
        ),
    )
    return {
        **_row_common(context, provenance),
        "source_id": context.source_id or f"{source_type_hint}:{context.uid}:{filename}",
        "source_type": _text(row.get("source_type"), source_type_hint),
        "attachment": attachment,
        "verification_status": row.get("verification_status", "attachment_reference"),
    }


def _preloaded_body(context: _RowContext) -> dict[str, Any]:
    """Normalize a caller-supplied body row with retrieval defaults and stable email provenance."""
    row = context.row
    provenance = context.provenance
    provenance.setdefault(
        "evidence_handle", _text(context.document_locator.get("evidence_handle") or context.source_id, f"email:{context.uid}")
    )
    return {
        **_row_common(context, provenance),
        "source_id": context.source_id or f"email:{context.uid}",
        "source_type": _text(row.get("source_type"), "email" if context.uid else "external"),
        "body_render_mode": row.get("body_render_mode", "quoted_snippet"),
        "body_render_source": row.get("body_render_source", "retrieval"),
        "verification_status": row.get("verification_status", "retrieval_exact"),
    }


def _preloaded_candidates(
    rows: list[dict[str, Any]],
    params: Any,
    exact_wording: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank preloaded rows once and partition them into body and attachment candidates."""
    bodies: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []
    ordered = sorted(rows, key=lambda row: _row_rank_key(row, exact_wording=exact_wording), reverse=True)
    for rank, row in enumerate(ordered, start=1):
        context = _RowContext(row, rank, params, exact_wording)
        if _text(row.get("candidate_kind")) == "attachment" or isinstance(row.get("attachment"), dict):
            attachments.append(_preloaded_attachment(context))
        else:
            bodies.append(_preloaded_body(context))
    return bodies, attachments


def _result_attachment(db: Any, result: Any, rank: int, params: Any, exact_wording: bool) -> dict[str, Any]:
    """Enrich a retrieved attachment with source identity, calibration, query-lane, and verification metadata."""
    metadata = result.metadata
    candidate = _attachment_candidate(db, result, rank=rank, params=params)
    attachment = as_dict(candidate.get("attachment"))
    uid = _text(metadata.get("uid"))
    source_type = _text(attachment.get("source_type_hint"), "attachment")
    candidate.update(
        source_id=f"{source_type}:{uid}:{_text(attachment.get('filename'), 'attachment')}",
        verification_status=_text(metadata.get("verification_status"), "attachment_reference"),
        exact_wording_requested=exact_wording,
        score_kind=_text(metadata.get("score_kind"), "semantic"),
        score_calibration=_text(metadata.get("score_calibration"), "calibrated"),
        result_key=_text(metadata.get("result_key")),
        matched_query_lanes=_strings(metadata.get("matched_query_lanes")),
        matched_query_queries=_strings(metadata.get("matched_query_queries")),
    )
    candidate["support_type"] = _support_type_for_result(result, matched_queries=candidate["matched_query_queries"])
    return candidate


def _result_body(db: Any, result: Any, rank: int, params: Any, exact_wording: bool) -> dict[str, Any]:
    """Convert a retrieved body result into a provenance-aware, wording-sensitive answer candidate."""
    metadata = {**result.metadata, "evidence_mode": params.evidence_mode}
    uid = _text(metadata.get("uid"))
    snippet, mode, source, verification, provenance, _full_email = _provenance_for_candidate(
        db, uid, _snippet(result.text), metadata=metadata
    )
    queries = _strings(metadata.get("matched_query_queries"))
    return {
        **candidate_summary(
            metadata,
            result,
            rank=rank,
            uid=uid,
            snippet=snippet,
            match_reason=_match_reason(rank, params),
        ),
        "source_id": f"email:{uid}",
        "body_render_mode": mode,
        "body_render_source": source,
        "verification_status": verification,
        "exact_wording_requested": exact_wording,
        "provenance": provenance,
        "score_kind": metadata.get("score_kind", "semantic"),
        "score_calibration": metadata.get("score_calibration", "calibrated"),
        "result_key": metadata.get("result_key", ""),
        "matched_query_lanes": _strings(metadata.get("matched_query_lanes")),
        "matched_query_queries": queries,
        "support_type": _support_type_for_result(result, matched_queries=queries),
        "follow_up": {"tool": "email_deep_context", "uid": uid},
    }


def _search_result_candidates(
    results: list[Any], db: Any, params: Any, exact_wording: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Preserve retrieval order while partitioning results into body and attachment candidates."""
    bodies: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []
    for rank, result in enumerate(results, start=1):
        if _is_attachment_result(result.metadata, chunk_id=result.chunk_id):
            attachments.append(_result_attachment(db, result, rank, params, exact_wording))
        else:
            bodies.append(_result_body(db, result, rank, params, exact_wording))
    return bodies, attachments


def build_initial_candidate_rows(
    *,
    preloaded_rows: list[dict[str, Any]],
    results: list[Any],
    db: Any,
    params: Any,
    exact_wording: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert preloaded evidence rows or search results into payload candidates."""
    if preloaded_rows:
        return _preloaded_candidates(preloaded_rows, params, exact_wording)
    return _search_result_candidates(results, db, params, exact_wording)


__all__ = ["build_initial_candidate_rows"]
