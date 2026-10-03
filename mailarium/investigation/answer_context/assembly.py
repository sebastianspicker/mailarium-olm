"""Retrieval, enrichment, and analysis workflow stages for answer-context assembly."""

from __future__ import annotations

from typing import Any

from mailarium.model.data_shapes import as_dict

from ..formatting import weak_message_semantics
from .budgeting import _dedupe_evidence_items, _reindex_evidence
from .candidates import build_initial_candidate_rows, preload_candidate_data
from .contracts import AnswerContextRequest
from .diagnostics import _retrieval_diagnostics
from .lanes import _derive_query_lanes
from .models import AnswerContextRuntime
from .payload import rebuild_runtime_sections
from .policy import _resolve_exact_wording_requested
from .search import _search_across_query_lanes
from .speakers import _speaker_attribution_for_candidate
from .text import _dicts
from .threads import (
    _attach_conversation_context,
    _conversation_group_summaries,
    _recipients_summary,
    _thread_graph_for_email,
    _thread_locator_for_candidate,
)


def _set_optional_filters(kwargs: dict[str, Any], params: AnswerContextRequest) -> None:
    """Copy explicitly supplied mailbox filters into retriever keyword arguments."""
    for key in ("sender", "subject", "folder", "has_attachments", "email_type"):
        value = getattr(params, key)
        if value is not None:
            kwargs[key] = value


def _set_date_filters(kwargs: dict[str, Any], params: AnswerContextRequest) -> None:
    """Copy inclusive date bounds only when the caller supplied them."""
    if params.date_from is not None:
        kwargs["date_from"] = params.date_from
    if params.date_to is not None:
        kwargs["date_to"] = params.date_to


def _answer_context_search_kwargs(params: AnswerContextRequest, top_k: int) -> dict[str, Any]:
    """Build ``search_filtered`` kwargs for the answer-context tool."""
    exact = _resolve_exact_wording_requested(
        question=params.question,
        explicit=getattr(params, "exact_wording_requested", None),
    )
    kwargs: dict[str, Any] = {"query": params.question, "top_k": top_k, "_exact_wording_requested": exact}
    _set_optional_filters(kwargs, params)
    _set_date_filters(kwargs, params)
    if params.rerank:
        kwargs["rerank"] = True
    if params.hybrid:
        kwargs["hybrid"] = True
    if params.scope is not None:
        kwargs["scope"] = params.scope
    return kwargs


def _load_search_results(runtime: AnswerContextRuntime) -> None:
    """Load search results while preserving the caller's fallback behavior."""
    preloaded_rows = _dicts(runtime.preloaded_evidence_rows)
    if runtime.preloaded_results is None and not preloaded_rows:
        runtime.results, runtime.lane_diagnostics, runtime.retrieval_context = _search_across_query_lanes(
            retriever=runtime.retriever,
            search_kwargs=runtime.search_kwargs,
            query_lanes=runtime.query_lanes,
            top_k=runtime.effective_top_k,
            scan_id=runtime.params.scan_id,
        )
    else:
        runtime.results = list(runtime.preloaded_results)[: runtime.effective_top_k] if runtime.preloaded_results else []
        runtime.lane_diagnostics = []
        runtime.retrieval_context = {}
    runtime.retrieval_context.setdefault("original_query", str(runtime.search_kwargs.get("query") or ""))
    if runtime.lane_diagnostics:
        first_lane = as_dict(runtime.lane_diagnostics[0])
        runtime.retrieval_context.setdefault("executed_query", str(first_lane.get("executed_query") or ""))
    runtime.candidate_data = preload_candidate_data(
        runtime.db,
        results=runtime.results,
        preloaded_rows=preloaded_rows,
    )
    runtime.full_map = runtime.candidate_data.full_by_uid
    runtime.segments_by_uid = runtime.candidate_data.segments_by_uid
    runtime.candidates, runtime.attachment_candidates = build_initial_candidate_rows(
        preloaded_rows=preloaded_rows,
        results=runtime.results,
        db=runtime.db,
        data=runtime.candidate_data,
        params=runtime.params,
        exact_wording=runtime.exact_wording,
    )


def run_retrieval_stage(runtime: AnswerContextRuntime) -> None:
    """Resolve settings and produce deterministic de-duplicated candidate rows."""
    from mailarium.platform.settings import get_settings

    runtime.settings = get_settings()
    runtime.retriever = runtime.deps.get_retriever()
    runtime.db = runtime.deps.get_archive_database()
    runtime.effective_top_k = min(runtime.params.max_results, runtime.settings.mcp_max_search_results)
    runtime.search_kwargs = _answer_context_search_kwargs(runtime.params, runtime.effective_top_k)
    runtime.query_lanes = _derive_query_lanes(
        retriever=runtime.retriever,
        params=runtime.params,
        search_kwargs=runtime.search_kwargs,
    )
    explicit = runtime.search_kwargs.get("_exact_wording_requested")
    runtime.exact_wording = _resolve_exact_wording_requested(
        question=runtime.params.question,
        explicit=bool(explicit) if explicit is not None else getattr(runtime.params, "exact_wording_requested", None),
    )
    _load_search_results(runtime)
    runtime.candidates, runtime.deduped_body = _dedupe_evidence_items(runtime.candidates)
    runtime.attachment_candidates, runtime.deduped_attachments = _dedupe_evidence_items(runtime.attachment_candidates)
    _reindex_evidence(runtime.candidates)
    _reindex_evidence(runtime.attachment_candidates)


def _candidate_records(candidate: dict[str, Any], event_map: Any, occurrence_map: Any) -> None:
    """Attach event and entity records to candidates only when the UID has non-empty matches."""
    uid = str(candidate.get("uid") or "")
    if not uid:
        return
    events = event_map.get(uid) if isinstance(event_map, dict) else None
    occurrences = occurrence_map.get(uid) if isinstance(occurrence_map, dict) else None
    if isinstance(events, list) and events:
        candidate["event_records"] = _dicts(events)
    if isinstance(occurrences, list) and occurrences:
        candidate["entity_occurrences"] = _dicts(occurrences)


def _attach_record_maps(runtime: AnswerContextRuntime, candidate_uids: list[str]) -> None:
    """Apply record maps while retaining source diagnostics."""
    db = runtime.db
    event_map = db.events.event_records_for_uids(candidate_uids) if db and candidate_uids else {}
    occurrence_map = db.entities.entity_occurrences_for_uids(candidate_uids) if db and candidate_uids else {}
    for candidate in [*runtime.candidates, *runtime.attachment_candidates]:
        _candidate_records(candidate, event_map, occurrence_map)


def _attach_thread_context(runtime: AnswerContextRuntime) -> None:
    """Apply thread context while retaining source diagnostics."""
    for candidate in [*runtime.candidates, *runtime.attachment_candidates]:
        full_email = runtime.full_map.get(str(candidate.get("uid") or ""))
        candidate.update(_thread_locator_for_candidate(candidate, full_email))
        thread_graph = _thread_graph_for_email(
            full_email,
            fallback_conversation_id=str(candidate.get("conversation_id") or ""),
        )
        if thread_graph:
            candidate["thread_graph"] = thread_graph
    runtime.conversation_groups, by_id = _conversation_group_summaries(
        runtime.db,
        candidates=runtime.candidates,
        attachment_candidates=runtime.attachment_candidates,
    )
    _attach_conversation_context([*runtime.candidates, *runtime.attachment_candidates], by_id)


def _enrich_body_candidate(runtime: AnswerContextRuntime, candidate: dict[str, Any]) -> None:
    """Add recipients, weak-message semantics, speaker attribution, and quoted blocks from the full email."""
    full_email = runtime.full_map.get(str(candidate.get("uid") or ""))
    candidate["recipients_summary"] = _recipients_summary(full_email)
    weak_message = weak_message_semantics(full_email or {})
    if weak_message:
        candidate["weak_message"] = weak_message
    context = candidate.get("conversation_context")
    speaker = _speaker_attribution_for_candidate(
        runtime.db,
        uid=str(candidate.get("uid") or ""),
        conversation_id=str(candidate.get("conversation_id") or ""),
        sender_email=str(candidate.get("sender_email") or ""),
        sender_name=str(candidate.get("sender_name") or ""),
        conversation_context=context if isinstance(context, dict) else None,
        full_email=full_email,
        segments=runtime.segments_by_uid.get(str(candidate.get("uid") or ""), []),
    )
    if speaker:
        candidate["speaker_attribution"] = speaker


def run_enrichment_stage(runtime: AnswerContextRuntime) -> None:
    """Attach persisted records, thread context, and quote attribution."""
    candidate_uids = [
        str(candidate.get("uid")) for candidate in [*runtime.candidates, *runtime.attachment_candidates] if candidate.get("uid")
    ]
    _attach_record_maps(runtime, candidate_uids)
    _attach_thread_context(runtime)
    for candidate in runtime.candidates:
        _enrich_body_candidate(runtime, candidate)


def run_analysis_stage(runtime: AnswerContextRuntime) -> None:
    """Build generic answer policy, timeline, and retrieval diagnostics."""
    rebuild_runtime_sections(
        runtime,
        conversation_group_summaries=_conversation_group_summaries,
        attach_conversation_context=_attach_conversation_context,
    )
    runtime.retrieval_diagnostics = _retrieval_diagnostics(
        runtime.retriever,
        candidate_count=len(runtime.candidates),
        attachment_candidate_count=len(runtime.attachment_candidates),
        lane_diagnostics=runtime.lane_diagnostics,
        retrieval_context=runtime.retrieval_context,
    )


__all__ = ["run_analysis_stage", "run_enrichment_stage", "run_retrieval_stage"]
