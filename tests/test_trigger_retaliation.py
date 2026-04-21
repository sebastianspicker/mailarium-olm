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
                "message_findings": {
                    "authored_text": {
                        "behavior_candidate_count": 1,
                        "behavior_candidates": [
                            {"behavior_id": "deadline_pressure"},
                        ],
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
    assert event["before_after"]["metrics"]["response_time"]["status"] == "not_available"
    assert event["before_after"]["metrics"]["escalation_rate"]["delta"] == 2
    assert event["before_after"]["metrics"]["criticism_frequency"]["delta"] == 1
    assert event["assessment"]["status"] == "possible_retaliatory_shift"
    assert event["evidence_chain"]["before_uids"] == ["u1"]
    assert event["evidence_chain"]["after_uids"] == ["u2", "u3"]


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
