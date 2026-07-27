"""Verifies inferred threading links messages to plausible parents using header and subject signals."""

from mailarium.thread_inference import infer_parent_candidate

from .helpers.email_db_builders import make_inferred_parent_email, make_inferred_reply_email


def test_infer_parent_candidate_recovers_high_confidence_parent():
    parent = make_inferred_parent_email(conversation_id="conv-1")
    child = make_inferred_reply_email(
        in_reply_to="",
        references=[],
    )

    match = infer_parent_candidate(child, [parent])
    assert match is not None
    assert match.parent_uid == parent.uid
    assert match.thread_id == "conv-1"
    assert match.confidence >= 0.8
    assert "reply_context_from" in match.reason


def test_infer_parent_candidate_handles_aware_child_and_naive_parent_dates():
    parent = make_inferred_parent_email(conversation_id="conv-1")
    child = make_inferred_reply_email(
        date="2024-01-15T10:30:00+00:00",
        in_reply_to="",
        references=[],
    )

    match = infer_parent_candidate(child, [parent])

    assert match is not None
    assert match.parent_uid == parent.uid


def test_infer_parent_candidate_returns_none_for_ambiguous_matches():
    candidate_a = make_inferred_parent_email(
        message_id="<parent-a@example.com>",
        subject="Budget Review",
        sender_email="employee@example.test",
        to=["Bob <bob@example.com>"],
        to_identities=["bob@example.com"],
        date="2024-01-15T10:00:00",
    )
    candidate_b = make_inferred_parent_email(
        message_id="<parent-b@example.com>",
        subject="Budget Review",
        sender_email="employee@example.test",
        to=["Bob <bob@example.com>"],
        to_identities=["bob@example.com"],
        date="2024-01-15T10:05:00",
    )
    child = make_inferred_reply_email()

    assert infer_parent_candidate(child, [candidate_a, candidate_b]) is None


def test_infer_parent_candidate_returns_none_for_low_confidence_case():
    parent = make_inferred_parent_email(
        message_id="<parent@example.com>",
        subject="Different topic",
        sender_email="carol@example.com",
        to=["Dan <dan@example.com>"],
        to_identities=["dan@example.com"],
        date="2024-01-15T10:00:00",
    )
    child = make_inferred_reply_email(
        subject="RE: Budget Review",
        reply_context_from="",
        reply_context_to=[],
    )

    assert infer_parent_candidate(child, [parent]) is None


def test_infer_parent_candidate_never_mutates_canonical_thread_fields():
    parent = make_inferred_parent_email()
    child = make_inferred_reply_email(
        in_reply_to="",
        references=[],
    )

    infer_parent_candidate(child, [parent])
    assert child.in_reply_to == ""
    assert child.references == []
