"""Compact email and SQLite archive builders for focused database tests."""

from mailarium.email_db import EmailDatabase
from mailarium.parse_olm import Email


def _make_email(**overrides) -> Email:
    """Build deterministic email data without external services."""
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Hello",
        "sender_name": "Alice",
        "sender_email": "employee@example.test",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-15T10:30:00",
        "body_text": "Test body",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def make_network_db(*, include_reply: bool = True) -> EmailDatabase:
    """Build the deterministic contact graph used by network-query tests."""
    db = EmailDatabase(":memory:")
    db.insert_email(_make_email(message_id="<m1@example.test>", to=["Bob <bob@example.com>"]))
    db.insert_email(_make_email(message_id="<m2@example.test>", to=["Bob <bob@example.com>"]))
    db.insert_email(_make_email(message_id="<m3@example.test>", to=["Carol <carol@example.com>"]))
    if include_reply:
        db.insert_email(
            _make_email(
                message_id="<m4@example.test>",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <employee@example.test>"],
            )
        )
    return db


def insert_response_pair(db: EmailDatabase) -> None:
    """Seed the canonical original/reply pair used by temporal query tests."""
    db.insert_email(_make_email(message_id="<orig@example.test>", date="2024-01-01T10:00:00"))
    db.insert_email(
        _make_email(
            message_id="<reply@example.test>",
            subject="RE: Hello",
            sender_email="bob@example.com",
            sender_name="Bob",
            to=["Alice <employee@example.test>"],
            in_reply_to="<orig@example.test>",
            date="2024-01-01T11:00:00",
        )
    )


def make_inferred_parent_email(**overrides) -> Email:
    """Build a thread parent with the identity metadata used for inference."""
    defaults = {
        "message_id": "<parent@example.com>",
        "subject": "Budget Review",
        "sender_name": "Alice",
        "sender_email": "employee@example.test",
        "to": ["Bob <bob@example.com>"],
        "to_identities": ["bob@example.com"],
        "date": "2024-01-15T10:00:00",
    }
    defaults.update(overrides)
    return _make_email(**defaults)


def make_inferred_reply_email(**overrides) -> Email:
    """Build a reply-context record that is eligible for inferred threading."""
    defaults = {
        "message_id": "<child@example.com>",
        "subject": "RE: Budget Review",
        "sender_name": "Bob",
        "sender_email": "bob@example.com",
        "to": ["Alice <employee@example.test>"],
        "to_identities": ["employee@example.test"],
        "date": "2024-01-15T10:30:00",
        "reply_context_from": "employee@example.test",
        "reply_context_to": ["bob@example.com"],
        "reply_context_subject": "Budget Review",
    }
    defaults.update(overrides)
    return _make_email(**defaults)
