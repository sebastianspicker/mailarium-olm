from __future__ import annotations

from src.actor_resolution import resolve_actor_graph, resolve_actor_id
from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput


def test_resolve_actor_graph_merges_email_aliases_across_case_scope_and_candidates():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com", role_hint="manager")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
    )
    candidates = [
        {
            "uid": "uid-1",
            "sender_email": "MANAGER@example.com",
            "sender_name": "Morgan M.",
            "speaker_attribution": {
                "authored_speaker": {"email": "manager@example.com", "name": "Morgan Manager"},
                "quoted_blocks": [{"speaker_email": "alex@example.com"}],
            },
        }
    ]
    graph = resolve_actor_graph(
        case_scope=scope,
        candidates=candidates,
        attachment_candidates=[],
        full_map={
            "uid-1": {
                "to": ["Alex Example <alex@example.com>"],
                "cc": [],
                "bcc": [],
                "reply_context_from": "alex@example.com",
                "reply_context_to_json": "[]",
            }
        },
    )

    assert graph["stats"]["actor_count"] == 2
    manager = next(actor for actor in graph["actors"] if actor["primary_email"] == "manager@example.com")
    alex = next(actor for actor in graph["actors"] if actor["primary_email"] == "alex@example.com")
    assert manager["display_names"] == ["Morgan M.", "Morgan Manager"]
    assert "manager" in manager["role_hints"]
    actor_id, resolution = resolve_actor_id(graph, email="manager@example.com")
    assert actor_id == manager["actor_id"]
    assert resolution == {"resolved_by": "email", "ambiguous": False}
    quoted_actor_id, quoted_resolution = resolve_actor_id(graph, email="alex@example.com")
    assert quoted_actor_id == alex["actor_id"]
    assert quoted_resolution == {"resolved_by": "email", "ambiguous": False}


def test_resolve_actor_id_does_not_over_merge_ambiguous_name_only_reference():
    graph = resolve_actor_graph(
        case_scope=None,
        candidates=[
            {"uid": "uid-1", "sender_email": "alex.one@example.com", "sender_name": "Alex Example"},
            {"uid": "uid-2", "sender_email": "alex.two@example.com", "sender_name": "Alex Example"},
        ],
        attachment_candidates=[],
        full_map={},
    )

    actor_id, resolution = resolve_actor_id(graph, name="Alex Example")

    assert actor_id is None
    assert resolution == {"resolved_by": "name", "ambiguous": True}
    assert graph["stats"]["ambiguous_name_count"] == 1


def test_resolve_actor_graph_registers_comparators_and_representation_roles():
    scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com", role_hint="manager")],
        comparator_actors=[CasePartyInput(name="Pat Peer", email="personalrat@example.com")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
    )

    graph = resolve_actor_graph(
        case_scope=scope,
        candidates=[],
        attachment_candidates=[],
        full_map={},
    )

    assert graph["stats"]["actor_count"] == 3
    comparator = next(actor for actor in graph["actors"] if actor["primary_email"] == "personalrat@example.com")
    target = next(actor for actor in graph["actors"] if actor["primary_email"] == "alex@example.com")
    assert "comparator" in comparator["role_hints"]
    assert "representation" in comparator["role_hints"]
    assert "target_person" in target["role_hints"]


def test_resolve_actor_graph_tolerates_malformed_reply_context_json() -> None:
    graph = resolve_actor_graph(
        case_scope=None,
        candidates=[
            {
                "uid": "uid-malformed",
                "sender_email": "manager@example.com",
                "sender_name": "Morgan Manager",
            }
        ],
        attachment_candidates=[],
        full_map={
            "uid-malformed": {
                "to": ["Alex Example <alex@example.com>"],
                "cc": [],
                "bcc": [],
                "reply_context_from": "alex@example.com",
                "reply_context_to_json": "{invalid-json",
            }
        },
    )

    assert graph["stats"]["actor_count"] == 2
    reasons = {str(item.get("reason") or "") for item in graph["unresolved_references"]}
    assert "malformed_reply_context_to_json" in reasons


def test_resolve_actor_graph_uses_entity_occurrences_for_actor_hints() -> None:
    graph = resolve_actor_graph(
        case_scope=None,
        candidates=[
            {
                "uid": "uid-entity-occ",
                "sender_email": "leader@example.com",
                "sender_name": "Leitung",
                "entity_occurrences": [
                    {
                        "entity_text": "Alex Example",
                        "entity_type": "person",
                        "source_scope": "authored_body",
                    },
                    {
                        "entity_text": "SBV",
                        "entity_type": "organization",
                        "normalized_form": "sbv",
                        "source_scope": "authored_body",
                    },
                ],
            }
        ],
        attachment_candidates=[],
        full_map={},
    )

    leader = next(actor for actor in graph["actors"] if actor["primary_email"] == "leader@example.com")
    assert "representation" in leader["role_hints"]
    assert any("Alex Example" in actor["display_names"] for actor in graph["actors"])
