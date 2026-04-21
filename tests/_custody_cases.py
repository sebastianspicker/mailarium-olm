"""Shared custody test helpers for RF16."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from dataclasses import field as dataclass_field

import pytest

from src.email_db import EmailDatabase


@pytest.fixture()
def db() -> EmailDatabase:
    """Create a temporary EmailDatabase for custody testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        database = EmailDatabase(db_path)
        yield database
        database.close()


@pytest.fixture()
def db_with_email(db: EmailDatabase) -> EmailDatabase:
    """Database with a sample email inserted."""
    db.conn.execute(
        """INSERT INTO emails (uid, message_id, subject, sender_name, sender_email,
           date, folder, body_text, body_html, has_attachments, attachment_count,
           priority, is_read, body_length, content_sha256)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "test-uid-1",
            "<msg1@example.test>",
            "Test Subject",
            "Alice",
            "alice@example.test",
            "2024-01-15",
            "Inbox",
            "This is the email body with important evidence text.",
            "<p>This is the email body with important evidence text.</p>",
            0,
            0,
            0,
            1,
            50,
            hashlib.sha256(b"This is the email body with important evidence text.").hexdigest(),
        ),
    )
    db.conn.execute(
        "INSERT INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)",
        ("test-uid-1", "bob@example.test", "Bob", "to"),
    )
    db.conn.commit()
    return db


@dataclass
class FakeEmail:
    """Minimal fake parsed email payload for custody tests."""

    uid: str = "fake-uid"
    message_id: str = "<fake@example.test>"
    subject: str = "Fake Subject"
    sender_name: str = "Sender"
    sender_email: str = "sender@example.test"
    date: str = "2024-01-01"
    folder: str = "Inbox"
    email_type: str = "original"
    has_attachments: bool = False
    attachment_names: list[str] = dataclass_field(default_factory=list)
    priority: int = 0
    is_read: bool = True
    conversation_id: str = "conv-1"
    in_reply_to: str = ""
    base_subject: str = "Fake Subject"
    clean_body: str = "Hello world email content"
    body_html: str = "<p>Hello world email content</p>"
    to: list[object] = dataclass_field(default_factory=list)
    cc: list[object] = dataclass_field(default_factory=list)
    bcc: list[object] = dataclass_field(default_factory=list)
    attachments: list[object] = dataclass_field(default_factory=list)
