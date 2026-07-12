"""Core payload transformation for case-analysis outputs."""

from __future__ import annotations

from typing import Any

from .case_analysis_transform_stages import transform_payload
from .mcp_models import EmailCaseAnalysisInput


def transform_case_analysis_payload(answer_payload: dict[str, Any], params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Normalize an answer-context payload into the dedicated case-analysis contract."""
    return transform_payload(answer_payload, params)
