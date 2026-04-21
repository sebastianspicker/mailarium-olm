"""Shared helpers for the RF10 email browse test split."""

from __future__ import annotations

from src.email_db import EmailDatabase
from src.parse_olm import Email


def make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Hello",
        "sender_name": "Alice",
        "sender_email": "employee@example.test",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-15T10:30:00",
        "body_text": "Test body content",
        "body_html": "<p>Test body content</p>",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def seed_db(db: EmailDatabase, n: int = 5) -> None:
    """Insert n emails with sequential dates and folders."""
    for i in range(n):
        db.insert_email(
            make_email(
                message_id=f"<m{i}@ex.com>",
                date=f"2024-01-{10 + i:02d}T10:00:00",
                folder="Inbox" if i % 2 == 0 else "Sent",
                sender_email=f"sender{i}@example.com",
                sender_name=f"Sender {i}",
                subject=f"Email {i}",
            )
        )
