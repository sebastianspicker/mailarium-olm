# pylint: disable=too-many-locals


"""Split archive-harvest expansion-row helpers (case_analysis_harvest_expansion_rows)."""

from __future__ import annotations

from typing import Any

from .case_analysis_harvest_common import (
    _best_body_text,
    _compact,
    _email_language_fields,
    _expansion_error_entry,
)
from .case_analysis_harvest_expansion_diagnostics import _default_expansion_stage_diagnostics
from .case_analysis_harvest_quality import _seed_relevance_terms, _text_overlap_score


def _attachment_relevance_haystack(attachment: dict[str, Any]) -> str:
    """Build a searchable text haystack from an attachment for relevance scoring.

    Combines name, extracted_text, text_preview, and source_type_hint into a single string.
    """
    return " ".join(
        [
            str(attachment.get("name") or ""),
            str(attachment.get("extracted_text") or ""),
            str(attachment.get("text_preview") or ""),
            str((attachment.get("documentary_support") or {}).get("source_type_hint") or ""),
        ]
    )


def _attachment_sort_key(attachment: dict[str, Any], relevance_terms: list[str]) -> tuple[int, int, int, int, int, str]:
    """Generate sort key for ranking attachments by relevance.

    Returns a tuple that sorts attachments by:
    1. Text overlap score (descending - negative for ascending sort)
    2. Not inline (0) before inline (1)
    3. Has extracted text (0) before no text (1)
    4. Preferred source types (0) before others (1)
    5. Preferred extensions (0) before others (1)
    6. Filename (alphabetical)
    """
    return (
        -_text_overlap_score(haystack=_attachment_relevance_haystack(attachment), terms=relevance_terms),
        0 if not bool(attachment.get("is_inline")) else 1,
        0 if bool(_compact(attachment.get("extracted_text") or attachment.get("text_preview"))) else 1,
        0
        if _compact((attachment.get("documentary_support") or {}).get("source_type_hint"))
        in {"formal_document", "note_record", "participation_record", "time_record"}
        else 1,
        0 if _compact(attachment.get("name")).lower().endswith((".pdf", ".eml", ".ics", ".docx", ".txt")) else 1,
        _compact(attachment.get("name")).casefold(),
    )


def _rank_attachments(attachments: list[Any], relevance_terms: list[str]) -> list[dict[str, Any]]:
    """Rank attachments by relevance to the given terms.

    Returns a sorted list of attachment dicts, filtered to only include dict items.
    """
    return sorted(
        [attachment for attachment in attachments if isinstance(attachment, dict)],
        key=lambda attachment: _attachment_sort_key(attachment, relevance_terms),
    )


def _select_attachments(
    attachments: list[Any],
    *,
    relevance_terms: list[str],
    exhaustive_review: bool,
) -> list[dict[str, Any]]:
    """Select top attachments for expansion.

    Returns up to 5 (exhaustive) or 3 (non-exhaustive) attachments,
    skipping inline attachments without extracted text.
    """
    selected = []
    for attachment in _rank_attachments(attachments, relevance_terms):
        if bool(attachment.get("is_inline")) and not _compact(attachment.get("extracted_text") or attachment.get("text_preview")):
            continue
        selected.append(attachment)
        if len(selected) >= (5 if exhaustive_review else 3):
            break
    return selected


def _attachment_expansion_row(
    *,
    seed: dict[str, Any],
    uid: str,
    attachment: dict[str, Any],
    filename: str,
    relevance_terms: list[str],
) -> dict[str, Any]:
    """Build an expansion row for an attachment.

    Returns a dict with all fields needed for an attachment expansion evidence row.
    """
    attachment_text = _attachment_display_text(attachment)
    relevance_score = _attachment_expansion_relevance_score(attachment, relevance_terms)
    attachment_summary = _attachment_expansion_summary(attachment, filename)
    return {
        "uid": uid,
        "chunk_id": f"{uid}:attachment:{filename}",
        "score": _attachment_expansion_score(seed, relevance_score),
        "subject": _compact(seed.get("subject")),
        "sender_email": _compact(seed.get("sender_email")),
        "sender_name": _compact(seed.get("sender_name")),
        "date": _compact(seed.get("date")),
        "conversation_id": _compact(seed.get("conversation_id")),
        "folder": _compact(seed.get("folder")),
        "has_attachments": True,
        "candidate_kind": "attachment",
        "attachment_filename": filename,
        "snippet": attachment_text[:280],
        "matched_query_lanes": list(seed.get("matched_query_lanes") or []),
        "matched_query_queries": list(seed.get("matched_query_queries") or []),
        "result_key": f"{uid}:attachment:{filename}",
        "harvest_source": "attachment_expansion",
        "harvest_round": int(seed.get("harvest_round") or 0),
        "verification_status": "attachment_reference",
        "relevance_score": relevance_score,
        "attachment": attachment_summary,
        "detected_language": _compact(seed.get("detected_language")),
        "detected_language_confidence": _compact(seed.get("detected_language_confidence")),
        "provenance": _attachment_expansion_provenance(uid=uid, filename=filename),
    }


def _attachment_display_text(attachment: dict[str, Any]) -> str:
    """Extract display text from an attachment.

    Returns extracted_text if available, otherwise text_preview, otherwise name.
    """
    return _compact(attachment.get("extracted_text") or attachment.get("text_preview") or attachment.get("name"))


def _attachment_expansion_relevance_score(attachment: dict[str, Any], relevance_terms: list[str]) -> int:
    """Calculate relevance score for an attachment.

    Returns the text overlap score between attachment content and relevance terms.
    """
    return _text_overlap_score(
        haystack=" ".join(
            [
                str(attachment.get("name") or ""),
                str(attachment.get("extracted_text") or ""),
                str(attachment.get("text_preview") or ""),
            ]
        ),
        terms=relevance_terms,
    )


def _attachment_expansion_score(seed: dict[str, Any], relevance_score: int) -> float:
    """Calculate final expansion score for an attachment.

    Returns seed score multiplied by a relevance-based boost factor.
    """
    return float(seed.get("score") or 0.0) * (0.8 + min(relevance_score, 4) * 0.04)


def _attachment_expansion_summary(attachment: dict[str, Any], filename: str) -> dict[str, Any]:
    """Build summary dict for an attachment expansion.

    Returns a dict with filename, mime_type, evidence_strength, and text_available.
    """
    return {
        "filename": filename,
        "mime_type": _compact(attachment.get("mime_type")),
        "evidence_strength": _compact(attachment.get("evidence_strength")) or "weak_reference",
        "text_available": bool(_compact(attachment.get("extracted_text") or attachment.get("text_preview"))),
    }


def _attachment_expansion_provenance(*, uid: str, filename: str) -> dict[str, str]:
    """Build provenance dict for an attachment expansion.

    Returns evidence_handle, uid, attachment_filename, and body_render_source.
    """
    return {
        "evidence_handle": f"attachment:{uid}:{filename}",
        "uid": uid,
        "attachment_filename": filename,
        "body_render_source": "attachment_expansion",
    }


def _thread_row_sort_key(row: dict[str, Any], relevance_terms: list[str]) -> tuple[int, int, str]:
    """Generate sort key for ranking thread rows by relevance.

    Returns a tuple that sorts by:
    1. Text overlap score (descending - negative for ascending sort)
    2. Has attachments (0) before no attachments (1)
    3. Date (chronological)
    """
    return (
        -_text_overlap_score(
            haystack=" ".join(
                [
                    str(row.get("subject") or ""),
                    str(row.get("sender_name") or ""),
                    str(row.get("sender_email") or ""),
                    _best_body_text(dict(row)),
                ]
            ),
            terms=relevance_terms,
        ),
        0 if bool(row.get("has_attachments") or row.get("attachment_count")) else 1,
        str(row.get("date") or ""),
    )


def _rank_thread_rows(thread_rows: list[Any], relevance_terms: list[str]) -> list[dict[str, Any]]:
    """Rank thread rows by relevance to the given terms.

    Returns a sorted list of thread row dicts, filtered to only include dict items.
    """
    return sorted(
        [row for row in thread_rows if isinstance(row, dict)],
        key=lambda row: _thread_row_sort_key(row, relevance_terms),
    )


def _thread_expansion_error(
    diagnostics: dict[str, Any],
    *,
    conversation_id: str,
    seed: dict[str, Any],
    exc: Exception,
) -> None:
    """Record a thread expansion error in diagnostics.

    Adds an error entry with conversation_id, seed_uid, error_type, and error message.
    """
    _expansion_error_entry(
        diagnostics,
        {
            "conversation_id": conversation_id,
            "seed_uid": _compact(seed.get("uid")),
            "error_type": type(exc).__name__,
            "error": _compact(str(exc))[:240],
        },
    )


def _thread_expansion_row(
    *,
    seed: dict[str, Any],
    row: dict[str, Any],
    uid: str,
    conversation_id: str,
    relevance_terms: list[str],
) -> dict[str, Any]:
    """Build an expansion row for a thread message.

    Returns a dict with all fields needed for a thread expansion evidence row.
    """
    relevance_score = _text_overlap_score(
        haystack=" ".join([str(row.get("subject") or ""), _best_body_text(dict(row))]),
        terms=relevance_terms,
    )
    return {
        "uid": uid,
        "chunk_id": f"{uid}:thread_expansion",
        "score": float(seed.get("score") or 0.0) * (0.85 + min(relevance_score, 4) * 0.03),
        "subject": _compact(row.get("subject")),
        "sender_email": _compact(row.get("sender_email")),
        "sender_name": _compact(row.get("sender_name")),
        "date": _compact(row.get("date")),
        "conversation_id": conversation_id,
        "folder": _compact(row.get("folder")),
        "has_attachments": bool(row.get("has_attachments") or row.get("attachment_count")),
        "candidate_kind": "body",
        "attachment_filename": "",
        "snippet": _best_body_text(dict(row))[:280],
        "matched_query_lanes": list(seed.get("matched_query_lanes") or []),
        "matched_query_queries": list(seed.get("matched_query_queries") or []),
        "result_key": f"{uid}:thread_expansion",
        "harvest_source": "thread_expansion",
        "harvest_round": int(seed.get("harvest_round") or 0),
        "verification_status": "thread_context",
        "relevance_score": relevance_score,
        **_email_language_fields(dict(row)),
        "provenance": {
            "evidence_handle": f"thread:{uid}:{conversation_id}",
            "uid": uid,
            "conversation_id": conversation_id,
            "body_render_source": "thread_expansion",
        },
    }


def _thread_expansion_seed_rows(
    *,
    seed: dict[str, Any],
    thread_rows: list[Any],
    existing_uids: set[str],
    conversation_id: str,
    exhaustive_review: bool,
) -> list[dict[str, Any]]:
    """Generate thread expansion rows for a seed.

    Returns up to 4 (exhaustive) or 2 (non-exhaustive) expanded rows from thread.
    Skips rows already in existing_uids.
    """
    relevance_terms = _seed_relevance_terms(seed)
    expanded: list[dict[str, Any]] = []
    for row in _rank_thread_rows(thread_rows, relevance_terms):
        uid = _compact(row.get("uid"))
        if not uid or uid in existing_uids:
            continue
        existing_uids.add(uid)
        expanded.append(
            _thread_expansion_row(
                seed=seed,
                row=row,
                uid=uid,
                conversation_id=conversation_id,
                relevance_terms=relevance_terms,
            )
        )
        if len(expanded) >= (4 if exhaustive_review else 2):
            break
    return expanded


def _thread_rows_for_seed(
    db: Any,
    *,
    diagnostics: dict[str, Any],
    seed: dict[str, Any],
    conversation_id: str,
) -> list[Any]:
    """Fetch thread rows for a seed's conversation from the database.

    Returns list of thread emails or empty list on error.
    Records errors in diagnostics.
    """
    try:
        return db.get_thread_emails(conversation_id) or []
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _thread_expansion_error(diagnostics, conversation_id=conversation_id, seed=seed, exc=exc)
        return []


def _thread_seed_conversation_id(seed: dict[str, Any]) -> str:
    """Extract conversation_id from a seed for thread expansion.

    Returns empty string for attachment candidates, otherwise the seed's conversation_id.
    """
    if str(seed.get("candidate_kind") or "") == "attachment":
        return ""
    return _compact(seed.get("conversation_id"))


def _mark_attempted(diagnostics: dict[str, Any]) -> None:
    """Increment the attempted count in diagnostics."""
    diagnostics["attempted_count"] = int(diagnostics.get("attempted_count") or 0) + 1


def _finalize_expansion_diagnostics(diagnostics: dict[str, Any], expanded: list[dict[str, Any]]) -> dict[str, Any]:
    """Finalize expansion diagnostics with results.

    Sets expanded_row_count and status (partial if errors, otherwise ok).
    Returns the updated diagnostics dict.
    """
    diagnostics["expanded_row_count"] = len(expanded)
    diagnostics["status"] = "partial" if int(diagnostics.get("error_count") or 0) > 0 else "ok"
    return diagnostics


def _thread_expansion_rows(
    db: Any,
    *,
    evidence_bank: list[dict[str, Any]],
    exhaustive_review: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate thread expansion rows from evidence bank.

    Returns tuple of (expanded_rows, diagnostics).
    Skips seeds without conversation_id or when db doesn't support get_thread_emails.
    """
    diagnostics = _default_expansion_stage_diagnostics("thread_expansion")
    if db is None or not hasattr(db, "get_thread_emails"):
        return [], diagnostics
    existing_uids = {str(item.get("uid") or "") for item in evidence_bank if _compact(item.get("uid"))}
    expanded: list[dict[str, Any]] = []
    for seed in evidence_bank:
        conversation_id = _thread_seed_conversation_id(seed)
        if not conversation_id:
            continue
        _mark_attempted(diagnostics)
        thread_rows = _thread_rows_for_seed(db, diagnostics=diagnostics, seed=seed, conversation_id=conversation_id)
        expanded.extend(
            _thread_expansion_seed_rows(
                seed=seed,
                thread_rows=thread_rows,
                existing_uids=existing_uids,
                conversation_id=conversation_id,
                exhaustive_review=exhaustive_review,
            )
        )
    return expanded, _finalize_expansion_diagnostics(diagnostics, expanded)


def _attachment_expansion_error(diagnostics: dict[str, Any], *, uid: str, item: dict[str, Any], exc: Exception) -> None:
    """Record an attachment expansion error in diagnostics.

    Adds an error entry with uid, seed_result_key, error_type, and error message.
    """
    _expansion_error_entry(
        diagnostics,
        {
            "uid": uid,
            "seed_result_key": _compact(item.get("result_key")),
            "error_type": type(exc).__name__,
            "error": _compact(str(exc))[:240],
        },
    )


def _attachment_expansion_seed_rows(
    *,
    seed: dict[str, Any],
    uid: str,
    attachments: list[Any],
    exhaustive_review: bool,
    seen: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Generate attachment expansion rows for a seed.

    Returns list of expansion rows for selected attachments.
    Skips attachments already seen (by uid, filename pair).
    """
    relevance_terms = _seed_relevance_terms(seed)
    rows: list[dict[str, Any]] = []
    for attachment in _select_attachments(
        attachments,
        relevance_terms=relevance_terms,
        exhaustive_review=exhaustive_review,
    ):
        filename = _compact(attachment.get("name"))
        if not filename or (uid, filename) in seen:
            continue
        seen.add((uid, filename))
        rows.append(
            _attachment_expansion_row(
                seed=seed,
                uid=uid,
                attachment=attachment,
                filename=filename,
                relevance_terms=relevance_terms,
            )
        )
    return rows


def _attachment_expansion_rows(
    db: Any,
    *,
    evidence_bank: list[dict[str, Any]],
    exhaustive_review: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate attachment expansion rows from evidence bank.

    Returns tuple of (expanded_rows, diagnostics).
    Skips items without uid or when db doesn't support attachments_for_email.
    """
    diagnostics = _default_expansion_stage_diagnostics("attachment_expansion")
    if db is None or not hasattr(db, "attachments_for_email"):
        return [], diagnostics
    expanded: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in evidence_bank:
        uid = _compact(item.get("uid"))
        if not uid:
            continue
        _mark_attempted(diagnostics)
        try:
            attachments = db.attachments_for_email(uid) or []
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _attachment_expansion_error(diagnostics, uid=uid, item=item, exc=exc)
            continue
        expanded.extend(
            _attachment_expansion_seed_rows(
                seed=item,
                uid=uid,
                attachments=attachments,
                exhaustive_review=exhaustive_review,
                seen=seen,
            )
        )
    return expanded, _finalize_expansion_diagnostics(diagnostics, expanded)


__all__ = [
    "_attachment_expansion_rows",
    "_thread_expansion_rows",
]
