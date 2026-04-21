# mypy: disable-error-code=name-defined
"""Split helpers for search answer-context runtime (search_answer_context_runtime_budgeting)."""

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
from .search_answer_context_case_payloads import (
    _apply_actor_ids_to_candidates,
    _apply_actor_ids_to_case_bundle,
    _compact_language_rhetoric_payload,
    _compact_message_findings_payload,
)
from .search_answer_context_rendering import (
    _answer_policy,
    _answer_quality,
    _final_answer_contract,
    _render_final_answer,
    _resolve_exact_wording_requested,
)
from .search_answer_context_runtime_payload import _compact_optional_case_surfaces, build_payload, rebuild_sections
from .utils import ToolDepsProto, json_response

# ruff: noqa: F401


def _trim_snippet_for_budget(text: Any, *, max_chars: int) -> str:
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _trim_provenance_for_budget(provenance: Any) -> dict[str, Any]:
    if not isinstance(provenance, dict):
        return {}
    return {
        "evidence_handle": provenance.get("evidence_handle"),
        "visible_excerpt_start": provenance.get("visible_excerpt_start"),
        "visible_excerpt_end": provenance.get("visible_excerpt_end"),
        "visible_excerpt_compacted": provenance.get("visible_excerpt_compacted"),
    }


def _trim_candidate_for_budget(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    trimmed = {
        "rank": item.get("rank"),
        "uid": item.get("uid"),
        "subject": item.get("subject"),
        "sender_email": item.get("sender_email"),
        "date": item.get("date"),
        "score": item.get("score"),
        "snippet": _trim_snippet_for_budget(item.get("snippet"), max_chars=120),
        "provenance": _trim_provenance_for_budget(item.get("provenance")),
    }
    attachment = item.get("attachment")
    if isinstance(attachment, dict):
        trimmed["attachment"] = {
            "filename": attachment.get("filename"),
            "evidence_strength": attachment.get("evidence_strength"),
            "text_available": attachment.get("text_available"),
        }
    if isinstance(item.get("language_rhetoric"), dict):
        trimmed["language_rhetoric"] = _compact_language_rhetoric_payload(item.get("language_rhetoric"))
    if isinstance(item.get("message_findings"), dict):
        trimmed["message_findings"] = _compact_message_findings_payload(item.get("message_findings"))
    reply_pairing = item.get("reply_pairing")
    if isinstance(reply_pairing, dict):
        trimmed["reply_pairing"] = {
            "response_status": reply_pairing.get("response_status"),
            "supports_selective_non_response_inference": reply_pairing.get("supports_selective_non_response_inference"),
        }
    return trimmed


__all__ = [
    "_trim_candidate_for_budget",
    "_trim_provenance_for_budget",
    "_trim_snippet_for_budget",
]
