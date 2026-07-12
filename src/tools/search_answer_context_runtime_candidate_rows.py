"""Candidate-row builders for answer-context runtime payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._utils import _as_dict
from . import search_answer_context_impl as impl
from .search_answer_context_runtime_ranking import (
    _result_competition_key,
    _support_type_for_result,
    _support_type_for_row,
)


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _strings(values: Any) -> list[str]:
    return [str(item) for item in (values or []) if item]


def _dicts(values: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (values or []) if isinstance(item, dict)]


def _row_rank_key(row: dict[str, Any], *, exact_wording: bool) -> tuple[float, float, str]:
    proxy = type("_RowProxy", (), {"metadata": row, "score": float(row.get("score") or 0.0), "chunk_id": ""})()
    return _result_competition_key(proxy, exact_wording=exact_wording)


@dataclass(frozen=True)
class _RowContext:
    row: dict[str, Any]
    rank: int
    params: Any
    exact_wording: bool
    later_round_only_handles: set[str]

    @property
    def uid(self) -> str:
        return _text(self.row.get("uid"))

    @property
    def source_id(self) -> str:
        return _text(self.row.get("source_id"), f"email:{self.uid}" if self.uid else _text(self.row.get("result_key")))

    @property
    def document_locator(self) -> dict[str, Any]:
        return dict(self.row.get("document_locator") or {})

    @property
    def provenance(self) -> dict[str, Any]:
        return dict(self.row.get("provenance") or {})


def _row_common(context: _RowContext, provenance: dict[str, Any]) -> dict[str, Any]:
    row = context.row
    handle = _text(provenance.get("evidence_handle"))
    harvest_round = int(row.get("harvest_round") or 0)
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
        "match_reason": row.get("match_reason") or impl._match_reason(context.rank, context.params),
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
        "harvest_round": harvest_round,
        "later_round_recovery": harvest_round > 0,
        "later_round_only_recovery": handle in context.later_round_only_handles,
        "follow_up": row.get("follow_up") or ({"tool": "email_deep_context", "uid": context.uid} if context.uid else {}),
    }


def _preloaded_attachment(context: _RowContext) -> dict[str, Any]:
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
    row = context.row
    provenance = context.provenance
    provenance.setdefault(
        "evidence_handle", _text(context.document_locator.get("evidence_handle") or context.source_id, f"email:{context.uid}")
    )
    return {
        **_row_common(context, provenance),
        "source_id": context.source_id or f"email:{context.uid}",
        "source_type": _text(row.get("source_type"), "email" if context.uid else "mixed_source"),
        "body_render_mode": row.get("body_render_mode", "quoted_snippet"),
        "body_render_source": row.get("body_render_source", row.get("harvest_source", "retrieval")),
        "verification_status": row.get("verification_status", "retrieval_exact"),
    }


def _preloaded_candidates(
    rows: list[dict[str, Any]], params: Any, exact_wording: bool, later_handles: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bodies: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []
    ordered = sorted(rows, key=lambda row: _row_rank_key(row, exact_wording=exact_wording), reverse=True)
    for rank, row in enumerate(ordered, start=1):
        context = _RowContext(row, rank, params, exact_wording, later_handles)
        if _text(row.get("candidate_kind")) == "attachment" or isinstance(row.get("attachment"), dict):
            attachments.append(_preloaded_attachment(context))
        else:
            bodies.append(_preloaded_body(context))
    return bodies, attachments


def _result_attachment(db: Any, result: Any, rank: int, params: Any, exact_wording: bool) -> dict[str, Any]:
    metadata = result.metadata
    candidate = impl._attachment_candidate(db, result, rank=rank, params=params)
    attachment = _as_dict(candidate.get("attachment"))
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
    metadata = {**result.metadata, "evidence_mode": params.evidence_mode}
    uid = _text(metadata.get("uid"))
    snippet, mode, source, verification, provenance, _full_email = impl._provenance_for_candidate(
        db, uid, impl._snippet(result.text), metadata=metadata
    )
    queries = _strings(metadata.get("matched_query_queries"))
    return {
        "rank": rank,
        "uid": uid,
        "source_id": f"email:{uid}",
        "subject": metadata.get("subject", ""),
        "sender_email": metadata.get("sender_email", ""),
        "sender_name": metadata.get("sender_name", ""),
        "date": metadata.get("date", ""),
        "conversation_id": metadata.get("conversation_id", ""),
        "score": result.score,
        "snippet": snippet,
        "match_reason": impl._match_reason(rank, params),
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
    bodies: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []
    for rank, result in enumerate(results, start=1):
        if impl._is_attachment_result(result.metadata, chunk_id=result.chunk_id):
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
    later_round_only_handles: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert preloaded evidence rows or search results into payload candidates."""
    if preloaded_rows:
        return _preloaded_candidates(preloaded_rows, params, exact_wording, later_round_only_handles)
    return _search_result_candidates(results, db, params, exact_wording)


__all__ = ["build_initial_candidate_rows"]
