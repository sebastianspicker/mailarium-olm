from __future__ import annotations

from src.cross_message_patterns import build_case_patterns


def test_build_case_patterns_summarizes_recurrence_by_behavior_taxonomy_and_thread():
    patterns = build_case_patterns(
        candidates=[
            {
                "uid": "u1",
                "date": "2026-02-10T09:00:00",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-a",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "escalation",
                                "confidence": "medium",
                                "taxonomy_ids": ["escalation_pressure"],
                            }
                        ]
                    }
                },
            },
            {
                "uid": "u2",
                "date": "2026-02-11T09:00:00",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-a",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "deadline_pressure",
                                "confidence": "high",
                                "taxonomy_ids": ["escalation_pressure", "unequal_demands"],
                            }
                        ]
                    }
                },
            },
            {
                "uid": "u3",
                "date": "2026-02-14T09:00:00",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-b",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "escalation",
                                "confidence": "high",
                                "taxonomy_ids": ["escalation_pressure"],
                            }
                        ]
                    }
                },
            },
        ],
        target_actor_id="actor-target",
    )

    behavior_keys = [summary["key"] for summary in patterns["behavior_patterns"]]
    escalation_summary = next(summary for summary in patterns["behavior_patterns"] if summary["key"] == "escalation")
    taxonomy_summary = next(summary for summary in patterns["taxonomy_patterns"] if summary["key"] == "escalation_pressure")

    assert patterns["version"] == "1"
    assert behavior_keys == ["deadline_pressure", "escalation"]
    assert patterns["summary"]["message_count_with_findings"] == 3
    assert escalation_summary["primary_recurrence"] in {"repeated", "escalating"}
    assert "targeted" in escalation_summary["recurrence_flags"]
    assert taxonomy_summary["message_count"] == 3
    assert patterns["directional_summaries"][0]["sender_actor_id"] == "actor-manager"
    assert patterns["directional_summaries"][0]["target_actor_id"] == "actor-target"
    assert patterns["directional_summaries"][0]["behavior_counts"]["escalation"] == 2


def test_build_case_patterns_keeps_one_off_events_isolated():
    patterns = build_case_patterns(
        candidates=[
            {
                "uid": "u1",
                "date": "2026-03-01T10:00:00",
                "sender_actor_id": "actor-1",
                "thread_group_id": "thread-a",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "undermining",
                                "confidence": "medium",
                                "taxonomy_ids": ["undermining_credibility"],
                            }
                        ]
                    }
                },
            }
        ]
    )

    assert patterns["behavior_patterns"][0]["primary_recurrence"] == "isolated"
    assert patterns["behavior_patterns"][0]["recurrence_flags"] == []
