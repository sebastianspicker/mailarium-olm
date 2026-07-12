"""Typed mutable state shared by answer-context runtime stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..mcp_models import EmailAnswerContextInput
from .utils import ToolDepsProto


@dataclass
class AnswerContextRuntime:
    """State carried through retrieval, enrichment, analysis, and packing."""

    deps: ToolDepsProto
    params: EmailAnswerContextInput
    preloaded_results: list[Any] | None = None
    preloaded_evidence_rows: list[dict[str, Any]] | None = None
    lane_diagnostics_override: list[dict[str, Any]] | None = None
    retrieval_context_override: dict[str, Any] | None = None
    settings: Any = None
    retriever: Any = None
    db: Any = None
    effective_top_k: int = 0
    search_kwargs: dict[str, Any] = field(default_factory=dict)
    query_lanes: list[Any] = field(default_factory=list)
    exact_wording: bool = False
    results: list[Any] = field(default_factory=list)
    lane_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    retrieval_context: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    attachment_candidates: list[dict[str, Any]] = field(default_factory=list)
    deduped_body: int = 0
    deduped_attachments: int = 0
    full_map: dict[str, Any] = field(default_factory=dict)
    conversation_groups: list[dict[str, Any]] = field(default_factory=list)
    answer_quality: dict[str, Any] = field(default_factory=dict)
    timeline: dict[str, Any] = field(default_factory=dict)
    answer_policy: dict[str, Any] = field(default_factory=dict)
    final_answer_contract: dict[str, Any] = field(default_factory=dict)
    retrieval_diagnostics: dict[str, Any] = field(default_factory=dict)
    case_bundle: dict[str, Any] | None = None
    actor_graph: dict[str, Any] = field(default_factory=dict)
    power_context: dict[str, Any] | None = None
    case_patterns: dict[str, Any] | None = None
    retaliation_analysis: dict[str, Any] | None = None
    comparative_treatment: dict[str, Any] | None = None
    communication_graph: dict[str, Any] | None = None
    multi_source_case_bundle: dict[str, Any] | None = None
    finding_evidence_index: dict[str, Any] = field(default_factory=dict)
    evidence_table: dict[str, Any] = field(default_factory=dict)
    behavioral_strength_rubric: dict[str, Any] = field(default_factory=dict)
    investigation_report: dict[str, Any] | None = None
    compact_policy_contract: bool = False
    compact_search: bool = False
    compact_report_only: bool = False
    compact_case_evidence: bool = False
    packing: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnswerContextPayloadState:
    """Inputs needed to render the current public payload snapshot."""

    runtime: AnswerContextRuntime
