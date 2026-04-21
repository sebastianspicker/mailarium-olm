"""Shared helpers for the RF15 evidence-core test split."""

from __future__ import annotations

from src.email_db import EmailDatabase
from src.parse_olm import Email


def make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Meeting notes",
        "sender_name": "Alice Manager",
        "sender_email": "alice@example.test",
        "to": ["Bob <bob@example.test>"],
        "cc": [],
        "bcc": [],
        "date": "2024-03-15T10:30:00",
        "body_text": "You are not welcome here. We don't need people like you.",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def seed_evidence(db: EmailDatabase) -> list[dict]:
    """Insert 3 emails and 4 evidence items for testing."""
    email_one = make_email(message_id="<m1@x>", body_text="You are incompetent.", date="2024-01-10T10:00:00")
    email_two = make_email(message_id="<m2@x>", body_text="This is your fault.", date="2024-02-15T10:00:00")
    email_three = make_email(message_id="<m3@x>", body_text="You should leave.", date="2024-03-20T10:00:00")
    db.insert_email(email_one)
    db.insert_email(email_two)
    db.insert_email(email_three)

    items = [
        db.add_evidence(email_one.uid, "gaslighting", "You are incompetent", "Gaslighting.", 4),
        db.add_evidence(email_two.uid, "bossing", "This is your fault", "Blame-shifting.", 3),
        db.add_evidence(email_three.uid, "harassment", "You should leave", "Hostile push-out.", 5),
        db.add_evidence(email_one.uid, "discrimination", "You are incompetent", "Targeting disability.", 5),
    ]
    return items
