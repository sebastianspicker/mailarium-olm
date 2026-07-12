"""Retrieval, enrichment, and analysis stages for answer-context assembly."""

from __future__ import annotations

from typing import Any

from .._utils import _as_dict
from ..actor_resolution import resolve_actor_graph
from ..behavioral_evidence_chains import build_behavioral_evidence_chains
from ..behavioral_strength import apply_behavioral_strength
from ..case_intake import build_case_bundle
from ..communication_graph import build_communication_graph
from ..comparative_treatment import build_comparative_treatment
from ..cross_message_patterns import build_case_patterns
from ..formatting import weak_message_semantics
from ..investigation_report import build_investigation_report
from ..multi_source_case_bundle import build_multi_source_case_bundle
from ..power_context import apply_power_context_to_actor_graph, build_power_context
from ..trigger_retaliation import build_retaliation_analysis
from . import search_answer_context_impl as impl
from .search_answer_context_budget import _dedupe_evidence_items, _reindex_evidence
from .search_answer_context_case_payloads import _apply_actor_ids_to_candidates, _apply_actor_ids_to_case_bundle
from .search_answer_context_rendering import _resolve_exact_wording_requested
from .search_answer_context_runtime_candidate_rows import build_initial_candidate_rows
from .search_answer_context_runtime_lanes import _derive_query_lanes
from .search_answer_context_runtime_payload import rebuild_sections
from .search_answer_context_runtime_search import _search_across_query_lanes
from .search_answer_context_runtime_state import AnswerContextRuntime


def _dict_rows(items: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (items or []) if isinstance(item, dict)]


def _later_round_handles(runtime: AnswerContextRuntime) -> set[str]:
    return {
        str(item).strip() for item in runtime.retrieval_context.get("later_round_only_evidence_handles", []) if str(item).strip()
    }


def _load_search_results(runtime: AnswerContextRuntime) -> None:
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
        runtime.lane_diagnostics = _dict_rows(runtime.lane_diagnostics_override)
        runtime.retrieval_context = dict(runtime.retrieval_context_override or {})
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
        later_round_only_handles=_later_round_handles(runtime),
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


def _speaker_for_candidate(runtime: AnswerContextRuntime, candidate: dict[str, Any], full_email: Any) -> dict[str, Any] | None:
    context = candidate.get("conversation_context")
    return impl._speaker_attribution_for_candidate(
        runtime.db,
        uid=str(candidate.get("uid") or ""),
        conversation_id=str(candidate.get("conversation_id") or ""),
        sender_email=str(candidate.get("sender_email") or ""),
        sender_name=str(candidate.get("sender_name") or ""),
        conversation_context=context if isinstance(context, dict) else None,
        full_email=full_email,
    )


def _attach_candidate_analysis(
    runtime: AnswerContextRuntime,
    candidate: dict[str, Any],
    full_email: Any,
    speaker: dict[str, Any] | None,
) -> None:
    if runtime.params.case_scope is None:
        return
    candidate["language_rhetoric"] = impl._language_rhetoric_for_candidate(
        runtime.db,
        uid=str(candidate.get("uid") or ""),
        full_email=full_email,
        fallback_text=str(candidate.get("snippet") or ""),
        speaker_attribution=speaker,
    )
    candidate["message_findings"] = impl._message_findings_for_candidate(
        db=runtime.db,
        uid=str(candidate.get("uid") or ""),
        full_email=full_email,
        language_rhetoric=candidate["language_rhetoric"],
        case_scope=runtime.params.case_scope,
    )


def _enrich_body_candidate(runtime: AnswerContextRuntime, candidate: dict[str, Any]) -> None:
    full_email = runtime.full_map.get(str(candidate.get("uid") or ""))
    candidate["recipients_summary"] = impl._recipients_summary(full_email)
    weak_message = weak_message_semantics(full_email or {})
    if weak_message:
        candidate["weak_message"] = weak_message
    speaker = _speaker_for_candidate(runtime, candidate, full_email)
    if speaker:
        candidate["speaker_attribution"] = speaker
    _attach_candidate_analysis(runtime, candidate, full_email, speaker)


def run_enrichment_stage(runtime: AnswerContextRuntime) -> None:
    """Attach persisted records, thread context, and per-message analysis."""
    candidate_uids = [
        str(candidate.get("uid")) for candidate in [*runtime.candidates, *runtime.attachment_candidates] if candidate.get("uid")
    ]
    db = runtime.db
    runtime.full_map = db.get_emails_full_batch(candidate_uids) if db and hasattr(db, "get_emails_full_batch") else {}
    _attach_record_maps(runtime, candidate_uids)
    _attach_thread_context(runtime)
    for candidate in runtime.candidates:
        _enrich_body_candidate(runtime, candidate)
    if runtime.params.case_scope is not None:
        impl._apply_reply_pairings_to_candidates(
            candidates=runtime.candidates,
            full_map=_as_dict(runtime.full_map),
            case_scope=runtime.params.case_scope,
        )


def _build_case_surfaces(runtime: AnswerContextRuntime) -> None:
    runtime.case_bundle = build_case_bundle(runtime.params.case_scope) if runtime.params.case_scope is not None else None
    runtime.actor_graph = resolve_actor_graph(
        case_scope=runtime.params.case_scope,
        candidates=runtime.candidates,
        attachment_candidates=runtime.attachment_candidates,
        full_map=runtime.full_map,
    )
    runtime.power_context = build_power_context(runtime.params.case_scope, runtime.actor_graph)
    apply_power_context_to_actor_graph(runtime.actor_graph, runtime.power_context)
    if runtime.case_bundle is None:
        return
    _apply_actor_ids_to_case_bundle(runtime.case_bundle, runtime.actor_graph)
    _apply_actor_ids_to_candidates(runtime.candidates, runtime.actor_graph)
    _apply_actor_ids_to_candidates(runtime.attachment_candidates, runtime.actor_graph)
    scope = _as_dict(runtime.case_bundle.get("scope"))
    target_actor_id = str((_as_dict(scope.get("target_person"))).get("actor_id") or "")
    runtime.case_patterns = build_case_patterns(candidates=runtime.candidates, target_actor_id=target_actor_id)
    runtime.retaliation_analysis = build_retaliation_analysis(
        case_scope=runtime.params.case_scope,
        case_bundle=runtime.case_bundle,
        candidates=runtime.candidates,
    )
    runtime.comparative_treatment = build_comparative_treatment(
        case_bundle=runtime.case_bundle,
        candidates=runtime.candidates,
        full_map=_as_dict(runtime.full_map),
    )
    runtime.communication_graph = build_communication_graph(
        case_bundle=runtime.case_bundle,
        candidates=runtime.candidates,
        full_map=_as_dict(runtime.full_map),
    )
    runtime.multi_source_case_bundle = build_multi_source_case_bundle(
        case_bundle=runtime.case_bundle,
        candidates=runtime.candidates,
        attachment_candidates=runtime.attachment_candidates,
        full_map=_as_dict(runtime.full_map),
    )


def _build_evidence_surfaces(runtime: AnswerContextRuntime) -> None:
    if runtime.case_bundle is None:
        return
    runtime.finding_evidence_index, runtime.evidence_table = build_behavioral_evidence_chains(
        candidates=runtime.candidates,
        case_patterns=runtime.case_patterns,
        retaliation_analysis=runtime.retaliation_analysis,
        comparative_treatment=runtime.comparative_treatment,
        communication_graph=runtime.communication_graph,
    )
    (
        runtime.finding_evidence_index,
        runtime.evidence_table,
        runtime.behavioral_strength_rubric,
    ) = apply_behavioral_strength(runtime.finding_evidence_index, runtime.evidence_table)
    runtime.investigation_report = build_investigation_report(
        case_bundle=runtime.case_bundle,
        candidates=runtime.candidates,
        timeline=runtime.timeline,
        power_context=runtime.power_context,
        case_patterns=runtime.case_patterns,
        retaliation_analysis=runtime.retaliation_analysis,
        comparative_treatment=runtime.comparative_treatment,
        communication_graph=runtime.communication_graph,
        actor_identity_graph=runtime.actor_graph,
        finding_evidence_index=runtime.finding_evidence_index,
        evidence_table=runtime.evidence_table,
        multi_source_case_bundle=runtime.multi_source_case_bundle,
        output_language=str(getattr(runtime.params, "output_language", "en") or "en"),
        translation_mode=str(getattr(runtime.params, "translation_mode", "translation_aware") or "translation_aware"),
    )


def run_analysis_stage(runtime: AnswerContextRuntime) -> None:
    """Build answer policy and optional case-level evidence surfaces."""
    (
        runtime.conversation_groups,
        runtime.answer_quality,
        runtime.timeline,
        runtime.answer_policy,
        runtime.final_answer_contract,
    ) = rebuild_sections(
        db=runtime.db,
        candidates=runtime.candidates,
        attachment_candidates=runtime.attachment_candidates,
        params=runtime.params,
        conversation_group_summaries=impl._conversation_group_summaries,
        attach_conversation_context=impl._attach_conversation_context,
    )
    runtime.retrieval_diagnostics = impl._retrieval_diagnostics(
        runtime.retriever,
        candidate_count=len(runtime.candidates),
        attachment_candidate_count=len(runtime.attachment_candidates),
        lane_diagnostics=runtime.lane_diagnostics,
        harvest_context=runtime.retrieval_context,
    )
    _build_case_surfaces(runtime)
    _build_evidence_surfaces(runtime)
