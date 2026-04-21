"""Persistence tests for inferred thread candidates."""

from src.email_db import EmailDatabase
from src.parse_olm import Email


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


def test_insert_email_persists_inferred_parent_and_edge():
    db = EmailDatabase(":memory:")
    parent = _make_email(
        message_id="<parent@example.com>",
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
        reply_context_from="alice@example.com",
        reply_context_to=["bob@example.com"],
        reply_context_subject="Budget Review",
    )

    db.insert_email(parent)
    db.insert_email(child)

    row = db.conn.execute(
        (
            "SELECT inferred_parent_uid, inferred_thread_id, inferred_match_reason, "
            "inferred_match_confidence FROM emails WHERE uid = ?"
        ),
        (child.uid,),
    ).fetchone()
    assert row["inferred_parent_uid"] == parent.uid
    assert row["inferred_thread_id"] == "conv-1"
    assert row["inferred_match_confidence"] >= 0.8
    assert "reply_context_from" in row["inferred_match_reason"]

    edge = db.conn.execute(
        "SELECT child_uid, parent_uid, edge_type, confidence FROM conversation_edges WHERE child_uid = ?",
        (child.uid,),
    ).fetchone()
    assert edge is not None
    assert edge["parent_uid"] == parent.uid
    assert edge["edge_type"] == "inferred"
    assert edge["confidence"] >= 0.8
    db.close()
