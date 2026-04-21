"""Low-level evidence and retrieval helpers for answer-context rendering."""

from __future__ import annotations

import re
from typing import Any

from ..formatting import resolve_body_for_render
from ..mcp_models import EmailAnswerContextInput

_ATTACHMENT_HEADER_RE = re.compile(r'^\[Attachment:\s*(.+?)\s+from email\s+"', re.IGNORECASE)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _snippet(text: str, *, max_chars: int = 280) -> str:
    """Return a compact single-line snippet for answer evidence."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _match_reason(rank: int, params: EmailAnswerContextInput) -> str:
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
    """Return whether a search result represents attachment-derived evidence."""
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


def _thread_graph_for_email(
    full_email: dict[str, Any] | None,
    *,
    fallback_conversation_id: str = "",
) -> dict[str, Any] | None:
    """Return canonical vs inferred thread graph fields for one email."""
    if not full_email and not fallback_conversation_id:
        return None
    references = []
    if full_email:
        raw_references = full_email.get("references") or []
        if not raw_references and full_email.get("references_json"):
            import json

            try:
                raw_references = json.loads(str(full_email.get("references_json") or "[]"))
            except json.JSONDecodeError:
                raw_references = []
        if isinstance(raw_references, list):
            references = [str(reference) for reference in raw_references if reference]
    conversation_id = str((full_email or {}).get("conversation_id") or fallback_conversation_id or "")
    in_reply_to = str((full_email or {}).get("in_reply_to") or "")
    canonical = {
        "conversation_id": conversation_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "has_thread_links": bool(conversation_id or in_reply_to or references),
    }
    inferred = {
        "parent_uid": str((full_email or {}).get("inferred_parent_uid") or ""),
        "thread_id": str((full_email or {}).get("inferred_thread_id") or ""),
        "reason": str((full_email or {}).get("inferred_match_reason") or ""),
        "confidence": float((full_email or {}).get("inferred_match_confidence") or 0.0),
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
        has_forensic_text = bool((full_email.get("forensic_body_text") or "").strip())
        if requested_mode == "forensic":
            body_text, body_render_source = resolve_body_for_render(full_email, "forensic" if has_forensic_text else "retrieval")
            body_render_mode = "forensic" if has_forensic_text else "retrieval"
            snippet, status_suffix, snippet_start, snippet_end = _verified_snippet_for_mode(body_text, retrieval_snippet)
            verification_status = (
                "forensic_exact" if status_suffix == "exact" and body_render_mode == "forensic" else "forensic_fallback_retrieval"
            )
        elif requested_mode == "hybrid":
            if has_forensic_text:
                forensic_text, forensic_source = resolve_body_for_render(full_email, "forensic")
                body_render_mode = "forensic"
                body_render_source = forensic_source
                snippet, status_suffix, snippet_start, snippet_end = _verified_snippet_for_mode(forensic_text, retrieval_snippet)
                verification_status = "hybrid_verified_forensic" if status_suffix == "exact" else "hybrid_forensic_fallback"
            else:
                body_text, body_render_source = resolve_body_for_render(full_email, "retrieval")
                snippet, _, snippet_start, snippet_end = _verified_snippet_for_mode(body_text, retrieval_snippet)
                verification_status = "hybrid_fallback_retrieval"
        else:
            body_text, body_render_source = resolve_body_for_render(full_email, "retrieval")
            snippet, status_suffix, snippet_start, snippet_end = _verified_snippet_for_mode(body_text, retrieval_snippet)
            verification_status = "retrieval_exact" if status_suffix == "exact" else "retrieval_fallback"
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
