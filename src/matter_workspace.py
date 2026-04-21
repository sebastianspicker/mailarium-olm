"""Shared matter-workspace core for MCP-backed legal-support outputs."""

from __future__ import annotations

import hashlib
from typing import Any

MATTER_WORKSPACE_VERSION = "1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _hash_id(prefix: str, *parts: str) -> str:
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

    party_candidates: list[dict[str, Any]] = []
    target_person = _party_entity(
        _as_dict(scope.get("target_person")),
        roles_in_matter=["target_person"],
        source_paths=["case_bundle.scope.target_person"],
    )
    if target_person is not None:
        party_candidates.append(target_person)
    for actor in _as_list(scope.get("suspected_actors")):
        entry = _party_entity(
            _as_dict(actor),
            roles_in_matter=["suspected_actor"],
            source_paths=["case_bundle.scope.suspected_actors"],
        )
        if entry is not None:
            party_candidates.append(entry)
    for actor in _as_list(scope.get("comparator_actors")):
        entry = _party_entity(
            _as_dict(actor),
            roles_in_matter=["comparator_actor"],
            source_paths=["case_bundle.scope.comparator_actors"],
        )
        if entry is not None:
            party_candidates.append(entry)
    for trigger_event in _as_list(scope.get("trigger_events")):
        trigger_actor = _party_entity(
            _as_dict(_as_dict(trigger_event).get("actor")),
            roles_in_matter=["trigger_actor"],
            source_paths=["case_bundle.scope.trigger_events"],
        )
        if trigger_actor is not None:
            party_candidates.append(trigger_actor)
    for role_fact in _as_list(_as_dict(scope.get("org_context")).get("role_facts")):
        entry = _party_entity(
            _as_dict(_as_dict(role_fact).get("person")),
            roles_in_matter=["org_context_person"],
            source_paths=["case_bundle.scope.org_context.role_facts"],
        )
        if entry is not None:
            party_candidates.append(entry)
    for reporting_line in _as_list(_as_dict(scope.get("org_context")).get("reporting_lines")):
        for person_key in ("manager", "report"):
            entry = _party_entity(
                _as_dict(_as_dict(reporting_line).get(person_key)),
                roles_in_matter=["org_context_person"],
                source_paths=["case_bundle.scope.org_context.reporting_lines"],
            )
            if entry is not None:
                party_candidates.append(entry)
    for relation in _as_list(_as_dict(scope.get("org_context")).get("dependency_relations")):
        for person_key in ("controller", "dependent"):
            entry = _party_entity(
                _as_dict(_as_dict(relation).get(person_key)),
                roles_in_matter=["org_context_person"],
                source_paths=["case_bundle.scope.org_context.dependency_relations"],
            )
            if entry is not None:
                party_candidates.append(entry)
    for context in _as_list(_as_dict(scope.get("org_context")).get("vulnerability_contexts")):
        entry = _party_entity(
            _as_dict(_as_dict(context).get("person")),
            roles_in_matter=["vulnerability_context_person"],
            source_paths=["case_bundle.scope.org_context.vulnerability_contexts"],
        )
        if entry is not None:
            party_candidates.append(entry)

    parties = _merge_party_entities(party_candidates)

    issue_tracks = [
        {
            "entity_id": _hash_id("issue_track", str(item.get("issue_track") or "")),
            "issue_track": str(item.get("issue_track") or ""),
            "title": str(item.get("title") or ""),
            "neutral_question": str(item.get("neutral_question") or ""),
        }
        for item in _as_list(scope.get("employment_issue_frameworks"))
        if isinstance(item, dict) and str(item.get("issue_track") or "")
    ]
    issue_tags = [
        {
            "entity_id": _hash_id("issue_tag", str(item.get("tag_id") or "")),
            "tag_id": str(item.get("tag_id") or ""),
            "label": str(item.get("label") or ""),
            "assignment_basis": str(item.get("assignment_basis") or ""),
        }
        for item in _as_list(scope.get("employment_issue_tag_payloads"))
        if isinstance(item, dict) and str(item.get("tag_id") or "")
    ]

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
        "evidence_registry": {
            "source_count": int(
                _as_dict(source_bundle.get("summary")).get("source_count") or len(_as_list(source_bundle.get("sources")))
            ),
            "source_type_counts": dict(_as_dict(_as_dict(source_bundle.get("summary")).get("source_type_counts"))),
            "exhibit_ids": [
                str(row.get("exhibit_id") or "")
                for row in _as_list(evidence_index.get("rows"))
                if isinstance(row, dict) and str(row.get("exhibit_id") or "")
            ],
            "source_ids": [
                str(source.get("source_id") or "")
                for source in _as_list(source_bundle.get("sources"))
                if isinstance(source, dict) and str(source.get("source_id") or "")
            ],
        },
        "chronology_registry": {
            "entry_ids": [
                str(entry.get("chronology_id") or "")
                for entry in _as_list(chronology.get("entries"))
                if isinstance(entry, dict) and str(entry.get("chronology_id") or "")
            ],
            "entry_count": int(chronology.get("entry_count") or len(_as_list(chronology.get("entries")))),
            "date_range": dict(_as_dict(chronology.get("summary")).get("date_range") or {}),
            "date_precision_counts": dict(_as_dict(chronology.get("summary")).get("date_precision_counts") or {}),
        },
        "registry_refs": {
            "case_bundle_ref": bundle_id,
            "matter_evidence_index_version": str(evidence_index.get("version") or ""),
            "master_chronology_version": str(chronology.get("version") or ""),
        },
    }
