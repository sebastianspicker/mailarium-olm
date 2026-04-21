from __future__ import annotations

from src.comparative_treatment import build_comparative_treatment


def test_build_comparative_treatment_reports_target_vs_comparator_deltas():
    analysis = build_comparative_treatment(
        case_bundle={
            "scope": {
                "target_person": {
                    "email": "alex@example.com",
                    "actor_id": "actor-target",
                },
                "comparator_actors": [
                    {
                        "email": "pat@example.com",
                        "actor_id": "actor-comparator",
                    }
                ],
            }
        },
        candidates=[
            {
                "uid": "u1",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-a",
                "language_rhetoric": {"authored_text": {"signal_count": 3}},
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
                "thread_group_id": "thread-a",
                "language_rhetoric": {"authored_text": {"signal_count": 1}},
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
            "u1": {
                "to": ["Alex Example <alex@example.com>"],
                "cc": [],
                "bcc": [],
            },
            "u2": {
                "to": ["Pat Peer <pat@example.com>"],
                "cc": [],
                "bcc": [],
            },
        },
    )

    comparator = analysis["comparator_summaries"][0]

    assert analysis["version"] == "1"
    assert analysis["target_actor_id"] == "actor-target"
    assert analysis["summary"]["available_comparator_count"] == 1
    assert comparator["status"] == "comparator_available"
    assert comparator["similarity_checks"]["shared_process_step"] is True
    assert "tone_to_target_harsher_than_to_comparator" in comparator["unequal_treatment_signals"]
    assert "same_sender_escalates_more_against_target" in comparator["unequal_treatment_signals"]
    assert comparator["evidence_chain"]["target_uids"] == ["u1"]
    assert comparator["evidence_chain"]["comparator_uids"] == ["u2"]


def test_build_comparative_treatment_preserves_no_suitable_comparator_state():
    analysis = build_comparative_treatment(
        case_bundle={
            "scope": {
                "target_person": {
                    "email": "alex@example.com",
                    "actor_id": "actor-target",
                },
                "comparator_actors": [
                    {
                        "email": "pat@example.com",
                        "actor_id": "actor-comparator",
                    }
                ],
            }
        },
        candidates=[
            {
                "uid": "u1",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-a",
                "language_rhetoric": {"authored_text": {"signal_count": 2}},
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                        ]
                    }
                },
            },
        ],
        full_map={
            "u1": {
                "to": ["Alex Example <alex@example.com>"],
                "cc": [],
                "bcc": [],
            },
        },
    )

    comparator = analysis["comparator_summaries"][0]

    assert comparator["status"] == "no_suitable_comparator"
    assert comparator["similarity_checks"]["similarity_score"] == 0
    assert analysis["summary"]["no_suitable_comparator_count"] == 1
