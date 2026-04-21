"""Tests for extracted quoted reply-context blocks."""

from __future__ import annotations

from src.reply_context import extract_reply_context


def test_extract_reply_context_from_plain_text_block():
    context = extract_reply_context(
        body_text=(
            "Current answer.\n\n"
            "From: Alice <employee@example.test>\n"
            "Sent: Monday, January 1, 2025 10:00 AM\n"
            "To: Bob <bob@example.com>\n"
            "Subject: Original topic\n\n"
            "Prior body."
        ),
        body_html="",
        email_type="reply",
    )

    assert context is not None
    assert context.from_email == "employee@example.test"
    assert context.to_emails == ["bob@example.com"]
    assert context.subject == "Original topic"
    assert context.source == "body_text"


def test_extract_reply_context_from_german_outlook_block():
    context = extract_reply_context(
        body_text=(
            "Aktuelle Antwort.\n\n"
            "Von: Alice <employee@example.test>\n"
            "Gesendet: Montag, 1. Januar 2025 10:00\n"
            "An: Bob <bob@example.com>\n"
            "Betreff: Urspruengliches Thema\n\n"
            "Vorheriger Text."
        ),
        body_html="",
        email_type="reply",
    )

    assert context is not None
    assert context.from_email == "employee@example.test"
    assert context.to_emails == ["bob@example.com"]
    assert context.subject == "Urspruengliches Thema"


def test_extract_reply_context_supports_wrapped_subject_lines():
    context = extract_reply_context(
        body_text=(
            "Current answer.\n\n"
            "From: Alice <employee@example.test>\n"
            "Sent: Monday, January 1, 2025 10:00 AM\n"
            "To: Bob <bob@example.com>\n"
            "Subject: Original topic with a very long\n"
            " continuation line\n\n"
            "Prior body."
        ),
        body_html="",
        email_type="reply",
    )

    assert context is not None
    assert context.subject == "Original topic with a very long continuation line"


def test_extract_reply_context_returns_none_for_original_messages():
    context = extract_reply_context(
        body_text="Normal original email without quoted headers.",
        body_html="",
        email_type="original",
    )
    assert context is None


def test_extract_reply_context_from_on_wrote_wrapper_followed_by_headers():
    context = extract_reply_context(
        body_text=(
            "Current answer.\n\n"
            "On Tue, 1 Jan 2025 at 10:00 Alice wrote:\n"
            "From: Alice <employee@example.test>\n"
            "To: Bob <bob@example.com>\n"
            "Subject: Original topic\n\n"
            "Prior body."
        ),
        body_html="",
        email_type="reply",
    )

    assert context is not None
    assert context.from_email == "employee@example.test"
    assert context.to_emails == ["bob@example.com"]
    assert context.subject == "Original topic"
    assert context.confidence < 0.8


def test_extract_reply_context_from_original_message_separator():
    context = extract_reply_context(
        body_text=(
            "Current answer.\n\n"
            "----- Original Message -----\n"
            "From: Alice <employee@example.test>\n"
            "To: Bob <bob@example.com>\n"
            "Subject: Original topic\n\n"
            "Prior body."
        ),
        body_html="",
        email_type="reply",
    )

    assert context is not None
    assert context.from_email == "employee@example.test"
