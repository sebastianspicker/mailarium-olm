"""General-RAG input model for answer-context retrieval."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .mcp_models_base import DateRangeInput, MessageSearchFilterInput, StrictInput
from .retrieval_policy import MAX_SCOPE_LENGTH, normalize_scope


class EmailAnswerContextInput(DateRangeInput, MessageSearchFilterInput, StrictInput):
    """Input for building a compact, general-purpose evidence bundle."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural-language archive question to answer from retrieved evidence.",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of candidate emails to return in the evidence bundle (1-20).",
    )
    evidence_mode: Literal["retrieval", "forensic", "hybrid"] = Field(
        default="retrieval",
        description=(
            "Evidence render policy. 'retrieval' returns normalized-body evidence, "
            "'forensic' prefers source-preserved body text, and 'hybrid' retrieves with "
            "normalized text but verifies snippets against forensic text when available."
        ),
    )
    rerank: bool = Field(
        default=False,
        description="Re-rank results with cross-encoder for better precision (slower).",
    )
    hybrid: bool = Field(
        default=False,
        description="Use hybrid semantic + BM25 keyword search for better recall.",
    )
    query_lanes: list[str] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "Optional ordered retrieval queries for multi-lane evidence gathering. "
            "When supplied, answer-context searches these lanes and merges the strongest unique hits."
        ),
    )
    exact_wording_requested: bool | None = Field(
        default=None,
        description=(
            "Optional explicit quote-intent override. When omitted, exact-wording intent is inferred from the question text."
        ),
    )
    scan_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Optional progressive scan-session identifier. "
            "When supplied, multi-lane retrieval deduplicates across lane searches and records scan metadata."
        ),
    )
    scope: str | None = Field(
        default=None,
        max_length=MAX_SCOPE_LENGTH,
        description=(
            "Optional general-RAG relevance scope such as 'general', 'finance', or 'research'. "
            "The retriever applies it to this request and chooses explainable hybrid weights automatically."
        ),
    )

    @field_validator("scope")
    @classmethod
    def normalize_retrieval_scope(cls, value: str | None) -> str | None:
        """Normalize scope whitespace/case and reject unsafe or oversized labels."""
        return normalize_scope(value) if value is not None else None

    @field_validator("query_lanes")
    @classmethod
    def normalize_query_lanes(cls, value: list[str]) -> list[str]:
        """Normalize query lanes before downstream processing."""
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            lane = " ".join(str(item or "").split()).strip()
            lowered = lane.casefold()
            if not lane or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(lane[:500])
        return normalized
