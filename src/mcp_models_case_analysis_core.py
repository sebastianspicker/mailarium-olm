"""Core answer-context and chat-entry case-analysis input models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .mcp_models_analysis import BehavioralCaseScopeInput
from .mcp_models_base import DateRangeInput, StrictInput, _validate_local_read_path


class EmailAnswerContextInput(DateRangeInput, StrictInput):
    """Input for building a compact answer-ready evidence bundle."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural-language mailbox question to answer from retrieved evidence.",
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
    sender: str | None = Field(default=None, description="Filter by sender (partial match).")
    subject: str | None = Field(default=None, description="Filter by subject (partial match).")
    folder: str | None = Field(default=None, description="Filter by folder name (partial match).")
    has_attachments: bool | None = Field(default=None, description="Filter by attachment presence.")
    email_type: Literal["reply", "forward", "original"] | None = Field(
        default=None,
        description="Filter by email type: 'reply', 'forward', or 'original'.",
    )
    rerank: bool = Field(
        default=False,
        description="Re-rank results with cross-encoder for better precision (slower).",
    )
    hybrid: bool = Field(
        default=False,
        description="Use hybrid semantic + BM25 keyword search for better recall.",
    )
    case_scope: BehavioralCaseScopeInput | None = Field(
        default=None,
        description="Structured investigation scope for case-based behavioural analysis.",
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

    @field_validator("query_lanes")
    @classmethod
    def normalize_query_lanes(cls, value: list[str]) -> list[str]:
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


class CaseChatLogEntryInput(StrictInput):
    """Structured chat-log artifact for mixed-source case analysis."""

    source_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional stable operator-supplied identifier for the chat record.",
    )
    platform: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional chat platform label, such as Teams, Slack, or WhatsApp.",
    )
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Optional human-readable title for the chat record or thread.",
    )
    date: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description="Optional ISO-like timestamp or date for the chat message or export fragment.",
    )
    participants: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Optional normalized participant labels or email addresses visible in the chat record.",
    )
    text: str = Field(
        ...,
        min_length=1,
        max_length=12000,
        description="Visible chat text or operator-supplied chat excerpt to preserve in the mixed-source bundle.",
    )
    related_email_uid: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Optional related email uid for cross-source linking when the chat record belongs to a known email thread.",
    )

    @field_validator("participants")
    @classmethod
    def normalize_participants(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            participant = str(item).strip()
            lowered = participant.lower()
            if not participant or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(participant)
        return normalized


class CaseChatExportInput(StrictInput):
    """Native chat-export file reference for mixed-source case analysis."""

    source_path: str = Field(
        ...,
        min_length=1,
        description="Absolute path to a native chat-export file such as Teams HTML, Slack JSON, or plain-text export.",
    )
    source_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional stable operator-supplied identifier for the chat export.",
    )
    platform: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional chat platform label, such as Teams, Slack, or WhatsApp.",
    )
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Optional human-readable title for the chat export or thread.",
    )
    date: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description="Optional ISO-like timestamp or date for the exported chat fragment.",
    )
    participants: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Optional participant labels or email addresses visible in the chat export.",
    )
    related_email_uid: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Optional related email uid for cross-source linking when the chat export belongs to a known email thread.",
    )

    @field_validator("participants")
    @classmethod
    def normalize_participants(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            participant = str(item).strip()
            lowered = participant.lower()
            if not participant or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(participant)
        return normalized

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, value: str) -> str:
        validated = _validate_local_read_path(value, field_name="source_path")
        if validated is None:
            raise ValueError("source_path is required")
        return validated
