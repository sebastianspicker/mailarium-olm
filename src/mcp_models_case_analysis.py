"""Case-analysis MCP input models extracted from search-facing schemas."""

from __future__ import annotations

from .mcp_models_case_analysis_core import (
    CaseChatExportInput,
    CaseChatLogEntryInput,
    EmailAnswerContextInput,
)
from .mcp_models_case_analysis_legal_support import EmailLegalSupportExportInput, EmailLegalSupportInput
from .mcp_models_case_analysis_manifest import (
    EmailCaseAnalysisInput,
    EmailCaseExecuteAllWavesInput,
    EmailCaseExecuteWaveInput,
    EmailCaseFullPackInput,
    EmailCaseGatherEvidenceInput,
    EmailCasePromptPreflightInput,
    MatterArtifactInput,
    MatterManifestInput,
)

__all__ = [
    "CaseChatExportInput",
    "CaseChatLogEntryInput",
    "EmailAnswerContextInput",
    "EmailCaseAnalysisInput",
    "EmailCaseExecuteAllWavesInput",
    "EmailCaseExecuteWaveInput",
    "EmailCaseFullPackInput",
    "EmailCaseGatherEvidenceInput",
    "EmailCasePromptPreflightInput",
    "EmailLegalSupportExportInput",
    "EmailLegalSupportInput",
    "MatterArtifactInput",
    "MatterManifestInput",
]
