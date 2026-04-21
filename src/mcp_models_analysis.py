"""MCP input models for analysis, network, entity, thread, and reporting tools."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from .mcp_models_analysis_case_events import AdverseActionInput, TriggerEventInput
from .mcp_models_analysis_case_parties import (
    BehavioralOrgContextInput,
    CasePartyInput,
    DependencyRelationInput,
    InstitutionalActorInput,
    ReportingLineInput,
    RoleFactInput,
    VulnerabilityContextInput,
)
from .mcp_models_analysis_case_scope import BehavioralCaseScopeInput
from .mcp_models_base import (
    DateRangeInput,
    PlainInput,
    StrictInput,
    _validate_output_path,
)

__all__ = [
    "ActionItemsInput",
    "AdverseActionInput",
    "BehavioralCaseScopeInput",
    "BehavioralOrgContextInput",
    "CasePartyInput",
    "CoordinatedTimingInput",
    "DecisionsInput",
    "DependencyRelationInput",
    "EmailAdminInput",
    "EmailAttachmentsInput",
    "EmailClustersInput",
    "EmailContactsInput",
    "EmailQualityInput",
    "EmailReportInput",
    "EmailTemporalInput",
    "EmailThreadLookupInput",
    "EmailTopicsInput",
    "EntityNetworkInput",
    "EntitySearchInput",
    "EntityTimelineInput",
    "InstitutionalActorInput",
    "ListEntitiesInput",
    "NetworkAnalysisInput",
    "RelationshipPathsInput",
    "RelationshipSummaryInput",
    "ReportingLineInput",
    "RoleFactInput",
    "SharedRecipientsInput",
    "ThreadSummaryInput",
    "TriggerEventInput",
    "VulnerabilityContextInput",
]

# ── Network Analysis Inputs ──────────────────────────────────


class NetworkAnalysisInput(PlainInput):
    """Input for network analysis."""

    top_n: int = Field(default=20, ge=1, le=100, description="Number of top nodes to return.")


# ── Entity Inputs ────────────────────────────────────────────


class EntitySearchInput(StrictInput):
    """Input for entity search."""

    entity: str = Field(..., description="Entity text to search for (partial match).", min_length=1)
    entity_type: Literal["organization", "url", "phone", "email", "person", "event"] | None = Field(
        default=None,
        description="Filter by entity type: 'organization', 'url', 'phone', 'email', 'person', 'event'.",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max results to return.")


class ListEntitiesInput(PlainInput):
    """Input for listing top entities."""

    entity_type: Literal["organization", "url", "phone", "email", "person", "event"] | None = Field(
        default=None, description="Filter by type: 'organization', 'url', 'phone', 'email', 'person', 'event'."
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max entities to return.")


class EntityNetworkInput(StrictInput):
    """Input for entity co-occurrence network."""

    entity: str = Field(..., description="Entity to find co-occurrences for.", min_length=1)
    limit: int = Field(default=20, ge=1, le=100, description="Max co-occurring entities to return.")


class EntityTimelineInput(StrictInput):
    """Input for entity mention timeline."""

    entity: str = Field(
        ...,
        description="Entity text to track over time (partial match).",
        min_length=1,
    )
    period: Literal["day", "week", "month"] = Field(
        default="month",
        description="Aggregation period: 'day', 'week', or 'month'.",
    )


# ── Thread Intelligence Inputs ───────────────────────────────


class ThreadSummaryInput(StrictInput):
    """Input for thread summarization."""

    conversation_id: str = Field(..., description="Conversation thread ID from a previous search result.", min_length=1)
    max_sentences: int = Field(default=5, ge=1, le=20, description="Max sentences in the summary.")


class ActionItemsInput(StrictInput):
    """Input for action item extraction."""

    conversation_id: str | None = Field(default=None, description="Thread ID. If omitted, scans recent emails.")
    days: int | None = Field(default=None, ge=1, le=365, description="Scan emails from last N days.")
    limit: int = Field(default=20, ge=1, le=100, description="Max action items to return.")


class DecisionsInput(StrictInput):
    """Input for decision extraction."""

    conversation_id: str | None = Field(default=None, description="Thread ID to extract decisions from.")
    days: int | None = Field(default=None, ge=1, le=365, description="Scan emails from last N days.")
    limit: int = Field(default=30, ge=1, le=100, description="Max decisions to return.")


# ── Relationship Inputs ─────────────────────────────────────


class RelationshipPathsInput(StrictInput):
    """Input for finding communication paths between two people."""

    source: str = Field(
        ...,
        description="Source email address.",
        min_length=1,
    )
    target: str = Field(
        ...,
        description="Target email address.",
        min_length=1,
    )
    max_hops: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Maximum number of intermediate hops (1-6).",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum paths to return.",
    )


class SharedRecipientsInput(PlainInput):
    """Input for finding recipients common to multiple senders."""

    email_addresses: list[str] = Field(
        ...,
        description="List of sender email addresses (2 or more).",
        min_length=2,
    )
    min_shared: int = Field(
        default=2,
        ge=2,
        description="Minimum number of senders who must share a recipient.",
    )
    limit: int = Field(
        default=30,
        ge=1,
        le=200,
        description="Maximum number of shared recipients to return.",
    )


class CoordinatedTimingInput(PlainInput):
    """Input for detecting synchronized communication patterns."""

    email_addresses: list[str] = Field(
        ...,
        description="List of sender email addresses (2 or more).",
        min_length=2,
    )
    window_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Time window size in hours for co-activity detection.",
    )
    min_events: int = Field(
        default=3,
        ge=2,
        description="Minimum emails within a window to count as coordinated.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of coordinated windows to return.",
    )


class RelationshipSummaryInput(StrictInput):
    """Input for a full person profile."""

    email_address: str = Field(
        ...,
        description="Email address to profile.",
        min_length=1,
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max contacts to return in profile.",
    )


# ── Cluster & Topic Inputs ──────────────────────────────────


class EmailClustersInput(PlainInput):
    """Input for listing clusters or emails in a cluster.

    Omit cluster_id to list all clusters; set it to list emails in that cluster.
    """

    cluster_id: int | None = Field(
        default=None,
        ge=0,
        description="Cluster ID. Omit to list all clusters; set to list emails in that cluster.",
    )
    limit: int = Field(default=30, ge=1, le=100, description="Max results to return.")


class EmailTopicsInput(PlainInput):
    """Input for listing topics or emails assigned to a topic.

    Omit topic_id to list all topics; set it to list emails for that topic.
    """

    topic_id: int | None = Field(
        default=None,
        ge=0,
        description="Topic ID. Omit to list all topics; set to list emails for that topic.",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max results to return.")


class EmailThreadLookupInput(StrictInput):
    """Input for looking up a thread by conversation_id or thread_topic.

    Provide exactly one of conversation_id or thread_topic.
    """

    conversation_id: str | None = Field(
        default=None,
        description="Conversation thread ID from search results.",
        min_length=1,
    )
    thread_topic: str | None = Field(
        default=None,
        description="Thread topic string (exact match from OLM metadata).",
        min_length=1,
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max emails in the thread to return.")

    @model_validator(mode="after")
    def exactly_one_key(self):
        if self.conversation_id and self.thread_topic:
            raise ValueError("Provide exactly one of conversation_id or thread_topic, not both.")
        if not self.conversation_id and not self.thread_topic:
            raise ValueError("Provide exactly one of conversation_id or thread_topic.")
        return self


class EmailContactsInput(StrictInput):
    """Input for contact analysis.

    Omit compare_with for top contacts; set it for bidirectional communication stats.
    """

    email_address: str = Field(
        ...,
        description="Email address to analyze.",
        min_length=1,
    )
    compare_with: str | None = Field(
        default=None,
        description="Second email address for bidirectional stats. Omit for top contacts.",
        min_length=1,
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max contacts to return.")


# ── Temporal & Quality Inputs ────────────────────────────────


class EmailTemporalInput(DateRangeInput, StrictInput):
    """Input for temporal analysis.

    analysis='volume': email volume over time (day/week/month).
    analysis='activity': hour-of-day x day-of-week heatmap.
    analysis='response_times': recent-sample response times per sender based on canonical reply pairs.
    """

    analysis: Literal["volume", "activity", "response_times"] = Field(
        ...,
        description="Analysis type: 'volume', 'activity', or 'response_times'.",
    )
    period: Literal["day", "week", "month"] = Field(
        default="day",
        description="Aggregation period for volume: 'day', 'week', or 'month'.",
    )
    sender: str | None = Field(default=None, description="Filter by sender email.")
    limit: int = Field(default=20, ge=1, le=100, description="Max sender rows for the response_times recent-sample output.")


class EmailQualityInput(PlainInput):
    """Input for data quality checks.

    check='duplicates': find near-duplicate emails.
    check='languages': language distribution.
    check='sentiment': sentiment distribution.
    """

    check: Literal["duplicates", "languages", "sentiment"] = Field(
        ...,
        description="Quality check: 'duplicates', 'languages', or 'sentiment'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Max duplicate pairs to return (only for check='duplicates').",
    )
    threshold: float = Field(
        default=0.85,
        ge=0.5,
        le=1.0,
        description="Similarity threshold (only for check='duplicates').",
    )


# ── Report & Attachment Inputs ───────────────────────────────


class EmailReportInput(StrictInput):
    """Input for report generation.

    type='archive': HTML archive overview report.
    type='network': GraphML network export.
    type='writing': writing style analysis per sender.
    """

    type: Literal["archive", "network", "writing"] = Field(
        ...,
        description="Report type: 'archive', 'network', or 'writing'.",
    )
    output_path: str = Field(
        default="private/exports/report.html",
        description="Output file path (for archive/network types).",
    )
    title: str = Field(
        default="Email Archive Report",
        description="Report title (for archive type).",
    )
    privacy_mode: Literal[
        "full_access",
        "external_counsel_export",
        "internal_complaint_use",
        "witness_sharing",
    ] = Field(
        default="full_access",
        description=(
            "Archive-report privacy mode. Redacted modes suppress direct contact data and, where applicable, "
            "medical or privileged detail in the rendered report."
        ),
    )
    sender: str | None = Field(
        default=None,
        description="Sender to analyze (for writing type). Omit to compare top senders.",
    )
    limit: int = Field(default=10, ge=1, le=50, description="Max results (for writing type).")

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, v: str | None) -> str | None:
        return _validate_output_path(v)


class EmailAttachmentsInput(StrictInput):
    """Input for attachment discovery.

    mode='list': browse all attachments with filters and pagination.
    mode='search': find emails with matching attachments.
    mode='stats': aggregate attachment statistics.
    """

    mode: Literal["list", "search", "stats"] = Field(
        ...,
        description="Attachment mode: 'list', 'search', or 'stats'.",
    )
    filename: str | None = Field(default=None, description="Filter by filename (partial match).")
    extension: str | None = Field(default=None, description="Filter by file extension, e.g. 'pdf'.")
    mime_type: str | None = Field(default=None, description="Filter by MIME type (partial match).")
    sender: str | None = Field(
        default=None,
        description="Filter by sender (partial match, list mode only).",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max results to return.")
    offset: int = Field(default=0, ge=0, description="Pagination offset (list mode only).")


class EmailAdminInput(StrictInput):
    """Input for admin/diagnostic operations.

    action='diagnostics': show resolved runtime settings, embedder state, and MCP budgets.
    action='reingest_bodies': re-parse OLM bodies (requires olm_path).
    action='reembed': re-embed all chunks (optional batch_size).
    action='reingest_metadata': backfill v7 metadata (requires olm_path).
    action='reingest_analytics': backfill language/sentiment (no extra params).
    """

    action: Literal["diagnostics", "reingest_bodies", "reembed", "reingest_metadata", "reingest_analytics"] = Field(
        ...,
        description=("Admin action: 'diagnostics', 'reingest_bodies', 'reembed', 'reingest_metadata', or 'reingest_analytics'."),
    )
    olm_path: str | None = Field(
        default=None,
        description="Path to .olm file (required for reingest_bodies and reingest_metadata).",
        min_length=1,
    )
    force: bool = Field(
        default=False,
        description="Force re-parse all emails (for reingest_bodies only).",
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        description="Chunks per embedding batch (for reembed only).",
    )
