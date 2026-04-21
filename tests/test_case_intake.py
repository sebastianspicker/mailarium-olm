from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.case_intake import build_case_bundle, build_case_intake_guidance
from src.mcp_models import (
    AdverseActionInput,
    BehavioralCaseScopeInput,
    BehavioralOrgContextInput,
    CasePartyInput,
    DependencyRelationInput,
    InstitutionalActorInput,
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
        context_people=[
            CasePartyInput(name="Lara Langer", email="lara.langer@example.test"),
        ],
        institutional_actors=[
            InstitutionalActorInput(
                label="HR mailbox",
                actor_type="shared_mailbox",
                email="hr-mailbox@example.test",
                function="HR gatekeeper and notice route",
            )
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
    assert bundle["scope"]["context_people"][0]["email"] == "lara.langer@example.test"
    assert bundle["scope"]["institutional_actors"][0]["email"] == "hr-mailbox@example.test"
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


def test_behavioral_case_scope_rejects_target_duplication_in_context_people():
    with pytest.raises(ValidationError, match="context_people must not duplicate the target_person email"):
        BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
            context_people=[CasePartyInput(name="Alex Example", email="alex@example.com")],
            allegation_focus=["mobbing"],
            analysis_goal="internal_review",
        )


def test_behavioral_case_scope_emits_operator_guidance_for_weak_high_stakes_intake():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation", "unequal_treatment", "mobbing"],
        analysis_goal="lawyer_briefing",
    )

    guidance = build_case_intake_guidance(scope)
    bundle = build_case_bundle(scope)

    assert guidance["status"] == "degraded"
    assert guidance["supports_retaliation_analysis"] is False
    assert guidance["supports_comparator_analysis"] is False
    assert guidance["supports_power_analysis"] is False
    assert guidance["missing_recommended_fields"] == [
        "suspected_actors",
        "comparator_actors",
        "trigger_events",
        "alleged_adverse_actions",
        "org_context",
        "context_notes",
        "comparator_equivalence_notes",
        "expected_document_collections",
        "known_missing_records",
    ]
    assert [item["code"] for item in guidance["warnings"]] == [
        "retaliation_focus_without_trigger_events",
        "retaliation_focus_without_alleged_adverse_actions",
        "unequal_treatment_focus_without_comparators",
        "comparator_review_without_equivalence_notes",
        "power_focused_review_without_org_context",
        "high_stakes_goal_without_context_notes",
        "suspected_actors_not_supplied",
    ]
    assert [item["field"] for item in guidance["recommended_next_inputs"]] == [
        "trigger_events",
        "alleged_adverse_actions",
        "comparator_actors",
        "comparator_equivalence_notes",
        "org_context",
        "context_notes",
        "suspected_actors",
    ]
    assert bundle["intake_guidance"] == guidance


def test_behavioral_case_scope_emits_employment_issue_frameworks() -> None:
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation", "discrimination"],
        analysis_goal="lawyer_briefing",
        comparator_actors=[CasePartyInput(name="Pat Peer", email="pat@example.com")],
        trigger_events=[
            TriggerEventInput(
                trigger_type="complaint",
                date="2026-02-03",
                actor=CasePartyInput(name="Alex Example", email="alex@example.com"),
            )
        ],
        org_context=BehavioralOrgContextInput(
            vulnerability_contexts=[
                VulnerabilityContextInput(
                    person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    context_type="disability",
                    notes="Documented disability context.",
                )
            ]
        ),
        context_notes="SBV consultation and BEM prevention steps appear missing after the complaint.",
        employment_issue_tags=[
            "sbv_participation",
            "prevention_bem_sgb_ix_167",
            "sbv_participation",
        ],
        employment_issue_tracks=[
            "disability_disadvantage",
            "retaliation_after_protected_event",
            "participation_duty_gap",
            "disability_disadvantage",
        ],
    )

    guidance = build_case_intake_guidance(scope)
    bundle = build_case_bundle(scope)

    assert scope.employment_issue_tracks == [
        "disability_disadvantage",
        "retaliation_after_protected_event",
        "participation_duty_gap",
    ]
    assert scope.employment_issue_tags == [
        "sbv_participation",
        "prevention_bem_sgb_ix_167",
    ]
    frameworks = guidance["employment_issue_frameworks"]
    assert [item["issue_track"] for item in frameworks] == scope.employment_issue_tracks
    assert frameworks[0]["intake_status"] == "ready_for_issue_spotting"
    assert frameworks[1]["required_proof_elements"]
    assert frameworks[2]["missing_document_checklist"]
    assert bundle["scope"]["employment_issue_track_titles"] == [
        "Disability-Related Disadvantage",
        "Retaliation After Protected or Participation Event",
        "Participation-Duty Gap",
    ]
    assert bundle["scope"]["employment_issue_frameworks"] == frameworks
    assert bundle["scope"]["employment_issue_tags"] == [
        "sbv_participation",
        "prevention_bem_sgb_ix_167",
        "agg_disability_disadvantage",
        "retaliation_massregelung",
        "comparator_evidence",
    ]
    assert bundle["scope"]["employment_issue_tag_payloads"][0]["assignment_basis"] == "operator_supplied"
    assert any(
        payload["tag_id"] == "retaliation_massregelung" and payload["assignment_basis"] == "bounded_inference"
        for payload in bundle["scope"]["employment_issue_tag_payloads"]
    )


def test_behavioral_case_scope_includes_extended_legal_support_intake_fields() -> None:
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation", "unequal_treatment"],
        analysis_goal="lawyer_briefing",
        comparator_actors=[CasePartyInput(name="Pat Peer", email="pat@example.com")],
        trigger_events=[TriggerEventInput(trigger_type="complaint", date="2026-02-01")],
        asserted_rights_timeline=[TriggerEventInput(trigger_type="escalation_to_hr", date="2026-02-03")],
        alleged_adverse_actions=[AdverseActionInput(action_type="project_removal", date="2026-02-10")],
        comparator_equivalence_notes="Same manager, same team, same approval workflow.",
        expected_document_collections=["Personnel file", "time system export", "SBV file"],
        known_missing_records=["BEM invitation minutes", "calendar invite for review meeting"],
        context_notes="Retaliation and participation review.",
    )

    guidance = build_case_intake_guidance(scope)
    bundle = build_case_bundle(scope)

    assert bundle["scope"]["asserted_rights_timeline"][0]["trigger_type"] == "escalation_to_hr"
    assert bundle["scope"]["alleged_adverse_actions"][0]["action_type"] == "project_removal"
    assert bundle["scope"]["comparator_equivalence_notes"] == "Same manager, same team, same approval workflow."
    assert bundle["scope"]["expected_document_collections"] == ["Personnel file", "time system export", "SBV file"]
    assert bundle["scope"]["known_missing_records"] == [
        "BEM invitation minutes",
        "calendar invite for review meeting",
    ]
    assert "alleged_adverse_actions" in guidance["recommended_fields_present"]
    assert "comparator_equivalence_notes" in guidance["recommended_fields_present"]
