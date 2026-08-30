"""Explicit request and mutable state for answer-context assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import AnswerContextDependencies, AnswerContextRequest

"""Typed mutable state shared by answer-context runtime stages."""


@dataclass
class AnswerContextRuntime:
    """State carried through retrieval, enrichment, analysis, and packing."""

    deps: AnswerContextDependencies
    params: AnswerContextRequest
    preloaded_results: list[Any] | None = None
    preloaded_evidence_rows: list[dict[str, Any]] | None = None
    settings: Any = None
    retriever: Any = None
    db: Any = None
    effective_top_k: int = 0
    search_kwargs: dict[str, Any] = field(default_factory=dict)
    query_lanes: list[str] = field(default_factory=list)
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
    compact_policy_contract: bool = False
    compact_search: bool = False
    packing: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnswerContextPayloadState:
    """Inputs needed to render the current public payload snapshot."""

    runtime: AnswerContextRuntime
