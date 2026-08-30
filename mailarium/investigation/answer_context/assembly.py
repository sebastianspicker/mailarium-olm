"""Evidence analysis, payload assembly, and budget packing workflow stages."""

from __future__ import annotations

from typing import Any

from mailarium.investigation.answer_context.rendering import (
    _answer_policy,
    _answer_quality,
    _citation_reference_payloads,
    _final_answer_contract,
    _render_final_answer,
    _timeline_summary,
)
from mailarium.model.data_shapes import as_dict, as_list

from ..formatting import weak_message_semantics
from .budgeting import (
    _compact_snippets_for_budget,
    _compact_timeline_events,
    _dedupe_evidence_items,
    _estimated_json_chars,
    _reindex_evidence,
    _strip_optional_evidence_fields,
    _summarize_conversation_groups_for_budget,
    _summarize_timeline_for_budget,
    _trim_candidate_for_budget,
    _trim_snippet_for_budget,
    _weakest_evidence_target,
)
from .candidates import (
    _attach_conversation_context,
    _conversation_group_summaries,
    _recipients_summary,
    _speaker_attribution_for_candidate,
    _thread_graph_for_email,
    _thread_locator_for_candidate,
    build_initial_candidate_rows,
)
from .contracts import AnswerContextRequest
from .models import AnswerContextPayloadState, AnswerContextRuntime
from .ranking import _derive_query_lanes, _search_across_query_lanes
from .rendering import _resolve_exact_wording_requested

"""Payload-shaping helpers for answer-context evidence output."""


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _strings(values: Any, limit: int | None = None) -> list[str]:
    items = as_list(values)
    if limit is not None:
        items = items[:limit]
    return [str(item) for item in items if str(item).strip()]


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


def _lane_diagnostic(item: dict[str, Any]) -> dict[str, Any]:
    """Project internal lane execution data onto the stable public diagnostics schema."""
    return {
        "lane_id": _text(item.get("lane_id")),
        "query": _text(item.get("query")),
        "executed_query": _text(item.get("executed_query")),
        "result_count": int(item.get("result_count") or 0),
        "used_query_expansion": bool(item.get("used_query_expansion")),
        "scan_id": _text(item.get("scan_id")),
        "excluded_count": int(item.get("excluded_count") or 0),
        "search_top_k": int(item.get("search_top_k") or 0),
        "new_key_count": int(item.get("new_key_count") or 0),
        "expansion_terms": _strings(item.get("expansion_terms")),
        "recovered_expansion_terms": _strings(item.get("recovered_expansion_terms")),
        "recovered_expansion_key_count": int(item.get("recovered_expansion_key_count") or 0),
    }


def _attach_query_diagnostics(payload: dict[str, Any], context: dict[str, Any], debug: dict[str, Any]) -> None:
    """Apply query diagnostics while retaining source diagnostics."""
    original = _text(context.get("original_query") or debug.get("original_query")).strip()
    executed = _text(context.get("executed_query") or debug.get("executed_query")).strip()
    suffix = _text(debug.get("query_expansion_suffix")).strip()
    if original:
        payload["original_query"] = original
    if executed:
        payload["executed_query"] = executed
    if executed and executed != original:
        payload["query_changed"] = True
    if suffix:
        payload["query_expansion_suffix"] = suffix


def _retrieval_diagnostics(
    retriever: Any,
    *,
    candidate_count: int,
    attachment_candidate_count: int,
    lane_diagnostics: list[dict[str, Any]] | None = None,
    retrieval_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return visible retrieval diagnostics for answer-context callers."""
    debug = as_dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)))
    policy = as_dict(debug.get("retrieval_policy"))
    fusion = as_dict(debug.get("fusion"))
    payload: dict[str, Any] = {
        "used_query_expansion": bool(debug.get("used_query_expansion")),
        "expand_query_requested": bool(debug.get("expand_query_requested")),
        "use_hybrid": bool(debug.get("use_hybrid")),
        "use_rerank": bool(debug.get("use_rerank")),
        "fetch_size": int(debug.get("fetch_size") or 0),
        "result_mix": {
            "body_candidates": candidate_count,
            "attachment_candidates": attachment_candidate_count,
            "total_candidates": candidate_count + attachment_candidate_count,
        },
    }
    if policy:
        payload["retrieval_policy"] = policy
    if fusion:
        payload["fusion"] = fusion
    context = as_dict(retrieval_context)
    _attach_query_diagnostics(payload, context, debug)
    if lane_diagnostics:
        payload["query_lane_count"] = len(lane_diagnostics)
        payload["query_lanes"] = [_lane_diagnostic(item) for item in lane_diagnostics if isinstance(item, dict)]
    return payload


def _copy_if_truthy(source: dict[str, Any], target: dict[str, Any], keys: tuple[str, ...]) -> None:
    """Copy selected diagnostic fields only when their values carry useful information."""
    for key in keys:
        if source.get(key):
            target[key] = source[key]


def _public_retrieval_diagnostics(retrieval_diagnostics: dict[str, Any], *, compact_search: bool) -> dict[str, Any]:
    """Return a budget-safe retrieval diagnostics payload for answer-context output."""
    payload: dict[str, Any] = {
        "used_query_expansion": bool(retrieval_diagnostics.get("used_query_expansion")),
        "use_hybrid": bool(retrieval_diagnostics.get("use_hybrid")),
    }
    policy = as_dict(retrieval_diagnostics.get("retrieval_policy"))
    if policy:
        payload["retrieval_policy"] = policy
    fusion = as_dict(retrieval_diagnostics.get("fusion"))
    if fusion and not compact_search:
        payload["fusion"] = fusion
    keys = ("query_lane_count", "query_lanes", "original_query", "executed_query", "query_expansion_suffix")
    _copy_if_truthy(retrieval_diagnostics, payload, keys)
    if not compact_search:
        _copy_if_truthy(retrieval_diagnostics, payload, ("expand_query_requested", "use_rerank", "fetch_size", "query_changed"))
    failure = _text(retrieval_diagnostics.get("suspected_failure_mode"))
    if failure:
        payload["suspected_failure_mode"] = failure
        if not compact_search:
            payload["review_note"] = _text(retrieval_diagnostics.get("review_note"))
    return payload


"""Payload-building helpers for generic answer-context assembly."""


def rebuild_sections(
    *,
    db: Any,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    params: Any,
    conversation_group_summaries: Any,
    attach_conversation_context: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Recompute group, quality, timeline, and answer-policy sections."""
    groups, by_id = conversation_group_summaries(
        db,
        candidates=candidates,
        attachment_candidates=attachment_candidates,
    )
    attach_conversation_context([*candidates, *attachment_candidates], by_id)
    answer_quality = _answer_quality(
        candidates=candidates,
        attachment_candidates=attachment_candidates,
        conversation_groups=groups,
    )
    answer_policy = _answer_policy(
        question=params.question,
        evidence_mode=params.evidence_mode,
        candidates=candidates,
        attachment_candidates=attachment_candidates,
        answer_quality=answer_quality,
        exact_wording_requested=getattr(params, "exact_wording_requested", None),
    )
    return (
        groups,
        answer_quality,
        _timeline_summary(candidates=candidates, attachment_candidates=attachment_candidates),
        answer_policy,
        _final_answer_contract(answer_policy=answer_policy),
    )


def rebuild_runtime_sections(
    runtime: Any,
    *,
    conversation_group_summaries: Any,
    attach_conversation_context: Any,
) -> None:
    """Recompute and assign every derived analysis section on one runtime."""
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
        conversation_group_summaries=conversation_group_summaries,
        attach_conversation_context=attach_conversation_context,
    )


def _public_item(item: dict[str, Any], state: AnswerContextPayloadState) -> dict[str, Any]:
    """Remove internal thread fields and compact provenance further when response packing was applied."""
    public = dict(item)
    for key in ("thread_group_id", "thread_group_source", "inferred_thread_id"):
        public.pop(key, None)
    if bool(state.runtime.packing.get("applied")):
        public.pop("conversation_context", None)
        public.pop("match_reason", None)
        provenance = public.get("provenance")
        if isinstance(provenance, dict):
            public["provenance"] = {
                "evidence_handle": provenance.get("evidence_handle"),
                "visible_excerpt_start": provenance.get("visible_excerpt_start"),
                "visible_excerpt_end": provenance.get("visible_excerpt_end"),
                "visible_excerpt_compacted": provenance.get("visible_excerpt_compacted"),
            }
    return public


def _nonempty_strings(values: Any) -> list[str]:
    """Normalize iterable values to strings while discarding empty entries."""
    return [str(item) for item in list(values or []) if item]


def _compact_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Compact policy to keep bounded tool responses useful."""
    return {
        "decision": _text(policy.get("decision")),
        "verification_mode": _text(policy.get("verification_mode")),
        "max_citations": int(policy.get("max_citations") or 0),
        "cite_candidate_uids": _nonempty_strings(policy.get("cite_candidate_uids")),
        "cite_candidate_references": _citation_reference_payloads(policy.get("cite_candidate_references")),
        "refuse_to_overclaim": bool(policy.get("refuse_to_overclaim", True)),
    }


def _compact_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Compact contract to keep bounded tool responses useful."""
    return {
        "decision": _text(contract.get("decision")),
        "answer_shape": _text((contract.get("answer_format") or {}).get("shape")),
        "citation_style": _text((contract.get("citation_format") or {}).get("style")),
        "required_citation_uids": _nonempty_strings(contract.get("required_citation_uids")),
        "required_citation_handles": _nonempty_strings(contract.get("required_citation_handles")),
        "verification_mode": _text(contract.get("verification_mode")),
        "refuse_to_overclaim": bool(contract.get("refuse_to_overclaim", True)),
    }


def _policy_payloads(state: AnswerContextPayloadState) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return full policy contracts unless response budgeting explicitly requires compact forms."""
    runtime = state.runtime
    if not runtime.compact_policy_contract:
        return runtime.answer_policy, runtime.final_answer_contract
    return _compact_policy(runtime.answer_policy), _compact_contract(runtime.final_answer_contract)


def _search_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    """Expose effective search settings and public retrieval diagnostics, including scope when present."""
    runtime = state.runtime
    params = runtime.params
    diagnostics = runtime.retrieval_diagnostics
    payload: dict[str, Any] = {
        "top_k": runtime.effective_top_k,
        "date_from": params.date_from,
        "date_to": params.date_to,
        "hybrid": bool(diagnostics.get("use_hybrid", params.hybrid)),
        "expand_query": bool(diagnostics.get("expand_query_requested", False)),
        "retrieval_diagnostics": _public_retrieval_diagnostics(
            diagnostics,
            compact_search=runtime.compact_search,
        ),
    }
    if params.scope is not None:
        payload["scope"] = params.scope
    if not runtime.compact_search:
        payload.update(
            sender=params.sender,
            subject=params.subject,
            folder=params.folder,
            has_attachments=params.has_attachments,
            email_type=params.email_type,
            rerank=params.rerank,
        )
    return payload


def _base_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    """Assemble counts, public candidates, conversation groups, timeline, policy, and answer contract."""
    runtime = state.runtime
    policy, contract = _policy_payloads(state)
    total = len(runtime.candidates) + len(runtime.attachment_candidates)
    return {
        "question": runtime.params.question,
        "count": total,
        "counts": {
            "body": len(runtime.candidates),
            "attachments": len(runtime.attachment_candidates),
            "total": total,
        },
        "candidates": [_public_item(item, state) for item in runtime.candidates],
        "attachment_candidates": [_public_item(item, state) for item in runtime.attachment_candidates],
        "conversation_groups": runtime.conversation_groups,
        "answer_quality": runtime.answer_quality,
        "timeline": runtime.timeline,
        "answer_policy": policy,
        "final_answer_contract": contract,
        "final_answer": _render_final_answer(
            candidates=runtime.candidates,
            attachment_candidates=runtime.attachment_candidates,
            answer_policy=runtime.answer_policy,
            final_answer_contract=runtime.final_answer_contract,
        ),
        "evidence_mode": {"requested": runtime.params.evidence_mode},
        "search": _search_payload(state),
    }


def _final_budget_fields(payload: dict[str, Any], state: AnswerContextPayloadState) -> None:
    """Render budget fields in the response format consumed by callers."""
    runtime = state.runtime
    if not runtime.candidates and not runtime.attachment_candidates:
        payload["message"] = "No candidate evidence found for the question."
    if runtime.effective_top_k < runtime.params.max_results:
        payload["_capped"] = {
            "requested": runtime.params.max_results,
            "effective": runtime.effective_top_k,
            "profile": runtime.settings.mcp_model_profile,
        }
    payload["_packed"] = runtime.packing


def build_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    """Build one public answer-context payload from typed runtime state."""
    payload = _base_payload(state)
    _final_budget_fields(payload, state)
    return payload


__all__ = ["build_payload", "rebuild_runtime_sections", "rebuild_sections"]


"""Retrieval and generic enrichment stages for answer-context assembly."""


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
        first_lane = as_dict(runtime.lane_diagnostics[0])
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
    from mailarium.config import get_settings

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


"""Response-budget packing stage for answer-context payloads."""


class AnswerContextPacker:
    """Apply deterministic compaction phases to one runtime state."""

    def __init__(self, runtime: AnswerContextRuntime) -> None:
        """Bind one answer-context runtime and its configured response-size budget."""
        self.runtime = runtime
        self.budget = runtime.settings.mcp_max_json_response_chars

    @property
    def truncated(self) -> dict[str, int]:
        """Return the mutable counters for evidence removed during budget packing."""
        return self.runtime.packing["truncated"]

    def render(self) -> dict[str, Any]:
        """Build the current public answer-context payload from runtime state."""
        return build_payload(AnswerContextPayloadState(self.runtime))

    def over_budget(self) -> bool:
        """Determine whether the rendered payload exceeds the configured character budget."""
        return self.budget > 0 and _estimated_json_chars(self.render()) > self.budget

    def cited_uids(self) -> list[str]:
        """List candidate identifiers protected from removal because the policy cites them."""
        return [str(uid) for uid in self.runtime.answer_policy.get("cite_candidate_uids", []) if uid]

    def rebuild(self) -> None:
        """Recompute derived sections after evidence compaction and trim excess timeline events."""
        runtime = self.runtime
        rebuild_runtime_sections(
            runtime,
            conversation_group_summaries=_conversation_group_summaries,
            attach_conversation_context=_attach_conversation_context,
        )
        compacted, dropped = _compact_timeline_events(runtime.timeline)
        if dropped > self.truncated["timeline_events"]:
            self.truncated["timeline_events"] = dropped
            runtime.timeline = compacted

    def compact_groups_and_timeline(self) -> None:
        """Trim conversation groups and timeline events when their rendered payload exceeds budget."""
        runtime = self.runtime
        if len(runtime.conversation_groups) > 3 and self.over_budget():
            self.truncated["conversation_groups"] = len(runtime.conversation_groups) - 3
            runtime.conversation_groups = runtime.conversation_groups[:3]
            self._refresh_policy()
            runtime.packing["applied"] = True
        compacted, dropped = _compact_timeline_events(runtime.timeline)
        if dropped > 0 and self.over_budget():
            runtime.timeline = compacted
            self.truncated["timeline_events"] = dropped
            runtime.packing["applied"] = True

    def _refresh_policy(self) -> None:
        """Recalculate answer quality, citation policy, and final-answer contract after compaction."""
        runtime = self.runtime
        runtime.answer_quality = _answer_quality(
            candidates=runtime.candidates,
            attachment_candidates=runtime.attachment_candidates,
            conversation_groups=runtime.conversation_groups,
        )
        runtime.answer_policy = _answer_policy(
            question=runtime.params.question,
            evidence_mode=runtime.params.evidence_mode,
            candidates=runtime.candidates,
            attachment_candidates=runtime.attachment_candidates,
            answer_quality=runtime.answer_quality,
            exact_wording_requested=getattr(runtime.params, "exact_wording_requested", None),
        )
        runtime.final_answer_contract = _final_answer_contract(answer_policy=runtime.answer_policy)

    def compact_snippets(self, phase: str) -> None:
        """Shorten evidence snippets for one phase, then rebuild dependent answer sections."""
        if not self.over_budget():
            return
        runtime = self.runtime
        count = _compact_snippets_for_budget(
            runtime.candidates,
            runtime.attachment_candidates,
            cited_candidate_uids=self.cited_uids(),
            phase=phase,
        )
        if count <= 0:
            return
        self.truncated["snippet_compactions"] += count
        self.rebuild()
        self.summarize_sections()
        runtime.packing["applied"] = True

    def drop_weakest_candidates(self) -> None:
        """Remove lowest-priority uncited evidence until the response fits its size budget."""
        runtime = self.runtime
        while self.over_budget() and len(runtime.candidates) + len(runtime.attachment_candidates) > 1:
            target = _weakest_evidence_target(
                runtime.candidates,
                runtime.attachment_candidates,
                cited_candidate_uids=self.cited_uids(),
            )
            if target is None:
                break
            kind, index = target
            if kind == "attachment":
                runtime.attachment_candidates.pop(index)
                self.truncated["attachment_candidates"] += 1
            else:
                runtime.candidates.pop(index)
                self.truncated["body_candidates"] += 1
            _reindex_evidence(runtime.candidates)
            _reindex_evidence(runtime.attachment_candidates)
            self.rebuild()
            runtime.packing["applied"] = True

    def summarize_sections(self) -> None:
        """Condense thread and timeline sections, then refresh policy derived from retained evidence."""
        runtime = self.runtime
        if runtime.conversation_groups:
            groups, dropped = _summarize_conversation_groups_for_budget(runtime.conversation_groups)
            self.truncated["conversation_groups"] = max(self.truncated["conversation_groups"], dropped)
            runtime.conversation_groups = groups
        if runtime.timeline.get("events"):
            timeline, dropped = _summarize_timeline_for_budget(runtime.timeline)
            self.truncated["timeline_events"] = max(self.truncated["timeline_events"], dropped)
            runtime.timeline = timeline
        self._refresh_policy()

    def strip_optional_fields(self) -> None:
        """Remove nonessential evidence fields when snippet compaction cannot meet the budget."""
        if not self.over_budget():
            return
        runtime = self.runtime
        count = _strip_optional_evidence_fields(
            runtime.candidates,
            runtime.attachment_candidates,
        )
        if count <= 0:
            return
        self.truncated["field_compactions"] += count
        self.rebuild()
        self.summarize_sections()
        runtime.packing["applied"] = True

    def enable_contract_compaction(self) -> None:
        """Enable compact policy and search representations while the response remains oversized."""
        runtime = self.runtime
        if self.over_budget() and not runtime.compact_policy_contract:
            runtime.compact_policy_contract = True
            self.truncated["field_compactions"] += 2
            runtime.packing["applied"] = True
        if self.over_budget() and not runtime.compact_search:
            runtime.compact_search = True
            self.truncated["field_compactions"] += 1
            runtime.packing["applied"] = True

    def compact_final_sections(self, payload: dict[str, Any]) -> None:
        """Reduce final payload sections to their essential fields when preliminary packing is insufficient."""
        if self.budget <= 0 or _estimated_json_chars(payload) <= self.budget:
            return
        payload["candidates"] = [_trim_candidate_for_budget(item) for item in list(payload.get("candidates") or [])]
        payload["attachment_candidates"] = [
            _trim_candidate_for_budget(item) for item in list(payload.get("attachment_candidates") or [])
        ]
        quality = payload.get("answer_quality")
        if isinstance(quality, dict):
            payload["answer_quality"] = {
                "confidence_label": quality.get("confidence_label"),
                "confidence_score": quality.get("confidence_score"),
                "top_candidate_uid": quality.get("top_candidate_uid"),
            }
        timeline = payload.get("timeline")
        if isinstance(timeline, dict):
            payload["timeline"] = _compact_timeline_payload(timeline, include_transition=True)
        groups = payload.get("conversation_groups")
        if isinstance(groups, list):
            payload["conversation_groups"] = [
                {
                    "thread_group_id": group.get("thread_group_id"),
                    "thread_group_source": group.get("thread_group_source"),
                    "top_uid": group.get("top_uid"),
                    "message_count": group.get("message_count"),
                }
                for group in groups[:1]
                if isinstance(group, dict)
            ]
        self.truncated["field_compactions"] += 4
        self.runtime.packing["applied"] = True

    def drop_final_sections(self, payload: dict[str, Any]) -> None:
        """Remove optional final sections and reduce timeline fields to satisfy a strict budget."""
        if self.budget <= 0 or _estimated_json_chars(payload) <= self.budget:
            return
        payload.pop("answer_quality", None)
        payload.pop("conversation_groups", None)
        timeline = payload.get("timeline")
        if isinstance(timeline, dict):
            payload["timeline"] = _compact_timeline_payload(timeline, include_transition=False)
        self.truncated["field_compactions"] += 2
        self.runtime.packing["applied"] = True

    def compact_final_contracts(self, payload: dict[str, Any]) -> None:
        """Shrink snippets, policy, and search contracts after earlier final-section reductions."""
        if self.budget <= 0 or _estimated_json_chars(payload) <= self.budget:
            return
        for item in list(payload.get("candidates") or []):
            if isinstance(item, dict):
                item["snippet"] = _trim_snippet_for_budget(item.get("snippet"), max_chars=48)
        for item in list(payload.get("attachment_candidates") or []):
            if isinstance(item, dict):
                item["snippet"] = _trim_snippet_for_budget(item.get("snippet"), max_chars=48)
        policy = payload.get("answer_policy")
        if isinstance(policy, dict):
            payload["answer_policy"] = {
                "decision": policy.get("decision"),
                "verification_mode": policy.get("verification_mode"),
                "max_citations": policy.get("max_citations"),
            }
        self._compact_contract_payload(payload)
        search = payload.get("search")
        if isinstance(search, dict):
            payload["search"] = {
                "top_k": search.get("top_k"),
                "hybrid": search.get("hybrid"),
                "expand_query": search.get("expand_query"),
                "retrieval_diagnostics": as_dict(search.get("retrieval_diagnostics")),
            }
        self.truncated["field_compactions"] += 3
        self.runtime.packing["applied"] = True

    @staticmethod
    def _compact_contract_payload(payload: dict[str, Any]) -> None:
        """Compact contract payload to keep bounded tool responses useful."""
        contract = payload.get("final_answer_contract")
        if not isinstance(contract, dict):
            return
        citation_format = contract.get("citation_format")
        citation_style = str(citation_format.get("style") or "") if isinstance(citation_format, dict) else ""
        payload["final_answer_contract"] = {
            "decision": contract.get("decision"),
            "citation_style": citation_style or contract.get("citation_style"),
            "required_citation_handles": contract.get("required_citation_handles"),
            "verification_mode": contract.get("verification_mode"),
        }

    def minimal_final_payload(self, payload: dict[str, Any]) -> None:
        """Apply the final payload fallback by retaining only required search and truncation information."""
        if self.budget <= 0 or _estimated_json_chars(payload) <= self.budget:
            return
        payload.pop("timeline", None)
        payload["search"] = {"top_k": (payload.get("search") or {}).get("top_k")}
        self.truncated["field_compactions"] += 2
        self.runtime.packing["applied"] = True


def _compact_timeline_payload(timeline: dict[str, Any], *, include_transition: bool) -> dict[str, Any]:
    """Retain the bounded timeline summary fields needed by final payloads."""
    keys = ["event_count", "date_range", "first_uid", "last_uid"]
    if include_transition:
        keys.append("key_transition_uid")
    return {key: timeline.get(key) for key in keys}


def _initialize_packing(runtime: AnswerContextRuntime) -> None:
    """Initialize budget, deduplication, and truncation counters for one response."""
    runtime.packing = {
        "applied": False,
        "budget_chars": runtime.settings.mcp_max_json_response_chars,
        "estimated_chars_before": 0,
        "estimated_chars_after": 0,
        "deduplicated": {
            "body_candidates": runtime.deduped_body,
            "attachment_candidates": runtime.deduped_attachments,
        },
        "truncated": {
            "body_candidates": 0,
            "attachment_candidates": 0,
            "conversation_groups": 0,
            "timeline_events": 0,
            "snippet_compactions": 0,
            "field_compactions": 0,
        },
    }


def pack_answer_context(runtime: AnswerContextRuntime) -> dict[str, Any]:
    """Apply ordered budget phases and return the final public payload."""
    _initialize_packing(runtime)
    packer = AnswerContextPacker(runtime)
    initial = packer.render()
    before = _estimated_json_chars(initial)
    runtime.packing["estimated_chars_before"] = before
    runtime.packing["applied"] = bool(
        runtime.deduped_body or runtime.deduped_attachments or before > runtime.settings.mcp_max_json_response_chars > 0
    )
    if packer.budget > 0:
        packer.compact_groups_and_timeline()
        packer.compact_snippets("primary")
        packer.drop_weakest_candidates()
        packer.strip_optional_fields()
        packer.compact_snippets("secondary")
        packer.enable_contract_compaction()
    payload = packer.render()
    packer.compact_final_sections(payload)
    packer.drop_final_sections(payload)
    packer.compact_final_contracts(payload)
    packer.minimal_final_payload(payload)
    runtime.packing["estimated_chars_after"] = _estimated_json_chars(payload)
    payload["_packed"] = runtime.packing
    return payload
