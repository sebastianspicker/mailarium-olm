"""Public answer-context facade with stable helper imports."""

from __future__ import annotations

from typing import Any

from ..mcp_models import EmailAnswerContextInput
from . import search_answer_context_impl as _impl
from .search_answer_context_budget import (
    _compact_snippets_for_budget,
    _compact_timeline_events,
    _dedupe_evidence_items,
    _estimated_json_chars,
    _packing_priority,
    _reindex_evidence,
    _snippet_budget_for_item,
    _strip_optional_evidence_fields,
    _summarize_conversation_groups_for_budget,
    _summarize_timeline_for_budget,
    _weakest_evidence_target,
)
from .search_answer_context_impl import (  # noqa: F401
    _answer_context_search_kwargs,
    _apply_actor_ids_to_candidates,
    _apply_actor_ids_to_case_bundle,
    _apply_reply_pairings_to_candidates,
    _as_dict,
    _attach_conversation_context,
    _attachment_candidate,
    _attachment_evidence_profile,
    _compact_actor_identity_graph_payload,
    _compact_case_bundle_payload,
    _compact_case_patterns_payload,
    _compact_comparative_treatment_payload,
    _compact_language_rhetoric_payload,
    _compact_message_findings_payload,
    _compact_optional_case_surfaces,
    _compact_retaliation_analysis_payload,
    _conversation_group_summaries,
    _infer_quoted_speaker,
    _is_attachment_result,
    _language_rhetoric_for_candidate,
    _match_reason,
    _message_findings_for_candidate,
    _provenance_for_candidate,
    _public_retrieval_diagnostics,
    _quote_attribution_metrics,
    _recipients_summary,
    _retrieval_diagnostics,
    _segment_rows_for_uid,
    _snippet,
    _speaker_attribution_for_candidate,
    _thread_graph_for_email,
    _thread_locator_for_candidate,
)
from .search_answer_context_rendering import (
    _answer_policy,
    _answer_quality,
    _final_answer_contract,
    _render_final_answer,
    _timeline_summary,
)
from .utils import ToolDepsProto

__all__ = [
    "_answer_context_search_kwargs",
    "_answer_policy",
    "_answer_quality",
    "_attachment_evidence_profile",
    "_compact_message_findings_payload",
    "_compact_snippets_for_budget",
    "_compact_timeline_events",
    "_dedupe_evidence_items",
    "_estimated_json_chars",
    "_final_answer_contract",
    "_infer_quoted_speaker",
    "_packing_priority",
    "_reindex_evidence",
    "_render_final_answer",
    "_segment_rows_for_uid",
    "_snippet_budget_for_item",
    "_strip_optional_evidence_fields",
    "_summarize_conversation_groups_for_budget",
    "_summarize_timeline_for_budget",
    "_thread_locator_for_candidate",
    "_timeline_summary",
    "_weakest_evidence_target",
    "build_answer_context",
    "build_answer_context_payload",
]


async def build_answer_context(deps: ToolDepsProto, params: EmailAnswerContextInput) -> str:
    """Build the answer-context payload for ``email_answer_context``."""

    _impl._segment_rows_for_uid = _segment_rows_for_uid
    _impl._infer_quoted_speaker = _infer_quoted_speaker
    return await _impl.build_answer_context(deps, params)


async def build_answer_context_payload(
    deps: ToolDepsProto,
    params: EmailAnswerContextInput,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build the structured answer-context payload before outward JSON rendering."""

    from . import search_answer_context_runtime as _runtime

    return await _runtime.build_answer_context_payload(deps, params, **kwargs)
