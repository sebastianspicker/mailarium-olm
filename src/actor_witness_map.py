"""Shared actor-map and witness-map builders for counsel-facing outputs."""
# pylint: disable=too-many-arguments,too-many-boolean-expressions,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from src._utils import as_dict, as_list, compact

ACTOR_WITNESS_MAP_VERSION = "1"


_IDENTITY_PATTERN = re.compile(r"^(?P<name>.*?)<(?P<email>[^<>]+)>$")


def _parse_identity(value: Any) -> tuple[str, str]:
    """Parse an identity string into name and email components.

    Returns:
        A tuple of (name, email) extracted from the identity string.
        Handles formats like 'Name <email@example.com>' or plain email addresses.
    """
    text = compact(value)
    if not text:
        return ("", "")
    match = _IDENTITY_PATTERN.match(text)
    if match:
        return (compact(match.group("name")), compact(match.group("email")).lower())
    if "@" in text and " " not in text:
        return ("", text.lower())
    return (text, "")


def _synthetic_actor_id(*, name: str, email: str) -> str:
    """Generate a synthetic actor ID from name and email.

    Creates a deterministic synthetic actor ID using BLAKE2s hash of the
    email (or name if email is empty) to ensure consistent identification.
    """
    signature = email or name.lower()
    digest = hashlib.blake2s(signature.encode("utf-8"), digest_size=6).hexdigest()
    return f"actor-synth-{digest}"


def _actor_name(actor: dict[str, Any]) -> str:
    """Extract the primary name from an actor dictionary.

    Returns the primary_name if available, otherwise the first display_name.
    """
    primary_name = compact(actor.get("primary_name"))
    if primary_name:
        return primary_name
    display_names = [str(item) for item in as_list(actor.get("display_names")) if compact(item)]
    if display_names:
        return display_names[0]
    return ""


def _actor_role_hint(actor: dict[str, Any]) -> str:
    """Extract the role hint from an actor dictionary.

    Returns the role_hint if available, otherwise the first role_hints entry.
    """
    role_hint = compact(actor.get("role_hint"))
    if role_hint:
        return role_hint
    role_hints = [str(item) for item in as_list(actor.get("role_hints")) if compact(item)]
    if role_hints:
        return role_hints[0]
    return ""


def _actor_email(actor: dict[str, Any]) -> str:
    """Extract the primary email from an actor dictionary.

    Returns the primary_email if available, otherwise the first emails entry.
    """
    primary_email = compact(actor.get("primary_email"))
    if primary_email:
        return primary_email
    emails = [str(item) for item in as_list(actor.get("emails")) if compact(item)]
    if emails:
        return emails[0]
    return ""


def _record_holder_kind(source_type: str) -> str:
    """Map a source type to its corresponding record holder kind."""
    return {
        "email": "email_record_holder",
        "calendar_event": "calendar_record_holder",
        "note_record": "note_record_holder",
        "time_record": "time_record_holder",
        "participation_record": "participation_record_holder",
    }.get(source_type, "document_record_holder")


def _source_identity_tokens(source: dict[str, Any]) -> list[str]:
    """Extract identity tokens (names and emails) from a source dictionary.

    Returns a deduplicated list of normalized identity tokens from the source.
    """
    tokens: list[str] = []
    for entry in _source_identity_entries(source):
        for value in (entry.get("name"), entry.get("email")):
            compacted = compact(value).lower()
            if compacted:
                tokens.append(compacted)
    return list(dict.fromkeys(tokens))


def _source_identity_entries(source: dict[str, Any]) -> list[dict[str, str]]:
    """Extract identity entries from a source dictionary.

    Parses author, sender, participants, recipients, and other identity fields
    from the source and returns deduplicated identity entries with name and email.
    """
    entries: list[dict[str, str]] = []
    for key in ("author", "sender_name", "sender_email"):
        name, email = _parse_identity(source.get(key))
        if name or email:
            entries.append({"name": name, "email": email})
    for list_key in ("participants", "recipients", "to", "cc", "bcc"):
        for item in as_list(source.get(list_key)):
            name, email = _parse_identity(item)
            if name or email:
                entries.append({"name": name, "email": email})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        identity_key = (compact(entry.get("name")).lower(), compact(entry.get("email")).lower())
        if identity_key == ("", "") or identity_key in seen:
            continue
        seen.add(identity_key)
        deduped.append({"name": compact(entry.get("name")), "email": compact(entry.get("email")).lower()})
    return deduped


def _actor_ids_for_source(
    source: dict[str, Any],
    *,
    actor_by_email: dict[str, str],
    actor_by_name: dict[str, str],
) -> list[str]:
    """Find actor IDs associated with a source.

    Returns actor IDs by matching source identity tokens against the provided
    actor mappings (by email and name). Falls back to the source's actor_id if present.
    """
    actor_id = str(source.get("actor_id") or "")
    if actor_id:
        return [actor_id]
    participant_ids: list[str] = []
    for participant in _source_identity_tokens(source):
        normalized = compact(participant).lower()
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
    inputs = _actor_witness_inputs(
        case_bundle, actor_identity_graph, communication_graph, master_chronology, matter_workspace, multi_source_case_bundle
    )
    if inputs is None:
        return None
    (
        scope,
        chronology_entries,
        _workspace_parties,
        graph_findings,
        mixed_sources,
        graph_actors,
        actor_by_email,
        actor_by_name,
        party_by_email,
        party_by_name,
    ) = inputs
    chronology_by_actor = _chronology_actor_map(chronology_entries, mixed_sources, actor_by_email, actor_by_name)
    coordination_by_actor, graph_signal_counts_by_actor = _coordination_maps(graph_findings)
    record_data = _record_holder_data(scope, matter_workspace, mixed_sources, actor_by_email, actor_by_name)
    (
        witness_email_set,
        witness_name_set,
        target_entity_id,
        record_holders,
        source_count_by_actor,
        actor_rows,
        decision_makers,
        independent_witnesses,
        mixed_or_nonindependent_witnesses,
    ) = record_data
    _populate_actor_rows(
        graph_actors,
        party_by_email,
        party_by_name,
        chronology_by_actor,
        graph_signal_counts_by_actor,
        coordination_by_actor,
        source_count_by_actor,
        witness_email_set,
        witness_name_set,
        target_entity_id,
        (actor_rows, decision_makers, independent_witnesses, mixed_or_nonindependent_witnesses),
    )

    return _final_actor_witness_payload(
        coordination_by_actor,
        actor_rows,
        decision_makers,
        independent_witnesses,
        mixed_or_nonindependent_witnesses,
        record_holders,
    )


def _actor_witness_inputs(
    case_bundle, actor_identity_graph, communication_graph, master_chronology, matter_workspace, multi_source_case_bundle
):
    scope = as_dict(as_dict(case_bundle).get("scope"))
    actor_graph = as_dict(actor_identity_graph)
    chronology_entries = _dict_rows(master_chronology, "entries")
    workspace_parties = _dict_rows(matter_workspace, "parties")
    graph_findings = _dict_rows(communication_graph, "graph_findings")
    mixed_sources = _dict_rows(multi_source_case_bundle, "sources")
    graph_actors = [
        entry for entry in as_list(actor_graph.get("actors")) if isinstance(entry, dict) and str(entry.get("actor_id") or "")
    ]
    if not graph_actors and not workspace_parties:
        return None
    party_by_email = _party_map(workspace_parties, "email")
    party_by_name = _party_map(workspace_parties, "name")
    graph_actors.extend(_synthetic_source_actors(graph_actors, mixed_sources, party_by_email, party_by_name))
    actor_by_email, actor_by_name = _actor_maps(graph_actors)
    return (
        scope,
        chronology_entries,
        workspace_parties,
        graph_findings,
        mixed_sources,
        graph_actors,
        actor_by_email,
        actor_by_name,
        party_by_email,
        party_by_name,
    )


def _dict_rows(payload, key):
    return [entry for entry in as_list(as_dict(payload).get(key)) if isinstance(entry, dict)]


def _party_map(parties, key):
    return {compact(entry.get(key)).lower(): entry for entry in parties if compact(entry.get(key))}


def _actor_maps(actors):
    by_email = {
        _actor_email(actor).lower(): str(actor.get("actor_id") or "")
        for actor in actors
        if _actor_email(actor) and str(actor.get("actor_id") or "")
    }
    by_name = {
        _actor_name(actor).lower(): str(actor.get("actor_id") or "")
        for actor in actors
        if _actor_name(actor) and str(actor.get("actor_id") or "")
    }
    return by_email, by_name


def _synthetic_source_actors(graph_actors, sources, party_by_email, party_by_name):
    names = {_actor_name(actor).lower() for actor in graph_actors if _actor_name(actor)}
    emails = {_actor_email(actor).lower() for actor in graph_actors if _actor_email(actor)}
    synthetic = []
    for source in sources:
        for identity in _source_identity_entries(source):
            row = _synthetic_actor(identity, names, emails, party_by_email, party_by_name)
            if row is not None:
                synthetic.append(row)
    return synthetic


def _synthetic_actor(identity, names, emails, party_by_email, party_by_name):
    name, email = compact(identity.get("name")), compact(identity.get("email")).lower()
    if _identity_exists(name, email, names, emails):
        return None
    party = _identity_party(name, email, party_by_email, party_by_name)
    roles = [str(item) for item in as_list(as_dict(party).get("roles_in_matter")) if item]
    if name:
        names.add(name.lower())
    if email:
        emails.add(email)
    return {
        "actor_id": _synthetic_actor_id(name=name, email=email),
        "primary_email": email,
        "display_names": [name] if name else [],
        "role_hints": [roles[0] if roles else "source_participant"],
        "role_context": {},
    }


def _identity_exists(name, email, names, emails):
    return bool((email and email in emails) or (name and name.lower() in names) or (not name and not email))


def _identity_party(name, email, by_email, by_name):
    party = by_email.get(email) if email else None
    return by_name.get(name.lower()) if party is None and name else party


def _chronology_actor_map(chronology_entries, mixed_sources, actor_by_email, actor_by_name):
    chronology_by_actor: dict[str, list[dict[str, Any]]] = {}
    source_actor_ids_by_uid, source_actor_ids_by_source_id = _source_actor_maps(mixed_sources, actor_by_email, actor_by_name)
    for entry in chronology_entries:
        for actor_id in _chronology_actor_ids(entry, source_actor_ids_by_uid, source_actor_ids_by_source_id):
            chronology_by_actor.setdefault(actor_id, []).append(entry)
    return chronology_by_actor


def _source_actor_maps(mixed_sources, actor_by_email, actor_by_name):
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
    return source_actor_ids_by_uid, source_actor_ids_by_source_id


def _chronology_actor_ids(entry, by_uid, by_source_id):
    uid = str(entry.get("uid") or "")
    explicit = str(entry.get("actor_id") or "")
    actor_ids = [explicit] if explicit else []
    if not actor_ids and uid:
        actor_ids = [item for item in by_uid.get(uid, []) if item]
    return actor_ids or _linked_actor_ids(entry, by_source_id)


def _linked_actor_ids(entry, by_source_id):
    actor_ids = []
    source_ids = [str(item) for item in as_list(as_dict(entry.get("source_linkage")).get("source_ids")) if str(item).strip()]
    for source_id in source_ids:
        for actor_id in by_source_id.get(source_id, []):
            if actor_id and actor_id not in actor_ids:
                actor_ids.append(actor_id)
    return actor_ids


def _coordination_maps(graph_findings):
    coordination_by_actor: dict[str, list[dict[str, Any]]] = {}
    graph_signal_counts_by_actor: dict[str, Counter[str]] = {}
    for finding in graph_findings:
        signal_type = str(finding.get("graph_signal_type") or "")
        sender_node_id = str(as_dict(finding.get("evidence_chain")).get("sender_node_id") or "")
        if not signal_type or not sender_node_id:
            continue
        graph_signal_counts_by_actor.setdefault(sender_node_id, Counter())[signal_type] += 1
        coordination_by_actor.setdefault(sender_node_id, []).append(
            {
                "coordination_id": str(finding.get("finding_id") or ""),
                "coordination_type": signal_type,
                "summary": str(finding.get("summary") or ""),
                "message_uids": [
                    str(item) for item in as_list(as_dict(finding.get("evidence_chain")).get("message_uids")) if item
                ][:4],
                "thread_group_ids": [
                    str(item) for item in as_list(as_dict(finding.get("evidence_chain")).get("thread_group_ids")) if item
                ][:3],
            }
        )
    return coordination_by_actor, graph_signal_counts_by_actor


def _record_holder_data(scope, matter_workspace, mixed_sources, actor_by_email, actor_by_name):
    witnesses = [entry for entry in as_list(scope.get("witnesses")) if isinstance(entry, dict)]
    witness_email_set = {compact(entry.get("email")).lower() for entry in witnesses if compact(entry.get("email"))}
    witness_name_set = {compact(entry.get("name")).lower() for entry in witnesses if compact(entry.get("name"))}

    matter = as_dict(matter_workspace).get("matter")
    target_entity_id = str(as_dict(matter).get("target_person_entity_id") or "")

    actor_rows: list[dict[str, Any]] = []
    decision_makers: list[dict[str, Any]] = []
    independent_witnesses: list[dict[str, Any]] = []
    mixed_or_nonindependent_witnesses: list[dict[str, Any]] = []
    record_holders: list[dict[str, Any]] = []

    record_holders, source_count_by_actor, source_type_count_by_actor = _aggregate_record_holders(
        mixed_sources, actor_by_email, actor_by_name
    )
    _fill_record_holders(record_holders, source_type_count_by_actor, mixed_sources, actor_by_email, actor_by_name)
    return (
        witness_email_set,
        witness_name_set,
        target_entity_id,
        record_holders,
        source_count_by_actor,
        actor_rows,
        decision_makers,
        independent_witnesses,
        mixed_or_nonindependent_witnesses,
    )


def _aggregate_record_holders(mixed_sources, actor_by_email, actor_by_name):
    record_holders, seen = [], set()
    source_count_by_actor = Counter()
    source_type_count_by_actor = {}
    for source in mixed_sources:
        source_type = str(source.get("source_type") or "")
        actor_ids = _actor_ids_for_source(source, actor_by_email=actor_by_email, actor_by_name=actor_by_name)
        if not actor_ids or not source_type:
            continue
        for actor_id in actor_ids:
            source_count_by_actor[actor_id] += 1
            source_type_count_by_actor.setdefault(actor_id, Counter())[source_type] += 1
            key = (actor_id, source_type)
            if key in seen:
                continue
            seen.add(key)
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

    return record_holders, source_count_by_actor, source_type_count_by_actor


def _fill_record_holders(record_holders, source_type_counts, mixed_sources, actor_by_email, actor_by_name):
    for holder in record_holders:
        actor_id = str(holder.get("actor_id") or "")
        source_type = str(holder.get("source_type") or "")
        holder["source_count"] = int(source_type_counts.get(actor_id, Counter()).get(source_type, 0))
        holder["source_ids"] = [
            str(source.get("source_id") or "")
            for source in mixed_sources
            if actor_id in _actor_ids_for_source(source, actor_by_email=actor_by_email, actor_by_name=actor_by_name)
            and str(source.get("source_type") or "") == source_type
        ][:4]


def _populate_actor_rows(
    graph_actors,
    party_by_email,
    party_by_name,
    chronology_by_actor,
    graph_signal_counts_by_actor,
    coordination_by_actor,
    source_count_by_actor,
    witness_email_set,
    witness_name_set,
    target_entity_id,
    outputs,
):
    actor_rows, decision_makers, independent_witnesses, mixed_or_nonindependent_witnesses = outputs
    context = {
        "party_by_email": party_by_email,
        "party_by_name": party_by_name,
        "chronology": chronology_by_actor,
        "signals": graph_signal_counts_by_actor,
        "coordination": coordination_by_actor,
        "source_counts": source_count_by_actor,
        "witness_emails": witness_email_set,
        "witness_names": witness_name_set,
        "target_entity_id": target_entity_id,
    }
    for actor in graph_actors:
        data = _actor_row(actor, context)
        if data is None:
            continue
        row, decision_markers, signal_counts, chronology_ids = data
        actor_rows.append(row)
        _append_decision_maker(row, decision_markers, signal_counts, chronology_ids, decision_makers)
        witness = _witness_row(row, context, chronology_ids)
        if witness is not None:
            destination = mixed_or_nonindependent_witnesses if witness["independence_blockers"] else independent_witnesses
            destination.append(witness)


def _actor_row(actor, context):
    actor_id = str(actor.get("actor_id") or "")
    if not actor_id:
        return None
    email, name, role_hint, party = _actor_identity(actor, context)
    roles = [str(item) for item in as_list(as_dict(party).get("roles_in_matter")) if item]
    role_context = as_dict(actor.get("role_context"))
    chronology = context["chronology"].get(actor_id, [])
    chronology_ids = _entry_ids(chronology, "chronology_id", 6)
    uid_links = _entry_ids(chronology, "uid", 6)
    decision_markers = sum(
        len(as_list(role_context.get(key)))
        for key in ("supplied_role_facts", "dependencies_as_controller", "inferred_hierarchy_hints")
    )
    signal_counts = dict(context["signals"].get(actor_id) or {})
    status = _role_status(email, name, roles, role_context, signal_counts, party, context, decision_markers)
    row = {
        "actor_id": actor_id,
        "name": name,
        "email": email,
        "role_hint": role_hint,
        "roles_in_matter": roles,
        "relationship_to_events": _relationship_text(actor_id, chronology, signal_counts, context["source_counts"]),
        "status": status,
        "tied_event_ids": chronology_ids,
        "tied_message_or_document_ids": uid_links,
        "coordination_points": context["coordination"].get(actor_id, [])[:3],
        "helps_hurts_mixed": _help_class(status),
        "source_record_count": int(context["source_counts"].get(actor_id, 0)),
    }
    return row, decision_markers, signal_counts, chronology_ids


def _actor_identity(actor, context):
    email, name, role_hint = _actor_email(actor), _actor_name(actor), _actor_role_hint(actor)
    party = context["party_by_email"].get(email.lower()) if email else None
    if party is None and name:
        party = context["party_by_name"].get(name.lower())
    if not name:
        name = compact(as_dict(party).get("name"))
    if not role_hint:
        role_hint = compact((as_list(as_dict(party).get("roles_in_matter")) or [""])[0])
    return email, name, role_hint, party


def _entry_ids(entries, key, limit):
    return [str(entry.get(key) or "") for entry in entries if str(entry.get(key) or "")][:limit]


def _role_status(email, name, roles, role_context, signals, party, context, decision_markers):
    decision = _is_decision_maker(roles, signals, decision_markers)
    witness_identity = _is_named_witness(email, name, context)
    gatekeeper = _is_gatekeeper(role_context, signals)
    status = {
        "decision_maker": decision,
        "witness": bool(witness_identity or "org_context_person" in roles or "comparator_actor" in roles),
        "gatekeeper": gatekeeper,
        "supporter": "vulnerability_context_person" in roles,
    }
    if context["target_entity_id"] and str(as_dict(party).get("entity_id") or "") == context["target_entity_id"]:
        status.update({"decision_maker": False, "gatekeeper": False, "supporter": False})
    return status


def _is_decision_maker(roles, signals, markers):
    signal_ids = ("decision_visibility_asymmetry", "repeated_exclusion", "thread_fork_exclusion")
    return bool(markers or ("target_person" not in roles and any(key in signals for key in signal_ids)))


def _is_named_witness(email, name, context):
    if email:
        return email.lower() in context["witness_emails"]
    return bool(name and name.lower() in context["witness_names"])


def _is_gatekeeper(role_context, signals):
    dependencies = as_list(role_context.get("dependencies_as_controller")) or as_list(
        role_context.get("dependencies_as_dependent")
    )
    return bool(dependencies or any(key in signals for key in ("thread_fork_exclusion", "visibility_asymmetry")))


def _relationship_text(actor_id, chronology, signals, source_counts):
    parts = []
    if chronology:
        parts.append(f"Linked to {len(chronology)} chronology event(s) in the shared registry.")
    if signals:
        parts.append(
            "Communication-graph signals include " + ", ".join(f"{key} ({count})" for key, count in sorted(signals.items())) + "."
        )
    if source_counts.get(actor_id):
        parts.append(f"Associated with {int(source_counts[actor_id])} mixed-source record(s).")
    return " ".join(parts or ["Present in the matter registry but not yet strongly tied to recorded events."])


def _help_class(status):
    if status["decision_maker"] or status["gatekeeper"]:
        return "hurts"
    return "helps" if status["supporter"] else "mixed"


def _append_decision_maker(row, decision_markers, signals, chronology_ids, destination):
    if not row["status"]["decision_maker"]:
        return
    basis = [
        label for label, enabled in (("role_context", decision_markers > 0), ("communication_graph", bool(signals))) if enabled
    ]
    destination.append(
        {
            "actor_id": row["actor_id"],
            "name": row["name"],
            "email": row["email"],
            "decision_basis": basis,
            "tied_event_ids": chronology_ids[:4],
        }
    )


def _witness_row(row, context, chronology_ids):
    status, roles = row["status"], row["roles_in_matter"]
    if not status["witness"] or status["decision_maker"]:
        return None
    email, name, actor_id = row["email"], row["name"], row["actor_id"]
    scoped = bool((email and email.lower() in context["witness_emails"]) or (name and name.lower() in context["witness_names"]))
    present = bool(context["source_counts"].get(actor_id, 0))
    basis = _witness_basis(status, roles, scoped, present)
    blockers = _independence_blockers(status, roles, scoped, present)
    return {
        "actor_id": actor_id,
        "name": name,
        "email": email,
        "witness_basis": basis,
        "independence_status": "potentially_independent" if not blockers else "mixed_or_nonindependent",
        "independence_blockers": blockers,
        "tied_event_ids": chronology_ids[:4],
    }


def _witness_basis(status, roles, scoped, record_present):
    checks = (
        ("case_scope_witness", scoped),
        ("supporter", status["supporter"]),
        ("org_context_person", "org_context_person" in roles),
        ("comparator_actor", "comparator_actor" in roles),
        ("record_presence", record_present),
    )
    return [label for label, enabled in checks if enabled]


def _independence_blockers(status, roles, scoped, record_present):
    checks = (
        ("gatekeeper_role", status["gatekeeper"]),
        ("org_context_only", "org_context_person" in roles and not scoped),
        ("comparator_actor_only", "comparator_actor" in roles and not scoped),
        ("record_presence_only", record_present and not scoped),
        ("suspected_actor_role", "suspected_actor" in roles),
    )
    return [label for label, enabled in checks if enabled]


def _final_actor_witness_payload(
    coordination_by_actor, actor_rows, decision_makers, independent_witnesses, mixed_witnesses, record_holders
):
    coordination_points = _coordination_points(coordination_by_actor)
    _sort_actor_outputs(actor_rows, decision_makers, independent_witnesses, mixed_witnesses, record_holders)
    status_counts = _actor_status_counts(actor_rows)

    return {
        "version": ACTOR_WITNESS_MAP_VERSION,
        "actor_map": {
            "actor_count": len(actor_rows),
            "actors": actor_rows,
            "summary": {
                "decision_maker_count": status_counts["decision_maker"],
                "witness_count": status_counts["witness"],
                "gatekeeper_count": status_counts["gatekeeper"],
                "supporter_count": status_counts["supporter"],
                "coordination_point_count": len(coordination_points),
            },
        },
        "witness_map": {
            "primary_decision_makers": decision_makers,
            "potentially_independent_witnesses": independent_witnesses,
            "mixed_or_nonindependent_witnesses": mixed_witnesses,
            "high_value_record_holders": record_holders,
            "coordination_points": coordination_points[:8],
        },
    }


def _coordination_points(by_actor):
    points = [point for rows in by_actor.values() for point in rows if isinstance(point, dict)]
    return sorted(points, key=lambda item: (str(item.get("coordination_type") or ""), str(item.get("coordination_id") or "")))


def _sort_actor_outputs(actors, decision_makers, independent, mixed, holders):
    actors.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("email") or ""), str(item.get("actor_id") or "")))
    for rows in (decision_makers, independent, mixed):
        rows.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("email") or "")))
    holders.sort(key=lambda item: (str(item.get("actor_id") or ""), str(item.get("source_type") or "")))


def _actor_status_counts(actor_rows):
    counts = Counter()
    for row in actor_rows:
        for key, enabled in as_dict(row.get("status")).items():
            if enabled:
                counts[key] += 1
    return counts
