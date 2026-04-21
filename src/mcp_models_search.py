"""MCP input models for search, browse, export, and scan tools."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator

from . import mcp_models_case_analysis as _mcp_models_case_analysis
from .mcp_models_base import (
    DateRangeInput,
    PlainInput,
    StrictInput,
    _validate_output_path,
    _validate_readable_file_path,
    _validate_runtime_path,
)

CaseChatLogEntryInput = _mcp_models_case_analysis.CaseChatLogEntryInput
CaseChatExportInput = _mcp_models_case_analysis.CaseChatExportInput
EmailAnswerContextInput = _mcp_models_case_analysis.EmailAnswerContextInput
EmailCaseAnalysisInput = _mcp_models_case_analysis.EmailCaseAnalysisInput
EmailLegalSupportInput = _mcp_models_case_analysis.EmailLegalSupportInput
EmailLegalSupportExportInput = _mcp_models_case_analysis.EmailLegalSupportExportInput
MatterArtifactInput = _mcp_models_case_analysis.MatterArtifactInput
MatterManifestInput = _mcp_models_case_analysis.MatterManifestInput

# ── Core Search Inputs ───────────────────────────────────────


class EmailSearchStructuredInput(DateRangeInput, StrictInput):
    """Structured JSON search input for automation clients."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Semantic search query (natural language).",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=30,
        description="Number of results to return (1-30).",
        validation_alias=AliasChoices("top_k", "max_results"),
    )
    sender: str | None = Field(default=None, description="Filter by sender (partial match).")
    subject: str | None = Field(default=None, description="Filter by subject (partial match).")
    folder: str | None = Field(default=None, description="Filter by folder name (partial match).")
    cc: str | None = Field(default=None, description="CC recipient filter (partial match).")
    to: str | None = Field(default=None, description="To recipient filter (partial match).")
    bcc: str | None = Field(default=None, description="BCC recipient filter (partial match).")
    has_attachments: bool | None = Field(default=None, description="Filter by attachment presence.")
    priority: int | None = Field(default=None, ge=0, description="Minimum priority level (emails with priority >= this value).")
    email_type: Literal["reply", "forward", "original"] | None = Field(
        default=None,
        description="Filter by email type: 'reply', 'forward', or 'original'.",
    )
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold (0.0-1.0).",
    )
    rerank: bool = Field(
        default=False,
        description="Re-rank results with cross-encoder for better precision (slower).",
    )
    hybrid: bool = Field(
        default=False,
        description="Use hybrid semantic + BM25 keyword search for better recall.",
    )
    topic_id: int | None = Field(
        default=None,
        ge=0,
        description="Filter to emails assigned to this topic (from email_topics tool).",
    )
    cluster_id: int | None = Field(
        default=None,
        ge=0,
        description="Filter to emails in this cluster (from email_clusters tool).",
    )
    expand_query: bool = Field(
        default=False,
        description="Expand query with semantically related terms for better recall.",
        validation_alias=AliasChoices("expand_query", "query_expansion"),
    )
    category: str | None = Field(
        default=None,
        description="Filter by Outlook category name (partial match). E.g., 'Meeting'.",
    )
    is_calendar: bool | None = Field(
        default=None,
        description="Filter by calendar/meeting messages. True = only calendar, False = exclude.",
    )
    attachment_name: str | None = Field(
        default=None,
        description="Filter by attachment filename (partial match). E.g., 'report' or 'budget.xlsx'.",
    )
    attachment_type: str | None = Field(
        default=None,
        description="Filter by attachment file extension. E.g., 'pdf', 'docx', 'xlsx'.",
    )
    scan_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Scan session ID for progressive search. Excludes previously seen emails and tracks new ones.",
    )


class FindSimilarInput(StrictInput):
    """Input for finding similar emails."""

    uid: str | None = Field(default=None, description="Email UID to find similar emails for.")
    query: str | None = Field(default=None, description="Query text to find similar emails for.")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results to return (1-50).")
    scan_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Scan session ID for progressive search. Excludes previously seen emails and tracks new ones.",
    )

    @model_validator(mode="after")
    def at_least_one_input(self):
        if not self.uid and not self.query:
            raise ValueError("Provide at least one of uid or query.")
        return self


class EmailTriageInput(DateRangeInput, StrictInput):
    """Input for fast-triage email scanning with ultra-compact results."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language query for triage scanning.",
    )
    top_k: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Results to return (1-100). Use high values to avoid missing evidence.",
    )
    preview_chars: int = Field(
        default=200,
        ge=0,
        le=500,
        description="Body preview per result. 0=metadata only, 200=decide relevance, 500=extract quotes.",
    )
    sender: str | None = Field(default=None, description="Filter by sender (partial match).")
    folder: str | None = Field(default=None, description="Filter by folder name.")
    has_attachments: bool | None = Field(default=None, description="Filter by attachment presence.")
    hybrid: bool = Field(
        default=False,
        description="Use hybrid semantic + keyword search for better recall.",
    )
    scan_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Scan session ID for progressive search. Excludes previously seen emails and tracks new ones.",
    )


# ── Archive Info Inputs ──────────────────────────────────────


class ListSendersInput(PlainInput):
    """Input for listing senders."""

    limit: int = Field(
        default=30,
        description="Max number of senders to return, sorted by email count.",
        ge=1,
        le=200,
    )


# ── Ingestion Input ──────────────────────────────────────────


class EmailIngestInput(StrictInput):
    """Input for ingesting an OLM email archive."""

    olm_path: str = Field(
        ...,
        description="Absolute path to the .olm file to ingest.",
        min_length=1,
    )
    max_emails: int | None = Field(
        default=None,
        description="Optional cap on number of emails to parse.",
        ge=1,
    )
    batch_size: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Chunk-write batch size for ingest.",
    )
    dry_run: bool = Field(
        default=False,
        description="If true, parse and chunk without writing to the database.",
    )
    extract_attachments: bool = Field(
        default=False,
        description="If true, extract and index text content from attachments (PDF, DOCX, XLSX, text).",
    )
    extract_entities: bool = Field(
        default=False,
        description="If true, extract named entities (people, orgs, locations) during ingestion.",
    )
    embed_images: bool = Field(
        default=False,
        description=(
            "If true, embed image attachments (JPG, PNG, etc.) using Visualized-BGE-M3 "
            "for cross-modal search. Automatically enables extract_attachments."
        ),
    )
    incremental: bool = Field(
        default=False,
        description="If true, skip emails already marked complete in the ingest ledger.",
    )
    timing: bool = Field(
        default=False,
        description="If true, include parse/queue/sqlite/entity/analytics/embed timing buckets.",
    )
    chromadb_path: str | None = Field(
        default=None,
        description="Optional custom ChromaDB directory for the ingest run.",
    )
    sqlite_path: str | None = Field(
        default=None,
        description="Optional custom SQLite metadata database path for the ingest run.",
    )

    @field_validator("olm_path")
    @classmethod
    def validate_olm_path(cls, value: str) -> str:
        validated = _validate_readable_file_path(value, field_name="olm_path")
        if validated is None:
            raise ValueError("olm_path is required")
        if Path(validated).suffix.lower() != ".olm":
            raise ValueError("olm_path must point to a .olm archive")
        return validated

    @field_validator("chromadb_path")
    @classmethod
    def validate_chromadb_path(cls, value: str | None) -> str | None:
        return _validate_runtime_path(value, field_name="chromadb_path")

    @field_validator("sqlite_path")
    @classmethod
    def validate_sqlite_path(cls, value: str | None) -> str | None:
        return _validate_runtime_path(value, field_name="sqlite_path")


# ── Export & Browse Inputs ──────────────────────────────────


class EmailExportInput(StrictInput):
    """Input for exporting a single email or conversation thread as HTML/PDF.

    Provide exactly one of ``uid`` (single email) or ``conversation_id`` (thread).
    """

    uid: str | None = Field(
        default=None,
        description="Email UID to export a single email.",
        min_length=1,
    )
    conversation_id: str | None = Field(
        default=None,
        description="Conversation thread ID to export a full thread.",
        min_length=1,
    )
    output_path: str | None = Field(
        default=None,
        description="File path to save export. If omitted, returns HTML string.",
    )
    format: Literal["html", "pdf"] = Field(
        default="html",
        description="Output format: 'html' or 'pdf' (pdf requires weasyprint).",
    )
    render_mode: Literal["retrieval", "forensic"] = Field(
        default="retrieval",
        description="Body render mode: 'retrieval' for normalized text or 'forensic' for source-preserved body text.",
    )

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, v: str | None) -> str | None:
        return _validate_output_path(v)

    @model_validator(mode="after")
    def exactly_one_id(self):
        if self.uid and self.conversation_id:
            raise ValueError("Provide exactly one of uid or conversation_id, not both.")
        if not self.uid and not self.conversation_id:
            raise ValueError("Provide exactly one of uid or conversation_id.")
        if self.format == "pdf" and self.output_path is None:
            raise ValueError("pdf export requires output_path; omit output_path only for in-memory HTML export.")
        return self


class BrowseInput(DateRangeInput, PlainInput):
    """Input for paginated email browsing, category listing, and calendar browsing."""

    offset: int = Field(default=0, ge=0, description="Starting position.")
    limit: int = Field(default=10, ge=1, le=50, description="Emails per page.")
    folder: str | None = Field(default=None, description="Filter by folder (exact match).")
    sender: str | None = Field(default=None, description="Filter by sender (partial match).")
    category: str | None = Field(default=None, description="Filter by category (exact match).")
    sort_order: Literal["asc", "desc"] = Field(
        default="desc",
        description="Sort order: 'asc' (oldest first) or 'desc' (newest first).",
    )
    include_body: bool = Field(
        default=False,
        description="Include body text in results (default off to save context).",
    )
    render_mode: Literal["retrieval", "forensic"] = Field(
        default="retrieval",
        description="Body render mode when include_body=true: 'retrieval' or 'forensic'.",
    )
    is_calendar: bool | None = Field(
        default=None,
        description="Filter by calendar/meeting messages. True = only calendar emails.",
    )
    list_categories: bool = Field(
        default=False,
        description="If true, return category list with counts instead of emails.",
    )


class EmailDeepContextInput(StrictInput):
    """Input for deep single-email analysis combining body, thread, evidence, and sender."""

    uid: str = Field(
        ...,
        min_length=1,
        description="Email UID to analyze in depth.",
        validation_alias=AliasChoices("uid", "email_uid"),
    )
    include_thread: bool = Field(default=True, description="Include thread summary and timeline.")
    include_evidence: bool = Field(default=True, description="Include existing evidence from this email.")
    include_sender_stats: bool = Field(
        default=True,
        description="Include sender communication profile.",
        validation_alias=AliasChoices("include_sender_stats", "include_sender_profile"),
    )
    include_conversation_debug: bool = Field(
        default=False,
        description="Include segments and inferred-thread debug metadata.",
    )
    render_mode: Literal["retrieval", "forensic"] = Field(
        default="retrieval",
        description="Body render mode for the returned email body: 'retrieval' or 'forensic'.",
    )
    max_body_chars: int | None = Field(
        default=None,
        ge=0,
        description="Max body text chars (0=unlimited, None=use profile default).",
    )


# ── Discovery & Scan Inputs ─────────────────────────────────


class EmailDiscoveryInput(StrictInput):
    """Input for keyword/suggestion discovery.

    mode='keywords': top keywords (filterable by sender/folder).
    mode='suggestions': categorized search suggestions.
    """

    mode: Literal["keywords", "suggestions"] = Field(
        ...,
        description="Discovery mode: 'keywords' or 'suggestions'.",
    )
    sender: str | None = Field(default=None, description="Filter keywords by sender email.")
    folder: str | None = Field(default=None, description="Filter keywords by folder name.")
    limit: int = Field(default=30, ge=1, le=200, description="Max results to return.")


class EmailScanInput(StrictInput):
    """Input for scan session management.

    action='status': session stats (seen count, candidate counts).
    action='flag': flag UIDs as candidates with a label.
    action='candidates': return flagged candidates, optionally filtered.
    action='reset': clear a session (or all if scan_id='__all__').
    """

    action: Literal["status", "flag", "candidates", "reset"] = Field(
        ...,
        description="Scan action: 'status', 'flag', 'candidates', or 'reset'.",
    )
    scan_id: str = Field(
        ...,
        description="Scan session identifier (e.g., 'investigation_2026', 'harassment_case').",
        min_length=1,
        max_length=100,
    )
    uids: list[str] | None = Field(
        default=None,
        description="Email UIDs to flag (for action='flag'). Max 50 per call.",
        max_length=50,
    )
    label: str | None = Field(
        default=None,
        description="Label for flagging or filtering candidates (e.g., 'bossing', 'relevant', 'maybe').",
    )
    phase: int | None = Field(
        default=None,
        ge=1,
        le=3,
        description="Phase marker: 1=scan, 2=refine, 3=deep.",
    )
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Relevance score to record with flagged candidates.",
    )
