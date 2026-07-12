# mypy: disable-error-code=name-defined
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split archive-harvest helpers (case_analysis_harvest_expansion)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._utils import _as_dict
from .case_analysis_harvest_common import (
    EnrichedRowIdentity,
    _build_enriched_row_identity,
    _compact,
)
from .case_analysis_harvest_expansion_diagnostics import _coerce_expansion_stage_result
from .case_analysis_harvest_expansion_rows import (
    _attachment_expansion_rows,
    _thread_expansion_rows,
)
from .mcp_models import EmailAnswerContextInput

if TYPE_CHECKING:
    pass


def _full_email_for_uid(db: Any, uid: str) -> dict[str, Any]:
    """Retrieve the full email record for a given UID from the database.

    Args:
        db: The email database with get_emails_full_batch method.
        uid: The unique identifier of the email to retrieve.

    Returns:
        A dict containing the full email record, or empty dict if not found or db is invalid.
    """
    if db is None or not uid or not hasattr(db, "get_emails_full_batch"):
        return {}
    return dict((db.get_emails_full_batch([uid]) or {}).get(uid) or {})


def _candidate_context(
    *,
    db: Any,
    metadata: dict[str, Any],
    uid: str,
    impl: Any,
    full_email: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build context information for a candidate email/segment.

    Args:
        db: The email database.
        metadata: Metadata dict for the candidate.
        uid: The unique identifier of the email.
        impl: The implementation object with context methods.
        full_email: The full email record, or None.

    Returns:
        A dict with thread_locator, recipients_summary, speaker_attribution,
        reply_context_from, and reply_context_emails.
    """
    thread_locator = impl._thread_locator_for_candidate(
        {"uid": uid, "conversation_id": metadata.get("conversation_id", "")},
        full_email,
    )
    reply_context_from, reply_context_emails = impl._reply_context_identities(
        full_email,
        str(metadata.get("sender_email") or ""),
    )
    return {
        "thread_locator": thread_locator,
        "recipients_summary": impl._recipients_summary(full_email),
        "speaker_attribution": impl._speaker_attribution_for_candidate(
            db,
            uid=uid,
            conversation_id=str(metadata.get("conversation_id") or ""),
            sender_email=str(metadata.get("sender_email") or ""),
            sender_name=str(metadata.get("sender_name") or ""),
            conversation_context=None,
            full_email=full_email,
        ),
        "reply_context_from": reply_context_from,
        "reply_context_emails": reply_context_emails,
    }


def _segment_identity(
    *,
    metadata: dict[str, Any],
    result: Any,
    uid: str,
    impl: Any,
    context: dict[str, Any],
    full_email: dict[str, Any],
) -> EnrichedRowIdentity:
    """Create an EnrichedRowIdentity for a segment candidate.

    Args:
        metadata: Metadata dict for the segment.
        result: The search/segment result object.
        uid: The unique identifier of the email.
        impl: The implementation object with snippet and provenance methods.
        context: Pre-computed context dict from _candidate_context.
        full_email: The full email record.

    Returns:
        An EnrichedRowIdentity configured for a segment with appropriate provenance.
    """
    segment_type = _compact(metadata.get("segment_type"))
    segment_ordinal = int(metadata.get("segment_ordinal") or 0)
    body_render_source = _compact(metadata.get("body_render_source")) or "message_segments"
    return EnrichedRowIdentity(
        snippet=impl._snippet(getattr(result, "text", "") or ""),
        body_render_mode="segment",
        body_render_source=body_render_source,
        verification_status="segment_exact",
        provenance={
            "evidence_handle": f"segment:{uid}:{segment_type}:{segment_ordinal}",
            "uid": uid,
            "segment_type": segment_type,
            "segment_ordinal": segment_ordinal,
            "body_render_source": body_render_source,
        },
        harvest_source="segment_search",
        recipients_summary=context["recipients_summary"],
        speaker_attribution=context["speaker_attribution"],
        reply_context_from=context["reply_context_from"],
        reply_context_emails=context["reply_context_emails"],
        thread_locator=context["thread_locator"],
        email_language_source=full_email or metadata,
        extra_fields={
            "segment_type": segment_type,
            "segment_ordinal": segment_ordinal,
        },
    )


def _enrich_segment_candidate(
    db: Any,
    entry: dict[str, Any],
    metadata: dict[str, Any],
    result: Any,
    impl: Any,
    index: int,
    uid: str,
) -> dict[str, Any]:
    """Enrich a segment candidate into a full evidence row.

    Args:
        db: The email database.
        entry: The original bank entry dict.
        metadata: Metadata dict for the segment.
        result: The search/segment result object.
        impl: The implementation object.
        index: The rank/index of this candidate.
        uid: The unique identifier of the email.

    Returns:
        A dict representing the enriched evidence row for the segment.
    """
    segment_full_email = _full_email_for_uid(db, uid)
    context = _candidate_context(db=db, metadata=metadata, uid=uid, impl=impl, full_email=segment_full_email or None)
    return _build_enriched_row_identity(
        index,
        entry,
        metadata,
        result,
        identity=_segment_identity(
            metadata=metadata,
            result=result,
            uid=uid,
            impl=impl,
            context=context,
            full_email=segment_full_email,
        ),
    )


def _body_identity(
    *,
    db: Any,
    metadata: dict[str, Any],
    result: Any,
    uid: str,
    impl: Any,
) -> EnrichedRowIdentity:
    """Create an EnrichedRowIdentity for a body (full email) candidate.

    Args:
        db: The email database.
        metadata: Metadata dict for the email.
        result: The search result object.
        uid: The unique identifier of the email.
        impl: The implementation object with snippet and provenance methods.

    Returns:
        An EnrichedRowIdentity configured for a body candidate with computed provenance.
    """
    retrieval_snippet = impl._snippet(getattr(result, "text", "") or "")
    snippet, body_render_mode, body_render_source, verification_status, provenance_payload, full_email = (
        impl._provenance_for_candidate(db, uid, retrieval_snippet, metadata=metadata)
    )
    context = _candidate_context(db=db, metadata=metadata, uid=uid, impl=impl, full_email=full_email)
    return EnrichedRowIdentity(
        snippet=snippet,
        body_render_mode=body_render_mode,
        body_render_source=body_render_source,
        verification_status=verification_status,
        provenance=provenance_payload,
        harvest_source="search_result",
        recipients_summary=context["recipients_summary"],
        speaker_attribution=context["speaker_attribution"],
        reply_context_from=context["reply_context_from"],
        reply_context_emails=context["reply_context_emails"],
        thread_locator=context["thread_locator"],
        email_language_source=full_email or {},
    )


def _enrich_body_candidate(
    db: Any,
    entry: dict[str, Any],
    metadata: dict[str, Any],
    result: Any,
    impl: Any,
    index: int,
    uid: str,
) -> dict[str, Any]:
    """Enrich a body (full email) candidate into a full evidence row.

    Args:
        db: The email database.
        entry: The original bank entry dict.
        metadata: Metadata dict for the email.
        result: The search result object.
        impl: The implementation object.
        index: The rank/index of this candidate.
        uid: The unique identifier of the email.

    Returns:
        A dict representing the enriched evidence row for the body candidate.
    """
    return _build_enriched_row_identity(
        index,
        entry,
        metadata,
        result,
        identity=_body_identity(db=db, metadata=metadata, result=result, uid=uid, impl=impl),
    )


def _db_uid_map(db: Any, method_name: str, candidate_uids: list[str]) -> dict[str, Any]:
    """Retrieve a map of UIDs to values using a database method.

    Args:
        db: The email database.
        method_name: The name of the method to call on the database.
        candidate_uids: List of UIDs to look up.

    Returns:
        A dict mapping UIDs to their values, or empty dict if method doesn't exist or fails.
    """
    if not hasattr(db, method_name):
        return {}
    value = getattr(db, method_name)(candidate_uids)
    return _as_dict(value)


def _attach_row_list(row: dict[str, Any], *, key: str, values: Any) -> None:
    """Attach a list of dict values to a row under a specified key.

    Args:
        row: The row dict to modify in-place.
        key: The key under which to store the values.
        values: The values to attach. If a list of dicts, they are copied.
    """
    if isinstance(values, list) and values:
        row[key] = [dict(item) for item in values if isinstance(item, dict)]


def _augment_event_occurrences(
    db: Any,
    enriched_rows: list[dict[str, Any]],
) -> None:
    """Augment enriched rows with event records and entity occurrences from the database.

    Args:
        db: The email database with event_records_for_uids and entity_occurrences_for_uids methods.
        enriched_rows: List of evidence rows to augment in-place.
    """
    candidate_uids = [str(item.get("uid") or "") for item in enriched_rows if _compact(item.get("uid"))]
    if db is None or not candidate_uids:
        return
    event_map = _db_uid_map(db, "event_records_for_uids", candidate_uids)
    occurrence_map = _db_uid_map(db, "entity_occurrences_for_uids", candidate_uids)
    for row in enriched_rows:
        uid = _compact(row.get("uid"))
        _attach_row_list(row, key="event_records", values=event_map.get(uid))
        _attach_row_list(row, key="entity_occurrences", values=occurrence_map.get(uid))


def _enriched_attachment_candidate(
    *,
    db: Any,
    entry: dict[str, Any],
    result: Any,
    impl: Any,
    index: int,
    answer_params: EmailAnswerContextInput,
) -> dict[str, Any]:
    """Enrich an attachment candidate into a full evidence row.

    Args:
        db: The email database.
        entry: The original bank entry dict.
        result: The search result object for the attachment.
        impl: The implementation object with attachment candidate methods.
        index: The rank/index of this candidate.
        answer_params: The email answer context input parameters.

    Returns:
        A dict representing the enriched evidence row for the attachment candidate.
    """
    attachment_candidate = impl._attachment_candidate(db, result, rank=index + 1, params=answer_params)
    attachment_candidate["harvest_source"] = "search_result"
    attachment_candidate["harvest_round"] = int(entry.get("harvest_round") or 0)
    return {**dict(entry), **attachment_candidate, "candidate_kind": "attachment"}


def _enriched_bank_entry(
    *,
    db: Any,
    answer_params: EmailAnswerContextInput,
    entry: dict[str, Any],
    result: Any,
    impl: Any,
    index: int,
) -> dict[str, Any]:
    """Enrich a single bank entry based on its type (segment, attachment, or body).

    Args:
        db: The email database.
        answer_params: The email answer context input parameters.
        entry: The original bank entry dict.
        result: The search result object.
        impl: The implementation object.
        index: The rank/index of this entry.

    Returns:
        A dict representing the enriched evidence row.
    """
    if result is None:
        return dict(entry)
    metadata = dict(_as_dict(result.metadata))
    metadata.setdefault("evidence_mode", answer_params.evidence_mode)
    uid = _compact(metadata.get("uid"))
    if _compact(metadata.get("score_kind")) == "segment_sql":
        return _enrich_segment_candidate(db, entry, metadata, result, impl, index, uid)
    if _compact(entry.get("candidate_kind")) == "attachment":
        return _enriched_attachment_candidate(
            db=db,
            entry=entry,
            result=result,
            impl=impl,
            index=index,
            answer_params=answer_params,
        )
    return _enrich_body_candidate(db, entry, metadata, result, impl, index, uid)


def _expansion_diagnostics_payload(
    *,
    thread_diagnostics: dict[str, Any],
    attachment_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Create a combined diagnostics payload from thread and attachment diagnostics.

    Args:
        thread_diagnostics: Diagnostics dict from thread expansion.
        attachment_diagnostics: Diagnostics dict from attachment expansion.

    Returns:
        A combined diagnostics dict with aggregated error counts and status.
    """
    thread_error_count = int(thread_diagnostics.get("error_count") or 0)
    attachment_error_count = int(attachment_diagnostics.get("error_count") or 0)
    total_error_count = thread_error_count + attachment_error_count
    return {
        "status": "partial" if total_error_count > 0 else "ok",
        "error_count": total_error_count,
        "thread_expansion": thread_diagnostics,
        "attachment_expansion": attachment_diagnostics,
    }


def _expand_enriched_rows(
    *,
    db: Any,
    enriched: list[dict[str, Any]],
    exhaustive_review: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Expand enriched rows with thread and attachment expansion.

    Args:
        db: The email database.
        enriched: List of already-enriched evidence rows.
        exhaustive_review: Whether to perform exhaustive review.

    Returns:
        A tuple of (all_rows, diagnostics) where all_rows includes original enriched rows
        plus expanded thread and attachment rows, and diagnostics contains expansion stats.
    """
    thread_rows, thread_diagnostics = _coerce_expansion_stage_result(
        _thread_expansion_rows(db, evidence_bank=enriched, exhaustive_review=exhaustive_review),
        stage="thread_expansion",
    )
    attachment_rows, attachment_diagnostics = _coerce_expansion_stage_result(
        _attachment_expansion_rows(db, evidence_bank=enriched, exhaustive_review=exhaustive_review),
        stage="attachment_expansion",
    )
    return (
        [*enriched, *thread_rows, *attachment_rows],
        _expansion_diagnostics_payload(
            thread_diagnostics=thread_diagnostics,
            attachment_diagnostics=attachment_diagnostics,
        ),
    )


def _enrich_evidence_bank(
    *,
    db: Any,
    answer_params: EmailAnswerContextInput,
    bank_entries: list[dict[str, Any]],
    bank_results: list[Any],
    exhaustive_review: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Enrich a bank of entries and results into evidence rows with expansion.

    Args:
        db: The email database.
        answer_params: The email answer context input parameters.
        bank_entries: List of bank entry dicts.
        bank_results: List of search result objects corresponding to entries.
        exhaustive_review: Whether to perform exhaustive review.

    Returns:
        A tuple of (enriched_rows, diagnostics) where enriched_rows are the fully
        enriched evidence rows (including expansions), and diagnostics contains
        expansion and enrichment statistics.
    """
    from .tools import search_answer_context_impl as impl

    enriched = [
        _enriched_bank_entry(
            db=db,
            answer_params=answer_params,
            entry=entry,
            result=bank_results[index] if index < len(bank_results) else None,
            impl=impl,
            index=index,
        )
        for index, entry in enumerate(bank_entries)
    ]
    _augment_event_occurrences(db, enriched)
    return _expand_enriched_rows(db=db, enriched=enriched, exhaustive_review=exhaustive_review)


__all__ = [
    "_attachment_expansion_rows",
    "_augment_event_occurrences",
    "_enrich_body_candidate",
    "_enrich_evidence_bank",
    "_enrich_segment_candidate",
    "_thread_expansion_rows",
]
