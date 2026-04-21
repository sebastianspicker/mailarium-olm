"""Behavioural-analysis case scope input models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from .mcp_models_analysis_case_events import TriggerEventInput
from .mcp_models_analysis_case_parties import BehavioralOrgContextInput, CasePartyInput
from .mcp_models_base import DateRangeInput, StrictInput


class BehavioralCaseScopeInput(DateRangeInput, StrictInput):
    """Formal investigation scope for behavioural-analysis workflows."""

    case_label: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Optional analyst-defined case label for easier human reference.",
    )
    target_person: CasePartyInput = Field(
        ...,
        description="The suspected target person for the analysis case.",
    )
    comparator_actors: list[CasePartyInput] = Field(
        default_factory=list,
        max_length=20,
        description="Optional comparator actors for comparative-treatment analysis.",
    )
    suspected_actors: list[CasePartyInput] = Field(
        default_factory=list,
        max_length=20,
        description="Optional list of suspected actors connected to the case.",
    )
    allegation_focus: list[
        Literal[
            "discrimination",
            "bullying",
            "mobbing",
            "hostility",
            "intimidation",
            "exclusion",
            "unequal_treatment",
            "retaliation",
            "manipulation",
            "abuse_of_authority",
            "all",
        ]
    ] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="One or more allegation-focus categories for the case.",
    )
    analysis_goal: Literal[
        "internal_review",
        "lawyer_briefing",
        "formal_complaint",
        "hr_review",
        "neutral_chronology",
        "other",
    ] = Field(
        ...,
        description="The intended use for the analysis output.",
    )
    context_notes: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional context notes supplied by the operator for investigation scoping.",
    )
    trigger_events: list[TriggerEventInput] = Field(
        default_factory=list,
        max_length=20,
        description="Optional explicit trigger events for before/after retaliation analysis.",
    )
    org_context: BehavioralOrgContextInput | None = Field(
        default=None,
        description="Optional structured org, hierarchy, and dependency context for power analysis.",
    )

    @field_validator("allegation_focus")
    @classmethod
    def normalize_allegation_focus(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def validate_actor_set(self):
        target_email = (self.target_person.email or "").strip().lower()
        for actor in self.suspected_actors:
            actor_email = (actor.email or "").strip().lower()
            if target_email and actor_email and actor_email == target_email:
                raise ValueError("suspected_actors must not duplicate the target_person email.")
        for actor in self.comparator_actors:
            actor_email = (actor.email or "").strip().lower()
            if target_email and actor_email and actor_email == target_email:
                raise ValueError("comparator_actors must not duplicate the target_person email.")
        return self
