"""Behavioural-analysis trigger and event input models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .mcp_models_analysis_case_parties import CasePartyInput
from .mcp_models_base import StrictInput


class TriggerEventInput(StrictInput):
    """Explicit trigger event for retaliation-style before/after analysis."""

    trigger_type: Literal[
        "complaint",
        "illness_disability_disclosure",
        "escalation_to_hr",
        "objection_refusal",
        "boundary_assertion",
        "other",
    ] = Field(
        ...,
        description="Structured trigger event type relevant to retaliation analysis.",
    )
    date: str = Field(
        ...,
        min_length=10,
        max_length=40,
        description="Trigger event date or timestamp in ISO-like format.",
    )
    actor: CasePartyInput | None = Field(
        default=None,
        description="Optional actor most directly associated with the trigger event.",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional clarifying notes for the trigger event.",
    )
