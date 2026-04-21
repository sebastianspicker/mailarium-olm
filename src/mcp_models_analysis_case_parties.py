"""Behavioural-analysis case party and org context input models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .mcp_models_base import StrictInput


class CasePartyInput(StrictInput):
    """Structured person reference for behavioural-analysis case intake."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display name for the person in the case scope.",
    )
    email: str | None = Field(
        default=None,
        max_length=254,
        description="Optional email address for the person.",
    )
    role_hint: str | None = Field(
        default=None,
        max_length=120,
        description="Optional role hint such as manager, peer, HR, or admin.",
    )


class InstitutionalActorInput(StrictInput):
    """Structured institutional actor, mailbox, or workflow surface."""

    label: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display label for the institutional actor, mailbox, distribution list, or system surface.",
    )
    actor_type: Literal[
        "institutional_body",
        "shared_mailbox",
        "distribution_list",
        "workflow_surface",
        "system_surface",
        "external_body",
        "other",
    ] = Field(
        ...,
        description="Structured actor classification for one non-person case surface.",
    )
    email: str | None = Field(
        default=None,
        max_length=254,
        description="Optional mailbox or distribution-list email address for the institutional actor.",
    )
    function: str | None = Field(
        default=None,
        max_length=240,
        description="Optional concise function or routing role for the institutional actor.",
    )
    notes: str | None = Field(
        default=None,
        max_length=800,
        description="Optional relevance notes for why this institutional actor matters in the case.",
    )


class RoleFactInput(StrictInput):
    """Operator-supplied structured role/org fact for one actor."""

    person: CasePartyInput = Field(..., description="The actor this structured role fact applies to.")
    role_type: Literal["manager", "peer", "hr", "admin", "external", "direct_report", "employee", "other"] = Field(
        ...,
        description="Structured role classification for the actor.",
    )
    title: str | None = Field(default=None, max_length=160, description="Optional formal title.")
    department: str | None = Field(default=None, max_length=160, description="Optional department or unit.")
    team: str | None = Field(default=None, max_length=160, description="Optional team or subgroup.")
    source: Literal["supplied_fact"] = Field(
        default="supplied_fact",
        description="Structured org facts are explicitly operator-supplied in BA3.",
    )


class ReportingLineInput(StrictInput):
    """Operator-supplied manager/report relationship."""

    manager: CasePartyInput = Field(..., description="Manager or supervising actor.")
    report: CasePartyInput = Field(..., description="Direct report or subordinate actor.")
    source: Literal["supplied_fact"] = Field(
        default="supplied_fact",
        description="Reporting lines are explicitly supplied facts in BA3.",
    )


class DependencyRelationInput(StrictInput):
    """Operator-supplied dependency or control relation relevant to power analysis."""

    controller: CasePartyInput = Field(..., description="Actor with practical control, gatekeeping, or approval power.")
    dependent: CasePartyInput = Field(..., description="Actor dependent on the controller in this context.")
    dependency_type: Literal[
        "approval",
        "information_access",
        "schedule_control",
        "contract_renewal",
        "hr_process",
        "performance_review",
        "complaint_process",
        "resource_access",
        "other",
    ] = Field(
        ...,
        description="Type of dependency relevant to the case.",
    )
    notes: str | None = Field(default=None, max_length=500, description="Optional clarifying notes.")
    source: Literal["supplied_fact"] = Field(
        default="supplied_fact",
        description="Dependency context is explicitly supplied in BA3.",
    )


class VulnerabilityContextInput(StrictInput):
    """Operator-supplied vulnerability or sensitivity context."""

    person: CasePartyInput = Field(..., description="Actor the vulnerability context applies to.")
    context_type: Literal[
        "illness",
        "disability",
        "probation",
        "temporary_contract",
        "complaint_pending",
        "grievance_process",
        "leave",
        "other",
    ] = Field(
        ...,
        description="Structured vulnerability context relevant to dependency or pressure analysis.",
    )
    notes: str | None = Field(default=None, max_length=500, description="Optional clarifying notes.")
    source: Literal["supplied_fact"] = Field(
        default="supplied_fact",
        description="Vulnerability context is explicitly supplied in BA3.",
    )


class BehavioralOrgContextInput(StrictInput):
    """Optional structured org, hierarchy, and power metadata for a case."""

    role_facts: list[RoleFactInput] = Field(
        default_factory=list,
        max_length=50,
        description="Optional structured role or org facts for actors in the case.",
    )
    reporting_lines: list[ReportingLineInput] = Field(
        default_factory=list,
        max_length=50,
        description="Optional structured reporting-line relationships.",
    )
    dependency_relations: list[DependencyRelationInput] = Field(
        default_factory=list,
        max_length=50,
        description="Optional structured practical dependency relations.",
    )
    vulnerability_contexts: list[VulnerabilityContextInput] = Field(
        default_factory=list,
        max_length=50,
        description="Optional structured vulnerability contexts.",
    )
