"""Stable data models for the retriever facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mailarium.config import get_settings
from mailarium.model.message_formatting import format_context_block

from .result_filters import _json_safe, _safe_json_float, apply_metadata_filters
from .retrieval_policy import RetrievalPolicy


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
        """Expose the declared score kind, defaulting absent metadata to semantic ranking."""
        value = str(self.metadata.get("score_kind") or "").strip().lower()
        return value or "semantic"

    @property
    def score_calibration(self) -> str:
        """Identify whether the score is calibrated or synthetic when metadata omits it."""
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
        """Report whether any textual, optional, or categorical search filter is active."""
        text_filters = (self.sender, self.date_from, self.date_to, self.subject, self.folder, self.cc, self.to, self.bcc)
        optional_filters = (self.has_attachments, self.priority, self.min_score, self.allowed_uids, self.is_calendar)
        return (
            any(text_filters)
            or any(value is not None for value in optional_filters)
            or any((self.email_type, self.category, self.attachment_name, self.attachment_type))
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
class SearchRequest:
    """Typed, immutable input snapshot for one retrieval operation.

    This is deliberately independent of CLI and MCP request models so the
    search engine can be used by local callers without importing an interface
    package.  ``SearchRequest`` remains an alias below for existing
    callers while the public engine uses the clearer generic name.
    """

    query: str
    top_k: int = 10
    sender: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    subject: str | None = None
    folder: str | None = None
    cc: str | None = None
    to: str | None = None
    bcc: str | None = None
    has_attachments: bool | None = None
    priority: int | None = None
    min_score: float | None = None
    email_type: str | None = None
    rerank: bool = False
    hybrid: bool = False
    topic_id: int | None = None
    cluster_id: int | None = None
    expand_query: bool = False
    category: str | None = None
    is_calendar: bool | None = None
    attachment_name: str | None = None
    attachment_type: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class SearchPlan:
    """Execution plan for one filtered search run."""

    query: str
    lexical_query: str
    top_k: int
    use_rerank: bool
    use_hybrid: bool
    fetch_size: int
    retrieval_policy: RetrievalPolicy


@dataclass(frozen=True)
class SearchResponse:
    """Deterministic result and diagnostic snapshot from ``SearchEngine``."""

    results: tuple[SearchResult, ...]
    diagnostics: dict[str, Any]

    def as_list(self) -> list[SearchResult]:
        """Return a fresh mutable list for compatibility-oriented callers."""
        return list(self.results)
