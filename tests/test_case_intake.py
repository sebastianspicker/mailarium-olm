from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.case_intake import build_case_bundle
from src.mcp_models import (
    BehavioralCaseScopeInput,
    BehavioralOrgContextInput,
    CasePartyInput,
    DependencyRelationInput,
    ReportingLineInput,
    RoleFactInput,
    TriggerEventInput,
    VulnerabilityContextInput,
)


def test_behavioral_case_scope_deduplicates_focus_and_builds_bundle():
    scope = BehavioralCaseScopeInput(
        case_label="HR-2026-04",
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com", role_hint="employee"),
        comparator_actors=[
            CasePartyInput(name="Pat Peer", email="pat@example.com", role_hint="employee"),
        ],
        suspected_actors=[
            CasePartyInput(name="Morgan Manager", email="morgan@example.com", role_hint="manager"),
        ],
        date_from="2026-01-01",
        date_to="2026-03-31",
        allegation_focus=["retaliation", "exclusion", "retaliation"],
        analysis_goal="hr_review",
        context_notes="Follow-up after a formal complaint.",
    )

    bundle = build_case_bundle(scope)

    assert scope.allegation_focus == ["retaliation", "exclusion"]
    assert bundle["bundle_id"].startswith("case-")
    assert bundle["required_fields"] == ["target_person", "allegation_focus", "analysis_goal"]
    assert "context_notes" in bundle["provided_optional_fields"]
    assert bundle["scope"]["target_person"]["email"] == "alex@example.com"
    assert bundle["scope"]["comparator_actors"][0]["email"] == "pat@example.com"
    assert bundle["scope"]["suspected_actors"][0]["role_hint"] == "manager"
    assert bundle["scope"]["focus_taxonomy_ids"] == [
        "retaliatory_sequence",
        "escalation_pressure",
        "selective_non_response",
        "exclusion",
        "withholding_information",
    ]
    assert bundle["scope"]["analysis_goal"] == "hr_review"


def test_behavioral_case_scope_includes_structured_org_context_in_bundle():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com", role_hint="employee"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="morgan@example.com", role_hint="manager")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        org_context=BehavioralOrgContextInput(
            role_facts=[
                RoleFactInput(
                    person=CasePartyInput(name="Morgan Manager", email="morgan@example.com"),
                    role_type="manager",
                    title="Head of Unit",
                    department="Operations",
                    team="Ops",
                )
            ],
            reporting_lines=[
                ReportingLineInput(
                    manager=CasePartyInput(name="Morgan Manager", email="morgan@example.com"),
                    report=CasePartyInput(name="Alex Example", email="alex@example.com"),
                )
            ],
            dependency_relations=[
                DependencyRelationInput(
                    controller=CasePartyInput(name="Morgan Manager", email="morgan@example.com"),
                    dependent=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    dependency_type="performance_review",
                    notes="Annual review authority",
                )
            ],
            vulnerability_contexts=[
                VulnerabilityContextInput(
                    person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    context_type="complaint_pending",
                    notes="Formal complaint already filed",
                )
            ],
        ),
    )

    bundle = build_case_bundle(scope)

    assert "org_context" in bundle["provided_optional_fields"]
    assert bundle["scope"]["org_context"]["role_facts"][0]["role_type"] == "manager"
    assert bundle["scope"]["org_context"]["reporting_lines"][0]["manager"]["email"] == "morgan@example.com"
    assert bundle["scope"]["org_context"]["dependency_relations"][0]["dependency_type"] == "performance_review"
    assert bundle["scope"]["org_context"]["vulnerability_contexts"][0]["context_type"] == "complaint_pending"


def test_behavioral_case_scope_includes_trigger_events_in_bundle():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        trigger_events=[
            TriggerEventInput(
                trigger_type="complaint",
                date="2026-02-03",
                actor=CasePartyInput(name="Alex Example", email="alex@example.com"),
                notes="Formal complaint filed.",
            )
        ],
    )

    bundle = build_case_bundle(scope)

    assert "trigger_events" in bundle["provided_optional_fields"]
    assert bundle["scope"]["trigger_events"][0]["trigger_type"] == "complaint"
    assert bundle["scope"]["trigger_events"][0]["date"] == "2026-02-03"
    assert bundle["scope"]["trigger_events"][0]["actor"]["email"] == "alex@example.com"


def test_behavioral_case_scope_rejects_target_duplication_in_actor_set():
    with pytest.raises(ValidationError, match="suspected_actors must not duplicate the target_person email"):
        BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
            suspected_actors=[CasePartyInput(name="Alex Example", email="alex@example.com")],
            allegation_focus=["mobbing"],
            analysis_goal="internal_review",
        )


def test_behavioral_case_scope_rejects_target_duplication_in_comparator_set():
    with pytest.raises(ValidationError, match="comparator_actors must not duplicate the target_person email"):
        BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
            comparator_actors=[CasePartyInput(name="Alex Example", email="alex@example.com")],
            allegation_focus=["unequal_treatment"],
            analysis_goal="internal_review",
        )
