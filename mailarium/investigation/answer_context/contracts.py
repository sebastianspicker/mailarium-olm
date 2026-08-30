"""Domain-facing contracts for answer-context construction.

The MCP layer owns concrete validation models and response serialization.  This
module describes only the request fields and runtime capabilities the
investigation workflow needs, so it remains usable by other adapters.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol


class AnswerContextRequest(Protocol):
    """Validated request fields consumed by the answer-context workflow."""

    question: str
    max_results: int
    evidence_mode: Literal["retrieval", "forensic", "hybrid"]
    rerank: bool
    hybrid: bool
    query_lanes: list[str]
    exact_wording_requested: bool | None
    scan_id: str | None
    scope: str | None
    sender: str | None
    subject: str | None
    folder: str | None
    has_attachments: bool | None
    email_type: Literal["reply", "forward", "original"] | None
    date_from: str | None
    date_to: str | None


class AnswerContextDependencies(Protocol):
    """Runtime capabilities required to assemble answer-context payloads."""

    def get_retriever(self) -> Any:
        """Return the retriever used for evidence discovery."""
        ...

    def get_archive_database(self) -> Any | None:
        """Return the optional archive database used for enrichment."""
        ...

    async def offload(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run blocking workflow stages without blocking the caller's event loop."""
        ...


__all__ = ["AnswerContextDependencies", "AnswerContextRequest"]
