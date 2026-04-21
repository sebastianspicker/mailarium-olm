"""Behavioural-analysis case scope input models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from .mcp_models_analysis_case_events import AdverseActionInput, TriggerEventInput
from .mcp_models_analysis_case_parties import BehavioralOrgContextInput, CasePartyInput, InstitutionalActorInput
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
    context_people: list[CasePartyInput] = Field(
        default_factory=list,
        max_length=40,
        description=(
            "Optional additional explicitly named natural persons relevant to the matter without implying a suspected-actor "
            "or comparator role."
        ),
    )
    institutional_actors: list[InstitutionalActorInput] = Field(
        default_factory=list,
        max_length=50,
        description="Optional institutional bodies, shared mailboxes, workflow surfaces, systems, or distribution lists.",
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
    asserted_rights_timeline: list[TriggerEventInput] = Field(
        default_factory=list,
        max_length=20,
        description="Optional explicit rights assertions or protected acts relevant to retaliation framing.",
    )
    alleged_adverse_actions: list[AdverseActionInput] = Field(
        default_factory=list,
        max_length=20,
        description="Optional explicit alleged adverse actions relevant to treatment or retaliation framing.",
    )
    org_context: BehavioralOrgContextInput | None = Field(
        default=None,
        description="Optional structured org, hierarchy, and dependency context for power analysis.",
    )
    comparator_equivalence_notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional notes explaining why selected comparators are genuinely comparable.",
    )
    expected_document_collections: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Optional expected document collections that should exist for this matter.",
    )
    known_missing_records: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Optional records known to be missing or not yet obtained.",
    )
    employment_issue_tags: list[
        Literal[
            "eingruppierung",
            "agg_disability_disadvantage",
            "retaliation_massregelung",
            "mobile_work_home_office",
            "sbv_participation",
            "pr_participation",
            "prevention_bem_sgb_ix_167",
            "medical_recommendations_ignored",
            "task_withdrawal_td_fixation",
            "worktime_control_surveillance",
            "witness_relevance",
            "comparator_evidence",
        ]
    ] = Field(
        default_factory=list,
        max_length=20,
        description=("Optional operator-supplied employment-matter issue tags to organize the record in machine-readable form."),
    )
    employment_issue_tracks: list[
        Literal[
            "disability_disadvantage",
            "retaliation_after_protected_event",
            "eingruppierung_dispute",
            "prevention_duty_gap",
            "participation_duty_gap",
        ]
    ] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Optional neutral employment-matter issue tracks to organize the record for counsel- or HR-facing review "
            "without implying legal liability or statutory satisfaction."
        ),
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

    @field_validator("employment_issue_tracks")
    @classmethod
    def normalize_issue_tracks(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    @field_validator("employment_issue_tags")
    @classmethod
    def normalize_issue_tags(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    @field_validator("expected_document_collections", "known_missing_records")
    @classmethod
    def normalize_text_lists(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            text = " ".join(str(item).split()).strip()
            lowered = text.lower()
            if not text or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(text)
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
        for actor in self.context_people:
            actor_email = (actor.email or "").strip().lower()
            if target_email and actor_email and actor_email == target_email:
                raise ValueError("context_people must not duplicate the target_person email.")
        return self
