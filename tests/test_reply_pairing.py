from __future__ import annotations

from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput
from src.reply_pairing import _extract_emails, build_reply_pairing_index


def test_extract_emails_preserves_all_addresses_in_one_recipient_string() -> None:
    assert _extract_emails(["Alice <alice@example.com>, Bob <bob@example.com>"]) == [
        "alice@example.com",
        "bob@example.com",
    ]


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


def test_build_reply_pairing_index_uses_second_recipient_as_relevant_actor() -> None:
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
            "to": ["Other Person <other@example.com>, Morgan Manager <manager@example.com>"],
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

    assert index["u1"]["relevant_actor_emails"] == ["manager@example.com"]
    assert index["u1"]["response_status"] == "indirect_activity_without_direct_reply"


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


def test_build_reply_pairing_index_handles_mixed_timezone_and_invalid_dates() -> None:
    index = build_reply_pairing_index(
        candidates=_mixed_timezone_candidates(),
        full_map=_mixed_timezone_full_map(),
        case_scope=_reply_pairing_case_scope(),
    )

    assert index["request"]["response_status"] == "direct_reply"
    assert index["request"]["direct_reply_uid"] == "reply"
    assert index["request"]["response_delay_hours"] == 1.5
    assert index["invalid"]["response_status"] == "no_reply_observed"


def _reply_pairing_case_scope() -> BehavioralCaseScopeInput:
    return BehavioralCaseScopeInput(
        target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
        suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
        allegation_focus=["retaliation"],
        analysis_goal="hr_review",
    )


def _mixed_timezone_candidates() -> list[dict[str, str]]:
    return [
        _reply_pairing_candidate(
            uid="invalid", date="not-a-date", sender_email="alex@example.com", conversation_id="conv-invalid"
        ),
        _reply_pairing_candidate(
            uid="request",
            date="2026-02-01T09:00:00+01:00",
            sender_email="alex@example.com",
            conversation_id="conv-1",
        ),
        _reply_pairing_candidate(
            uid="reply",
            date="2026-02-01T09:30:00",
            sender_email="manager@example.com",
            subject="Re: Need confirmation",
            conversation_id="conv-1",
            snippet="Confirmed.",
        ),
    ]


def _reply_pairing_candidate(
    *,
    uid: str,
    date: str,
    sender_email: str,
    conversation_id: str,
    subject: str = "Need confirmation",
    snippet: str = "Please confirm whether the figures are approved.",
) -> dict[str, str]:
    return {
        "uid": uid,
        "date": date,
        "sender_email": sender_email,
        "subject": subject,
        "conversation_id": conversation_id,
        "snippet": snippet,
    }


def _mixed_timezone_full_map() -> dict[str, dict[str, object]]:
    return {
        "invalid": _reply_pairing_full_email(to=["Morgan Manager <manager@example.com>"], conversation_id="conv-invalid"),
        "request": _reply_pairing_full_email(to=["Morgan Manager <manager@example.com>"], conversation_id="conv-1"),
        "reply": _reply_pairing_full_email(
            to=["Alex Example <alex@example.com>"],
            conversation_id="conv-1",
            body_text="Confirmed.",
        ),
    }


def _reply_pairing_full_email(*, to: list[str], conversation_id: str, body_text: str | None = None) -> dict[str, object]:
    return {
        "to": to,
        "cc": [],
        "bcc": [],
        "conversation_id": conversation_id,
        "body_text": body_text or "Please confirm whether the figures are approved.",
    }


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
