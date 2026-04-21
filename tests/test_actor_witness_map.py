from __future__ import annotations

from src.actor_witness_map import build_actor_witness_map


def test_build_actor_witness_map_renders_actor_and_witness_outputs() -> None:
    payload = build_actor_witness_map(
        case_bundle={
            "scope": {
                "target_person": {"name": "Alex Example", "email": "alex@example.com"},
                "witnesses": [{"name": "Jamie Witness", "email": "jamie@example.com"}],
            }
        },
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-target",
                    "primary_email": "alex@example.com",
                    "display_names": ["Alex Example"],
                    "role_hints": ["employee"],
                },
                {
                    "actor_id": "actor-manager",
                    "primary_email": "manager@example.com",
                    "display_names": ["Morgan Manager"],
                    "role_hints": ["manager"],
                    "role_context": {
                        "supplied_role_facts": [{"role": "manager"}],
                        "dependencies_as_controller": [{"dependency_type": "approval"}],
                    },
                },
                {
                    "actor_id": "actor-witness",
                    "primary_email": "jamie@example.com",
                    "display_names": ["Jamie Witness"],
                    "role_hints": ["colleague"],
                },
            ]
        },
        communication_graph={
            "graph_findings": [
                {
                    "finding_id": "decision_visibility_asymmetry:actor-manager",
                    "graph_signal_type": "decision_visibility_asymmetry",
                    "summary": "Decision flow varies with target visibility.",
                    "evidence_chain": {
                        "sender_node_id": "actor-manager",
                        "message_uids": ["uid-2"],
                        "thread_group_ids": ["conv-1"],
                    },
                }
            ]
        },
        master_chronology={
            "entries": [
                {
                    "chronology_id": "chron-1",
                    "actor_id": "actor-manager",
                    "uid": "uid-1",
                },
                {
                    "chronology_id": "chron-2",
                    "actor_id": "actor-witness",
                    "uid": "uid-2",
                },
            ]
        },
        matter_workspace={
            "matter": {"target_person_entity_id": "person-target"},
            "parties": [
                {
                    "entity_id": "person-target",
                    "name": "Alex Example",
                    "email": "alex@example.com",
                    "roles_in_matter": ["target_person"],
                },
                {
                    "entity_id": "person-manager",
                    "name": "Morgan Manager",
                    "email": "manager@example.com",
                    "roles_in_matter": ["suspected_actor", "org_context_person"],
                },
                {
                    "entity_id": "person-witness",
                    "name": "Jamie Witness",
                    "email": "jamie@example.com",
                    "roles_in_matter": ["org_context_person"],
                },
            ],
        },
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "actor_id": "actor-manager",
                },
                {
                    "source_id": "calendar:uid-2",
                    "source_type": "calendar_event",
                    "actor_id": "actor-witness",
                },
            ]
        },
    )

    assert payload is not None
    assert payload["version"] == "1"
    actor_map = payload["actor_map"]
    witness_map = payload["witness_map"]
    assert actor_map["actor_count"] == 3
    manager = next(row for row in actor_map["actors"] if row["actor_id"] == "actor-manager")
    assert manager["status"]["decision_maker"] is True
    assert manager["status"]["gatekeeper"] is True
    assert manager["helps_hurts_mixed"] == "hurts"
    assert manager["coordination_points"][0]["coordination_type"] == "decision_visibility_asymmetry"
    witness = next(row for row in actor_map["actors"] if row["actor_id"] == "actor-witness")
    assert witness["status"]["witness"] is True
    assert witness["tied_event_ids"] == ["chron-2"]
    assert witness_map["primary_decision_makers"][0]["actor_id"] == "actor-manager"
    assert witness_map["potentially_independent_witnesses"][0]["actor_id"] == "actor-witness"
    assert witness_map["high_value_record_holders"][0]["record_holder_type"] in {
        "calendar_record_holder",
        "email_record_holder",
    }
    assert witness_map["coordination_points"][0]["coordination_id"] == "decision_visibility_asymmetry:actor-manager"


def test_build_actor_witness_map_uses_chat_participants_when_actor_id_is_missing() -> None:
    payload = build_actor_witness_map(
        case_bundle={"scope": {"target_person": {"name": "Alex Example", "email": "alex@example.com"}}},
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-manager",
                    "primary_email": "manager@example.com",
                    "display_names": ["Morgan Manager"],
                    "role_hints": ["manager"],
                }
            ]
        },
        communication_graph={"graph_findings": []},
        master_chronology={"entries": []},
        matter_workspace={
            "matter": {},
            "parties": [
                {
                    "entity_id": "person-manager",
                    "name": "Morgan Manager",
                    "email": "manager@example.com",
                    "roles_in_matter": ["org_context_person"],
                }
            ],
        },
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "chat:1",
                    "source_type": "chat_log",
                    "actor_id": "",
                    "participants": ["manager@example.com"],
                }
            ]
        },
    )

    assert payload is not None
    manager = next(row for row in payload["actor_map"]["actors"] if row["actor_id"] == "actor-manager")
    assert manager["source_record_count"] == 1
    assert any(
        holder["actor_id"] == "actor-manager" and holder["source_type"] == "chat_log"
        for holder in payload["witness_map"]["high_value_record_holders"]
    )


def test_build_actor_witness_map_does_not_treat_org_context_record_holder_as_independent() -> None:
    payload = build_actor_witness_map(
        case_bundle={"scope": {"target_person": {"name": "Alex Example", "email": "alex@example.com"}}},
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-manager",
                    "primary_email": "manager@example.com",
                    "display_names": ["Morgan Manager"],
                    "role_hints": ["manager"],
                }
            ]
        },
        communication_graph={"graph_findings": []},
        master_chronology={"entries": [{"chronology_id": "chron-1", "actor_id": "actor-manager", "uid": "uid-1"}]},
        matter_workspace={
            "matter": {},
            "parties": [
                {
                    "entity_id": "person-manager",
                    "name": "Morgan Manager",
                    "email": "manager@example.com",
                    "roles_in_matter": ["org_context_person"],
                }
            ],
        },
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "actor_id": "actor-manager",
                }
            ]
        },
    )

    assert payload is not None
    manager = next(row for row in payload["actor_map"]["actors"] if row["actor_id"] == "actor-manager")
    assert manager["status"]["witness"] is True
    assert payload["witness_map"]["potentially_independent_witnesses"] == []


def test_build_actor_witness_map_backfills_party_identity_and_uid_linkage() -> None:
    payload = build_actor_witness_map(
        case_bundle={"scope": {"target_person": {"name": "Alex Example", "email": "alex@example.com"}}},
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-target",
                    "primary_email": "alex@example.com",
                    "display_names": ["Alex Example"],
                    "role_hints": ["employee"],
                },
                {
                    "actor_id": "actor-manager",
                    "primary_email": "manager@example.com",
                    "display_names": [],
                    "role_hints": [],
                },
            ]
        },
        communication_graph={"graph_findings": []},
        master_chronology={
            "entries": [
                {
                    "chronology_id": "chron-1",
                    "uid": "uid-1",
                    "actor_id": "",
                }
            ]
        },
        matter_workspace={
            "matter": {},
            "parties": [
                {
                    "entity_id": "person-manager",
                    "name": "Morgan Manager",
                    "email": "manager@example.com",
                    "roles_in_matter": ["suspected_actor"],
                }
            ],
        },
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "formal_document:1",
                    "source_type": "formal_document",
                    "uid": "uid-1",
                    "actor_id": "",
                    "author": "manager@example.com",
                }
            ]
        },
    )

    assert payload is not None
    manager = next(row for row in payload["actor_map"]["actors"] if row["actor_id"] == "actor-manager")
    assert manager["name"] == "Morgan Manager"
    assert manager["role_hint"] == "suspected_actor"
    assert manager["tied_event_ids"] == ["chron-1"]
    assert manager["source_record_count"] == 1


def test_build_actor_witness_map_synthesizes_source_people_and_links_source_backed_chronology() -> None:
    payload = build_actor_witness_map(
        case_bundle={"scope": {"target_person": {"name": "Alex Example", "email": "alex@example.com"}}},
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-target",
                    "primary_email": "alex@example.com",
                    "display_names": ["Alex Example"],
                    "role_hints": ["employee"],
                }
            ]
        },
        communication_graph={"graph_findings": []},
        master_chronology={
            "entries": [
                {
                    "chronology_id": "chron-1",
                    "uid": "",
                    "actor_id": "",
                    "source_linkage": {"source_ids": ["manifest:file:thread:1"]},
                }
            ]
        },
        matter_workspace={"matter": {}, "parties": []},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "manifest:file:thread:1",
                    "source_type": "formal_document",
                    "author": "Morgan Manager <manager@example.com>",
                    "recipients": ["Alex Example <alex@example.com>"],
                }
            ]
        },
    )

    assert payload is not None
    manager = next(row for row in payload["actor_map"]["actors"] if row["email"] == "manager@example.com")
    assert manager["name"] == "Morgan Manager"
    assert manager["source_record_count"] == 1
    assert manager["tied_event_ids"] == ["chron-1"]
    assert any(
        holder["actor_id"] == manager["actor_id"] and holder["source_type"] == "formal_document"
        for holder in payload["witness_map"]["high_value_record_holders"]
    )
