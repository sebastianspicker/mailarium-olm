"""Persistence tests for message conversation segments."""

from mailarium.conversation_segments import extract_segments
from mailarium.email_db import EmailDatabase

from .helpers.email_db_builders import _make_email


def test_insert_email_persists_message_segments():
    db = EmailDatabase(":memory:")
    body_text = "Latest answer.\n\nOn Mon, Jan 1, 2025 at 10:00 AM Alice wrote:\n> Older line 1"
    email = _make_email(body_text=body_text, segments=extract_segments(body_text, "", "", "reply"))

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
