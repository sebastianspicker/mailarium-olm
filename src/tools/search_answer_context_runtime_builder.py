# mypy: disable-error-code=name-defined
"""Split helpers for search answer-context runtime (search_answer_context_runtime_builder)."""

from __future__ import annotations

import re
from typing import Any

from ..actor_resolution import resolve_actor_graph
from ..behavioral_evidence_chains import build_behavioral_evidence_chains
from ..behavioral_strength import apply_behavioral_strength
from ..case_intake import build_case_bundle
from ..communication_graph import build_communication_graph
from ..comparative_treatment import build_comparative_treatment
from ..cross_message_patterns import build_case_patterns
from ..formatting import weak_message_semantics
from ..investigation_report import build_investigation_report
from ..mcp_models import EmailAnswerContextInput
from ..multi_source_case_bundle import build_multi_source_case_bundle
from ..power_context import apply_power_context_to_actor_graph, build_power_context
from ..trigger_retaliation import build_retaliation_analysis
from . import search_answer_context_impl as impl
from .search_answer_context_budget import (
    _compact_snippets_for_budget,
    _compact_timeline_events,
    _dedupe_evidence_items,
    _estimated_json_chars,
    _reindex_evidence,
    _strip_optional_evidence_fields,
    _summarize_conversation_groups_for_budget,
    _summarize_timeline_for_budget,
    _weakest_evidence_target,
)
from .search_answer_context_case_payloads import _apply_actor_ids_to_candidates, _apply_actor_ids_to_case_bundle
from .search_answer_context_rendering import (
    _answer_policy,
    _answer_quality,
    _final_answer_contract,
    _render_final_answer,
    _resolve_exact_wording_requested,
)
from .search_answer_context_runtime_candidate_rows import build_initial_candidate_rows
from .search_answer_context_runtime_payload import _compact_optional_case_surfaces, build_payload, rebuild_sections
from .utils import ToolDepsProto, json_response

# ruff: noqa: F401,F821


async def build_answer_context_payload(
    deps: ToolDepsProto,
    params: EmailAnswerContextInput,
    *,
    preloaded_results: list[Any] | None = None,
    preloaded_evidence_rows: list[dict[str, Any]] | None = None,
    lane_diagnostics_override: list[dict[str, Any]] | None = None,
    retrieval_context_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the structured answer-context payload before outward JSON rendering."""

    def _run() -> dict[str, Any]:
        from ..config import get_settings

        settings = get_settings()
        r = deps.get_retriever()
        db = deps.get_email_db()
        effective_top_k = min(params.max_results, settings.mcp_max_search_results)
        search_kwargs = impl._answer_context_search_kwargs(params, effective_top_k)
        query_lanes = _derive_query_lanes(retriever=r, params=params, search_kwargs=search_kwargs)
        exact_wording = _resolve_exact_wording_requested(
            question=params.question,
            explicit=(
                bool(search_kwargs.get("_exact_wording_requested"))
                if search_kwargs.get("_exact_wording_requested") is not None
                else getattr(params, "exact_wording_requested", None)
            ),
        )
        preloaded_rows = [dict(item) for item in (preloaded_evidence_rows or []) if isinstance(item, dict)]
        if preloaded_results is None and not preloaded_rows:
            results, lane_diagnostics, retrieval_context = _search_across_query_lanes(
                retriever=r,
                search_kwargs=search_kwargs,
                query_lanes=query_lanes,
                top_k=effective_top_k,
                scan_id=params.scan_id,
            )
        else:
            results = list(preloaded_results)[:effective_top_k] if isinstance(preloaded_results, list) else []
            lane_diagnostics = [dict(item) for item in (lane_diagnostics_override or []) if isinstance(item, dict)]
            retrieval_context = dict(retrieval_context_override or {})
        retrieval_context.setdefault("original_query", str(search_kwargs.get("query") or ""))
        if lane_diagnostics:
            retrieval_context.setdefault(
                "executed_query",
                str((lane_diagnostics[0] if isinstance(lane_diagnostics[0], dict) else {}).get("executed_query") or ""),
            )
        later_round_only_handles = {
            str(item).strip() for item in retrieval_context.get("later_round_only_evidence_handles", []) if str(item).strip()
        }
        candidates, attachment_candidates = build_initial_candidate_rows(
            preloaded_rows=preloaded_rows,
            results=results,
            db=db,
            params=params,
            exact_wording=exact_wording,
            later_round_only_handles=later_round_only_handles,
        )

        candidates, deduped_body = _dedupe_evidence_items(candidates)
        attachment_candidates, deduped_attachments = _dedupe_evidence_items(attachment_candidates)
        _reindex_evidence(candidates)
        _reindex_evidence(attachment_candidates)

        candidate_uids = [
            str(candidate.get("uid") or "") for candidate in [*candidates, *attachment_candidates] if candidate.get("uid")
        ]
        full_map = db.get_emails_full_batch(candidate_uids) if db and hasattr(db, "get_emails_full_batch") else {}
        event_map = (
            db.event_records_for_uids(candidate_uids) if db and hasattr(db, "event_records_for_uids") and candidate_uids else {}
        )
        occurrence_map = (
            db.entity_occurrences_for_uids(candidate_uids)
            if db and hasattr(db, "entity_occurrences_for_uids") and candidate_uids
            else {}
        )
        for candidate in [*candidates, *attachment_candidates]:
            uid = str(candidate.get("uid") or "")
            if not uid:
                continue
            events = event_map.get(uid) if isinstance(event_map, dict) else None
            if isinstance(events, list) and events:
                candidate["event_records"] = [dict(item) for item in events if isinstance(item, dict)]
            occurrences = occurrence_map.get(uid) if isinstance(occurrence_map, dict) else None
            if isinstance(occurrences, list) and occurrences:
                candidate["entity_occurrences"] = [dict(item) for item in occurrences if isinstance(item, dict)]
        for candidate in [*candidates, *attachment_candidates]:
            full_email = full_map.get(str(candidate.get("uid") or "")) if isinstance(full_map, dict) else None
            candidate.update(impl._thread_locator_for_candidate(candidate, full_email))
            thread_graph = impl._thread_graph_for_email(
                full_email,
                fallback_conversation_id=str(candidate.get("conversation_id") or ""),
            )
            if thread_graph:
                candidate["thread_graph"] = thread_graph
        conversation_groups, conversation_group_by_id = impl._conversation_group_summaries(
            db,
            candidates=candidates,
            attachment_candidates=attachment_candidates,
        )
        impl._attach_conversation_context([*candidates, *attachment_candidates], conversation_group_by_id)
        for candidate in candidates:
            full_email = full_map.get(str(candidate.get("uid") or "")) if isinstance(full_map, dict) else None
            candidate["recipients_summary"] = impl._recipients_summary(full_email)
            weak_message = weak_message_semantics(full_email or {})
            if weak_message:
                candidate["weak_message"] = weak_message
            speaker_attribution = impl._speaker_attribution_for_candidate(
                db,
                uid=str(candidate.get("uid") or ""),
                conversation_id=str(candidate.get("conversation_id") or ""),
                sender_email=str(candidate.get("sender_email") or ""),
                sender_name=str(candidate.get("sender_name") or ""),
                conversation_context=(
                    candidate.get("conversation_context") if isinstance(candidate.get("conversation_context"), dict) else None
                ),
                full_email=full_email,
            )
            if speaker_attribution:
                candidate["speaker_attribution"] = speaker_attribution
            if params.case_scope is not None:
                candidate["language_rhetoric"] = impl._language_rhetoric_for_candidate(
                    db,
                    uid=str(candidate.get("uid") or ""),
                    full_email=full_email,
                    fallback_text=str(candidate.get("snippet") or ""),
                    speaker_attribution=speaker_attribution,
                )
                candidate["message_findings"] = impl._message_findings_for_candidate(
                    db=db,
                    uid=str(candidate.get("uid") or ""),
                    full_email=full_email,
                    language_rhetoric=candidate["language_rhetoric"],
                    case_scope=params.case_scope,
                )
        if params.case_scope is not None:
            impl._apply_reply_pairings_to_candidates(
                candidates=candidates,
                full_map=full_map if isinstance(full_map, dict) else {},
                case_scope=params.case_scope,
            )

        conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = rebuild_sections(
            db=db,
            candidates=candidates,
            attachment_candidates=attachment_candidates,
            params=params,
            conversation_group_summaries=impl._conversation_group_summaries,
            attach_conversation_context=impl._attach_conversation_context,
        )
        retrieval_diagnostics = impl._retrieval_diagnostics(
            r,
            candidate_count=len(candidates),
            attachment_candidate_count=len(attachment_candidates),
            lane_diagnostics=lane_diagnostics,
            harvest_context=retrieval_context,
        )
        case_bundle = build_case_bundle(params.case_scope) if params.case_scope is not None else None
        actor_graph = resolve_actor_graph(
            case_scope=params.case_scope,
            candidates=candidates,
            attachment_candidates=attachment_candidates,
            full_map=full_map,
        )
        power_context = build_power_context(params.case_scope, actor_graph)
        apply_power_context_to_actor_graph(actor_graph, power_context)
        if case_bundle is not None:
            _apply_actor_ids_to_case_bundle(case_bundle, actor_graph)
        _apply_actor_ids_to_candidates(candidates, actor_graph)
        _apply_actor_ids_to_candidates(attachment_candidates, actor_graph)
        target_actor_id = ""
        if case_bundle is not None and isinstance(case_bundle.get("scope"), dict):
            target_actor_id = str(
                ((case_bundle["scope"].get("target_person") or {}) if isinstance(case_bundle["scope"], dict) else {}).get(
                    "actor_id"
                )
                or ""
            )
        case_patterns = (
            build_case_patterns(candidates=candidates, target_actor_id=target_actor_id) if case_bundle is not None else None
        )
        retaliation_analysis = (
            build_retaliation_analysis(case_scope=params.case_scope, case_bundle=case_bundle, candidates=candidates)
            if case_bundle is not None
            else None
        )
        comparative_treatment = (
            build_comparative_treatment(
                case_bundle=case_bundle,
                candidates=candidates,
                full_map=full_map if isinstance(full_map, dict) else {},
            )
            if case_bundle is not None
            else None
        )
        communication_graph = (
            build_communication_graph(
                case_bundle=case_bundle,
                candidates=candidates,
                full_map=full_map if isinstance(full_map, dict) else {},
            )
            if case_bundle is not None
            else None
        )
        multi_source_case_bundle = (
            build_multi_source_case_bundle(
                case_bundle=case_bundle,
                candidates=candidates,
                attachment_candidates=attachment_candidates,
                full_map=full_map if isinstance(full_map, dict) else {},
            )
            if case_bundle is not None
            else None
        )
        finding_evidence_index, evidence_table = (
            build_behavioral_evidence_chains(
                candidates=candidates,
                case_patterns=case_patterns,
                retaliation_analysis=retaliation_analysis,
                comparative_treatment=comparative_treatment,
                communication_graph=communication_graph,
            )
            if case_bundle is not None
            else ({}, {})
        )
        if case_bundle is not None:
            finding_evidence_index, evidence_table, behavioral_strength_rubric = apply_behavioral_strength(
                finding_evidence_index,
                evidence_table,
            )
        else:
            behavioral_strength_rubric = {}
        investigation_report = (
            build_investigation_report(
                case_bundle=case_bundle,
                candidates=candidates,
                timeline=timeline,
                power_context=power_context,
                case_patterns=case_patterns,
                retaliation_analysis=retaliation_analysis,
                comparative_treatment=comparative_treatment,
                communication_graph=communication_graph,
                actor_identity_graph=actor_graph,
                finding_evidence_index=finding_evidence_index,
                evidence_table=evidence_table,
                multi_source_case_bundle=multi_source_case_bundle,
                output_language=str(getattr(params, "output_language", "en") or "en"),
                translation_mode=str(getattr(params, "translation_mode", "translation_aware") or "translation_aware"),
            )
            if case_bundle is not None
            else None
        )
        deduplicated = {
            "body_candidates": deduped_body,
            "attachment_candidates": deduped_attachments,
        }
        compact_policy_contract = False
        compact_search = False
        compact_report_only = False
        compact_case_evidence = False
        truncated = {
            "body_candidates": 0,
            "attachment_candidates": 0,
            "conversation_groups": 0,
            "timeline_events": 0,
            "snippet_compactions": 0,
            "field_compactions": 0,
        }
        packing: dict[str, Any] = {
            "applied": False,
            "budget_chars": settings.mcp_max_json_response_chars,
            "estimated_chars_before": 0,
            "estimated_chars_after": 0,
            "deduplicated": deduplicated,
            "truncated": truncated,
        }

        def _render_payload() -> dict[str, Any]:
            return build_payload(
                params=params,
                effective_top_k=effective_top_k,
                settings=settings,
                retrieval_diagnostics=retrieval_diagnostics,
                candidates=candidates,
                attachment_candidates=attachment_candidates,
                groups=conversation_groups,
                answer_quality=answer_quality,
                timeline=timeline,
                answer_policy=answer_policy,
                final_answer_contract=final_answer_contract,
                final_answer=_render_final_answer(
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    answer_policy=answer_policy,
                    final_answer_contract=final_answer_contract,
                ),
                case_bundle=case_bundle,
                actor_graph=actor_graph,
                power_context=power_context,
                case_patterns=case_patterns,
                retaliation_analysis=retaliation_analysis,
                comparative_treatment=comparative_treatment,
                communication_graph=communication_graph,
                multi_source_case_bundle=multi_source_case_bundle,
                finding_evidence_index=finding_evidence_index,
                evidence_table=evidence_table,
                behavioral_strength_rubric=behavioral_strength_rubric,
                investigation_report=investigation_report,
                compact_policy_contract=compact_policy_contract,
                compact_search=compact_search,
                compact_report_only=compact_report_only,
                compact_case_evidence=compact_case_evidence,
                packing=packing,
            )

        def _cited_candidate_uids() -> list[str]:
            return [str(uid) for uid in answer_policy.get("cite_candidate_uids", []) if uid]

        initial_payload = _render_payload()
        packing["estimated_chars_before"] = _estimated_json_chars(initial_payload)
        packing["applied"] = bool(
            deduped_body or deduped_attachments or packing["estimated_chars_before"] > settings.mcp_max_json_response_chars > 0
        )

        budget = settings.mcp_max_json_response_chars
        if budget > 0:
            if len(conversation_groups) > 3 and _estimated_json_chars(_render_payload()) > budget:
                truncated["conversation_groups"] = len(conversation_groups) - 3
                conversation_groups = conversation_groups[:3]
                answer_quality = _answer_quality(
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    conversation_groups=conversation_groups,
                )
                answer_policy = _answer_policy(
                    question=params.question,
                    evidence_mode=params.evidence_mode,
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    answer_quality=answer_quality,
                    exact_wording_requested=getattr(params, "exact_wording_requested", None),
                )
                final_answer_contract = _final_answer_contract(answer_policy=answer_policy)
                packing["applied"] = True
            compacted_timeline, dropped_events = _compact_timeline_events(timeline)
            if dropped_events > 0 and _estimated_json_chars(_render_payload()) > budget:
                timeline = compacted_timeline
                truncated["timeline_events"] = dropped_events
                packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget:
                truncated["snippet_compactions"] += _compact_snippets_for_budget(
                    candidates,
                    attachment_candidates,
                    cited_candidate_uids=_cited_candidate_uids(),
                    phase="primary",
                )
                if truncated["snippet_compactions"] > 0:
                    conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = rebuild_sections(
                        db=db,
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        params=params,
                        conversation_group_summaries=impl._conversation_group_summaries,
                        attach_conversation_context=impl._attach_conversation_context,
                    )
                    compacted_timeline, dropped_events = _compact_timeline_events(timeline)
                    if dropped_events > truncated["timeline_events"]:
                        truncated["timeline_events"] = dropped_events
                        timeline = compacted_timeline
                    packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget and not compact_report_only and case_bundle is not None:
                compact_report_only = True
                packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget and not compact_case_evidence and case_bundle is not None:
                compact_case_evidence = True
                packing["applied"] = True
            while _estimated_json_chars(_render_payload()) > budget and (len(candidates) + len(attachment_candidates)) > 1:
                weakest_target = _weakest_evidence_target(
                    candidates,
                    attachment_candidates,
                    cited_candidate_uids=_cited_candidate_uids(),
                )
                if weakest_target is None:
                    break
                kind, index = weakest_target
                if kind == "attachment":
                    attachment_candidates.pop(index)
                    truncated["attachment_candidates"] += 1
                else:
                    candidates.pop(index)
                    truncated["body_candidates"] += 1
                _reindex_evidence(candidates)
                _reindex_evidence(attachment_candidates)
                conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = rebuild_sections(
                    db=db,
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    params=params,
                    conversation_group_summaries=impl._conversation_group_summaries,
                    attach_conversation_context=impl._attach_conversation_context,
                )
                compacted_timeline, dropped_events = _compact_timeline_events(timeline)
                if dropped_events > truncated["timeline_events"]:
                    truncated["timeline_events"] = dropped_events
                    timeline = compacted_timeline
                packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget:
                field_compactions = _strip_optional_evidence_fields(
                    candidates,
                    attachment_candidates,
                    force_deep_candidate_analysis_strip=(truncated["body_candidates"] + truncated["attachment_candidates"]) > 0,
                )
                if field_compactions > 0:
                    truncated["field_compactions"] = field_compactions
                    conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = rebuild_sections(
                        db=db,
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        params=params,
                        conversation_group_summaries=impl._conversation_group_summaries,
                        attach_conversation_context=impl._attach_conversation_context,
                    )
                    if conversation_groups:
                        summarized_groups, dropped_groups = _summarize_conversation_groups_for_budget(conversation_groups)
                        truncated["conversation_groups"] = max(truncated["conversation_groups"], dropped_groups)
                        conversation_groups = summarized_groups
                    if timeline.get("events"):
                        summarized_timeline, dropped_events = _summarize_timeline_for_budget(timeline)
                        truncated["timeline_events"] = max(truncated["timeline_events"], dropped_events)
                        timeline = summarized_timeline
                    answer_quality = _answer_quality(
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        conversation_groups=conversation_groups,
                    )
                    answer_policy = _answer_policy(
                        question=params.question,
                        evidence_mode=params.evidence_mode,
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        answer_quality=answer_quality,
                        exact_wording_requested=getattr(params, "exact_wording_requested", None),
                    )
                    final_answer_contract = _final_answer_contract(answer_policy=answer_policy)
                    packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget:
                extra_compactions = _compact_snippets_for_budget(
                    candidates,
                    attachment_candidates,
                    cited_candidate_uids=_cited_candidate_uids(),
                    phase="secondary",
                )
                if extra_compactions > 0:
                    truncated["snippet_compactions"] += extra_compactions
                    conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = rebuild_sections(
                        db=db,
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        params=params,
                        conversation_group_summaries=impl._conversation_group_summaries,
                        attach_conversation_context=impl._attach_conversation_context,
                    )
                    if conversation_groups:
                        summarized_groups, dropped_groups = _summarize_conversation_groups_for_budget(conversation_groups)
                        truncated["conversation_groups"] = max(truncated["conversation_groups"], dropped_groups)
                        conversation_groups = summarized_groups
                    if timeline.get("events"):
                        summarized_timeline, dropped_events = _summarize_timeline_for_budget(timeline)
                        truncated["timeline_events"] = max(truncated["timeline_events"], dropped_events)
                        timeline = summarized_timeline
                    answer_quality = _answer_quality(
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        conversation_groups=conversation_groups,
                    )
                    answer_policy = _answer_policy(
                        question=params.question,
                        evidence_mode=params.evidence_mode,
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        answer_quality=answer_quality,
                        exact_wording_requested=getattr(params, "exact_wording_requested", None),
                    )
                    final_answer_contract = _final_answer_contract(answer_policy=answer_policy)
                    packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget and not compact_policy_contract:
                compact_policy_contract = True
                truncated["field_compactions"] += 2
                packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget and not compact_search:
                compact_search = True
                truncated["field_compactions"] += 1
                packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget and not compact_report_only and case_bundle is not None:
                compact_report_only = True
                truncated["field_compactions"] += 1
                packing["applied"] = True
            if _estimated_json_chars(_render_payload()) > budget and not compact_case_evidence and case_bundle is not None:
                compact_case_evidence = True
                truncated["field_compactions"] += 2
                packing["applied"] = True

        final_payload = _render_payload()

        if budget > 0 and _estimated_json_chars(final_payload) > budget and case_bundle is not None:
            removed_surfaces = _compact_optional_case_surfaces(final_payload, budget=budget)
            if removed_surfaces > 0:
                truncated["field_compactions"] += removed_surfaces
                packing["applied"] = True
        if budget > 0 and _estimated_json_chars(final_payload) > budget:
            final_payload["candidates"] = [
                _trim_candidate_for_budget(item) for item in list(final_payload.get("candidates") or [])
            ]
            final_payload["attachment_candidates"] = [
                _trim_candidate_for_budget(item) for item in list(final_payload.get("attachment_candidates") or [])
            ]
            answer_quality_payload = final_payload.get("answer_quality")
            if isinstance(answer_quality_payload, dict):
                final_payload["answer_quality"] = {
                    "confidence_label": answer_quality_payload.get("confidence_label"),
                    "confidence_score": answer_quality_payload.get("confidence_score"),
                    "top_candidate_uid": answer_quality_payload.get("top_candidate_uid"),
                }
            timeline_payload = final_payload.get("timeline")
            if isinstance(timeline_payload, dict):
                final_payload["timeline"] = {
                    "event_count": timeline_payload.get("event_count"),
                    "date_range": timeline_payload.get("date_range"),
                    "first_uid": timeline_payload.get("first_uid"),
                    "last_uid": timeline_payload.get("last_uid"),
                    "key_transition_uid": timeline_payload.get("key_transition_uid"),
                }
            group_payload = final_payload.get("conversation_groups")
            if isinstance(group_payload, list):
                final_payload["conversation_groups"] = [
                    {
                        "thread_group_id": group.get("thread_group_id"),
                        "thread_group_source": group.get("thread_group_source"),
                        "top_uid": group.get("top_uid"),
                        "message_count": group.get("message_count"),
                    }
                    for group in group_payload[:1]
                    if isinstance(group, dict)
                ]
            truncated["field_compactions"] += 4
            packing["applied"] = True
        if budget > 0 and _estimated_json_chars(final_payload) > budget:
            final_payload.pop("answer_quality", None)
            final_payload.pop("conversation_groups", None)
            timeline_payload = final_payload.get("timeline")
            if isinstance(timeline_payload, dict):
                final_payload["timeline"] = {
                    "event_count": timeline_payload.get("event_count"),
                    "date_range": timeline_payload.get("date_range"),
                    "first_uid": timeline_payload.get("first_uid"),
                    "last_uid": timeline_payload.get("last_uid"),
                }
            truncated["field_compactions"] += 2
            packing["applied"] = True
        if budget > 0 and _estimated_json_chars(final_payload) > budget:
            for item in list(final_payload.get("candidates") or []):
                if isinstance(item, dict):
                    item["snippet"] = _trim_snippet_for_budget(item.get("snippet"), max_chars=48)
            for item in list(final_payload.get("attachment_candidates") or []):
                if isinstance(item, dict):
                    item["snippet"] = _trim_snippet_for_budget(item.get("snippet"), max_chars=48)
            answer_policy_payload = final_payload.get("answer_policy")
            if isinstance(answer_policy_payload, dict):
                final_payload["answer_policy"] = {
                    "decision": answer_policy_payload.get("decision"),
                    "verification_mode": answer_policy_payload.get("verification_mode"),
                    "max_citations": answer_policy_payload.get("max_citations"),
                }
            contract_payload = final_payload.get("final_answer_contract")
            if isinstance(contract_payload, dict):
                citation_format = contract_payload.get("citation_format")
                citation_style = ""
                if isinstance(citation_format, dict):
                    citation_style = str(citation_format.get("style") or "")
                final_payload["final_answer_contract"] = {
                    "decision": contract_payload.get("decision"),
                    "citation_style": citation_style or contract_payload.get("citation_style"),
                    "required_citation_handles": contract_payload.get("required_citation_handles"),
                    "verification_mode": contract_payload.get("verification_mode"),
                }
            search_payload = final_payload.get("search")
            if isinstance(search_payload, dict):
                retrieval_payload = search_payload.get("retrieval_diagnostics")
                final_payload["search"] = {
                    "top_k": search_payload.get("top_k"),
                    "hybrid": search_payload.get("hybrid"),
                    "expand_query": search_payload.get("expand_query"),
                    "retrieval_diagnostics": retrieval_payload if isinstance(retrieval_payload, dict) else {},
                }
            truncated["field_compactions"] += 3
            packing["applied"] = True
        if budget > 0 and _estimated_json_chars(final_payload) > budget:
            final_payload.pop("timeline", None)
            final_payload["search"] = {"top_k": (final_payload.get("search") or {}).get("top_k")}
            truncated["field_compactions"] += 2
            packing["applied"] = True
        packing["estimated_chars_after"] = _estimated_json_chars(final_payload)
        final_payload["_packed"] = packing
        return final_payload

    if hasattr(deps, "offload"):
        return await deps.offload(_run)
    return _run()


async def build_answer_context(deps: ToolDepsProto, params: EmailAnswerContextInput) -> str:
    """Build the answer-context payload for ``email_answer_context``."""
    return json_response(await build_answer_context_payload(deps, params))


__all__ = [
    "build_answer_context",
    "build_answer_context_payload",
]
