"""Stable request, result, and plan models for the search engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .retrieval_policy import RetrievalPolicy


def _safe_json_float(value: Any) -> float | None:
    """Safely convert a value to a rounded float, handling non-finite values."""
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    if not math.isfinite(number):
        return None
    return round(number, 4)


def _json_safe(value: Any) -> Any:
    """Make a value JSON-safe by handling non-finite floats and nested structures."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


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
class SearchRequest:
    """Typed, immutable input snapshot for one retrieval operation.

    This is deliberately independent of CLI and MCP request models so the
    search engine can be used by local callers without importing an interface
    package.
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
        """Return the results as a fresh mutable list."""
        return list(self.results)
