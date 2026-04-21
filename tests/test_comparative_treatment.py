from __future__ import annotations

from src.comparative_treatment import build_comparative_treatment, shared_comparator_points


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
                "subject": "Re: Figures",
                "date": "2026-02-10T10:00:00",
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
                "subject": "Figures",
                "date": "2026-02-10T11:00:00",
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
                "cc": ["HR Example <hr@example.com>"],
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

    assert analysis["version"] == "2"
    assert analysis["target_actor_id"] == "actor-target"
    assert analysis["summary"]["available_comparator_count"] == 1
    assert analysis["summary"]["high_quality_comparator_count"] == 0
    assert comparator["status"] == "comparator_available"
    assert comparator["comparison_quality"] == "partial"
    assert comparator["comparison_quality_label"] == "partial_comparator"
    assert comparator["similarity_checks"]["shared_process_step"] is True
    assert comparator["similarity_checks"]["shared_workflow_stage"] is False
    assert comparator["similarity_checks"]["same_sender_decision_path"] is True
    assert comparator["similarity_checks"]["shared_subject"] is True
    assert comparator["similarity_checks"]["shared_day"] is True
    assert comparator["similarity_checks"]["shared_day_window"] is True
    assert comparator["similarity_checks"]["shared_visibility_band"] is False
    assert "tone_to_target_harsher_than_to_comparator" in comparator["unequal_treatment_signals"]
    assert "same_sender_escalates_more_against_target" in comparator["unequal_treatment_signals"]
    assert "same_sender_uses_more_public_visibility_against_target" in comparator["unequal_treatment_signals"]
    assert "same_sender_uses_broader_visibility_against_target" in comparator["unequal_treatment_signals"]
    assert "Target and comparator messages do not share a clear process step or thread." not in comparator["uncertainty_reasons"]
    assert comparator["evidence_chain"]["target_uids"] == ["u1"]
    assert comparator["evidence_chain"]["comparator_uids"] == ["u2"]
    matrix = comparator["comparator_matrix"]
    assert matrix["row_count"] >= 1
    assert matrix["rows"][0]["matrix_row_id"].startswith("comparator:actor-comparator:")
    assert matrix["rows"][0]["claimant_treatment"]
    assert matrix["rows"][0]["comparator_treatment"]
    assert matrix["rows"][0]["comparison_strength"] in {"moderate", "weak"}
    assert matrix["rows"][0]["likely_significance"]
    assert analysis["summary"]["matrix_row_count"] == matrix["row_count"]
    assert analysis["summary"]["strong_matrix_row_count"] >= 0
    assert analysis["summary"]["moderate_matrix_row_count"] >= 0
    assert analysis["summary"]["discovery_candidate_count"] == 0
    assert analysis["comparator_points"][0]["comparator_point_id"].startswith("comparator:actor-comparator:")
    assert analysis["comparator_points"][0]["point_summary"]
    assert shared_comparator_points(analysis)[0]["comparison_strength"] in {"moderate", "weak"}


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
                "subject": "Figures",
                "date": "2026-02-10T10:00:00",
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
    assert comparator["comparison_quality"] == "weak"
    assert comparator["comparison_quality_label"] == "no_suitable_comparator"
    assert comparator["similarity_checks"]["similarity_score"] == 0
    assert comparator["similarity_checks"]["shared_workflow_stage"] is False
    assert comparator["comparator_matrix"]["row_count"] >= 1
    assert comparator["comparator_matrix"]["rows"][0]["comparison_strength"] == "not_comparable"
    assert comparator["discovery_candidates"] == []
    assert analysis["summary"]["no_suitable_comparator_count"] == 1
    assert analysis["summary"]["weak_quality_comparator_count"] == 1
    assert analysis["summary"]["low_quality_comparator_count"] == 1
    assert analysis["summary"]["not_comparable_matrix_row_count"] >= 1


def test_build_comparative_treatment_returns_insufficiency_when_comparators_are_missing() -> None:
    analysis = build_comparative_treatment(
        case_bundle={
            "scope": {
                "target_person": {
                    "email": "alex@example.com",
                    "actor_id": "actor-target",
                },
                "comparator_actors": [],
            }
        },
        candidates=[],
        full_map={},
    )

    assert analysis is not None
    assert analysis["summary"]["status"] == "insufficient_comparator_scope"
    assert analysis["summary"]["missing_inputs"] == ["comparator_actors"]
    assert analysis["comparator_points"] == []
    assert analysis["insufficiency"]["reason_codes"] == ["missing_comparator_actors"]


def test_build_comparative_treatment_reports_high_quality_comparator_with_procedural_pressure_delta():
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
                "subject": "Status update",
                "date": "2026-02-10T10:00:00",
                "language_rhetoric": {"authored_text": {"signal_count": 2}},
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "deadline_pressure"},
                            {"behavior_id": "selective_accountability"},
                        ]
                    }
                },
            },
            {
                "uid": "u2",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-a",
                "subject": "Re: Status update",
                "date": "2026-02-11T09:00:00",
                "language_rhetoric": {"authored_text": {"signal_count": 0}},
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

    assert comparator["status"] == "comparator_available"
    assert comparator["comparison_quality"] == "high"
    assert comparator["comparison_quality_label"] == "high_quality_comparator"
    assert comparator["similarity_checks"]["shared_day_window"] is True
    assert comparator["similarity_checks"]["shared_workflow_stage"] is True
    assert comparator["similarity_checks"]["shared_visibility_band"] is True
    assert comparator["similarity_checks"]["shared_context_count"] >= 1
    assert "same_sender_demands_more_from_target" in comparator["unequal_treatment_signals"]
    assert "same_sender_uses_more_procedural_pressure_against_target" in comparator["unequal_treatment_signals"]
    assert analysis["summary"]["high_quality_comparator_count"] == 1
    row_ids = [row["issue_id"] for row in comparator["comparator_matrix"]["rows"]]
    assert "control_intensity" in row_ids
    control_row = next(row for row in comparator["comparator_matrix"]["rows"] if row["issue_id"] == "control_intensity")
    assert control_row["comparison_strength"] == "strong"
    assert control_row["likely_significance"]
    assert "same sender demands more from target" in control_row["claimant_treatment"].lower()
    strong_point = next(point for point in analysis["comparator_points"] if point["issue_id"] == "control_intensity")
    assert strong_point["comparison_strength"] == "strong"
    assert strong_point["supports_unequal_treatment_review"] is True


def test_build_comparative_treatment_emits_review_facing_discovery_candidates() -> None:
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
                "subject": "Status update",
                "date": "2026-02-10T10:00:00",
                "language_rhetoric": {"authored_text": {"signal_count": 1}},
                "message_findings": {"authored_text": {"behavior_candidates": [{"behavior_id": "deadline_pressure"}]}},
            },
            {
                "uid": "u2",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-a",
                "subject": "Re: Status update",
                "date": "2026-02-10T11:00:00",
                "language_rhetoric": {"authored_text": {"signal_count": 0}},
                "message_findings": {"authored_text": {"behavior_candidates": [{"behavior_id": "deadline_pressure"}]}},
            },
            {
                "uid": "u3",
                "sender_actor_id": "actor-manager",
                "thread_group_id": "thread-a",
                "subject": "Re: Status update",
                "date": "2026-02-10T11:30:00",
                "language_rhetoric": {"authored_text": {"signal_count": 0}},
                "message_findings": {"authored_text": {"behavior_candidates": [{"behavior_id": "deadline_pressure"}]}},
            },
        ],
        full_map={
            "u1": {"to": ["Alex Example <alex@example.com>"], "cc": [], "bcc": []},
            "u2": {"to": ["Pat Peer <pat@example.com>"], "cc": [], "bcc": []},
            "u3": {"to": ["Casey Colleague <casey@example.com>"], "cc": [], "bcc": []},
        },
    )

    assert analysis is not None
    assert analysis["summary"]["discovery_candidate_count"] == 1
    discovery = analysis["comparator_discovery_candidates"][0]
    assert discovery["candidate_email"] == "casey@example.com"
    assert discovery["confidence"] == "medium"
    assert discovery["promotion_rule"] == "review_facing_only_explicit_comparator_override_required"


def test_build_comparative_treatment_merges_source_backed_comparator_points() -> None:
    analysis = build_comparative_treatment(
        case_bundle={
            "scope": {
                "target_person": {
                    "name": "Alex Example",
                    "email": "alex@example.com",
                    "actor_id": "actor-target",
                },
                "comparator_actors": [
                    {
                        "name": "Pat Peer",
                        "email": "pat@example.com",
                        "actor_id": "actor-comparator",
                    }
                ],
            }
        },
        candidates=[],
        full_map={},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "note:target-home-office",
                    "source_type": "note_record",
                    "date": "2026-02-12",
                    "title": "Home office restriction",
                    "snippet": "Alex Example was denied home office after the complaint.",
                    "source_reliability": {"level": "high"},
                },
                {
                    "source_id": "note:comparator-home-office",
                    "source_type": "note_record",
                    "date": "2026-02-14",
                    "title": "Home office approval",
                    "snippet": "Pat Peer received home office approval for the same week.",
                    "source_reliability": {"level": "high"},
                },
            ]
        },
    )

    assert analysis is not None
    assert analysis["summary"]["source_backed_point_count"] == 1
    point = analysis["source_backed_comparator_points"][0]
    assert point["issue_id"] == "mobile_work_approvals_or_restrictions"
    assert point["comparison_strength"] == "moderate"
    assert point["supports_unequal_treatment_review"] is True
    assert point["supporting_source_ids"] == [
        "note:comparator-home-office",
        "note:target-home-office",
    ]
    assert any(row["issue_id"] == "mobile_work_approvals_or_restrictions" for row in shared_comparator_points(analysis))
