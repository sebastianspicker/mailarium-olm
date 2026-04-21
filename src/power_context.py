"""Role, hierarchy, and power-context enrichment helpers for BA3."""

from __future__ import annotations

from typing import Any

from .actor_resolution import resolve_actor_id


def _enrich_person_ref(person: dict[str, Any], actor_graph: dict[str, Any]) -> dict[str, Any]:
    """Return a person payload annotated with actor-resolution metadata."""
    enriched = dict(person)
    actor_id, resolution = resolve_actor_id(
        actor_graph,
        email=str(person.get("email") or ""),
        name=str(person.get("name") or ""),
    )
    enriched["actor_id"] = actor_id
    enriched["actor_resolution"] = resolution
    return enriched


def build_power_context(case_scope: Any | None, actor_graph: dict[str, Any]) -> dict[str, Any]:
    """Build case-scoped power-context output from structured BA3 inputs."""
    if case_scope is None:
        return {
            "org_context_provided": False,
            "missing_org_context": True,
            "supplied_role_facts": [],
            "reporting_lines": [],
            "dependency_relations": [],
            "vulnerability_contexts": [],
            "inferred_hierarchy_hints": [],
        }

    org_context = getattr(case_scope, "org_context", None)
    if org_context is None:
        inferred_hints: list[dict[str, Any]] = []
        for actor in actor_graph.get("actors", []):
            if not isinstance(actor, dict):
                continue
            for hint in actor.get("role_hints", []) or []:
                hint_text = str(hint or "").strip().lower()
                if hint_text in {"manager", "hr", "admin", "external", "peer"}:
                    inferred_hints.append(
                        {
                            "actor_id": actor.get("actor_id"),
                            "hint": hint_text,
                            "source": "case_party.role_hint",
                        }
                    )
        return {
            "org_context_provided": False,
            "missing_org_context": True,
            "supplied_role_facts": [],
            "reporting_lines": [],
            "dependency_relations": [],
            "vulnerability_contexts": [],
            "inferred_hierarchy_hints": inferred_hints,
        }

    supplied_role_facts = [
        {
            "person": _enrich_person_ref(
                {
                    "name": role_fact.person.name,
                    "email": role_fact.person.email,
                    "role_hint": role_fact.person.role_hint,
                },
                actor_graph,
            ),
            "role_type": str(role_fact.role_type),
            "title": role_fact.title,
            "department": role_fact.department,
            "team": role_fact.team,
            "source": str(role_fact.source),
        }
        for role_fact in org_context.role_facts
    ]
    reporting_lines = [
        {
            "manager": _enrich_person_ref(
                {
                    "name": line.manager.name,
                    "email": line.manager.email,
                    "role_hint": line.manager.role_hint,
                },
                actor_graph,
            ),
            "report": _enrich_person_ref(
                {
                    "name": line.report.name,
                    "email": line.report.email,
                    "role_hint": line.report.role_hint,
                },
                actor_graph,
            ),
            "source": str(line.source),
        }
        for line in org_context.reporting_lines
    ]
    dependency_relations = [
        {
            "controller": _enrich_person_ref(
                {
                    "name": relation.controller.name,
                    "email": relation.controller.email,
                    "role_hint": relation.controller.role_hint,
                },
                actor_graph,
            ),
            "dependent": _enrich_person_ref(
                {
                    "name": relation.dependent.name,
                    "email": relation.dependent.email,
                    "role_hint": relation.dependent.role_hint,
                },
                actor_graph,
            ),
            "dependency_type": str(relation.dependency_type),
            "notes": relation.notes,
            "source": str(relation.source),
        }
        for relation in org_context.dependency_relations
    ]
    vulnerability_contexts = [
        {
            "person": _enrich_person_ref(
                {
                    "name": context.person.name,
                    "email": context.person.email,
                    "role_hint": context.person.role_hint,
                },
                actor_graph,
            ),
            "context_type": str(context.context_type),
            "notes": context.notes,
            "source": str(context.source),
        }
        for context in org_context.vulnerability_contexts
    ]
    return {
        "org_context_provided": True,
        "missing_org_context": False,
        "supplied_role_facts": supplied_role_facts,
        "reporting_lines": reporting_lines,
        "dependency_relations": dependency_relations,
        "vulnerability_contexts": vulnerability_contexts,
        "inferred_hierarchy_hints": [],
    }


def apply_power_context_to_actor_graph(actor_graph: dict[str, Any], power_context: dict[str, Any]) -> None:
    """Attach structured power-context details to actor entries in the graph."""
    actor_map = {
        str(actor.get("actor_id") or ""): actor
        for actor in actor_graph.get("actors", [])
        if isinstance(actor, dict) and actor.get("actor_id")
    }
    for actor in actor_map.values():
        actor["role_context"] = {
            "supplied_role_facts": [],
            "inferred_hierarchy_hints": [],
            "dependencies_as_controller": [],
            "dependencies_as_dependent": [],
            "vulnerability_contexts": [],
        }

    for role_fact in power_context.get("supplied_role_facts", []):
        if not isinstance(role_fact, dict):
            continue
        actor_id = str((role_fact.get("person") or {}).get("actor_id") or "")
        if actor_id and actor_id in actor_map:
            actor_map[actor_id]["role_context"]["supplied_role_facts"].append(role_fact)

    for hint in power_context.get("inferred_hierarchy_hints", []):
        if not isinstance(hint, dict):
            continue
        actor_id = str(hint.get("actor_id") or "")
        if actor_id and actor_id in actor_map:
            actor_map[actor_id]["role_context"]["inferred_hierarchy_hints"].append(hint)

    for relation in power_context.get("dependency_relations", []):
        if not isinstance(relation, dict):
            continue
        controller_id = str((relation.get("controller") or {}).get("actor_id") or "")
        dependent_id = str((relation.get("dependent") or {}).get("actor_id") or "")
        if controller_id and controller_id in actor_map:
            actor_map[controller_id]["role_context"]["dependencies_as_controller"].append(relation)
        if dependent_id and dependent_id in actor_map:
            actor_map[dependent_id]["role_context"]["dependencies_as_dependent"].append(relation)

    for context in power_context.get("vulnerability_contexts", []):
        if not isinstance(context, dict):
            continue
        actor_id = str((context.get("person") or {}).get("actor_id") or "")
        if actor_id and actor_id in actor_map:
            actor_map[actor_id]["role_context"]["vulnerability_contexts"].append(context)
