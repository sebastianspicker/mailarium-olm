"""MCP input models for evidence management, chain of custody, and dossier tools."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .mcp_models_base import PlainInput, StrictInput, _validate_output_path

EVIDENCE_CATEGORIES = Literal[
    "bossing",
    "harassment",
    "discrimination",
    "retaliation",
    "hostile_environment",
    "micromanagement",
    "exclusion",
    "gaslighting",
    "workload",
    "general",
]

# ── Evidence Management Inputs ──────────────────────────────


class EvidenceAddInput(StrictInput):
    """Input for adding an evidence item."""

    email_uid: str = Field(..., description="UID of the source email (from search results).", min_length=1)
    category: EVIDENCE_CATEGORIES = Field(
        ...,
        description=(
            "Evidence category: bossing, harassment, discrimination, retaliation, "
            "hostile_environment, micromanagement, exclusion, gaslighting, "
            "workload, or general."
        ),
    )
    key_quote: str = Field(
        ...,
        description=("Exact quote from the email body that constitutes evidence. Must appear verbatim in the email text."),
        min_length=1,
    )
    summary: str = Field(
        ...,
        description="Brief description of why this is evidence (1-2 sentences).",
        min_length=1,
    )
    relevance: int = Field(
        ...,
        ge=1,
        le=5,
        description="Relevance rating: 1=tangential, 2=minor, 3=moderate, 4=significant, 5=critical.",
    )
    notes: str = Field(
        default="",
        description="Optional notes for the lawyer or analyst.",
    )


class EvidenceGetInput(PlainInput):
    """Input for getting a single evidence item."""

    evidence_id: int = Field(..., ge=1, description="ID of the evidence item.")


class EvidenceUpdateInput(StrictInput):
    """Input for updating an evidence item."""

    evidence_id: int = Field(..., ge=1, description="ID of the evidence item to update.")
    category: str | None = Field(default=None, description="New evidence category.")
    key_quote: str | None = Field(default=None, description="New exact quote from the email body.")
    summary: str | None = Field(default=None, description="New summary of why this is evidence.")
    relevance: int | None = Field(default=None, ge=1, le=5, description="New relevance rating (1-5).")
    notes: str | None = Field(default=None, description="New notes for the analyst.")


class EvidenceRemoveInput(PlainInput):
    """Input for removing an evidence item."""

    evidence_id: int = Field(..., ge=1, description="ID of the evidence item to remove.")


class EvidenceExportInput(StrictInput):
    """Input for exporting the evidence report."""

    output_path: str = Field(
        default="evidence_report.html",
        description="Output file path for the evidence report.",
    )
    format: Literal["html", "csv", "pdf"] = Field(
        default="html",
        description="Output format: 'html', 'csv', or 'pdf' (pdf requires weasyprint).",
    )
    min_relevance: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Only include items with this minimum relevance.",
    )
    category: str | None = Field(default=None, description="Only include items in this category.")

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, v: str) -> str:
        return _validate_output_path(v)  # type: ignore[return-value]


class EvidenceAddBatchInput(PlainInput):
    """Input for batch-adding evidence items."""

    items: list[EvidenceAddInput] = Field(
        ...,
        description="List of evidence items to add (1-20 per batch).",
        min_length=1,
        max_length=20,
    )


class EvidenceQueryInput(PlainInput):
    """Input for querying evidence items (list, search, or timeline).

    Omit query to list; set query to search. Use sort='date' for timeline view.
    """

    query: str | None = Field(
        default=None,
        description="Text to search for across key_quote, summary, and notes. Omit to list all.",
        max_length=500,
    )
    sort: Literal["relevance", "date"] = Field(
        default="relevance",
        description="Sort order: 'relevance' (default) or 'date' (chronological timeline).",
    )
    category: str | None = Field(default=None, description="Filter by category.")
    min_relevance: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Minimum relevance score.",
    )
    email_uid: str | None = Field(
        default=None,
        description="Filter to evidence from a specific email.",
    )
    limit: int = Field(default=25, ge=1, le=200, description="Max evidence items to return.")
    offset: int = Field(default=0, ge=0, description="Pagination offset for list/timeline modes.")
    include_quotes: bool = Field(
        default=False,
        description="Include full key_quote text. Default: compact mode with 80-char preview.",
    )


class EvidenceOverviewInput(PlainInput):
    """Input for evidence overview (stats + categories combined)."""

    category: str | None = Field(default=None, description="Filter stats by category.")
    min_relevance: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Filter stats by minimum relevance.",
    )


# ── Chain of Custody Inputs ─────────────────────────────────


class CustodyChainInput(PlainInput):
    """Input for viewing chain-of-custody audit trail."""

    target_type: Literal["email", "evidence", "ingestion_run", "export"] | None = Field(
        default=None,
        description="Filter by target type: 'email', 'evidence', 'ingestion_run', 'export'.",
    )
    target_id: str | None = Field(
        default=None,
        description="Filter by target ID (e.g., email UID, evidence ID).",
    )
    action: Literal["ingest_start", "evidence_add", "evidence_update", "evidence_remove", "export", "verify"] | None = Field(
        default=None,
        description=(
            "Filter by action type: 'ingest_start', 'evidence_add', 'evidence_update', 'evidence_remove', 'export', 'verify'."
        ),
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max events to return.")
    compact: bool = Field(
        default=True,
        description="Compact mode: omit details JSON and content_hash. Set false for full audit detail.",
    )


class EmailProvenanceInput(StrictInput):
    """Input for full email provenance lookup."""

    email_uid: str = Field(
        ...,
        description="Email UID to trace provenance for.",
        min_length=1,
    )


class EvidenceProvenanceInput(PlainInput):
    """Input for full evidence provenance lookup."""

    evidence_id: int = Field(
        ...,
        ge=1,
        description="Evidence item ID to trace provenance for.",
    )


# ── Dossier Generation Inputs ───────────────────────────────


class EmailDossierInput(StrictInput):
    """Input for generating or previewing a proof dossier.

    Set preview_only=True to check scope before full generation.
    """

    preview_only: bool = Field(
        default=False,
        description="If true, return counts and scope only (no file generated).",
    )
    output_path: str = Field(
        default="dossier.html",
        description="File path for the generated dossier.",
    )
    format: Literal["html", "pdf"] = Field(
        default="html",
        description="Output format: 'html' or 'pdf' (pdf requires weasyprint).",
    )
    title: str = Field(
        default="Proof Dossier",
        description="Title for the dossier cover page.",
    )
    case_reference: str = Field(default="", description="Case reference number.")
    custodian: str = Field(default="", description="Name of the evidence custodian.")
    prepared_by: str = Field(default="", description="Name/role of preparer.")
    min_relevance: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Only include evidence with this minimum relevance.",
    )
    category: str | None = Field(default=None, description="Only include this category.")
    include_relationships: bool = Field(default=True, description="Include relationship analysis.")
    include_custody: bool = Field(default=True, description="Include chain-of-custody log.")
    persons_of_interest: list[str] | None = Field(
        default=None,
        description="Email addresses to focus relationship analysis on.",
    )

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, v: str) -> str:
        return _validate_output_path(v)  # type: ignore[return-value]
