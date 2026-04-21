"""Shared actor-map and witness-map builders for counsel-facing outputs."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

ACTOR_WITNESS_MAP_VERSION = "1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


_IDENTITY_PATTERN = re.compile(r"^(?P<name>.*?)<(?P<email>[^<>]+)>$")


def _parse_identity(value: Any) -> tuple[str, str]:
    text = _compact(value)
    if not text:
        return ("", "")
    match = _IDENTITY_PATTERN.match(text)
    if match:
        return (_compact(match.group("name")), _compact(match.group("email")).lower())
    if "@" in text and " " not in text:
        return ("", text.lower())
    return (text, "")


def _synthetic_actor_id(*, name: str, email: str) -> str:
    signature = email or name.lower()
    digest = hashlib.blake2s(signature.encode("utf-8"), digest_size=6).hexdigest()
    return f"actor-synth-{digest}"


def _actor_name(actor: dict[str, Any]) -> str:
    primary_name = _compact(actor.get("primary_name"))
    if primary_name:
        return primary_name
    display_names = [str(item) for item in _as_list(actor.get("display_names")) if _compact(item)]
    if display_names:
        return display_names[0]
    return ""


def _actor_role_hint(actor: dict[str, Any]) -> str:
    role_hint = _compact(actor.get("role_hint"))
    if role_hint:
        return role_hint
    role_hints = [str(item) for item in _as_list(actor.get("role_hints")) if _compact(item)]
    if role_hints:
        return role_hints[0]
    return ""


def _actor_email(actor: dict[str, Any]) -> str:
    primary_email = _compact(actor.get("primary_email"))
    if primary_email:
        return primary_email
    emails = [str(item) for item in _as_list(actor.get("emails")) if _compact(item)]
    if emails:
        return emails[0]
    return ""


def _record_holder_kind(source_type: str) -> str:
    return {
        "email": "email_record_holder",
        "calendar_event": "calendar_record_holder",
        "note_record": "note_record_holder",
        "time_record": "time_record_holder",
        "participation_record": "participation_record_holder",
    }.get(source_type, "document_record_holder")


def _source_identity_tokens(source: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for entry in _source_identity_entries(source):
        for value in (entry.get("name"), entry.get("email")):
            compacted = _compact(value).lower()
            if compacted:
                tokens.append(compacted)
    return list(dict.fromkeys(tokens))


def _source_identity_entries(source: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for key in ("author", "sender_name", "sender_email"):
        name, email = _parse_identity(source.get(key))
        if name or email:
            entries.append({"name": name, "email": email})
    for list_key in ("participants", "recipients", "to", "cc", "bcc"):
        for item in _as_list(source.get(list_key)):
            name, email = _parse_identity(item)
            if name or email:
                entries.append({"name": name, "email": email})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        identity_key = (_compact(entry.get("name")).lower(), _compact(entry.get("email")).lower())
        if identity_key == ("", "") or identity_key in seen:
            continue
        seen.add(identity_key)
        deduped.append({"name": _compact(entry.get("name")), "email": _compact(entry.get("email")).lower()})
    return deduped


def _actor_ids_for_source(
    source: dict[str, Any],
    *,
    actor_by_email: dict[str, str],
    actor_by_name: dict[str, str],
) -> list[str]:
    actor_id = str(source.get("actor_id") or "")
    if actor_id:
        return [actor_id]
    participant_ids: list[str] = []
    for participant in _source_identity_tokens(source):
        normalized = _compact(participant).lower()
        if not normalized:
            continue
        matched_actor = actor_by_email.get(normalized) or actor_by_name.get(normalized)
        if matched_actor and matched_actor not in participant_ids:
            participant_ids.append(matched_actor)
    return participant_ids


def build_actor_witness_map(
    *,
    case_bundle: dict[str, Any] | None,
    actor_identity_graph: dict[str, Any] | None,
    communication_graph: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
    matter_workspace: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return shared actor-map and witness-map outputs from the matter registries."""
    scope = _as_dict(_as_dict(case_bundle).get("scope"))
    actor_graph = _as_dict(actor_identity_graph)
    chronology_entries = [entry for entry in _as_list(_as_dict(master_chronology).get("entries")) if isinstance(entry, dict)]
    workspace_parties = [entry for entry in _as_list(_as_dict(matter_workspace).get("parties")) if isinstance(entry, dict)]
    graph_findings = [entry for entry in _as_list(_as_dict(communication_graph).get("graph_findings")) if isinstance(entry, dict)]
    mixed_sources = [entry for entry in _as_list(_as_dict(multi_source_case_bundle).get("sources")) if isinstance(entry, dict)]

    graph_actors = [
        entry for entry in _as_list(actor_graph.get("actors")) if isinstance(entry, dict) and str(entry.get("actor_id") or "")
    ]
    if not graph_actors and not workspace_parties:
        return None

    actor_by_email = {
        _actor_email(actor).lower(): str(actor.get("actor_id") or "")
        for actor in graph_actors
        if _actor_email(actor) and str(actor.get("actor_id") or "")
    }
    actor_by_name = {
        _actor_name(actor).lower(): str(actor.get("actor_id") or "")
        for actor in graph_actors
        if _actor_name(actor) and str(actor.get("actor_id") or "")
    }

    party_by_email = {_compact(entry.get("email")).lower(): entry for entry in workspace_parties if _compact(entry.get("email"))}
    party_by_name = {_compact(entry.get("name")).lower(): entry for entry in workspace_parties if _compact(entry.get("name"))}

    existing_names = {_actor_name(actor).lower() for actor in graph_actors if _actor_name(actor)}
    existing_emails = {_actor_email(actor).lower() for actor in graph_actors if _actor_email(actor)}
    synthetic_actors: list[dict[str, Any]] = []
    for source in mixed_sources:
        for identity in _source_identity_entries(source):
            name = _compact(identity.get("name"))
            email = _compact(identity.get("email")).lower()
            if (email and email in existing_emails) or (name and name.lower() in existing_names) or (not name and not email):
                continue
            party = party_by_email.get(email) if email else None
            if party is None and name:
                party = party_by_name.get(name.lower())
            roles_in_matter = [str(item) for item in _as_list(_as_dict(party).get("roles_in_matter")) if item]
            synthetic_actors.append(
                {
                    "actor_id": _synthetic_actor_id(name=name, email=email),
                    "primary_email": email,
                    "display_names": [name] if name else [],
                    "role_hints": [roles_in_matter[0] if roles_in_matter else "source_participant"],
                    "role_context": {},
                }
            )
            if name:
                existing_names.add(name.lower())
            if email:
                existing_emails.add(email)
    graph_actors = [*graph_actors, *synthetic_actors]

    actor_by_email = {
        _actor_email(actor).lower(): str(actor.get("actor_id") or "")
        for actor in graph_actors
        if _actor_email(actor) and str(actor.get("actor_id") or "")
    }
    actor_by_name = {
        _actor_name(actor).lower(): str(actor.get("actor_id") or "")
        for actor in graph_actors
        if _actor_name(actor) and str(actor.get("actor_id") or "")
    }

    chronology_by_actor: dict[str, list[dict[str, Any]]] = {}
    source_actor_ids_by_uid: dict[str, list[str]] = {}
    source_actor_ids_by_source_id: dict[str, list[str]] = {}
    for source in mixed_sources:
        uid = str(source.get("uid") or "")
        actor_ids = _actor_ids_for_source(
            source,
            actor_by_email=actor_by_email,
            actor_by_name=actor_by_name,
        )
        if not uid:
            source_id = str(source.get("source_id") or "")
            if source_id and actor_ids:
                source_actor_ids_by_source_id[source_id] = actor_ids
            continue
        source_actor_ids_by_uid[uid] = actor_ids
        source_id = str(source.get("source_id") or "")
        if source_id and actor_ids:
            source_actor_ids_by_source_id[source_id] = actor_ids
    for entry in chronology_entries:
        uid = str(entry.get("uid") or "")
        actor_ids = [str(entry.get("actor_id") or "")] if str(entry.get("actor_id") or "") else []
        if not actor_ids and uid:
            actor_ids = [item for item in source_actor_ids_by_uid.get(uid, []) if item]
        if not actor_ids:
            source_linkage = _as_dict(entry.get("source_linkage"))
            source_ids = [str(item) for item in _as_list(source_linkage.get("source_ids")) if str(item).strip()]
            for source_id in source_ids:
                for actor_id in source_actor_ids_by_source_id.get(source_id, []):
                    if actor_id and actor_id not in actor_ids:
                        actor_ids.append(actor_id)
        for actor_id in actor_ids:
            chronology_by_actor.setdefault(actor_id, []).append(entry)

    coordination_by_actor: dict[str, list[dict[str, Any]]] = {}
    graph_signal_counts_by_actor: dict[str, Counter[str]] = {}
    for finding in graph_findings:
        signal_type = str(finding.get("graph_signal_type") or "")
        sender_node_id = str(_as_dict(finding.get("evidence_chain")).get("sender_node_id") or "")
        if not signal_type or not sender_node_id:
            continue
        graph_signal_counts_by_actor.setdefault(sender_node_id, Counter())[signal_type] += 1
        coordination_by_actor.setdefault(sender_node_id, []).append(
            {
                "coordination_id": str(finding.get("finding_id") or ""),
                "coordination_type": signal_type,
                "summary": str(finding.get("summary") or ""),
                "message_uids": [
                    str(item) for item in _as_list(_as_dict(finding.get("evidence_chain")).get("message_uids")) if item
                ][:4],
                "thread_group_ids": [
                    str(item) for item in _as_list(_as_dict(finding.get("evidence_chain")).get("thread_group_ids")) if item
                ][:3],
            }
        )

    witnesses = [entry for entry in _as_list(scope.get("witnesses")) if isinstance(entry, dict)]
    witness_email_set = {_compact(entry.get("email")).lower() for entry in witnesses if _compact(entry.get("email"))}
    witness_name_set = {_compact(entry.get("name")).lower() for entry in witnesses if _compact(entry.get("name"))}

    matter = _as_dict(matter_workspace).get("matter")
    target_entity_id = str(_as_dict(matter).get("target_person_entity_id") or "")

    actor_rows: list[dict[str, Any]] = []
    decision_makers: list[dict[str, Any]] = []
    independent_witnesses: list[dict[str, Any]] = []
    mixed_or_nonindependent_witnesses: list[dict[str, Any]] = []
    record_holders: list[dict[str, Any]] = []

    seen_record_holder_keys: set[tuple[str, str]] = set()
    source_count_by_actor: Counter[str] = Counter()
    source_type_count_by_actor: dict[str, Counter[str]] = {}
    for source in mixed_sources:
        source_type = str(source.get("source_type") or "")
        actor_ids = _actor_ids_for_source(source, actor_by_email=actor_by_email, actor_by_name=actor_by_name)
        if not actor_ids or not source_type:
            continue
        for actor_id in actor_ids:
            source_count_by_actor[actor_id] += 1
            source_type_count_by_actor.setdefault(actor_id, Counter())[source_type] += 1
            key = (actor_id, source_type)
            if key in seen_record_holder_keys:
                continue
            seen_record_holder_keys.add(key)
            record_holders.append(
                {
                    "actor_id": actor_id,
                    "record_holder_type": _record_holder_kind(source_type),
                    "source_type": source_type,
                    "source_count": 0,  # filled after aggregation
                    "source_ids": [],
                    "why_it_matters": (
                        f"This actor is linked to {source_type.replace('_', ' ')} material that may corroborate chronology,"
                        " access, participation, or decision flow."
                    ),
                }
            )

    for holder in record_holders:
        actor_id = str(holder.get("actor_id") or "")
        source_type = str(holder.get("source_type") or "")
        holder["source_count"] = int(source_type_count_by_actor.get(actor_id, Counter()).get(source_type, 0))
        holder["source_ids"] = [
            str(source.get("source_id") or "")
            for source in mixed_sources
            if actor_id in _actor_ids_for_source(source, actor_by_email=actor_by_email, actor_by_name=actor_by_name)
            and str(source.get("source_type") or "") == source_type
        ][:4]

    for actor in graph_actors:
        actor_id = str(actor.get("actor_id") or "")
        if not actor_id:
            continue
        email = _actor_email(actor)
        name = _actor_name(actor)
        role_hint = _actor_role_hint(actor)
        role_context = _as_dict(actor.get("role_context"))
        party = party_by_email.get(email.lower()) if email else None
        if party is None and name:
            party = party_by_name.get(name.lower())
        if not name:
            name = _compact(_as_dict(party).get("name"))
        if not role_hint:
            role_hint = _compact((_as_list(_as_dict(party).get("roles_in_matter")) or [""])[0])
        roles_in_matter = [str(item) for item in _as_list(_as_dict(party).get("roles_in_matter")) if item]
        chronology_items = chronology_by_actor.get(actor_id, [])
        chronology_ids = [
            str(entry.get("chronology_id") or "") for entry in chronology_items if str(entry.get("chronology_id") or "")
        ][:6]
        chronology_uid_links = [str(entry.get("uid") or "") for entry in chronology_items if str(entry.get("uid") or "")][:6]
        direct_decision_markers = (
            len(_as_list(role_context.get("supplied_role_facts")))
            + len(_as_list(role_context.get("dependencies_as_controller")))
            + len(_as_list(role_context.get("inferred_hierarchy_hints")))
        )
        graph_signal_counts = dict(graph_signal_counts_by_actor.get(actor_id) or {})
        coordination_points = coordination_by_actor.get(actor_id, [])[:3]
        role_status = {
            "decision_maker": bool(
                direct_decision_markers
                or (
                    "target_person" not in roles_in_matter
                    and any(
                        key in graph_signal_counts
                        for key in (
                            "decision_visibility_asymmetry",
                            "repeated_exclusion",
                            "thread_fork_exclusion",
                        )
                    )
                )
            ),
            "witness": bool(email.lower() in witness_email_set if email else name.lower() in witness_name_set if name else False)
            or "org_context_person" in roles_in_matter
            or "comparator_actor" in roles_in_matter,
            "gatekeeper": bool(
                len(_as_list(role_context.get("dependencies_as_controller")))
                or len(_as_list(role_context.get("dependencies_as_dependent")))
                or any(
                    key in graph_signal_counts
                    for key in (
                        "thread_fork_exclusion",
                        "visibility_asymmetry",
                    )
                )
            ),
            "supporter": bool("vulnerability_context_person" in roles_in_matter),
        }
        if target_entity_id and str(_as_dict(party).get("entity_id") or "") == target_entity_id:
            role_status = {
                **role_status,
                "decision_maker": False,
                "gatekeeper": False,
                "supporter": False,
            }
        relationship_parts: list[str] = []
        if chronology_items:
            relationship_parts.append(f"Linked to {len(chronology_items)} chronology event(s) in the shared registry.")
        if graph_signal_counts:
            relationship_parts.append(
                "Communication-graph signals include "
                + ", ".join(f"{key} ({count})" for key, count in sorted(graph_signal_counts.items()))
                + "."
            )
        if source_count_by_actor.get(actor_id):
            relationship_parts.append(f"Associated with {int(source_count_by_actor[actor_id])} mixed-source record(s).")
        if not relationship_parts:
            relationship_parts.append("Present in the matter registry but not yet strongly tied to recorded events.")

        classification = "mixed"
        if role_status["decision_maker"] or role_status["gatekeeper"]:
            classification = "hurts"
        elif role_status["supporter"]:
            classification = "helps"

        row = {
            "actor_id": actor_id,
            "name": name,
            "email": email,
            "role_hint": role_hint,
            "roles_in_matter": roles_in_matter,
            "relationship_to_events": " ".join(relationship_parts),
            "status": role_status,
            "tied_event_ids": chronology_ids,
            "tied_message_or_document_ids": chronology_uid_links,
            "coordination_points": coordination_points,
            "helps_hurts_mixed": classification,
            "source_record_count": int(source_count_by_actor.get(actor_id, 0)),
        }
        actor_rows.append(row)

        if role_status["decision_maker"]:
            decision_makers.append(
                {
                    "actor_id": actor_id,
                    "name": name,
                    "email": email,
                    "decision_basis": [
                        basis
                        for basis, enabled in (
                            ("role_context", direct_decision_markers > 0),
                            ("communication_graph", bool(graph_signal_counts)),
                        )
                        if enabled
                    ],
                    "tied_event_ids": chronology_ids[:4],
                }
            )

        if role_status["witness"] and not role_status["decision_maker"]:
            is_case_scope_witness = bool(
                (email and email.lower() in witness_email_set) or (name and name.lower() in witness_name_set)
            )
            witness_basis = [
                basis
                for basis, enabled in (
                    ("case_scope_witness", is_case_scope_witness),
                    ("supporter", role_status["supporter"]),
                    ("org_context_person", "org_context_person" in roles_in_matter),
                    ("comparator_actor", "comparator_actor" in roles_in_matter),
                    ("record_presence", bool(source_count_by_actor.get(actor_id, 0))),
                )
                if enabled
            ]
            independence_blockers = [
                blocker
                for blocker, enabled in (
                    ("gatekeeper_role", role_status["gatekeeper"]),
                    ("org_context_only", "org_context_person" in roles_in_matter and not is_case_scope_witness),
                    ("comparator_actor_only", "comparator_actor" in roles_in_matter and not is_case_scope_witness),
                    ("record_presence_only", bool(source_count_by_actor.get(actor_id, 0)) and not is_case_scope_witness),
                    ("suspected_actor_role", "suspected_actor" in roles_in_matter),
                )
                if enabled
            ]
            witness_row = {
                "actor_id": actor_id,
                "name": name,
                "email": email,
                "witness_basis": witness_basis,
                "independence_status": "potentially_independent" if not independence_blockers else "mixed_or_nonindependent",
                "independence_blockers": independence_blockers,
                "tied_event_ids": chronology_ids[:4],
            }
            if independence_blockers:
                mixed_or_nonindependent_witnesses.append(witness_row)
            else:
                independent_witnesses.append(witness_row)

    coordination_points = sorted(
        (point for points in coordination_by_actor.values() for point in points if isinstance(point, dict)),
        key=lambda item: (str(item.get("coordination_type") or ""), str(item.get("coordination_id") or "")),
    )

    actor_rows.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("email") or ""), str(item.get("actor_id") or "")))
    decision_makers.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("email") or "")))
    independent_witnesses.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("email") or "")))
    mixed_or_nonindependent_witnesses.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("email") or "")))
    record_holders.sort(key=lambda item: (str(item.get("actor_id") or ""), str(item.get("source_type") or "")))

    return {
        "version": ACTOR_WITNESS_MAP_VERSION,
        "actor_map": {
            "actor_count": len(actor_rows),
            "actors": actor_rows,
            "summary": {
                "decision_maker_count": sum(1 for row in actor_rows if _as_dict(row.get("status")).get("decision_maker")),
                "witness_count": sum(1 for row in actor_rows if _as_dict(row.get("status")).get("witness")),
                "gatekeeper_count": sum(1 for row in actor_rows if _as_dict(row.get("status")).get("gatekeeper")),
                "supporter_count": sum(1 for row in actor_rows if _as_dict(row.get("status")).get("supporter")),
                "coordination_point_count": len(coordination_points),
            },
        },
        "witness_map": {
            "primary_decision_makers": decision_makers,
            "potentially_independent_witnesses": independent_witnesses,
            "mixed_or_nonindependent_witnesses": mixed_or_nonindependent_witnesses,
            "high_value_record_holders": record_holders,
            "coordination_points": coordination_points[:8],
        },
    }
