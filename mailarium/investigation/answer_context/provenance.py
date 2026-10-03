"""Request-scoped candidate records, body rendering, and snippet provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..formatting import resolve_body_for_render
from .attachments import _is_attachment_result
from .models import _CandidateData
from .text import _snippet

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


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


def preload_candidate_data(
    db: ArchiveDatabase | None,
    *,
    results: list[Any],
    preloaded_rows: list[dict[str, Any]],
) -> _CandidateData:
    """Load each candidate message, segment set, and rich attachment set once per request."""
    result_uids = [str(result.metadata.get("uid") or "") for result in results]
    row_uids = [str(row.get("uid") or "") for row in preloaded_rows]
    uids = list(dict.fromkeys(uid for uid in [*result_uids, *row_uids] if uid))
    if not db or not uids:
        return _CandidateData({}, {}, {})

    full_by_uid = db.queries.get_emails_full_batch(uids)
    segments_by_uid = db.queries.message_segments_for_emails(uids)
    attachment_uids = list(
        dict.fromkeys(
            str(result.metadata.get("uid") or "")
            for result in results
            if _is_attachment_result(result.metadata, chunk_id=result.chunk_id) and result.metadata.get("uid")
        )
    )
    attachments_by_uid: dict[str, list[dict[str, Any]]] = {}
    for uid in attachment_uids:
        attachments_by_uid[uid] = list(db.attachments.attachments_for_email(uid) or [])
    return _CandidateData(full_by_uid if isinstance(full_by_uid, dict) else {}, segments_by_uid, attachments_by_uid)


def _segment_ordinal_for_snippet(segments: list[dict[str, Any]], snippet: str) -> int | None:
    """Return the first segment ordinal containing *snippet*, if available."""
    normalized_snippet = " ".join(snippet.split())
    for row in segments:
        segment_text = row.get("text", "")
        if not segment_text:
            continue
        if snippet in segment_text or normalized_snippet in " ".join(segment_text.split()):
            ordinal = row.get("ordinal")
            return int(ordinal) if ordinal is not None else None
    return None


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
    data: _CandidateData,
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

    full_email = data.full_by_uid.get(uid)
    if full_email:
        snippet, body_render_mode, body_render_source, verification_status, snippet_start, snippet_end = _render_candidate_body(
            full_email, requested_mode, retrieval_snippet
        )
        segment_ordinal = _segment_ordinal_for_snippet(data.segments_by_uid.get(uid, []), snippet)

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
