"""Structured case-intake helpers for behavioural-analysis workflows."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .behavioral_taxonomy import focus_to_taxonomy_ids


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
        "dependency_relations": [
            _dependency_relation_payload(relation) for relation in org_context.dependency_relations
        ],
        "vulnerability_contexts": [
            _vulnerability_context_payload(context) for context in org_context.vulnerability_contexts
        ],
    }


def _trigger_event_payload(trigger_event: Any) -> dict[str, Any]:
    """Serialize one explicit trigger event."""
    return {
        "trigger_type": str(trigger_event.trigger_type),
        "date": str(trigger_event.date),
        "actor": _person_payload(trigger_event.actor) if trigger_event.actor is not None else None,
        "notes": _compact_text(trigger_event.notes),
    }


def _normalized_scope_payload(case_scope: Any) -> dict[str, Any]:
    """Return the stable normalized scope payload used across BA outputs."""
    return {
        "case_label": _compact_text(case_scope.case_label),
        "target_person": _person_payload(case_scope.target_person),
        "comparator_actors": [_person_payload(actor) for actor in case_scope.comparator_actors],
        "suspected_actors": [_person_payload(actor) for actor in case_scope.suspected_actors],
        "date_from": case_scope.date_from,
        "date_to": case_scope.date_to,
        "allegation_focus": list(case_scope.allegation_focus),
        "focus_taxonomy_ids": focus_to_taxonomy_ids(list(case_scope.allegation_focus)),
        "analysis_goal": str(case_scope.analysis_goal),
        "context_notes": _compact_text(case_scope.context_notes),
        "trigger_events": [_trigger_event_payload(trigger_event) for trigger_event in case_scope.trigger_events],
        "org_context": _org_context_payload(case_scope.org_context),
    }


def build_case_bundle(case_scope: Any) -> dict[str, Any]:
    """Build a deterministic case-bundle block from structured intake input."""
    scope = _normalized_scope_payload(case_scope)
    digest_source = json.dumps(scope, sort_keys=True, separators=(",", ":"))
    bundle_id = f"case-{hashlib.sha1(digest_source.encode('utf-8')).hexdigest()[:12]}"
    provided_optional_fields = [
        field
        for field in (
            "case_label",
            "comparator_actors",
            "suspected_actors",
            "date_from",
            "date_to",
            "context_notes",
            "trigger_events",
            "org_context",
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
            "date_from",
            "date_to",
            "context_notes",
            "trigger_events",
            "org_context",
        ],
        "provided_optional_fields": provided_optional_fields,
    }
