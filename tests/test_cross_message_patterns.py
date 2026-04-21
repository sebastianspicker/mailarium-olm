from __future__ import annotations

from src.cross_message_patterns import build_case_patterns


def test_build_case_patterns_summarizes_recurrence_by_behavior_taxonomy_and_thread():
    patterns = build_case_patterns(
        candidates=[
            {
                "uid": "u1",
                "date": "2026-02-10T09:00:00",
                "sender_actor_id": "actor-manager",
                "target_actor_id": "actor-target",
                "thread_group_id": "thread-a",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "escalation",
                                "confidence": "medium",
                                "taxonomy_ids": ["escalation_pressure"],
                            }
                        ],
                        "relevant_wording": [{"text": "for the record"}],
                        "communication_classification": {
                            "primary_class": "controlling",
                            "applied_classes": ["controlling", "tense"],
                        },
                        "excluded_actors": ["alex@example.com"],
                    }
                },
            },
            {
                "uid": "u2",
                "date": "2026-02-11T09:00:00",
                "sender_actor_id": "actor-manager",
                "target_actor_id": "actor-target",
                "thread_group_id": "thread-a",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "deadline_pressure",
                                "confidence": "high",
                                "taxonomy_ids": ["escalation_pressure", "unequal_demands"],
                            }
                        ],
                        "relevant_wording": [{"text": "for the record"}],
                        "communication_classification": {
                            "primary_class": "controlling",
                            "applied_classes": ["controlling", "tense"],
                        },
                        "excluded_actors": ["alex@example.com"],
                    }
                },
            },
            {
                "uid": "u3",
                "date": "2026-02-14T09:00:00",
                "sender_actor_id": "actor-manager",
                "target_actor_id": "actor-target",
                "thread_group_id": "thread-b",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "escalation",
                                "confidence": "high",
                                "taxonomy_ids": ["escalation_pressure"],
                            }
                        ],
                        "relevant_wording": [{"text": "for the record"}],
                        "communication_classification": {
                            "primary_class": "controlling",
                            "applied_classes": ["controlling", "tense"],
                        },
                        "excluded_actors": ["alex@example.com"],
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
    corpus_review = patterns["corpus_behavioral_review"]
    assert corpus_review["message_count_reviewed"] == 3
    assert corpus_review["coverage_scope"] == "retrieved_candidate_slice"
    assert corpus_review["communication_class_counts"]["controlling"] >= 2
    assert corpus_review["recurring_phrases"][0]["phrase"] == "for the record"
    assert corpus_review["escalation_points"][0]["uid"] == "u1"


def test_build_case_patterns_requires_real_target_linkage_for_targeted_recurrence() -> None:
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
                            {"behavior_id": "escalation", "confidence": "medium", "taxonomy_ids": ["escalation_pressure"]}
                        ],
                        "excluded_actors": ["alex@example.com"],
                    }
                },
            },
            {
                "uid": "u2",
                "date": "2026-02-11T09:00:00",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-b",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "escalation", "confidence": "high", "taxonomy_ids": ["escalation_pressure"]}
                        ],
                        "excluded_actors": ["alex@example.com"],
                    }
                },
            },
        ],
        target_actor_id="actor-target",
    )

    escalation_summary = patterns["behavior_patterns"][0]

    assert escalation_summary["primary_recurrence"] == "repeated"
    assert "targeted" not in escalation_summary["recurrence_flags"]
    assert patterns["directional_summaries"] == []


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


def test_build_case_patterns_adds_corpus_level_response_and_coordination_reviews():
    patterns = build_case_patterns(
        candidates=[
            {
                "uid": "u1",
                "date": "2026-03-01T09:00:00",
                "sender_actor_id": "actor-target",
                "thread_group_id": "thread-a",
                "recipients_summary": {
                    "status": "available",
                    "cc_count": 0,
                    "visible_recipient_count": 1,
                    "visible_recipient_emails": ["manager@example.com"],
                    "signature": "manager@example.com",
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [],
                        "communication_classification": {"primary_class": "neutral", "applied_classes": ["neutral"]},
                    }
                },
                "reply_pairing": {
                    "target_authored_request": True,
                    "response_status": "direct_reply",
                    "response_delay_hours": 4,
                },
            },
            {
                "uid": "u2",
                "date": "2026-03-03T09:00:00",
                "sender_actor_id": "actor-target",
                "thread_group_id": "thread-b",
                "recipients_summary": {
                    "status": "available",
                    "cc_count": 0,
                    "visible_recipient_count": 1,
                    "visible_recipient_emails": ["manager@example.com"],
                    "signature": "manager@example.com",
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [],
                        "communication_classification": {"primary_class": "neutral", "applied_classes": ["neutral"]},
                    }
                },
                "reply_pairing": {
                    "target_authored_request": True,
                    "response_status": "indirect_activity_without_direct_reply",
                    "response_delay_hours": 49,
                    "supports_selective_non_response_inference": True,
                },
            },
            {
                "uid": "u3",
                "date": "2026-03-03T11:00:00",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-c",
                "recipients_summary": {
                    "status": "available",
                    "cc_count": 0,
                    "visible_recipient_count": 1,
                    "visible_recipient_emails": ["alex@example.com"],
                    "signature": "alex@example.com",
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "deadline_pressure", "confidence": "medium", "taxonomy_ids": ["unequal_demands"]},
                        ],
                        "communication_classification": {
                            "primary_class": "controlling",
                            "applied_classes": ["controlling"],
                        },
                    }
                },
            },
            {
                "uid": "u4",
                "date": "2026-03-03T18:00:00",
                "sender_actor_id": "actor-director",
                "thread_group_id": "thread-d",
                "recipients_summary": {
                    "status": "available",
                    "cc_count": 1,
                    "visible_recipient_count": 2,
                    "visible_recipient_emails": ["hr@example.com", "alex@example.com"],
                    "signature": "hr@example.com|alex@example.com",
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "escalation", "confidence": "medium", "taxonomy_ids": ["escalation_pressure"]},
                        ],
                        "communication_classification": {
                            "primary_class": "controlling",
                            "applied_classes": ["controlling", "tense"],
                        },
                    }
                },
            },
            {
                "uid": "u5",
                "date": "2026-03-04T09:00:00",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-e",
                "recipients_summary": {
                    "status": "available",
                    "cc_count": 1,
                    "visible_recipient_count": 2,
                    "visible_recipient_emails": ["alex@example.com", "hr@example.com"],
                    "signature": "alex@example.com|hr@example.com",
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {
                                "behavior_id": "selective_accountability",
                                "confidence": "medium",
                                "taxonomy_ids": ["unequal_demands"],
                            }
                        ],
                        "omissions_or_process_signals": [
                            {"signal": "target_absent_from_visible_recipients", "summary": "placeholder"}
                        ],
                        "communication_classification": {
                            "primary_class": "controlling",
                            "applied_classes": ["controlling"],
                        },
                    }
                },
            },
            {
                "uid": "u6",
                "date": "2026-03-05T09:00:00",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-f",
                "recipients_summary": {
                    "status": "available",
                    "cc_count": 0,
                    "visible_recipient_count": 1,
                    "visible_recipient_emails": ["colleague@example.com"],
                    "signature": "colleague@example.com",
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [],
                        "communication_classification": {
                            "primary_class": "neutral",
                            "applied_classes": ["neutral"],
                        },
                    }
                },
            },
        ],
        target_actor_id="actor-target",
    )

    corpus_review = patterns["corpus_behavioral_review"]

    assert corpus_review["response_timing_shifts"][0]["shift_label"] == "worsened_response"
    assert corpus_review["response_timing_shifts"][0]["comparability_basis"] == "same_visible_recipient_signature"
    assert corpus_review["cc_behavior_changes"][0]["change_types"] == ["visible_recipient_signature_changed", "cc_count_increase"]
    assert corpus_review["coordination_windows"][0]["actor_ids"] == ["actor-director", "actor-manager"]
    assert corpus_review["coordination_windows"][0]["shared_context_types"] == ["shared_visible_recipient_signature"]
    assert corpus_review["double_standards"][0]["sender_actor_id"] == "actor-manager"


def test_build_case_patterns_uses_event_records_for_sequence_signals() -> None:
    patterns = build_case_patterns(
        candidates=[
            {
                "uid": "u-event-1",
                "date": "2026-03-10T09:00:00",
                "sender_actor_id": "actor-manager",
                "target_actor_id": "actor-target",
                "thread_group_id": "thread-e1",
                "detected_language_confidence": "high",
                "message_findings": {"authored_text": {"behavior_candidates": []}},
                "event_records": [{"event_kind": "deadline_pressure", "source_scope": "authored_body", "confidence": "high"}],
            },
            {
                "uid": "u-event-2",
                "date": "2026-03-11T09:00:00",
                "sender_actor_id": "actor-manager",
                "target_actor_id": "actor-target",
                "thread_group_id": "thread-e2",
                "detected_language_confidence": "medium",
                "message_findings": {"authored_text": {"behavior_candidates": []}},
                "event_records": [{"event_kind": "escalation", "source_scope": "authored_body", "confidence": "medium"}],
            },
        ],
        target_actor_id="actor-target",
    )

    behavior_keys = {summary["key"] for summary in patterns["behavior_patterns"]}
    assert "deadline_pressure" in behavior_keys
    assert "escalation" in behavior_keys
    escalation_points = patterns["corpus_behavioral_review"]["escalation_points"]
    assert escalation_points
    assert escalation_points[0]["event_trigger_count"] >= 1
