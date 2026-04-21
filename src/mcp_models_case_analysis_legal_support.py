"""Legal-support export models layered on top of core case-analysis inputs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from .mcp_models_base import _validate_output_path
from .mcp_models_case_analysis_manifest import EmailCaseAnalysisInput


class EmailLegalSupportInput(EmailCaseAnalysisInput):
    """Input for durable legal-support MCP tools backed by case analysis."""

    review_mode: Literal["retrieval_only", "exhaustive_matter_review"] = Field(
        default="exhaustive_matter_review",
        description=(
            "Dedicated legal-support tools require exhaustive matter review. "
            "Use exhaustive_matter_review with a supplied matter_manifest so counsel-facing products cannot be mistaken "
            "for retrieval-bounded exploratory analysis."
        ),
    )

    @model_validator(mode="after")
    def validate_legal_support_review_mode(self):
        if self.review_mode != "exhaustive_matter_review":
            raise ValueError(
                "Dedicated legal-support tools require review_mode='exhaustive_matter_review' with matter_manifest. "
                "Use EmailCaseAnalysisInput for retrieval-bounded exploratory analysis."
            )
        return self


class EmailLegalSupportExportInput(EmailLegalSupportInput):
    """Input for portable legal-support exports and handoff bundles."""

    delivery_target: Literal[
        "counsel_handoff",
        "exhibit_register",
        "dashboard",
        "counsel_handoff_bundle",
    ] = Field(
        default="counsel_handoff",
        description=(
            "Which portable artifact to write: counsel handoff, exhibit register, dashboard, or the zipped handoff bundle."
        ),
    )
    delivery_format: Literal["html", "pdf", "json", "csv", "bundle"] = Field(
        default="html",
        description="Artifact format. Bundle exports use 'bundle'. Tabular exports use spreadsheet-safe CSV.",
    )
    output_path: str = Field(
        default="private/exports/legal_support_export.html",
        description="Destination path for the written artifact.",
    )

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, value: str) -> str:
        return _validate_output_path(value)  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_delivery_combo(self):
        if self.delivery_target == "counsel_handoff" and self.delivery_format not in {"html", "pdf"}:
            raise ValueError("counsel_handoff supports only html or pdf delivery_format.")
        if self.delivery_target == "exhibit_register" and self.delivery_format not in {"csv", "json"}:
            raise ValueError("exhibit_register supports only csv or json delivery_format.")
        if self.delivery_target == "dashboard" and self.delivery_format not in {"csv", "json"}:
            raise ValueError("dashboard supports only csv or json delivery_format.")
        if self.delivery_target == "counsel_handoff_bundle" and self.delivery_format != "bundle":
            raise ValueError("counsel_handoff_bundle requires delivery_format='bundle'.")
        return self
