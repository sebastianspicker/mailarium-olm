from __future__ import annotations

from src.actor_resolution import resolve_actor_graph
from src.mcp_models import (
    BehavioralCaseScopeInput,
    BehavioralOrgContextInput,
    CasePartyInput,
    DependencyRelationInput,
    ReportingLineInput,
    RoleFactInput,
    VulnerabilityContextInput,
)
from src.power_context import apply_power_context_to_actor_graph, build_power_context


def test_build_power_context_marks_missing_org_context_and_exposes_inferred_hints():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com", role_hint="employee"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com", role_hint="manager")],
        allegation_focus=["retaliation"],
        analysis_goal="internal_review",
    )
    actor_graph = resolve_actor_graph(case_scope=scope, candidates=[], attachment_candidates=[], full_map={})

    power_context = build_power_context(scope, actor_graph)

    assert power_context["org_context_provided"] is False
    assert power_context["missing_org_context"] is True
    assert power_context["supplied_role_facts"] == []
    assert power_context["inferred_hierarchy_hints"] == [
        {
            "actor_id": next(
                actor["actor_id"] for actor in actor_graph["actors"] if actor["primary_email"] == "manager@example.com"
            ),
            "hint": "manager",
            "source": "case_party.role_hint",
        }
    ]


def test_build_power_context_and_actor_graph_apply_supplied_role_dependency_and_vulnerability():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com", role_hint="employee"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com", role_hint="manager")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        org_context=BehavioralOrgContextInput(
            role_facts=[
                RoleFactInput(
                    person=CasePartyInput(name="Morgan Manager", email="manager@example.com"),
                    role_type="manager",
                    title="Head of Unit",
                    department="Operations",
                    team="Ops",
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
    actor_graph = resolve_actor_graph(case_scope=scope, candidates=[], attachment_candidates=[], full_map={})

    power_context = build_power_context(scope, actor_graph)
    apply_power_context_to_actor_graph(actor_graph, power_context)

    assert power_context["org_context_provided"] is True
    assert power_context["missing_org_context"] is False
    manager_fact = power_context["supplied_role_facts"][0]
    assert manager_fact["role_type"] == "manager"
    assert manager_fact["person"]["actor_id"]
    reporting_line = power_context["reporting_lines"][0]
    assert reporting_line["manager"]["actor_id"]
    assert reporting_line["report"]["actor_id"]
    dependency = power_context["dependency_relations"][0]
    assert dependency["dependency_type"] == "performance_review"
    vulnerability = power_context["vulnerability_contexts"][0]
    assert vulnerability["context_type"] == "complaint_pending"

    manager_actor = next(actor for actor in actor_graph["actors"] if actor["primary_email"] == "manager@example.com")
    alex_actor = next(actor for actor in actor_graph["actors"] if actor["primary_email"] == "alex@example.com")
    assert manager_actor["role_context"]["supplied_role_facts"][0]["role_type"] == "manager"
    assert manager_actor["role_context"]["dependencies_as_controller"][0]["dependency_type"] == "performance_review"
    assert alex_actor["role_context"]["dependencies_as_dependent"][0]["dependency_type"] == "performance_review"
    assert alex_actor["role_context"]["vulnerability_contexts"][0]["context_type"] == "complaint_pending"
