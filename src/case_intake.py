"""Structured case-intake helpers for behavioural-analysis workflows."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .behavioral_taxonomy import (
    employment_issue_tag_entries,
    focus_to_issue_tag_ids,
    focus_to_taxonomy_ids,
    issue_track_to_tag_ids,
    normalize_issue_tag_ids,
)
from .employment_issue_frameworks import build_issue_track_intake_payload, issue_track_titles


def _compact_text(value: str | None) -> str | None:
    """Normalize free-text fields for deterministic case-bundle ids."""
    if value is None:
        return None
    compacted = " ".join(value.split())
    return compacted or None


def _person_payload(person: Any) -> dict[str, Any]:
    """Convert one case-party model into a normalized serializable payload."""
    return {
        "name": str(person.name),
        "email": _compact_text(person.email),
        "role_hint": _compact_text(person.role_hint),
    }


def _institutional_actor_payload(actor: Any) -> dict[str, Any]:
    """Serialize one institutional actor, mailbox, or workflow surface."""
    return {
        "label": str(actor.label),
        "actor_type": str(actor.actor_type),
        "email": _compact_text(getattr(actor, "email", None)),
        "function": _compact_text(getattr(actor, "function", None)),
        "notes": _compact_text(getattr(actor, "notes", None)),
    }


def _role_fact_payload(role_fact: Any) -> dict[str, Any]:
    """Serialize one structured role fact."""
    return {
        "person": _person_payload(role_fact.person),
        "role_type": str(role_fact.role_type),
        "title": _compact_text(role_fact.title),
        "department": _compact_text(role_fact.department),
        "team": _compact_text(role_fact.team),
        "source": str(role_fact.source),
    }


def _reporting_line_payload(reporting_line: Any) -> dict[str, Any]:
    """Serialize one structured reporting line."""
    return {
        "manager": _person_payload(reporting_line.manager),
        "report": _person_payload(reporting_line.report),
        "source": str(reporting_line.source),
    }


def _dependency_relation_payload(relation: Any) -> dict[str, Any]:
    """Serialize one structured dependency relation."""
    return {
        "controller": _person_payload(relation.controller),
        "dependent": _person_payload(relation.dependent),
        "dependency_type": str(relation.dependency_type),
        "notes": _compact_text(relation.notes),
        "source": str(relation.source),
    }


def _vulnerability_context_payload(context: Any) -> dict[str, Any]:
    """Serialize one structured vulnerability context."""
    return {
        "person": _person_payload(context.person),
        "context_type": str(context.context_type),
        "notes": _compact_text(context.notes),
        "source": str(context.source),
    }


def _org_context_payload(org_context: Any | None) -> dict[str, Any] | None:
    """Serialize optional structured org context."""
    if org_context is None:
        return None
    return {
        "role_facts": [_role_fact_payload(role_fact) for role_fact in org_context.role_facts],
        "reporting_lines": [_reporting_line_payload(line) for line in org_context.reporting_lines],
        "dependency_relations": [_dependency_relation_payload(relation) for relation in org_context.dependency_relations],
        "vulnerability_contexts": [_vulnerability_context_payload(context) for context in org_context.vulnerability_contexts],
    }


def _trigger_event_payload(trigger_event: Any) -> dict[str, Any]:
    """Serialize one explicit trigger event."""
    return {
        "trigger_type": str(trigger_event.trigger_type),
        "date": str(trigger_event.date),
        "actor": _person_payload(trigger_event.actor) if trigger_event.actor is not None else None,
        "notes": _compact_text(trigger_event.notes),
    }


def _adverse_action_payload(adverse_action: Any) -> dict[str, Any]:
    """Serialize one explicit alleged adverse action."""
    return {
        "action_type": str(adverse_action.action_type),
        "date": str(adverse_action.date),
        "actor": _person_payload(adverse_action.actor) if adverse_action.actor is not None else None,
        "notes": _compact_text(adverse_action.notes),
    }


def _guidance_warning(
    *,
    code: str,
    severity: str,
    message: str,
    affects: list[str],
    recommended_field: str | None = None,
    recommendation: str | None = None,
) -> dict[str, Any]:
    """Return one structured intake-guidance warning."""
    payload = {
        "code": code,
        "severity": severity,
        "message": message,
        "affects": affects,
    }
    if recommended_field:
        payload["recommended_field"] = recommended_field
    if recommendation:
        payload["recommendation"] = recommendation
    return payload


def _normalized_scope_payload(case_scope: Any) -> dict[str, Any]:
    """Return the stable normalized scope payload used across BA outputs."""
    issue_track_frameworks = build_issue_track_intake_payload(case_scope)
    issue_tag_ids = normalize_issue_tag_ids(
        [
            *list(getattr(case_scope, "employment_issue_tags", [])),
            *[
                tag_id
                for issue_track in getattr(case_scope, "employment_issue_tracks", [])
                for tag_id in issue_track_to_tag_ids(
                    str(issue_track),
                    context_text=str(getattr(case_scope, "context_notes", "") or ""),
                )
            ],
            *focus_to_issue_tag_ids(list(case_scope.allegation_focus)),
        ]
    )
    issue_tag_lookup = {entry["tag_id"]: entry for entry in employment_issue_tag_entries()}
    return {
        "case_label": _compact_text(case_scope.case_label),
        "target_person": _person_payload(case_scope.target_person),
        "comparator_actors": [_person_payload(actor) for actor in case_scope.comparator_actors],
        "suspected_actors": [_person_payload(actor) for actor in case_scope.suspected_actors],
        "context_people": [_person_payload(actor) for actor in getattr(case_scope, "context_people", [])],
        "institutional_actors": [
            _institutional_actor_payload(actor) for actor in getattr(case_scope, "institutional_actors", [])
        ],
        "date_from": case_scope.date_from,
        "date_to": case_scope.date_to,
        "allegation_focus": list(case_scope.allegation_focus),
        "focus_taxonomy_ids": focus_to_taxonomy_ids(list(case_scope.allegation_focus)),
        "analysis_goal": str(case_scope.analysis_goal),
        "context_notes": _compact_text(case_scope.context_notes),
        "trigger_events": [_trigger_event_payload(trigger_event) for trigger_event in case_scope.trigger_events],
        "asserted_rights_timeline": [
            _trigger_event_payload(trigger_event) for trigger_event in getattr(case_scope, "asserted_rights_timeline", [])
        ],
        "alleged_adverse_actions": [_adverse_action_payload(item) for item in getattr(case_scope, "alleged_adverse_actions", [])],
        "org_context": _org_context_payload(case_scope.org_context),
        "comparator_equivalence_notes": _compact_text(getattr(case_scope, "comparator_equivalence_notes", None)),
        "expected_document_collections": list(getattr(case_scope, "expected_document_collections", [])),
        "known_missing_records": list(getattr(case_scope, "known_missing_records", [])),
        "employment_issue_tags": issue_tag_ids,
        "employment_issue_tag_payloads": [
            {
                "tag_id": tag_id,
                "label": str(issue_tag_lookup[tag_id]["label"]),
                "assignment_basis": (
                    "operator_supplied"
                    if tag_id in set(getattr(case_scope, "employment_issue_tags", []))
                    else "bounded_inference"
                ),
            }
            for tag_id in issue_tag_ids
            if tag_id in issue_tag_lookup
        ],
        "employment_issue_tracks": list(case_scope.employment_issue_tracks),
        "employment_issue_track_titles": issue_track_titles(list(case_scope.employment_issue_tracks)),
        "employment_issue_frameworks": issue_track_frameworks,
    }


def build_case_intake_guidance(case_scope: Any) -> dict[str, Any]:
    """Return machine-readable intake guidance for structured case analysis."""
    allegation_focus = {str(item) for item in case_scope.allegation_focus}
    high_stakes_goal = str(case_scope.analysis_goal) in {"hr_review", "lawyer_briefing", "formal_complaint"}
    warnings: list[dict[str, Any]] = []

    if "retaliation" in allegation_focus and not case_scope.trigger_events:
        warnings.append(
            _guidance_warning(
                code="retaliation_focus_without_trigger_events",
                severity="warning",
                message="Retaliation-focused review is degraded because no explicit trigger events were supplied.",
                affects=["retaliation_analysis", "overall_assessment"],
                recommended_field="trigger_events",
                recommendation="Add dated complaint, objection, HR-contact, illness-disclosure, or similar trigger events.",
            )
        )
    if "retaliation" in allegation_focus and not getattr(case_scope, "alleged_adverse_actions", []):
        warnings.append(
            _guidance_warning(
                code="retaliation_focus_without_alleged_adverse_actions",
                severity="info",
                message="Retaliation-focused review is weaker because no alleged adverse actions were supplied explicitly.",
                affects=["retaliation_analysis", "overall_assessment"],
                recommended_field="alleged_adverse_actions",
                recommendation="Add dated adverse actions such as project withdrawal, controls, exclusion, or restrictions.",
            )
        )
    if allegation_focus & {"discrimination", "unequal_treatment"} and not case_scope.comparator_actors:
        warnings.append(
            _guidance_warning(
                code="unequal_treatment_focus_without_comparators",
                severity="warning",
                message=(
                    "Unequal-treatment or discrimination-focused review is degraded because no comparator actors were supplied."
                ),
                affects=["comparative_treatment", "overall_assessment"],
                recommended_field="comparator_actors",
                recommendation="Add one or more relevant comparators from the same sender, process step, or role context.",
            )
        )
    if (
        allegation_focus & {"discrimination", "unequal_treatment"}
        and not (getattr(case_scope, "comparator_equivalence_notes", None) or "").strip()
    ):
        warnings.append(
            _guidance_warning(
                code="comparator_review_without_equivalence_notes",
                severity="info",
                message="Comparator review is weaker because no comparator-equivalence notes were supplied.",
                affects=["comparative_treatment", "overall_assessment"],
                recommended_field="comparator_equivalence_notes",
                recommendation=(
                    "Explain role similarity, manager overlap, process step, and why the comparators are meaningfully comparable."
                ),
            )
        )
    if (allegation_focus & {"mobbing", "bullying", "abuse_of_authority", "discrimination", "retaliation"}) and (
        case_scope.org_context is None
    ):
        warnings.append(
            _guidance_warning(
                code="power_focused_review_without_org_context",
                severity="warning",
                message="Power- or pattern-focused review is degraded because no org or dependency context was supplied.",
                affects=["power_context_analysis", "overall_assessment"],
                recommended_field="org_context",
                recommendation="Add reporting lines, role facts, dependency relations, or vulnerability contexts where known.",
            )
        )
    if high_stakes_goal and not (case_scope.context_notes or "").strip():
        warnings.append(
            _guidance_warning(
                code="high_stakes_goal_without_context_notes",
                severity="info",
                message=(
                    "High-stakes review would be easier to interpret with neutral "
                    "context notes about the underlying workflow or incident."
                ),
                affects=["executive_summary", "overall_assessment"],
                recommended_field="context_notes",
                recommendation="Add concise neutral background facts such as project context, incident timing, or process stage.",
            )
        )
    if not case_scope.suspected_actors:
        warnings.append(
            _guidance_warning(
                code="suspected_actors_not_supplied",
                severity="info",
                message="No suspected actors were supplied, so actor-targeted pattern review may remain broader than intended.",
                affects=["executive_summary", "case_patterns"],
                recommended_field="suspected_actors",
                recommendation=(
                    "Add the manager, colleague, or HR/contact actors you want the analysis to compare against the target."
                ),
            )
        )
    for issue_payload in build_issue_track_intake_payload(case_scope):
        issue_track = str(issue_payload.get("issue_track") or "")
        issue_title = str(issue_payload.get("title") or issue_track)
        for missing_input in issue_payload.get("missing_inputs", []):
            if not isinstance(missing_input, dict):
                continue
            field = str(missing_input.get("field") or "")
            warnings.append(
                _guidance_warning(
                    code=f"{issue_track}_under_documented",
                    severity="info",
                    message=(f"{issue_title} remains under-documented because {str(missing_input.get('reason') or '').lower()}"),
                    affects=["employment_issue_frameworks", "overall_assessment"],
                    recommended_field=field or None,
                    recommendation=str(missing_input.get("recommendation") or "") or None,
                )
            )

    recommended_presence = {
        "suspected_actors": bool(case_scope.suspected_actors),
        "comparator_actors": bool(case_scope.comparator_actors),
        "trigger_events": bool(case_scope.trigger_events),
        "alleged_adverse_actions": bool(getattr(case_scope, "alleged_adverse_actions", [])),
        "org_context": case_scope.org_context is not None,
        "context_notes": bool((case_scope.context_notes or "").strip()),
        "comparator_equivalence_notes": bool((getattr(case_scope, "comparator_equivalence_notes", None) or "").strip()),
        "expected_document_collections": bool(getattr(case_scope, "expected_document_collections", [])),
        "known_missing_records": bool(getattr(case_scope, "known_missing_records", [])),
    }
    missing_recommended_fields = [field for field, present in recommended_presence.items() if not present]
    supports_retaliation_analysis = bool(case_scope.trigger_events)
    supports_comparator_analysis = bool(case_scope.comparator_actors)
    supports_power_analysis = case_scope.org_context is not None

    status = "complete"
    if warnings or missing_recommended_fields:
        status = "degraded"

    return {
        "status": status,
        "recommended_fields_present": [field for field, present in recommended_presence.items() if present],
        "missing_recommended_fields": missing_recommended_fields,
        "downgrade_reasons": [str(item["code"]) for item in warnings],
        "warnings": warnings,
        "recommended_next_inputs": [
            {
                "field": str(item["recommended_field"]),
                "reason": str(item["message"]),
                "recommendation": str(item["recommendation"]),
            }
            for item in warnings
            if item.get("recommended_field") and item.get("recommendation")
        ],
        "supports_retaliation_analysis": supports_retaliation_analysis,
        "supports_comparator_analysis": supports_comparator_analysis,
        "supports_power_analysis": supports_power_analysis,
        "employment_issue_frameworks": build_issue_track_intake_payload(case_scope),
    }


def build_case_bundle(case_scope: Any) -> dict[str, Any]:
    """Build a deterministic case-bundle block from structured intake input."""
    scope = _normalized_scope_payload(case_scope)
    intake_guidance = build_case_intake_guidance(case_scope)
    digest_source = json.dumps(scope, sort_keys=True, separators=(",", ":"))
    bundle_id = f"case-{hashlib.sha256(digest_source.encode('utf-8')).hexdigest()[:12]}"
    provided_optional_fields = [
        field
        for field in (
            "case_label",
            "comparator_actors",
            "suspected_actors",
            "context_people",
            "institutional_actors",
            "date_from",
            "date_to",
            "context_notes",
            "trigger_events",
            "asserted_rights_timeline",
            "alleged_adverse_actions",
            "org_context",
            "comparator_equivalence_notes",
            "expected_document_collections",
            "known_missing_records",
        )
        if scope.get(field)
    ]
    return {
        "bundle_id": bundle_id,
        "scope": scope,
        "required_fields": [
            "target_person",
            "allegation_focus",
            "analysis_goal",
        ],
        "optional_fields": [
            "case_label",
            "comparator_actors",
            "suspected_actors",
            "context_people",
            "institutional_actors",
            "date_from",
            "date_to",
            "context_notes",
            "trigger_events",
            "asserted_rights_timeline",
            "alleged_adverse_actions",
            "org_context",
            "comparator_equivalence_notes",
            "expected_document_collections",
            "known_missing_records",
        ],
        "provided_optional_fields": provided_optional_fields,
        "intake_guidance": intake_guidance,
    }
