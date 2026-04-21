"""Tests for inferred thread-parent matching."""

from src.parse_olm import Email
from src.thread_inference import infer_parent_candidate


def _make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Budget Review",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-15T10:30:00",
        "body_text": "Test body",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
        "to_identities": ["bob@example.com"],
    }
    defaults.update(overrides)
    return Email(**defaults)


def test_infer_parent_candidate_recovers_high_confidence_parent():
    parent = _make_email(
        message_id="<parent@example.com>",
        subject="Budget Review",
        sender_name="Alice",
        sender_email="alice@example.com",
        to=["Bob <bob@example.com>"],
        to_identities=["bob@example.com"],
        date="2024-01-15T10:00:00",
        conversation_id="conv-1",
    )
    child = _make_email(
        message_id="<child@example.com>",
        subject="RE: Budget Review",
        sender_name="Bob",
        sender_email="bob@example.com",
        to=["Alice <alice@example.com>"],
        to_identities=["alice@example.com"],
        date="2024-01-15T10:30:00",
        in_reply_to="",
        references=[],
        reply_context_from="alice@example.com",
        reply_context_to=["bob@example.com"],
        reply_context_subject="Budget Review",
    )

    match = infer_parent_candidate(child, [parent])
    assert match is not None
    assert match.parent_uid == parent.uid
    assert match.thread_id == "conv-1"
    assert match.confidence >= 0.8
    assert "reply_context_from" in match.reason


def test_infer_parent_candidate_returns_none_for_ambiguous_matches():
    candidate_a = _make_email(
        message_id="<parent-a@example.com>",
        subject="Budget Review",
        sender_email="alice@example.com",
        to=["Bob <bob@example.com>"],
        to_identities=["bob@example.com"],
        date="2024-01-15T10:00:00",
    )
    candidate_b = _make_email(
        message_id="<parent-b@example.com>",
        subject="Budget Review",
        sender_email="alice@example.com",
        to=["Bob <bob@example.com>"],
        to_identities=["bob@example.com"],
        date="2024-01-15T10:05:00",
    )
    child = _make_email(
        message_id="<child@example.com>",
        subject="RE: Budget Review",
        sender_name="Bob",
        sender_email="bob@example.com",
        to=["Alice <alice@example.com>"],
        to_identities=["alice@example.com"],
        date="2024-01-15T10:30:00",
        reply_context_from="alice@example.com",
        reply_context_to=["bob@example.com"],
        reply_context_subject="Budget Review",
    )

    assert infer_parent_candidate(child, [candidate_a, candidate_b]) is None


def test_infer_parent_candidate_returns_none_for_low_confidence_case():
    parent = _make_email(
        message_id="<parent@example.com>",
        subject="Different topic",
        sender_email="carol@example.com",
        to=["Dan <dan@example.com>"],
        to_identities=["dan@example.com"],
        date="2024-01-15T10:00:00",
    )
    child = _make_email(
        message_id="<child@example.com>",
        subject="RE: Budget Review",
        sender_name="Bob",
        sender_email="bob@example.com",
        to=["Alice <alice@example.com>"],
        to_identities=["alice@example.com"],
        date="2024-01-15T10:30:00",
        reply_context_subject="Budget Review",
    )

    assert infer_parent_candidate(child, [parent]) is None


def test_infer_parent_candidate_never_mutates_canonical_thread_fields():
    parent = _make_email(
        message_id="<parent@example.com>",
        subject="Budget Review",
        sender_email="alice@example.com",
        to=["Bob <bob@example.com>"],
        to_identities=["bob@example.com"],
        date="2024-01-15T10:00:00",
    )
    child = _make_email(
        message_id="<child@example.com>",
        subject="RE: Budget Review",
        sender_name="Bob",
        sender_email="bob@example.com",
        to=["Alice <alice@example.com>"],
        to_identities=["alice@example.com"],
        date="2024-01-15T10:30:00",
        in_reply_to="",
        references=[],
        reply_context_from="alice@example.com",
    )

    infer_parent_candidate(child, [parent])
    assert child.in_reply_to == ""
    assert child.references == []
