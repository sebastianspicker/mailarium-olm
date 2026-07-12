"""Shared matter-workspace core for MCP-backed legal-support outputs."""
# pylint: disable=too-many-branches,too-many-locals

from __future__ import annotations

import hashlib
from typing import Any

from ._utils import _as_dict, _as_list, _compact

MATTER_WORKSPACE_VERSION = "1"


def _hash_id(prefix: str, *parts: str) -> str:
    """Generate a deterministic hash-based ID from a prefix and optional parts.

    Args:
        prefix: The ID prefix (e.g., 'person', 'matter').
        *parts: Variable number of string parts to include in the hash.

    Returns:
        A string ID in the format '{prefix}:{12_char_hex_digest}'.
    """
    digest_source = "||".join(_compact(part).lower() for part in parts if _compact(part))
    if not digest_source:
        digest_source = prefix
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _party_entity(
    person: dict[str, Any],
    *,
    roles_in_matter: list[str],
    source_paths: list[str],
) -> dict[str, Any] | None:
    """Create a party entity dict from person data with roles and source paths.

    Args:
        person: Dict containing person data with optional 'name', 'email', 'role_hint'.
        roles_in_matter: List of role strings for this person in the matter.
        source_paths: List of source path strings where this person was found.

    Returns:
        A party entity dict with entity_id, name, email, role_hint, roles_in_matter,
        and source_paths, or None if no identifying information is present.
    """
    name = _compact(person.get("name"))
    email = _compact(person.get("email"))
    role_hint = _compact(person.get("role_hint"))
    if not any((name, email, role_hint)):
        return None
    entity_id = _hash_id("person", email or name)
    return {
        "entity_id": entity_id,
        "name": name,
        "email": email,
        "role_hint": role_hint,
        "roles_in_matter": list(dict.fromkeys(role for role in roles_in_matter if _compact(role))),
        "source_paths": list(dict.fromkeys(path for path in source_paths if _compact(path))),
    }


def _merge_party_entities(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge party entity entries by entity_id, combining roles and source paths.

    Args:
        entries: List of party entity dicts to merge.

    Returns:
        List of merged party entity dicts, sorted by name then email.
        Entries with the same entity_id are merged, with roles_in_matter and
        source_paths combined (deduplicated), and missing fields filled from
        any entry that has them.
    """
    merged: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entity_id = str(entry.get("entity_id") or "")
        if not entity_id:
            continue
        bucket = merged.setdefault(entity_id, dict(entry))
        bucket["roles_in_matter"] = list(dict.fromkeys([*bucket.get("roles_in_matter", []), *entry.get("roles_in_matter", [])]))
        bucket["source_paths"] = list(dict.fromkeys([*bucket.get("source_paths", []), *entry.get("source_paths", [])]))
        if not bucket.get("name"):
            bucket["name"] = str(entry.get("name") or "")
        if not bucket.get("email"):
            bucket["email"] = str(entry.get("email") or "")
        if not bucket.get("role_hint"):
            bucket["role_hint"] = str(entry.get("role_hint") or "")
    return sorted(merged.values(), key=lambda item: (str(item.get("name") or ""), str(item.get("email") or "")))


def build_matter_workspace(
    *,
    case_bundle: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
    matter_evidence_index: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the shared matter workspace core for downstream legal-support layers."""
    if not isinstance(case_bundle, dict):
        return None

    scope = _as_dict(case_bundle.get("scope"))
    bundle_id = _compact(case_bundle.get("bundle_id"))
    matter_id = _hash_id(
        "matter",
        bundle_id or _compact(scope.get("case_label")),
        _compact(_as_dict(scope.get("target_person")).get("email")),
        _compact(scope.get("date_from")),
        _compact(scope.get("date_to")),
    )

    target_person = _party_entity(
        _as_dict(scope.get("target_person")),
        roles_in_matter=["target_person"],
        source_paths=["case_bundle.scope.target_person"],
    )
    party_candidates = [*(_direct_party_candidates(scope)), *(_org_party_candidates(scope))]
    parties = _merge_party_entities(party_candidates)
    issue_tracks, issue_tags = _workspace_issue_registry(scope)

    evidence_index = _as_dict(matter_evidence_index)
    chronology = _as_dict(master_chronology)
    source_bundle = _as_dict(multi_source_case_bundle)

    return {
        "version": MATTER_WORKSPACE_VERSION,
        "workspace_id": f"workspace:{matter_id.split(':', 1)[-1]}",
        "matter": {
            "matter_id": matter_id,
            "bundle_id": bundle_id,
            "case_label": _compact(scope.get("case_label")),
            "analysis_goal": _compact(scope.get("analysis_goal")),
            "date_range": {
                "date_from": _compact(scope.get("date_from")),
                "date_to": _compact(scope.get("date_to")),
            },
            "target_person_entity_id": str(target_person.get("entity_id") or "") if isinstance(target_person, dict) else "",
        },
        "parties": parties,
        "issue_registry": {
            "employment_issue_tracks": issue_tracks,
            "employment_issue_tags": issue_tags,
        },
        "evidence_registry": _workspace_evidence_registry(source_bundle, evidence_index),
        "chronology_registry": _workspace_chronology_registry(chronology),
        "registry_refs": {
            "case_bundle_ref": bundle_id,
            "matter_evidence_index_version": str(evidence_index.get("version") or ""),
            "master_chronology_version": str(chronology.get("version") or ""),
        },
    }


def _append_party(rows: list[dict[str, Any]], person: dict[str, Any], role: str, source_path: str) -> None:
    entry = _party_entity(person, roles_in_matter=[role], source_paths=[source_path])
    if entry is not None:
        rows.append(entry)


def _direct_party_candidates(scope: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _append_party(rows, _as_dict(scope.get("target_person")), "target_person", "case_bundle.scope.target_person")
    for key, role in (("suspected_actors", "suspected_actor"), ("comparator_actors", "comparator_actor")):
        for actor in _as_list(scope.get(key)):
            _append_party(rows, _as_dict(actor), role, f"case_bundle.scope.{key}")
    for event in _as_list(scope.get("trigger_events")):
        _append_party(
            rows,
            _as_dict(_as_dict(event).get("actor")),
            "trigger_actor",
            "case_bundle.scope.trigger_events",
        )
    return rows


def _org_party_candidates(scope: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    org_context = _as_dict(scope.get("org_context"))
    for fact in _as_list(org_context.get("role_facts")):
        _append_party(
            rows,
            _as_dict(_as_dict(fact).get("person")),
            "org_context_person",
            "case_bundle.scope.org_context.role_facts",
        )
    for context in _as_list(org_context.get("vulnerability_contexts")):
        _append_party(
            rows,
            _as_dict(_as_dict(context).get("person")),
            "vulnerability_context_person",
            "case_bundle.scope.org_context.vulnerability_contexts",
        )
    rows.extend(_org_relation_party_candidates(org_context))
    return rows


def _org_relation_party_candidates(org_context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    relation_groups = (
        ("reporting_lines", ("manager", "report")),
        ("dependency_relations", ("controller", "dependent")),
    )
    for group, person_keys in relation_groups:
        for relation in _as_list(org_context.get(group)):
            for person_key in person_keys:
                _append_party(
                    rows,
                    _as_dict(_as_dict(relation).get(person_key)),
                    "org_context_person",
                    f"case_bundle.scope.org_context.{group}",
                )
    return rows


def _workspace_issue_registry(scope: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _workspace_issue_tracks(scope), _workspace_issue_tags(scope)


def _workspace_issue_tracks(scope: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "entity_id": _hash_id("issue_track", str(item.get("issue_track") or "")),
            "issue_track": str(item.get("issue_track") or ""),
            "title": str(item.get("title") or ""),
            "neutral_question": str(item.get("neutral_question") or ""),
        }
        for item in _as_list(scope.get("employment_issue_frameworks"))
        if isinstance(item, dict) and str(item.get("issue_track") or "")
    ]


def _workspace_issue_tags(scope: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "entity_id": _hash_id("issue_tag", str(item.get("tag_id") or "")),
            "tag_id": str(item.get("tag_id") or ""),
            "label": str(item.get("label") or ""),
            "assignment_basis": str(item.get("assignment_basis") or ""),
        }
        for item in _as_list(scope.get("employment_issue_tag_payloads"))
        if isinstance(item, dict) and str(item.get("tag_id") or "")
    ]


def _workspace_evidence_registry(source_bundle: dict[str, Any], evidence_index: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(source_bundle.get("summary"))
    sources = _as_list(source_bundle.get("sources"))
    return {
        "source_count": int(summary.get("source_count") or len(sources)),
        "source_type_counts": dict(_as_dict(summary.get("source_type_counts"))),
        "exhibit_ids": _registry_values(_as_list(evidence_index.get("rows")), "exhibit_id"),
        "source_ids": _registry_values(sources, "source_id"),
    }


def _registry_values(rows: list[Any], key: str) -> list[str]:
    return [str(row.get(key) or "") for row in rows if isinstance(row, dict) and str(row.get(key) or "")]


def _workspace_chronology_registry(chronology: dict[str, Any]) -> dict[str, Any]:
    entries = _as_list(chronology.get("entries"))
    summary = _as_dict(chronology.get("summary"))
    return {
        "entry_ids": _registry_values(entries, "chronology_id"),
        "entry_count": int(chronology.get("entry_count") or len(entries)),
        "date_range": dict(_as_dict(summary.get("date_range"))),
        "date_precision_counts": dict(_as_dict(summary.get("date_precision_counts"))),
    }
