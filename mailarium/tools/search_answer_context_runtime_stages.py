"""Retrieval and generic enrichment stages for answer-context assembly."""

from __future__ import annotations

from typing import Any

from .._utils import _as_dict
from ..formatting import weak_message_semantics
from . import search_answer_context_impl as impl
from .search_answer_context_budget import _dedupe_evidence_items, _reindex_evidence
from .search_answer_context_rendering import _resolve_exact_wording_requested
from .search_answer_context_runtime_candidate_rows import build_initial_candidate_rows
from .search_answer_context_runtime_lanes import _derive_query_lanes
from .search_answer_context_runtime_payload import rebuild_runtime_sections
from .search_answer_context_runtime_search import _search_across_query_lanes
from .search_answer_context_runtime_state import AnswerContextRuntime


def _dict_rows(items: Any) -> list[dict[str, Any]]:
    """Copy only mapping-shaped records from optional database result collections."""
    return [dict(item) for item in (items or []) if isinstance(item, dict)]


def _load_search_results(runtime: AnswerContextRuntime) -> None:
    """Load search results while preserving the caller's fallback behavior."""
    preloaded_rows = _dict_rows(runtime.preloaded_evidence_rows)
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
        first_lane = _as_dict(runtime.lane_diagnostics[0])
        runtime.retrieval_context.setdefault("executed_query", str(first_lane.get("executed_query") or ""))
    runtime.candidates, runtime.attachment_candidates = build_initial_candidate_rows(
        preloaded_rows=preloaded_rows,
        results=runtime.results,
        db=runtime.db,
        params=runtime.params,
        exact_wording=runtime.exact_wording,
    )


def run_retrieval_stage(runtime: AnswerContextRuntime) -> None:
    """Resolve settings and produce deterministic de-duplicated candidate rows."""
    from ..config import get_settings

    runtime.settings = get_settings()
    runtime.retriever = runtime.deps.get_retriever()
    runtime.db = runtime.deps.get_email_db()
    runtime.effective_top_k = min(runtime.params.max_results, runtime.settings.mcp_max_search_results)
    runtime.search_kwargs = impl._answer_context_search_kwargs(runtime.params, runtime.effective_top_k)
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
        candidate["event_records"] = _dict_rows(events)
    if isinstance(occurrences, list) and occurrences:
        candidate["entity_occurrences"] = _dict_rows(occurrences)


def _attach_record_maps(runtime: AnswerContextRuntime, candidate_uids: list[str]) -> None:
    """Apply record maps while retaining source diagnostics."""
    db = runtime.db
    event_map = (
        db.event_records_for_uids(candidate_uids) if db and hasattr(db, "event_records_for_uids") and candidate_uids else {}
    )
    occurrence_map = (
        db.entity_occurrences_for_uids(candidate_uids)
        if db and hasattr(db, "entity_occurrences_for_uids") and candidate_uids
        else {}
    )
    for candidate in [*runtime.candidates, *runtime.attachment_candidates]:
        _candidate_records(candidate, event_map, occurrence_map)


def _attach_thread_context(runtime: AnswerContextRuntime) -> None:
    """Apply thread context while retaining source diagnostics."""
    for candidate in [*runtime.candidates, *runtime.attachment_candidates]:
        full_email = runtime.full_map.get(str(candidate.get("uid") or ""))
        candidate.update(impl._thread_locator_for_candidate(candidate, full_email))
        thread_graph = impl._thread_graph_for_email(
            full_email,
            fallback_conversation_id=str(candidate.get("conversation_id") or ""),
        )
        if thread_graph:
            candidate["thread_graph"] = thread_graph
    runtime.conversation_groups, by_id = impl._conversation_group_summaries(
        runtime.db,
        candidates=runtime.candidates,
        attachment_candidates=runtime.attachment_candidates,
    )
    impl._attach_conversation_context([*runtime.candidates, *runtime.attachment_candidates], by_id)


def _enrich_body_candidate(runtime: AnswerContextRuntime, candidate: dict[str, Any]) -> None:
    """Add recipients, weak-message semantics, speaker attribution, and quoted blocks from the full email."""
    full_email = runtime.full_map.get(str(candidate.get("uid") or ""))
    candidate["recipients_summary"] = impl._recipients_summary(full_email)
    weak_message = weak_message_semantics(full_email or {})
    if weak_message:
        candidate["weak_message"] = weak_message
    context = candidate.get("conversation_context")
    speaker = impl._speaker_attribution_for_candidate(
        runtime.db,
        uid=str(candidate.get("uid") or ""),
        conversation_id=str(candidate.get("conversation_id") or ""),
        sender_email=str(candidate.get("sender_email") or ""),
        sender_name=str(candidate.get("sender_name") or ""),
        conversation_context=context if isinstance(context, dict) else None,
        full_email=full_email,
    )
    if speaker:
        candidate["speaker_attribution"] = speaker


def run_enrichment_stage(runtime: AnswerContextRuntime) -> None:
    """Attach persisted records, thread context, and quote attribution."""
    candidate_uids = [
        str(candidate.get("uid")) for candidate in [*runtime.candidates, *runtime.attachment_candidates] if candidate.get("uid")
    ]
    db = runtime.db
    runtime.full_map = db.get_emails_full_batch(candidate_uids) if db and hasattr(db, "get_emails_full_batch") else {}
    _attach_record_maps(runtime, candidate_uids)
    _attach_thread_context(runtime)
    for candidate in runtime.candidates:
        _enrich_body_candidate(runtime, candidate)


def run_analysis_stage(runtime: AnswerContextRuntime) -> None:
    """Build generic answer policy, timeline, and retrieval diagnostics."""
    rebuild_runtime_sections(
        runtime,
        conversation_group_summaries=impl._conversation_group_summaries,
        attach_conversation_context=impl._attach_conversation_context,
    )
    runtime.retrieval_diagnostics = impl._retrieval_diagnostics(
        runtime.retriever,
        candidate_count=len(runtime.candidates),
        attachment_candidate_count=len(runtime.attachment_candidates),
        lane_diagnostics=runtime.lane_diagnostics,
        retrieval_context=runtime.retrieval_context,
    )
