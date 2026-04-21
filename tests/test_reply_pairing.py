from __future__ import annotations

from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput
from src.reply_pairing import build_reply_pairing_index


def test_build_reply_pairing_index_detects_indirect_activity_without_direct_reply() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
    )

    candidates = [
        {
            "uid": "u1",
            "date": "2026-02-01T09:00:00",
            "sender_email": "alex@example.com",
            "subject": "Need confirmation",
            "conversation_id": "conv-1",
            "snippet": "Please confirm whether the figures are approved.",
        },
        {
            "uid": "u2",
            "date": "2026-02-01T12:00:00",
            "sender_email": "manager@example.com",
            "subject": "Re: Need confirmation",
            "conversation_id": "conv-1",
            "snippet": "Please update HR separately.",
        },
    ]
    full_map = {
        "u1": {
            "to": ["Morgan Manager <manager@example.com>"],
            "cc": [],
            "bcc": [],
            "conversation_id": "conv-1",
            "body_text": "Please confirm whether the figures are approved.",
        },
        "u2": {
            "to": ["HR Example <hr@example.com>"],
            "cc": [],
            "bcc": [],
            "conversation_id": "conv-1",
            "body_text": "Please update HR separately.",
        },
    }

    index = build_reply_pairing_index(candidates=candidates, full_map=full_map, case_scope=case_scope)

    assert index["u1"]["request_expected"] is True
    assert index["u1"]["target_authored_request"] is True
    assert index["u1"]["response_status"] == "indirect_activity_without_direct_reply"
    assert index["u1"]["supports_selective_non_response_inference"] is True
    assert index["u1"]["later_activity_uids"] == ["u2"]


def test_build_reply_pairing_index_detects_direct_reply_and_delay() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
    )

    candidates = [
        {
            "uid": "u1",
            "date": "2026-02-01T09:00:00",
            "sender_email": "alex@example.com",
            "subject": "Need confirmation",
            "conversation_id": "conv-1",
            "snippet": "Please confirm whether the figures are approved.",
        },
        {
            "uid": "u2",
            "date": "2026-02-04T10:00:00",
            "sender_email": "manager@example.com",
            "subject": "Re: Need confirmation",
            "conversation_id": "conv-1",
            "snippet": "Confirmed.",
        },
    ]
    full_map = {
        "u1": {
            "to": ["Morgan Manager <manager@example.com>"],
            "cc": [],
            "bcc": [],
            "conversation_id": "conv-1",
            "body_text": "Please confirm whether the figures are approved.",
        },
        "u2": {
            "to": ["Alex Example <alex@example.com>"],
            "cc": [],
            "bcc": [],
            "conversation_id": "conv-1",
            "body_text": "Confirmed.",
        },
    }

    index = build_reply_pairing_index(candidates=candidates, full_map=full_map, case_scope=case_scope)

    assert index["u1"]["response_status"] == "delayed_reply"
    assert index["u1"]["direct_reply_uid"] == "u2"
    assert index["u1"]["response_delay_hours"] == 73.0


def test_build_reply_pairing_index_marks_format_limited_request_detection() -> None:
    case_scope = BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
    )

    candidates = [
        {
            "uid": "u1",
            "date": "2026-02-01T09:00:00",
            "sender_email": "alex@example.com",
            "subject": "Follow-up",
            "conversation_id": "conv-1",
            "snippet": "----- Original Message -----\nFrom: Morgan Manager <manager@example.com>",
        }
    ]
    full_map = {
        "u1": {
            "to": ["Morgan Manager <manager@example.com>"],
            "cc": [],
            "bcc": [],
            "conversation_id": "conv-1",
            "body_text": "----- Original Message -----\nFrom: Morgan Manager <manager@example.com>",
        }
    }

    index = build_reply_pairing_index(candidates=candidates, full_map=full_map, case_scope=case_scope)

    assert index["u1"]["request_expected"] is False
    assert index["u1"]["request_detection_status"] == "format_limited"
    assert index["u1"]["format_limited"] is True
    assert index["u1"]["request_detection_confidence"] < 0.5
