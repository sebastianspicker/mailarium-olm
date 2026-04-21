"""Stable data models for the retriever facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import get_settings
from .formatting import format_context_block
from .result_filters import _json_safe, _safe_json_float, apply_metadata_filters


@dataclass
class SearchResult:
    """A single search result."""

    chunk_id: str
    text: str
    metadata: dict
    distance: float

    @property
    def score(self) -> float:
        """Similarity score 0-1 (higher = more similar)."""
        return min(1.0, max(0.0, 1.0 - self.distance))

    @property
    def score_kind(self) -> str:
        """Return the outward score family for this result."""
        value = str(self.metadata.get("score_kind") or "").strip().lower()
        return value or "semantic"

    @property
    def score_calibration(self) -> str:
        """Return whether the score is calibrated or synthetic."""
        value = str(self.metadata.get("score_calibration") or "").strip().lower()
        if value:
            return value
        return "calibrated" if self.score_kind == "semantic" else "synthetic"

    def to_context_string(self) -> str:
        """Format as a human-readable context block for LLM prompts."""
        max_body = get_settings().mcp_max_body_chars
        return format_context_block(self.text, self.metadata, self.score, max_body_chars=max_body)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "score": _safe_json_float(self.score),
            "score_kind": self.score_kind,
            "score_calibration": self.score_calibration,
            "distance": _safe_json_float(self.distance),
            "metadata": _json_safe(self.metadata),
            "text": self.text,
        }


@dataclass(frozen=True)
class SearchFilters:
    """Normalized metadata filters for filtered search."""

    sender: str | None
    date_from: str | None
    date_to: str | None
    subject: str | None
    folder: str | None
    cc: str | None
    to: str | None
    bcc: str | None
    has_attachments: bool | None
    priority: int | None
    min_score: float | None
    email_type: str | None
    allowed_uids: set[str] | None
    category: str | None
    is_calendar: bool | None
    attachment_name: str | None
    attachment_type: str | None

    @property
    def has_filters(self) -> bool:
        return bool(
            self.sender
            or self.date_from
            or self.date_to
            or self.subject
            or self.folder
            or self.cc
            or self.to
            or self.bcc
            or self.has_attachments is not None
            or self.priority is not None
            or self.min_score is not None
            or self.email_type
            or self.allowed_uids is not None
            or self.category
            or self.is_calendar is not None
            or self.attachment_name
            or self.attachment_type
        )

    def apply(self, results: list[SearchResult], *, use_rerank: bool) -> list[SearchResult]:
        """Apply metadata filters with rerank-aware min-score handling."""
        if not self.has_filters:
            return results
        filter_min_score = None if use_rerank else self.min_score
        return apply_metadata_filters(
            results,
            sender=self.sender,
            subject=self.subject,
            folder=self.folder,
            cc=self.cc,
            to=self.to,
            bcc=self.bcc,
            email_type=self.email_type,
            date_from=self.date_from,
            date_to=self.date_to,
            has_attachments=self.has_attachments,
            priority=self.priority,
            min_score=filter_min_score,
            allowed_uids=self.allowed_uids,
            category=self.category,
            is_calendar=self.is_calendar,
            attachment_name=self.attachment_name,
            attachment_type=self.attachment_type,
        )


@dataclass(frozen=True)
class SearchPlan:
    """Execution plan for one filtered search run."""

    query: str
    top_k: int
    use_rerank: bool
    use_hybrid: bool
    fetch_size: int
