from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_models_analysis import (
    BehavioralCaseScopeInput,
    BehavioralOrgContextInput,
    CasePartyInput,
    DependencyRelationInput,
    ReportingLineInput,
    RoleFactInput,
    TriggerEventInput,
    VulnerabilityContextInput,
)
from src.mcp_models_analysis_case_events import TriggerEventInput as TriggerEventInputExtracted
from src.mcp_models_analysis_case_parties import (
    BehavioralOrgContextInput as BehavioralOrgContextInputExtracted,
)
from src.mcp_models_analysis_case_parties import (
    CasePartyInput as CasePartyInputExtracted,
)
from src.mcp_models_analysis_case_scope import BehavioralCaseScopeInput as BehavioralCaseScopeInputExtracted


def test_analysis_aggregator_reexports_split_behavioral_models():
    assert CasePartyInput is CasePartyInputExtracted
    assert BehavioralOrgContextInput is BehavioralOrgContextInputExtracted
    assert TriggerEventInput is TriggerEventInputExtracted
    assert BehavioralCaseScopeInput is BehavioralCaseScopeInputExtracted


def test_behavioral_case_scope_validation_matches_pre_split_contract():
    with pytest.raises(ValidationError, match="suspected_actors must not duplicate the target_person email"):
        BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
            suspected_actors=[CasePartyInput(name="Alex Example", email="alex@example.com")],
            allegation_focus=["retaliation"],
            analysis_goal="internal_review",
        )


def test_behavioral_org_context_models_round_trip_through_aggregator():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
        allegation_focus=["retaliation", "retaliation", "exclusion"],
        analysis_goal="hr_review",
        trigger_events=[
            TriggerEventInput(
                trigger_type="complaint",
                date="2026-02-03",
                actor=CasePartyInput(name="Alex Example", email="alex@example.com"),
            )
        ],
        org_context=BehavioralOrgContextInput(
            role_facts=[
                RoleFactInput(
                    person=CasePartyInput(name="Morgan Manager", email="manager@example.com"),
                    role_type="manager",
                )
            ],
            reporting_lines=[
                ReportingLineInput(
                    manager=CasePartyInput(name="Morgan Manager", email="manager@example.com"),
                    report=CasePartyInput(name="Alex Example", email="alex@example.com"),
                )
            ],
            dependency_relations=[
                DependencyRelationInput(
                    controller=CasePartyInput(name="Morgan Manager", email="manager@example.com"),
                    dependent=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    dependency_type="performance_review",
                )
            ],
            vulnerability_contexts=[
                VulnerabilityContextInput(
                    person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    context_type="complaint_pending",
                )
            ],
        ),
    )

    assert scope.allegation_focus == ["retaliation", "exclusion"]
    assert scope.trigger_events[0].trigger_type == "complaint"
    assert scope.org_context is not None
    assert scope.org_context.role_facts[0].role_type == "manager"
    assert scope.org_context.reporting_lines[0].manager.email == "manager@example.com"
