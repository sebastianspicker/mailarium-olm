from __future__ import annotations

from src.communication_graph import build_communication_graph


def test_build_communication_graph_reports_repeated_exclusion_and_visibility_asymmetry():
    graph = build_communication_graph(
        case_bundle={
            "scope": {
                "target_person": {
                    "name": "Alex Example",
                    "email": "alex@example.com",
                    "actor_id": "actor-target",
                }
            }
        },
        candidates=[
            {
                "uid": "u1",
                "sender_actor_id": "actor-manager",
                "sender_email": "manager@example.com",
                "thread_group_id": "thread-a",
                "snippet": "Alex Example will be informed later.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "withholding"},
                        ]
                    }
                },
            },
            {
                "uid": "u2",
                "sender_actor_id": "actor-manager",
                "sender_email": "manager@example.com",
                "thread_group_id": "thread-a",
                "snippet": "Alex Example will be informed later.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "exclusion"},
                        ]
                    }
                },
            },
            {
                "uid": "u3",
                "sender_actor_id": "actor-manager",
                "sender_email": "manager@example.com",
                "thread_group_id": "thread-a",
                "subject": "Project status update",
                "snippet": "We decided to proceed. Alex Example is informed on this update.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "deadline_pressure"},
                        ]
                    }
                },
            },
        ],
        full_map={
            "u1": {"to": ["HR Example <hr@example.com>"], "cc": [], "bcc": []},
            "u2": {"to": ["Ops Example <ops@example.com>"], "cc": [], "bcc": []},
            "u3": {"to": ["Alex Example <alex@example.com>"], "cc": ["HR Example <hr@example.com>"], "bcc": []},
        },
    )

    finding_types = [finding["graph_signal_type"] for finding in graph["graph_findings"]]

    assert graph["version"] == "1"
    assert graph["summary"]["target_actor_id"] == "actor-target"
    assert "repeated_exclusion" in finding_types
    assert "visibility_asymmetry" in finding_types
    assert "decision_visibility_asymmetry" in finding_types
    repeated = next(finding for finding in graph["graph_findings"] if finding["graph_signal_type"] == "repeated_exclusion")
    assert repeated["evidence_basis"] == "graph_plus_behavior"
    assert repeated["evidence_chain"]["message_uids"] == ["u1", "u2"]
    assert repeated["evidence_chain"]["subject_families"] == []
    decision = next(
        finding for finding in graph["graph_findings"] if finding["graph_signal_type"] == "decision_visibility_asymmetry"
    )
    assert decision["evidence_chain"]["included_uids"] == ["u3"]
    assert decision["evidence_chain"]["excluded_uids"] == ["u1", "u2"]


def test_build_communication_graph_reports_selective_escalation_and_forked_side_channel():
    graph = build_communication_graph(
        case_bundle={
            "scope": {
                "target_person": {
                    "name": "Alex Example",
                    "email": "alex@example.com",
                    "actor_id": "actor-target",
                }
            }
        },
        candidates=[
            {
                "uid": "u1",
                "sender_actor_id": "actor-manager",
                "sender_email": "manager@example.com",
                "thread_group_id": "thread-a",
                "snippet": "For the record, Alex Example failed to provide the figures.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                            {"behavior_id": "public_correction"},
                        ]
                    }
                },
            },
            {
                "uid": "u2",
                "sender_actor_id": "actor-manager",
                "sender_email": "manager@example.com",
                "thread_group_id": "thread-a",
                "snippet": "Alex Example will be informed later.",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                            {"behavior_id": "public_correction"},
                            {"behavior_id": "withholding"},
                        ]
                    }
                },
            },
        ],
        full_map={
            "u1": {
                "to": ["Alex Example <alex@example.com>", "HR Example <hr@example.com>"],
                "cc": ["Morgan Manager <manager@example.com>"],
                "bcc": [],
            },
            "u2": {
                "to": ["HR Example <hr@example.com>", "Legal Example <legal@example.com>"],
                "cc": ["Director Example <director@example.com>"],
                "bcc": [],
            },
        },
    )

    finding_types = [finding["graph_signal_type"] for finding in graph["graph_findings"]]

    assert "selective_escalation" in finding_types
    assert "forked_side_channel" in finding_types
    assert "thread_fork_exclusion" in finding_types
    assert "escalation_visibility_asymmetry" in finding_types
