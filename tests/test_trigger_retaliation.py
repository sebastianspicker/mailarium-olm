from __future__ import annotations

from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput, TriggerEventInput
from src.trigger_retaliation import build_retaliation_analysis


def test_build_retaliation_analysis_reports_before_after_deltas():
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        trigger_events=[
            TriggerEventInput(
                trigger_type="complaint",
                date="2026-02-03",
                actor=CasePartyInput(name="Alex Example", email="alex@example.com"),
            )
        ],
    )
    case_bundle = {
        "scope": {
            "target_person": {
                "actor_id": "actor-target",
            }
        }
    }

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle=case_bundle,
        candidates=[
            {
                "uid": "u1",
                "date": "2026-02-01T10:00:00",
                "sender_actor_id": "actor-manager",
                "reply_pairing": {
                    "request_expected": True,
                    "target_authored_request": True,
                    "response_status": "direct_reply",
                    "response_delay_hours": 4.0,
                    "supports_selective_non_response_inference": False,
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 2,
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                            {"behavior_id": "deadline_pressure"},
                        ],
                    }
                },
            },
            {
                "uid": "u2",
                "date": "2026-02-05T10:00:00",
                "sender_actor_id": "actor-manager",
                "reply_pairing": {
                    "request_expected": True,
                    "target_authored_request": True,
                    "response_status": "indirect_activity_without_direct_reply",
                    "response_delay_hours": None,
                    "supports_selective_non_response_inference": True,
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 2,
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                            {"behavior_id": "public_correction"},
                        ],
                    }
                },
            },
            {
                "uid": "u3",
                "date": "2026-02-06T10:00:00",
                "sender_actor_id": "actor-manager",
                "reply_pairing": {
                    "request_expected": True,
                    "target_authored_request": True,
                    "response_status": "no_reply_observed",
                    "response_delay_hours": None,
                    "supports_selective_non_response_inference": False,
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 1,
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                        ],
                    }
                },
            },
        ],
    )

    event = analysis["trigger_events"][0]

    assert analysis["version"] == "1"
    assert analysis["trigger_event_count"] == 1
    assert event["before_after"]["before_message_count"] == 1
    assert event["before_after"]["after_message_count"] == 2
    assert event["before_after"]["bucket_balance"]["window_status"] == "balanced"
    assert event["before_after"]["window_breakdown"]["immediate_after_count"] == 2
    assert event["before_after"]["window_breakdown"]["medium_term_count"] == 0
    assert event["before_after"]["metrics"]["response_time"]["status"] == "observed"
    assert event["before_after"]["metrics"]["response_time"]["before_average_hours"] == 4.0
    assert event["before_after"]["metrics"]["response_time"]["after_average_hours"] is None
    assert event["before_after"]["metrics"]["response_time"]["after_selective_non_response_count"] == 1
    assert event["before_after"]["metrics"]["escalation_rate"]["delta"] == 1
    assert event["before_after"]["metrics"]["escalation_rate"]["rate_delta"] == 0.0
    assert event["before_after"]["metrics"]["criticism_frequency"]["delta"] == 1
    assert event["before_after"]["metrics"]["selective_non_response"]["delta"] == 0
    assert event["assessment"]["status"] == "mixed_shift"
    assert event["assessment"]["analysis_quality"] == "medium"
    assert event["assessment"]["confounder_signals"] == ["post_trigger_burst_may_reflect_time_limited_operational_event"]
    assert event["evidence_chain"]["before_uids"] == ["u1"]
    assert event["evidence_chain"]["after_uids"] == ["u2", "u3"]
    timeline_assessment = analysis["retaliation_timeline_assessment"]
    assert timeline_assessment["protected_activity_timeline"][0]["trigger_type"] == "complaint"
    assert analysis["retaliation_point_count"] == 1
    assert analysis["retaliation_points"][0]["support_strength"] == "limited"
    assert timeline_assessment["adverse_action_timeline"][0]["uid"] == "u2"
    assert timeline_assessment["temporal_correlation_analysis"][0]["assessment_status"] == "mixed_shift"
    assert timeline_assessment["strongest_retaliation_indicators"]
    assert timeline_assessment["strongest_non_retaliatory_explanations"]
    assert timeline_assessment["overall_evidentiary_rating"]["rating"] == "limited_or_mixed_timing_support"


def test_build_retaliation_analysis_requires_before_and_after_context():
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        trigger_events=[TriggerEventInput(trigger_type="complaint", date="2026-02-03")],
    )

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle=None,
        candidates=[
            {
                "uid": "u2",
                "date": "2026-02-05T10:00:00",
                "sender_actor_id": "actor-manager",
                "reply_pairing": {
                    "request_expected": True,
                    "target_authored_request": True,
                    "response_status": "no_reply_observed",
                    "response_delay_hours": None,
                    "supports_selective_non_response_inference": False,
                },
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 1,
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                        ],
                    }
                },
            }
        ],
    )

    assert analysis["trigger_events"][0]["assessment"]["status"] == "insufficient_context"
    assert analysis["trigger_events"][0]["assessment"]["analysis_quality"] == "low"


def test_build_retaliation_analysis_surfaces_mixed_shift_and_confounders():
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        trigger_events=[TriggerEventInput(trigger_type="complaint", date="2026-02-03")],
    )

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle={"scope": {"target_person": {"actor_id": "actor-target"}}},
        candidates=[
            {
                "uid": "u1",
                "date": "2026-02-01T10:00:00",
                "subject": "Project status",
                "thread_group_id": "thread-before",
                "sender_actor_id": "actor-manager",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 2,
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                            {"behavior_id": "public_correction"},
                        ],
                    }
                },
            },
            {
                "uid": "u2",
                "date": "2026-02-10T10:00:00",
                "subject": "Different workflow",
                "thread_group_id": "thread-after",
                "sender_actor_id": "actor-hr",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 2,
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                            {"behavior_id": "deadline_pressure"},
                        ],
                    }
                },
            },
        ],
    )

    event = analysis["trigger_events"][0]

    assert event["before_after"]["window_breakdown"]["immediate_after_count"] == 1
    assert event["assessment"]["status"] == "mixed_shift"
    assert "new_sender_appears_after_trigger" in event["assessment"]["confounder_signals"]
    assert "workflow_or_thread_changed_after_trigger" in event["assessment"]["confounder_signals"]
    assert "topic_family_shift_after_trigger" in event["assessment"]["confounder_signals"]
    assert event["assessment"]["confounder_summary"]["confounder_count"] >= 3
    assert event["assessment"]["confounder_summary"]["confounder_weight"] in {"medium", "high"}
    timeline_assessment = analysis["retaliation_timeline_assessment"]
    explanations = [item["explanation"] for item in timeline_assessment["strongest_non_retaliatory_explanations"]]
    assert "new_sender_appears_after_trigger" in explanations


def test_build_retaliation_analysis_surfaces_restructuring_and_incident_confounders() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        trigger_events=[TriggerEventInput(trigger_type="complaint", date="2026-02-03")],
    )

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle={"scope": {"target_person": {"actor_id": "actor-target"}}},
        candidates=[
            {
                "uid": "u-before-1",
                "date": "2026-02-01T10:00:00",
                "subject": "Status update",
                "sender_actor_id": "actor-manager",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 1,
                        "behavior_candidates": [{"behavior_id": "escalation"}],
                    }
                },
            },
            {
                "uid": "u-before-2",
                "date": "2026-02-02T10:00:00",
                "subject": "Status update",
                "sender_actor_id": "actor-manager",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 1,
                        "behavior_candidates": [{"behavior_id": "deadline_pressure"}],
                    }
                },
            },
            {
                "uid": "u-after-1",
                "date": "2026-02-05T10:00:00",
                "subject": "Reorg incident review",
                "snippet": "Following the reorganization and outage incident, the new manager needs a formal process review.",
                "sender_actor_id": "actor-hr",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 2,
                        "behavior_candidates": [{"behavior_id": "escalation"}, {"behavior_id": "deadline_pressure"}],
                    }
                },
            },
            {
                "uid": "u-after-2",
                "date": "2026-02-06T10:00:00",
                "subject": "Reorg incident review follow-up",
                "snippet": "The department handover and outage ticket require legal and HR handling.",
                "sender_actor_id": "actor-hr",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 2,
                        "behavior_candidates": [{"behavior_id": "escalation"}, {"behavior_id": "public_correction"}],
                    }
                },
            },
        ],
    )

    event = analysis["trigger_events"][0]
    signals = set(event["assessment"]["confounder_signals"])
    assert "organizational_restructuring_context_after_trigger" in signals
    assert "performance_or_incident_context_after_trigger" in signals
    assert "formal_process_transition_after_trigger" in signals
    assert event["assessment"]["status"] == "mixed_shift"
    assert event["assessment"]["analysis_quality"] == "low"
    assert analysis["retaliation_points"][0]["counterargument"] in signals


def test_build_retaliation_analysis_emits_protected_activity_candidates_without_explicit_trigger() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
    )

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle={"scope": {"target_person": {"actor_id": "actor-target"}}},
        candidates=[
            {
                "uid": "u-complaint",
                "date": "2026-02-03T09:00:00",
                "subject": "Formal complaint to HR",
                "snippet": "I am escalating this complaint to HR and SBV for review.",
                "sender_actor_id": "actor-target",
            }
        ],
    )

    assert analysis is not None
    assert analysis["trigger_event_count"] == 0
    assert analysis["protected_activity_candidate_count"] == 1
    candidate = analysis["protected_activity_candidates"][0]
    assert candidate["candidate_type"] == "complaint"
    assert candidate["date_confidence"] == "exact"
    assert candidate["requires_confirmation"] is True
    assert candidate["source_linkage"]["supporting_uids"] == ["u-complaint"]
    assert analysis["anchor_requirement_status"] == "explicit_trigger_confirmation_required"
    assert analysis["retaliation_timeline_assessment"]["overall_evidentiary_rating"]["rating"] == "insufficient_timing_record"
    assert analysis["adverse_action_candidate_count"] == 0


def test_build_retaliation_analysis_uses_asserted_rights_timeline_as_explicit_trigger() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        asserted_rights_timeline=[TriggerEventInput(trigger_type="escalation_to_hr", date="2026-02-03")],
    )

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle={"scope": {"target_person": {"actor_id": "actor-target"}}},
        candidates=[
            {
                "uid": "u1",
                "date": "2026-02-01T10:00:00",
                "sender_actor_id": "actor-manager",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 1,
                        "behavior_candidates": [{"behavior_id": "escalation"}],
                    }
                },
            },
            {
                "uid": "u2",
                "date": "2026-02-05T10:00:00",
                "sender_actor_id": "actor-manager",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 2,
                        "behavior_candidates": [{"behavior_id": "escalation"}, {"behavior_id": "deadline_pressure"}],
                    }
                },
            },
        ],
    )

    assert analysis is not None
    assert analysis["trigger_event_count"] == 1
    assert analysis["trigger_events"][0]["trigger_type"] == "escalation_to_hr"
    assert analysis["anchor_requirement_status"] == "explicit_trigger_confirmed"


def test_build_retaliation_analysis_emits_adverse_action_candidates() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        trigger_events=[TriggerEventInput(trigger_type="complaint", date="2026-02-03")],
    )

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle={"scope": {"target_person": {"actor_id": "actor-target"}}},
        candidates=[
            {
                "uid": "u-action",
                "date": "2026-02-05T10:00:00",
                "subject": "Project removal after complaint",
                "snippet": "You are removed from project X and home office is suspended.",
                "sender_actor_id": "actor-manager",
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 1,
                        "behavior_candidates": [{"behavior_id": "deadline_pressure"}],
                    }
                },
            }
        ],
    )

    assert analysis is not None
    assert analysis["adverse_action_candidate_count"] >= 1
    adverse = analysis["adverse_action_candidates"][0]
    assert adverse["action_type"] in {"project_removal", "mobile_work_restriction"}
    assert adverse["requires_confirmation"] is True
    assert adverse["source_linkage"]["supporting_uids"] == ["u-action"]


def test_build_retaliation_analysis_merges_source_backed_candidates_and_points() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
        trigger_events=[TriggerEventInput(trigger_type="complaint", date="2026-02-03")],
    )

    analysis = build_retaliation_analysis(
        case_scope=case_scope,
        case_bundle={"scope": {"target_person": {"actor_id": "actor-target"}}},
        candidates=[],
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "note:complaint",
                    "source_type": "note_record",
                    "date": "2026-02-03",
                    "title": "Complaint to HR",
                    "snippet": "Formal complaint to HR and SBV about exclusion from the process.",
                },
                {
                    "source_id": "note:project-removal",
                    "source_type": "note_record",
                    "date": "2026-02-06",
                    "title": "Project removal after complaint",
                    "snippet": "Project removal and home office restriction after the complaint.",
                },
            ]
        },
    )

    assert analysis is not None
    assert analysis["protected_activity_candidate_count"] >= 1
    assert analysis["adverse_action_candidate_count"] >= 1
    assert analysis["source_backed_candidate_counts"] == {
        "protected_activity": 1,
        "adverse_actions": 2,
    }
    assert analysis["retaliation_point_count"] >= 1
    assert any(point["assessment_status"] == "source_backed_temporal_proximity" for point in analysis["retaliation_points"])
    assert any(
        row.get("source_id") == "note:project-removal"
        for row in analysis["retaliation_timeline_assessment"]["adverse_action_timeline"]
    )
