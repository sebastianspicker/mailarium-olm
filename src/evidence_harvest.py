"""Wave-driven evidence harvest and promotion helpers."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-return-statements,too-many-statements

from __future__ import annotations

from typing import Any

from ._utils import _as_dict, _as_list, _compact
from .question_execution_waves import get_wave_definition


def _coerce_non_negative_int(value: Any) -> int | None:
    """Coerce a value to a non-negative int, returning None if conversion fails or result is negative."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


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


def _wave_meta(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract wave metadata from payload including wave_id, label, question_ids, and scan_id."""
    wave_execution = _as_dict(payload.get("wave_execution"))
    wave_id = _compact(wave_execution.get("wave_id"))
    if not wave_id:
        raise ValueError("wave_execution.wave_id is required for evidence harvest")
    definition = get_wave_definition(wave_id)
    label = _compact(wave_execution.get("label")) or definition.label
    questions = [
        _compact(item) for item in (_as_list(wave_execution.get("questions")) or list(definition.question_ids)) if _compact(item)
    ]
    return {
        "wave_id": definition.wave_id,
        "wave_label": label,
        "question_ids": questions,
        "scan_id": _compact(wave_execution.get("scan_id")),
    }


def _raw_archive_candidates(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Extract raw archive candidates from payload's archive_harvest.evidence_bank."""
    archive_harvest = _as_dict(payload.get("archive_harvest"))
    evidence_bank = [row for row in _as_list(archive_harvest.get("evidence_bank")) if isinstance(row, dict)]
    rows: list[tuple[str, dict[str, Any]]] = []
    for row in evidence_bank:
        candidate_kind = _compact(row.get("candidate_kind")) or "body"
        rows.append((candidate_kind, dict(row)))
    return rows


def _candidate_rows(payload: dict[str, Any], *, harvest_limit_per_wave: int) -> list[tuple[str, dict[str, Any]]]:
    """Get candidate rows from payload, preferring archive harvest, with per-wave limit."""
    raw_rows = _raw_archive_candidates(payload)
    if raw_rows:
        return raw_rows[:harvest_limit_per_wave]
    body = [row for row in _as_list(payload.get("candidates")) if isinstance(row, dict)][:harvest_limit_per_wave]
    attachments = [row for row in _as_list(payload.get("attachment_candidates")) if isinstance(row, dict)][
        :harvest_limit_per_wave
    ]
    return [("body", row) for row in body] + [("attachment", row) for row in attachments]


def _candidate_summary(*, wave_label: str, question_ids: list[str], candidate_kind: str, rank: int) -> str:
    """Generate a human-readable summary for a harvested candidate."""
    joined_questions = ", ".join(question_ids[:4]) if question_ids else "unmapped questions"
    if candidate_kind == "attachment":
        return f"{wave_label}: harvested attachment candidate for {joined_questions} (rank {rank})."
    return f"{wave_label}: harvested exact-quote candidate for {joined_questions} (rank {rank})."


def _candidate_context(
    *,
    candidate: dict[str, Any],
    candidate_kind: str,
    wave_id: str,
    question_ids: list[str],
    scan_id: str,
) -> dict[str, Any]:
    """Extract and normalize context metadata from a candidate for evidence storage."""
    attachment = _as_dict(candidate.get("attachment")) if candidate_kind == "attachment" else {}
    provenance = _as_dict(candidate.get("provenance"))
    support_type = _compact(candidate.get("support_type"))
    return {
        "wave_id": wave_id,
        "question_ids": list(question_ids),
        "scan_id": scan_id,
        "candidate_kind": candidate_kind,
        "match_reason": _compact(candidate.get("match_reason")),
        "attachment_filename": _compact(attachment.get("filename")),
        "attachment_mime_type": _compact(attachment.get("mime_type")),
        "harvest_source": _compact(candidate.get("harvest_source")),
        "body_render_source": _compact(candidate.get("body_render_source") or provenance.get("body_render_source")),
        "verification_status": _compact(candidate.get("verification_status")),
        "language": _compact(candidate.get("detected_language")),
        "language_confidence": _compact(candidate.get("detected_language_confidence")),
        "matched_query_lanes": [item for item in _as_list(candidate.get("matched_query_lanes")) if _compact(item)],
        "matched_query_queries": [item for item in _as_list(candidate.get("matched_query_queries")) if _compact(item)],
        "thread_group_id": _compact(candidate.get("thread_group_id")),
        "thread_group_source": _compact(candidate.get("thread_group_source")),
        "segment_type": _compact(candidate.get("segment_type") or provenance.get("segment_type")),
        "segment_ordinal": int(candidate.get("segment_ordinal") or provenance.get("segment_ordinal") or 0),
        "support_type": support_type,
        "counterevidence": support_type == "counterevidence",
        "comparator_evidence": support_type == "comparator",
    }


def _notes_for_promoted_candidate(
    *,
    run_id: str,
    phase_id: str,
    wave_id: str,
    question_ids: list[str],
    candidate: dict[str, Any],
) -> str:
    """Build provenance notes for an auto-promoted evidence candidate."""
    lanes = ", ".join(_compact(item) for item in _as_list(candidate.get("matched_query_lanes")) if _compact(item))
    evidence_handle = _compact(_as_dict(candidate.get("provenance")).get("evidence_handle"))
    notes = [
        "Auto-promoted from wave-driven evidence harvest.",
        f"run_id={run_id}",
        f"phase_id={phase_id}",
        f"wave_id={wave_id}",
    ]
    if question_ids:
        notes.append(f"questions={','.join(question_ids)}")
    if lanes:
        notes.append(f"matched_query_lanes={lanes}")
    if evidence_handle:
        notes.append(f"evidence_handle={evidence_handle}")
    verification_status = _compact(candidate.get("verification_status"))
    if verification_status:
        notes.append(f"verification_status={verification_status}")
    harvest_source = _compact(candidate.get("harvest_source"))
    if harvest_source:
        notes.append(f"harvest_source={harvest_source}")
    candidate_kind = _compact(candidate.get("candidate_kind"))
    if candidate_kind:
        notes.append(f"candidate_kind={candidate_kind}")
    support_type = _compact(candidate.get("support_type"))
    if support_type:
        notes.append(f"support_type={support_type}")
    segment_type = _compact(candidate.get("segment_type"))
    if segment_type:
        notes.append(f"segment_type={segment_type}")
    return " | ".join(notes)


def _relevance_for_candidate(*, rank: int) -> int:
    """Map candidate rank to a relevance score (5 for rank 0-1, 4 for 2-3, 3 otherwise)."""
    if rank <= 1:
        return 5
    if rank <= 3:
        return 4
    return 3


def _exact_quote_from_surface(snippet: str, surface_text: str) -> str:
    """Extract exact quote from surface text using snippet bounds, tolerating collapsed whitespace."""
    surface = str(surface_text or "")
    compact_snippet = _compact(snippet)
    if not compact_snippet or not surface.strip():
        return ""
    start, end = _find_snippet_bounds(surface, compact_snippet)
    if start is None or end is None:
        return ""
    exact = surface[start:end].strip()
    return exact or ""


def _segment_exact_quote(db: Any, *, uid: str, candidate: dict[str, Any]) -> str:
    """Recover exact quote from message segments in the database for a candidate."""
    conn = getattr(db, "conn", None)
    if conn is None or not uid:
        return ""
    provenance = _as_dict(candidate.get("provenance"))
    segment_ordinal = int(candidate.get("segment_ordinal") or provenance.get("segment_ordinal") or 0)
    segment_type = _compact(candidate.get("segment_type") or provenance.get("segment_type"))
    rows = conn.execute(
        """SELECT ordinal, segment_type, text
           FROM message_segments
           WHERE email_uid = ?
           ORDER BY ordinal ASC""",
        (uid,),
    ).fetchall()
    snippet = _compact(candidate.get("snippet"))
    exact = _segment_quote(rows, snippet=snippet, segment_ordinal=segment_ordinal, segment_type=segment_type)
    return exact or _segment_quote(rows, snippet=snippet, segment_ordinal=0, segment_type=segment_type)


def _segment_quote(rows: list[Any], *, snippet: str, segment_ordinal: int, segment_type: str) -> str:
    for row in rows:
        if segment_ordinal and int(row["ordinal"] or 0) != segment_ordinal:
            continue
        if segment_type and _compact(row["segment_type"]) != segment_type:
            continue
        exact = _exact_quote_from_surface(snippet, str(row["text"] or ""))
        if exact:
            return exact
    return ""


def _attachment_exact_quote(db: Any, *, uid: str, candidate: dict[str, Any]) -> str:
    """Recover exact quote from email attachments in the database for a candidate."""
    if db is None or not uid or not hasattr(db, "attachments_for_email"):
        return ""
    attachment = _as_dict(candidate.get("attachment"))
    filename = _compact(attachment.get("filename") or candidate.get("attachment_filename"))
    attachment_id = _compact(attachment.get("attachment_id") or candidate.get("attachment_id"))
    snippet = _compact(candidate.get("snippet"))
    for record in _matching_attachment_records(db, uid=uid, attachment_id=attachment_id, filename=filename):
        for field in ("extracted_text", "text_preview"):
            exact = _exact_quote_from_surface(snippet, str(record.get(field) or ""))
            if exact:
                return exact
    return ""


def _matching_attachment_records(db: Any, *, uid: str, attachment_id: str, filename: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in db.attachments_for_email(uid):
        record_id, record_name = _compact(record.get("attachment_id")), _compact(record.get("name"))
        if attachment_id and record_id and record_id != attachment_id:
            continue
        if filename and record_name and record_name != filename:
            continue
        records.append(record)
    return records


def _body_exact_quote(db: Any, *, uid: str, candidate: dict[str, Any]) -> str:
    """Recover exact quote from email body text in the database for a candidate."""
    if db is None or not uid or not hasattr(db, "get_emails_full_batch"):
        return ""
    snippet = _compact(candidate.get("snippet"))
    full_batch = db.get_emails_full_batch([uid])
    full_email = dict(_as_dict(full_batch).get(uid) or {})
    for field in ("forensic_body_text", "body_text", "raw_body_text", "subject"):
        exact = _exact_quote_from_surface(snippet, str(full_email.get(field) or ""))
        if exact:
            return exact
    return _segment_exact_quote(db, uid=uid, candidate=candidate)


def _recover_exact_quote(db: Any, *, candidate_kind: str, candidate: dict[str, Any]) -> str:
    """Recover exact quote using multiple strategies (locator, attachment, segment, body)."""
    uid = _compact(candidate.get("uid"))
    if not uid:
        return ""
    locator_exact = _locator_exact_quote(db, candidate_kind=candidate_kind, candidate=candidate)
    if locator_exact:
        return locator_exact
    if candidate_kind == "attachment":
        return _attachment_exact_quote(db, uid=uid, candidate=candidate)
    segment_exact = _segment_exact_quote(db, uid=uid, candidate=candidate)
    if segment_exact:
        return segment_exact
    return _body_exact_quote(db, uid=uid, candidate=candidate)


def _locator_slice(text: str, *, start: int | None, end: int | None) -> str:
    """Safely slice text using start and end indices with bounds checking."""
    if not text:
        return ""
    if start is None or end is None:
        return ""
    if start < 0 or end <= start:
        return ""
    if start >= len(text):
        return ""
    bounded_end = min(end, len(text))
    return text[start:bounded_end].strip()


def _body_surface_for_locator(full_email: dict[str, Any], body_render_source: str) -> str:
    """Select the appropriate body text field from email based on render source."""
    normalized_source = _compact(body_render_source).casefold()
    if normalized_source in {"forensic_body_text", "quoted_reply", "message_segments"}:
        return str(full_email.get("forensic_body_text") or "")
    if normalized_source in {"raw_body_text", "raw_source"}:
        return str(full_email.get("raw_body_text") or "")
    return str(full_email.get("body_text") or full_email.get("forensic_body_text") or full_email.get("raw_body_text") or "")


def _locator_exact_quote(db: Any, *, candidate_kind: str, candidate: dict[str, Any]) -> str:
    """Recover exact quote using character position locator from candidate provenance."""
    uid = _compact(candidate.get("uid"))
    if not uid:
        return ""
    provenance = _as_dict(candidate.get("provenance"))
    start = _coerce_non_negative_int(candidate.get("snippet_start") or provenance.get("snippet_start"))
    end = _coerce_non_negative_int(candidate.get("snippet_end") or provenance.get("snippet_end"))
    if start is None or end is None:
        return ""
    if candidate_kind == "attachment":
        return _attachment_locator_quote(db, uid=uid, candidate=candidate, start=start, end=end)
    return _body_locator_quote(db, uid=uid, candidate=candidate, provenance=provenance, start=start, end=end)


def _attachment_locator_quote(db: Any, *, uid: str, candidate: dict[str, Any], start: int, end: int) -> str:
    if db is None or not hasattr(db, "attachments_for_email"):
        return ""
    attachment = _as_dict(candidate.get("attachment"))
    filename = _compact(attachment.get("filename") or candidate.get("attachment_filename"))
    attachment_id = _compact(attachment.get("attachment_id") or candidate.get("attachment_id"))
    for record in _matching_attachment_records(db, uid=uid, attachment_id=attachment_id, filename=filename):
        quote = _locator_slice(str(record.get("extracted_text") or ""), start=start, end=end)
        if quote:
            return quote
    return ""


def _body_locator_quote(db: Any, *, uid: str, candidate: dict[str, Any], provenance: dict[str, Any], start: int, end: int) -> str:
    if db is None or not hasattr(db, "get_emails_full_batch"):
        return ""
    full_email = dict(_as_dict(db.get_emails_full_batch([uid])).get(uid) or {})
    if not full_email:
        return ""
    render_source = _compact(candidate.get("body_render_source") or provenance.get("body_render_source"))
    return _locator_slice(_body_surface_for_locator(full_email, render_source), start=start, end=end)


def _document_locator_for_candidate(*, candidate_kind: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """Build a document locator dict from candidate provenance and metadata."""
    provenance = _as_dict(candidate.get("provenance"))
    locator = {
        "evidence_handle": _compact(provenance.get("evidence_handle")),
        "chunk_id": _compact(provenance.get("chunk_id")),
        "snippet_start": provenance.get("snippet_start"),
        "snippet_end": provenance.get("snippet_end"),
        "segment_type": _compact(candidate.get("segment_type") or provenance.get("segment_type")),
        "source_scope": _compact(provenance.get("source_scope") or candidate.get("source_scope")),
        "char_start": provenance.get("char_start"),
        "char_end": provenance.get("char_end"),
        "surface_hash": _compact(provenance.get("surface_hash") or candidate.get("surface_hash")),
        "body_render_source": _compact(candidate.get("body_render_source") or provenance.get("body_render_source")),
    }
    segment_ordinal = int(candidate.get("segment_ordinal") or provenance.get("segment_ordinal") or 0)
    if segment_ordinal > 0:
        locator["segment_ordinal"] = segment_ordinal
    if candidate_kind == "attachment":
        locator.update(_attachment_locator(candidate, provenance))
    return {key: value for key, value in locator.items() if value not in (None, "", {})}


def _attachment_locator(candidate: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    attachment = _as_dict(candidate.get("attachment"))
    return {
        "attachment_filename": _compact(attachment.get("filename") or candidate.get("attachment_filename")),
        "attachment_mime_type": _compact(attachment.get("mime_type")),
        "attachment_id": _compact(
            attachment.get("attachment_id") or candidate.get("attachment_id") or provenance.get("attachment_id")
        ),
        "content_sha256": _compact(
            attachment.get("content_sha256") or candidate.get("content_sha256") or provenance.get("content_sha256")
        ),
        "locator_version": int(
            attachment.get("locator_version") or candidate.get("locator_version") or provenance.get("locator_version") or 1
        ),
        "text_locator": _as_dict(attachment.get("text_locator")),
    }


def harvest_wave_payload(
    db: Any,
    *,
    payload: dict[str, Any],
    run_id: str,
    phase_id: str,
    harvest_limit_per_wave: int,
    promote_limit_per_wave: int,
) -> dict[str, Any]:
    """Persist harvested candidates for one wave and auto-promote exact body quotes."""
    if db is None:
        return {
            "status": "db_unavailable",
            "candidate_count": 0,
            "body_candidate_count": 0,
            "attachment_candidate_count": 0,
            "exact_body_candidate_count": 0,
            "duplicate_candidate_count": 0,
            "promoted_count": 0,
            "linked_existing_evidence_count": 0,
            "promoted_evidence_ids": [],
        }

    from .evidence_harvest_stages import harvest_wave_stage

    return harvest_wave_stage(
        db,
        payload=payload,
        run_id=run_id,
        phase_id=phase_id,
        harvest_limit_per_wave=harvest_limit_per_wave,
        promote_limit_per_wave=promote_limit_per_wave,
    )
