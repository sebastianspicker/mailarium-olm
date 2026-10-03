"""Candidate construction for retrieved results and caller-supplied evidence rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mailarium.model.attachment_record_semantics import enrich_attachment_record
from mailarium.model.data_shapes import as_dict

from .attachments import (
    _attachment_evidence_profile,
    _attachment_filename,
    _attachment_info,
    _attachment_provenance,
    _attachment_record_for_candidate,
    _is_attachment_result,
)
from .contracts import AnswerContextRequest
from .models import _CandidateData
from .provenance import _provenance_for_candidate, preload_candidate_data
from .ranking import _result_competition_key
from .support import _support_type_for_result, _support_type_for_row
from .text import _dicts, _snippet, _text, _truthy_strings

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


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


def _match_reason(rank: int, params: AnswerContextRequest) -> str:
    """Return a compact explanation for why a candidate was included."""
    parts = ["Top-ranked semantic match" if rank == 1 else "High-ranked semantic match"]
    if params.hybrid:
        parts.append("hybrid recall enabled")
    if params.rerank:
        parts.append("reranked for precision")
    return "; ".join(parts) + "."


def _attachment_candidate(
    data: _CandidateData,
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
    record = _attachment_record_for_candidate(data, uid, filename)
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
        "matched_query_lanes": _truthy_strings(row.get("matched_query_lanes")),
        "matched_query_queries": _truthy_strings(row.get("matched_query_queries")),
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


def _result_attachment(data: _CandidateData, result: Any, rank: int, params: Any, exact_wording: bool) -> dict[str, Any]:
    """Enrich a retrieved attachment with source identity, calibration, query-lane, and verification metadata."""
    metadata = result.metadata
    candidate = _attachment_candidate(data, result, rank=rank, params=params)
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
        matched_query_lanes=_truthy_strings(metadata.get("matched_query_lanes")),
        matched_query_queries=_truthy_strings(metadata.get("matched_query_queries")),
    )
    candidate["support_type"] = _support_type_for_result(result)
    return candidate


def _result_body(data: _CandidateData, result: Any, rank: int, params: Any, exact_wording: bool) -> dict[str, Any]:
    """Convert a retrieved body result into a provenance-aware, wording-sensitive answer candidate."""
    metadata = {**result.metadata, "evidence_mode": params.evidence_mode}
    uid = _text(metadata.get("uid"))
    snippet, mode, source, verification, provenance, _full_email = _provenance_for_candidate(
        data, uid, _snippet(result.text), metadata=metadata
    )
    queries = _truthy_strings(metadata.get("matched_query_queries"))
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
        "matched_query_lanes": _truthy_strings(metadata.get("matched_query_lanes")),
        "matched_query_queries": queries,
        "support_type": _support_type_for_result(result),
        "follow_up": {"tool": "email_deep_context", "uid": uid},
    }


def _search_result_candidates(
    results: list[Any], data: _CandidateData, params: Any, exact_wording: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Preserve retrieval order while partitioning results into body and attachment candidates."""
    bodies: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []
    for rank, result in enumerate(results, start=1):
        if _is_attachment_result(result.metadata, chunk_id=result.chunk_id):
            attachments.append(_result_attachment(data, result, rank, params, exact_wording))
        else:
            bodies.append(_result_body(data, result, rank, params, exact_wording))
    return bodies, attachments


def build_initial_candidate_rows(
    *,
    preloaded_rows: list[dict[str, Any]],
    results: list[Any],
    db: ArchiveDatabase | None,
    data: _CandidateData | None = None,
    params: Any,
    exact_wording: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert preloaded evidence rows or search results into payload candidates."""
    if preloaded_rows:
        return _preloaded_candidates(preloaded_rows, params, exact_wording)
    request_data = data or preload_candidate_data(db, results=results, preloaded_rows=preloaded_rows)
    return _search_result_candidates(results, request_data, params, exact_wording)


__all__ = ["build_initial_candidate_rows", "preload_candidate_data"]
