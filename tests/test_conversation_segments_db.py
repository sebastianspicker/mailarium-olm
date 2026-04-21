"""Persistence tests for message conversation segments."""

from src.conversation_segments import extract_segments
from src.email_db import EmailDatabase
from src.parse_olm import Email


def _make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Hello",
        "sender_name": "Alice",
        "sender_email": "employee@example.test",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-15T10:30:00",
        "body_text": "Latest answer.\n\nOn Mon, Jan 1, 2025 at 10:00 AM Alice wrote:\n> Older line 1",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
        "segments": extract_segments(
            "Latest answer.\n\nOn Mon, Jan 1, 2025 at 10:00 AM Alice wrote:\n> Older line 1",
            "",
            "",
            "reply",
        ),
    }
    defaults.update(overrides)
    return Email(**defaults)


def test_insert_email_persists_message_segments():
    db = EmailDatabase(":memory:")
    email = _make_email()

    db.insert_email(email)

    rows = db.conn.execute(
        "SELECT ordinal, segment_type, depth, text, source_surface FROM message_segments WHERE email_uid = ? ORDER BY ordinal",
        (email.uid,),
    ).fetchall()
    assert [(row["ordinal"], row["segment_type"], row["depth"], row["text"], row["source_surface"]) for row in rows] == [
        (0, "authored_body", 0, "Latest answer.", "body_text"),
        (1, "header_block", 0, "On Mon, Jan 1, 2025 at 10:00 AM Alice wrote:", "body_text"),
        (2, "quoted_reply", 1, "Older line 1", "body_text"),
    ]
    db.close()
