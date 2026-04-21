"""Manifest-backed case-analysis and full-pack input models."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .mcp_models_analysis import BehavioralCaseScopeInput
from .mcp_models_base import StrictInput, _validate_local_read_path, _validate_output_path
from .mcp_models_case_analysis_core import CaseChatExportInput, CaseChatLogEntryInput


class MatterArtifactInput(StrictInput):
    """Structured supplied-record entry for matter-manifest review."""

    source_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
        description="Optional stable identifier for the supplied matter artifact.",
    )
    source_class: Literal[
        "email",
        "attachment",
        "formal_document",
        "personnel_file_record",
        "job_evaluation_record",
        "prevention_record",
        "medical_record",
        "meeting_note",
        "calendar_export",
        "note_record",
        "time_record",
        "attendance_export",
        "participation_record",
        "chat_log",
        "chat_export",
        "archive_bundle",
        "screenshot",
        "other",
    ] = Field(
        ...,
        description="Declared source class for one supplied matter artifact.",
    )
    title: str | None = Field(default=None, min_length=1, max_length=200, description="Human-readable title.")
    date: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description="Optional ISO-like event or document date for the artifact.",
    )
    filename: str | None = Field(default=None, min_length=1, max_length=255, description="Optional filename.")
    source_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=1000,
        description=(
            "Optional local file path for file-backed matter ingestion. "
            "When provided, the repo may extract text and metadata directly from the file."
        ),
    )
    file_size_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Optional file size for file-backed matter artifacts.",
    )
    content_sha256: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="Optional SHA-256 checksum for stable file-backed artifact identity.",
    )
    mime_type: str | None = Field(default=None, min_length=1, max_length=120, description="Optional MIME type.")
    custodian: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional custodian or likely holder of the supplied artifact.",
    )
    acquisition_date: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description="Optional acquisition or export date for the artifact.",
    )
    expected_collection: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional expected document collection or folder label.",
    )
    text: str | None = Field(
        default=None,
        max_length=12000,
        description="Optional visible text or operator-supplied text summary for the artifact.",
    )
    summary: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional short operator summary when full text is unavailable.",
    )
    author: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Optional explicit author or sender for non-email artifacts.",
    )
    recipients: list[str] = Field(
        default_factory=list,
        max_length=40,
        description="Optional direct recipients for letters, emails, or formal records.",
    )
    cc_recipients: list[str] = Field(
        default_factory=list,
        max_length=40,
        description="Optional copied recipients for letter- or email-like artifacts.",
    )
    bcc_recipients: list[str] = Field(
        default_factory=list,
        max_length=40,
        description="Optional blind-copied recipients for email-like artifacts.",
    )
    participants: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Optional participant labels for chat, meeting, or process records.",
    )
    date_start: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description="Optional start date when the artifact refers to a date range rather than a single day.",
    )
    date_end: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description="Optional end date when the artifact refers to a date range rather than a single day.",
    )
    date_is_approximate: bool = Field(
        default=False,
        description="Whether the supplied date is approximate rather than exact.",
    )
    related_email_uid: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Optional related email uid for cross-source linking.",
    )
    review_status: Literal["parsed", "degraded", "unsupported", "excluded", "not_yet_reviewed"] = Field(
        default="parsed",
        description="Operator-declared current review state for the supplied artifact.",
    )
    extraction_state: (
        Literal[
            "text_extracted",
            "ocr_text_extracted",
            "ocr_failed",
            "binary_only",
            "image_embedding_only",
            "excluded",
            "not_reviewed",
            "unsupported",
            "extraction_failed",
            "archive_inventory_extracted",
            "sidecar_text_extracted",
        ]
        | None
    ) = Field(
        default=None,
        description="Optional extraction-state override for fidelity and completeness accounting.",
    )
    evidence_strength: Literal["strong_text", "weak_reference"] | None = Field(
        default=None,
        description="Optional extracted-evidence strength override.",
    )
    ocr_used: bool = Field(default=False, description="Whether OCR was required for the artifact text.")
    failure_reason: str | None = Field(default=None, max_length=200, description="Optional extraction failure reason.")
    excluded_reason: str | None = Field(default=None, max_length=200, description="Optional reason for exclusion.")
    text_source_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=1000,
        description="Optional stable path or handle for the extracted text carrier when it differs from source_path.",
    )
    text_locator: dict[str, object] = Field(
        default_factory=dict,
        description="Optional structured locator for full-document text or recovered sidecar transcripts.",
    )

    @field_validator("participants", "recipients", "cc_recipients", "bcc_recipients")
    @classmethod
    def normalize_artifact_participants(cls, value: list[str]) -> list[str]:
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
    def validate_source_path(cls, value: str | None) -> str | None:
        return _validate_local_read_path(value, field_name="source_path")

    @field_validator("text_source_path")
    @classmethod
    def validate_text_source_path(cls, value: str | None) -> str | None:
        return _validate_local_read_path(value, field_name="text_source_path")


class MatterManifestInput(StrictInput):
    """Structured manifest of supplied matter artifacts for completeness review."""

    manifest_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional stable identifier for the supplied matter manifest.",
    )
    artifacts: list[MatterArtifactInput] = Field(
        default_factory=list,
        max_length=500,
        description="Supplied matter artifacts that should be accounted for in the review ledger.",
    )


class EmailCaseAnalysisInput(StrictInput):
    """Input for dedicated workplace case analysis."""

    case_scope: BehavioralCaseScopeInput = Field(
        ...,
        description=(
            "Structured workplace-case scope for the analysis run. "
            "For retaliation review add trigger_events; for unequal-treatment or discrimination-style review "
            "add comparator_actors; for broader named-person coverage add context_people; for mailbox or routing surfaces "
            "add institutional_actors; for mobbing-, bullying-, or power-heavy review add org_context and context_notes."
        ),
    )
    source_scope: Literal["emails_only", "emails_and_attachments", "mixed_case_file"] = Field(
        ...,
        description=(
            "Declared source set for the case-analysis run. Use mixed_case_file only when chat_log_entries "
            "or other mixed-source records are intentionally supplied alongside the email evidence."
        ),
    )
    analysis_query: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Optional operator override for the internal retrieval query.",
    )
    query_lanes: list[str] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "Optional ordered retrieval lanes for wave-first or German-first evidence gathering. "
            "When omitted, the case-analysis runtime derives conservative lanes automatically."
        ),
    )
    wave_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description="Optional question-execution wave identifier such as 'wave_1' or 'wave_5a'.",
    )
    scan_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Optional progressive scan-session identifier for wave-first retrieval. "
            "Use one wave-level scan id when multiple retrieval lanes should share seen-result state."
        ),
    )
    max_results: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of evidence candidates to pull into the case-analysis bundle.",
    )
    evidence_mode: Literal["retrieval", "forensic", "hybrid"] = Field(
        default="hybrid",
        description="Evidence render policy for the internal analysis query.",
    )
    include_message_appendix: bool = Field(
        default=True,
        description="Include a message-level appendix in the final case-analysis payload.",
    )
    compact_case_evidence: bool = Field(
        default=False,
        description="Request a more compact case-analysis response when budgets or UI constraints matter.",
    )
    privacy_mode: Literal[
        "full_access",
        "external_counsel_export",
        "internal_complaint_use",
        "witness_sharing",
    ] = Field(
        default="full_access",
        description=(
            "Output privacy mode. 'full_access' leaves the case product unredacted. "
            "'external_counsel_export' redacts contact data, 'internal_complaint_use' also redacts privileged and "
            "medical detail, and 'witness_sharing' applies the highest redaction level."
        ),
    )
    output_mode: Literal["full_report", "report_only"] = Field(
        default="full_report",
        description="Return the full analysis payload or the report-focused subset.",
    )
    output_language: Literal["en", "de"] = Field(
        default="de",
        description=(
            "Requested narrative output language for bilingual legal-support products. "
            "Original-language evidence remains preserved separately."
        ),
    )
    translation_mode: Literal["source_only", "translation_aware"] = Field(
        default="source_only",
        description=(
            "Bilingual rendering mode. 'source_only' keeps original-language evidence and summaries together. "
            "'translation_aware' adds explicit separation between original-language quotations and output-language summaries."
        ),
    )
    review_mode: Literal["retrieval_only", "exhaustive_matter_review"] = Field(
        default="retrieval_only",
        description=(
            "Review policy. 'retrieval_only' keeps the current top-k evidence path. "
            "'exhaustive_matter_review' additionally requires a supplied matter manifest and treats it as the full "
            "artifact ledger for chronology, exhibit, and completeness work."
        ),
    )
    chat_log_entries: list[CaseChatLogEntryInput] = Field(
        default_factory=list,
        max_length=100,
        description=(
            "Optional structured chat-log records for mixed-source case analysis. Required when source_scope is mixed_case_file."
        ),
    )
    chat_exports: list[CaseChatExportInput] = Field(
        default_factory=list,
        max_length=100,
        description=(
            "Optional native chat-export files for mixed-source case analysis. "
            "Use this when the operator has export files but does not want to pre-structure chat_log_entries."
        ),
    )
    matter_manifest: MatterManifestInput | None = Field(
        default=None,
        description="Optional supplied-artifact manifest for completeness accounting and exhaustive matter review.",
    )
    matter_factual_context: str | None = Field(
        default=None,
        max_length=30000,
        description=(
            "Optional preserved operator-supplied factual matter context carried through prompt preflight into strict "
            "case JSON. This preserves narrative or markdown context without auto-promoting it into structured "
            "case_scope facts."
        ),
    )

    @model_validator(mode="after")
    def validate_case_scope_requirements(self):
        case_scope = self.case_scope
        if case_scope.date_from is None:
            raise ValueError(
                "case_scope.date_from is required for dedicated case analysis. "
                "Provide a bounded review window so chronology and before/after comparisons stay interpretable."
            )
        if case_scope.date_to is None:
            raise ValueError(
                "case_scope.date_to is required for dedicated case analysis. "
                "Provide a bounded review window so chronology and before/after comparisons stay interpretable."
            )
        has_manifest_artifacts = bool(self.matter_manifest is not None and self.matter_manifest.artifacts)
        if (
            self.source_scope == "mixed_case_file"
            and not self.chat_log_entries
            and not self.chat_exports
            and not has_manifest_artifacts
        ):
            raise ValueError(
                "mixed_case_file requires at least one of chat_log_entries, chat_exports, or matter_manifest artifacts. "
                "If you only want email evidence, use emails_only or emails_and_attachments instead."
            )
        if self.review_mode == "exhaustive_matter_review" and self.matter_manifest is None:
            raise ValueError(
                "exhaustive_matter_review requires matter_manifest so the run can account for every supplied artifact."
            )
        if (
            self.review_mode == "exhaustive_matter_review"
            and self.matter_manifest is not None
            and not self.matter_manifest.artifacts
        ):
            raise ValueError("exhaustive_matter_review requires at least one matter_manifest artifact.")
        return self

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


class EmailCaseExecuteWaveInput(EmailCaseAnalysisInput):
    """Input for one shared campaign wave execution."""

    scan_id_prefix: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional shared scan-session prefix used to derive the canonical per-wave scan id.",
    )

    @model_validator(mode="after")
    def validate_required_wave_id(self) -> EmailCaseExecuteWaveInput:
        if self.wave_id is None:
            raise ValueError("wave_id is required")
        return self


class EmailCaseExecuteAllWavesInput(EmailCaseAnalysisInput):
    """Input for the shared all-wave campaign execution workflow."""

    scan_id_prefix: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional shared scan-session prefix used to derive each canonical per-wave scan id.",
    )
    include_payloads: bool = Field(
        default=False,
        description="Include each per-wave payload in addition to the machine-readable summary rows.",
    )


def _harvest_limit_field(default: int = 12) -> int:
    return Field(
        default=default,
        ge=1,
        le=50,
        description="Maximum number of body and attachment candidates to persist per wave.",
    )


def _promote_limit_field(default: int = 4) -> int:
    return Field(
        default=default,
        ge=0,
        le=20,
        description="Maximum number of exact verified body quotes to auto-promote per wave.",
    )


class CaseGatherEvidenceLimitsInput(StrictInput):
    """Shared gather-evidence bounds for CLI and MCP entrypoints."""

    harvest_limit_per_wave: int = _harvest_limit_field()
    promote_limit_per_wave: int = _promote_limit_field()


class EmailCaseGatherEvidenceInput(EmailCaseExecuteAllWavesInput):
    """Input for the wave-driven evidence-gathering workflow."""

    run_id: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Stable run identifier used for harvested evidence-candidate persistence.",
    )
    phase_id: str = Field(
        ...,
        min_length=1,
        max_length=40,
        description="Stable phase identifier used for harvested evidence-candidate persistence.",
    )
    harvest_limit_per_wave: int = _harvest_limit_field()
    promote_limit_per_wave: int = _promote_limit_field()


class EmailCasePromptPreflightInput(StrictInput):
    """Input for bounded prompt-to-intake preflight before structured case analysis."""

    prompt_text: str = Field(
        ...,
        min_length=1,
        max_length=30000,
        description=(
            "Natural-language matter description or task prompt. This is parsed conservatively into a draft intake "
            "and an explicit missing-information report. It does not itself authorize exhaustive legal-support review."
        ),
    )
    output_language: Literal["en", "de"] = Field(
        default="de",
        description="Requested output language for the preflight summary.",
    )
    default_source_scope: Literal["emails_only", "emails_and_attachments", "mixed_case_file"] = Field(
        default="emails_and_attachments",
        description="Fallback source scope when the prompt does not clearly describe mixed-source material.",
    )
    assume_date_to_today: bool = Field(
        default=True,
        description=(
            "Whether open-ended ranges such as 'to the present' should draft date_to as today's date instead of "
            "leaving it unresolved."
        ),
    )
    today: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Injectable current date for deterministic tests and prompt-range resolution.",
    )

    @field_validator("today")
    @classmethod
    def validate_today(cls, value: str) -> str:
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError("today must be in YYYY-MM-DD format.")
        return value


class EmailCaseFullPackInput(StrictInput):
    """Input for compile-only full-pack intake from prompt plus supplied materials."""

    prompt_text: str = Field(
        ...,
        min_length=1,
        max_length=30000,
        description="Natural-language matter prompt used to draft the structured full-pack intake.",
    )
    materials_dir: str = Field(
        ...,
        min_length=1,
        description="Absolute or relative path to the supplied matter materials directory.",
    )
    output_language: Literal["en", "de"] = Field(
        default="de",
        description="Requested narrative output language for the compiled legal-support input.",
    )
    translation_mode: Literal["source_only", "translation_aware"] = Field(
        default="source_only",
        description="Bilingual rendering mode for the compiled legal-support input.",
    )
    default_source_scope: Literal["emails_only", "emails_and_attachments", "mixed_case_file"] = Field(
        default="emails_and_attachments",
        description="Fallback source scope when the prompt does not clearly describe mixed-source material.",
    )
    assume_date_to_today: bool = Field(
        default=True,
        description="Whether open-ended ranges in the prompt should draft date_to as today's date.",
    )
    today: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Injectable current date for deterministic prompt-range resolution.",
    )
    intake_overrides: dict[str, object] = Field(
        default_factory=dict,
        description=(
            "Optional structured overrides applied after prompt preflight. Supported keys currently include "
            "'case_scope', 'source_scope', 'output_language', and 'translation_mode'."
        ),
    )
    compile_only: bool = Field(
        default=False,
        description="When true, stop after blocker/ready compilation and do not run the downstream exhaustive workflow.",
    )
    privacy_mode: Literal[
        "full_access",
        "external_counsel_export",
        "internal_complaint_use",
        "witness_sharing",
    ] = Field(
        default="external_counsel_export",
        description="Privacy mode for the downstream legal-support run and optional export.",
    )
    delivery_target: Literal[
        "counsel_handoff",
        "exhibit_register",
        "dashboard",
        "counsel_handoff_bundle",
    ] = Field(
        default="counsel_handoff_bundle",
        description="Which artifact to export when output_path is provided.",
    )
    delivery_format: Literal["html", "pdf", "json", "csv", "bundle"] = Field(
        default="bundle",
        description="Delivery format for optional full-pack export output.",
    )
    output_path: str | None = Field(
        default=None,
        description="Optional path for a written export artifact. Omit to return the full-pack payload only.",
    )

    @field_validator("today")
    @classmethod
    def validate_full_pack_today(cls, value: str) -> str:
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError("today must be in YYYY-MM-DD format.")
        return value

    @field_validator("materials_dir")
    @classmethod
    def validate_materials_dir(cls, value: str) -> str:
        validated = _validate_local_read_path(value, field_name="materials_dir")
        if validated is None:
            raise ValueError("materials_dir is required")
        resolved = Path(validated).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(f"materials_dir must resolve to an existing directory: {resolved}")
        return validated

    @field_validator("output_path")
    @classmethod
    def validate_full_pack_output_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_output_path(value)

    @model_validator(mode="after")
    def validate_full_pack_delivery_combo(self):
        if self.output_path is None:
            return self
        if self.delivery_target == "counsel_handoff" and self.delivery_format not in {"html", "pdf"}:
            raise ValueError("counsel_handoff supports only html or pdf delivery_format.")
        if self.delivery_target == "exhibit_register" and self.delivery_format not in {"csv", "json"}:
            raise ValueError("exhibit_register supports only csv or json delivery_format.")
        if self.delivery_target == "dashboard" and self.delivery_format not in {"csv", "json"}:
            raise ValueError("dashboard supports only csv or json delivery_format.")
        if self.delivery_target == "counsel_handoff_bundle" and self.delivery_format != "bundle":
            raise ValueError("counsel_handoff_bundle requires delivery_format='bundle'.")
        return self
