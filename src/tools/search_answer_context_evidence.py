"""Evidence and retrieval helpers for answer-context rendering."""

from __future__ import annotations

from .search_answer_context_evidence_candidates import (
    _attach_conversation_context,
    _attachment_candidate,
    _attachment_evidence_profile,
    _attachment_record_for_candidate,
    _conversation_group_summaries,
)
from .search_answer_context_evidence_helpers import (
    _as_dict,
    _as_list,
    _attachment_extraction_state,
    _find_snippet_bounds,
    _is_attachment_result,
    _match_reason,
    _provenance_for_candidate,
    _recipients_summary,
    _segment_ordinal_for_snippet,
    _snippet,
    _thread_graph_for_email,
    _thread_locator_for_candidate,
    _verified_snippet_for_mode,
)
from .search_answer_context_evidence_payloads import (
    _answer_context_search_kwargs,
    _compact_optional_case_surfaces,
    _compact_retaliation_analysis_payload,
    _public_retrieval_diagnostics,
    _retrieval_diagnostics,
)

__all__ = [
    "_answer_context_search_kwargs",
    "_as_dict",
    "_as_list",
    "_attach_conversation_context",
    "_attachment_candidate",
    "_attachment_evidence_profile",
    "_attachment_extraction_state",
    "_attachment_record_for_candidate",
    "_compact_optional_case_surfaces",
    "_compact_retaliation_analysis_payload",
    "_conversation_group_summaries",
    "_find_snippet_bounds",
    "_is_attachment_result",
    "_match_reason",
    "_provenance_for_candidate",
    "_public_retrieval_diagnostics",
    "_recipients_summary",
    "_retrieval_diagnostics",
    "_segment_ordinal_for_snippet",
    "_snippet",
    "_thread_graph_for_email",
    "_thread_locator_for_candidate",
    "_verified_snippet_for_mode",
]
