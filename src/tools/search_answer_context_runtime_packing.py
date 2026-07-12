"""Response-budget packing stage for answer-context payloads."""

from __future__ import annotations

from typing import Any

from .._utils import _as_dict
from . import search_answer_context_impl as impl
from .search_answer_context_budget import (
    _compact_snippets_for_budget,
    _compact_timeline_events,
    _estimated_json_chars,
    _reindex_evidence,
    _strip_optional_evidence_fields,
    _summarize_conversation_groups_for_budget,
    _summarize_timeline_for_budget,
    _weakest_evidence_target,
)
from .search_answer_context_rendering import _answer_policy, _answer_quality, _final_answer_contract
from .search_answer_context_runtime_budgeting import _trim_candidate_for_budget, _trim_snippet_for_budget
from .search_answer_context_runtime_payload import _compact_optional_case_surfaces, build_payload, rebuild_sections
from .search_answer_context_runtime_state import AnswerContextPayloadState, AnswerContextRuntime


class AnswerContextPacker:
    """Apply deterministic compaction phases to one runtime state."""

    def __init__(self, runtime: AnswerContextRuntime) -> None:
        self.runtime = runtime
        self.budget = runtime.settings.mcp_max_json_response_chars

    @property
    def truncated(self) -> dict[str, int]:
        return self.runtime.packing["truncated"]

    def render(self) -> dict[str, Any]:
        return build_payload(AnswerContextPayloadState(self.runtime))

    def over_budget(self) -> bool:
        return self.budget > 0 and _estimated_json_chars(self.render()) > self.budget

    def cited_uids(self) -> list[str]:
        return [str(uid) for uid in self.runtime.answer_policy.get("cite_candidate_uids", []) if uid]

    def rebuild(self) -> None:
        runtime = self.runtime
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
        compacted, dropped = _compact_timeline_events(runtime.timeline)
        if dropped > self.truncated["timeline_events"]:
            self.truncated["timeline_events"] = dropped
            runtime.timeline = compacted

    def compact_groups_and_timeline(self) -> None:
        runtime = self.runtime
        if len(runtime.conversation_groups) > 3 and self.over_budget():
            self.truncated["conversation_groups"] = len(runtime.conversation_groups) - 3
            runtime.conversation_groups = runtime.conversation_groups[:3]
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
            runtime.packing["applied"] = True
        compacted, dropped = _compact_timeline_events(runtime.timeline)
        if dropped > 0 and self.over_budget():
            runtime.timeline = compacted
            self.truncated["timeline_events"] = dropped
            runtime.packing["applied"] = True

    def compact_snippets(self, phase: str) -> None:
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

    def enable_case_compaction(self, *, count_fields: bool) -> None:
        runtime = self.runtime
        if self.over_budget() and not runtime.compact_report_only and runtime.case_bundle is not None:
            runtime.compact_report_only = True
            self.truncated["field_compactions"] += int(count_fields)
            runtime.packing["applied"] = True
        if self.over_budget() and not runtime.compact_case_evidence and runtime.case_bundle is not None:
            runtime.compact_case_evidence = True
            self.truncated["field_compactions"] += 2 * int(count_fields)
            runtime.packing["applied"] = True

    def drop_weakest_candidates(self) -> None:
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
        runtime = self.runtime
        if runtime.conversation_groups:
            groups, dropped = _summarize_conversation_groups_for_budget(runtime.conversation_groups)
            self.truncated["conversation_groups"] = max(self.truncated["conversation_groups"], dropped)
            runtime.conversation_groups = groups
        if runtime.timeline.get("events"):
            timeline, dropped = _summarize_timeline_for_budget(runtime.timeline)
            self.truncated["timeline_events"] = max(self.truncated["timeline_events"], dropped)
            runtime.timeline = timeline
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

    def strip_optional_fields(self) -> None:
        if not self.over_budget():
            return
        runtime = self.runtime
        count = _strip_optional_evidence_fields(
            runtime.candidates,
            runtime.attachment_candidates,
            force_deep_candidate_analysis_strip=(self.truncated["body_candidates"] + self.truncated["attachment_candidates"]) > 0,
        )
        if count <= 0:
            return
        self.truncated["field_compactions"] = count
        self.rebuild()
        self.summarize_sections()
        runtime.packing["applied"] = True

    def enable_contract_compaction(self) -> None:
        runtime = self.runtime
        if self.over_budget() and not runtime.compact_policy_contract:
            runtime.compact_policy_contract = True
            self.truncated["field_compactions"] += 2
            runtime.packing["applied"] = True
        if self.over_budget() and not runtime.compact_search:
            runtime.compact_search = True
            self.truncated["field_compactions"] += 1
            runtime.packing["applied"] = True

    def compact_final_case_surfaces(self, payload: dict[str, Any]) -> None:
        runtime = self.runtime
        if self.budget > 0 and _estimated_json_chars(payload) > self.budget and runtime.case_bundle is not None:
            removed = _compact_optional_case_surfaces(payload, budget=self.budget)
            if removed > 0:
                self.truncated["field_compactions"] += removed
                runtime.packing["applied"] = True

    def compact_final_sections(self, payload: dict[str, Any]) -> None:
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
            payload["timeline"] = {
                "event_count": timeline.get("event_count"),
                "date_range": timeline.get("date_range"),
                "first_uid": timeline.get("first_uid"),
                "last_uid": timeline.get("last_uid"),
                "key_transition_uid": timeline.get("key_transition_uid"),
            }
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
        if self.budget <= 0 or _estimated_json_chars(payload) <= self.budget:
            return
        payload.pop("answer_quality", None)
        payload.pop("conversation_groups", None)
        timeline = payload.get("timeline")
        if isinstance(timeline, dict):
            payload["timeline"] = {
                "event_count": timeline.get("event_count"),
                "date_range": timeline.get("date_range"),
                "first_uid": timeline.get("first_uid"),
                "last_uid": timeline.get("last_uid"),
            }
        self.truncated["field_compactions"] += 2
        self.runtime.packing["applied"] = True

    def compact_final_contracts(self, payload: dict[str, Any]) -> None:
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
                "retrieval_diagnostics": _as_dict(search.get("retrieval_diagnostics")),
            }
        self.truncated["field_compactions"] += 3
        self.runtime.packing["applied"] = True

    @staticmethod
    def _compact_contract_payload(payload: dict[str, Any]) -> None:
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
        if self.budget <= 0 or _estimated_json_chars(payload) <= self.budget:
            return
        payload.pop("timeline", None)
        payload["search"] = {"top_k": (payload.get("search") or {}).get("top_k")}
        self.truncated["field_compactions"] += 2
        self.runtime.packing["applied"] = True


def _initialize_packing(runtime: AnswerContextRuntime) -> None:
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
        packer.enable_case_compaction(count_fields=False)
        packer.drop_weakest_candidates()
        packer.strip_optional_fields()
        packer.compact_snippets("secondary")
        packer.enable_contract_compaction()
        packer.enable_case_compaction(count_fields=True)
    payload = packer.render()
    packer.compact_final_case_surfaces(payload)
    packer.compact_final_sections(payload)
    packer.drop_final_sections(payload)
    packer.compact_final_contracts(payload)
    packer.minimal_final_payload(payload)
    runtime.packing["estimated_chars_after"] = _estimated_json_chars(payload)
    payload["_packed"] = runtime.packing
    return payload
