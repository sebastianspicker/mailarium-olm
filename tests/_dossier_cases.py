"""Shared fixtures for the RF9 dossier test split."""

from __future__ import annotations

import os
import tempfile

import pytest

from src.dossier_generator import DossierGenerator
from src.email_db import EmailDatabase


@pytest.fixture()
def db():
    """Create a temporary EmailDatabase with evidence data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        database = EmailDatabase(db_path)

        for i in range(1, 4):
            database.conn.execute(
                """INSERT INTO emails (uid, sender_email, sender_name, date, subject,
                   body_text, body_html, has_attachments, attachment_count,
                   priority, is_read, body_length, content_sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 1, 50, ?)""",
                (
                    f"uid-{i}",
                    f"sender{i}@test.com",
                    f"Sender {i}",
                    f"2024-01-{10 + i:02d}",
                    f"Subject {i}",
                    f"Body text {i} with evidence content here.",
                    f"<p>Body text {i}</p>",
                    f"sha256-fake-{i}",
                ),
            )
            database.conn.execute(
                "INSERT INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)",
                (f"uid-{i}", "recipient@example.test", "Recipient", "to"),
            )

        database.conn.execute(
            "INSERT INTO communication_edges(sender_email, recipient_email, email_count) VALUES(?,?,?)",
            ("sender1@example.test", "sender2@example.test", 5),
        )

        database.conn.commit()

        database.add_evidence("uid-1", "harassment", "evidence content", "Summary 1", 5)
        database.add_evidence("uid-2", "discrimination", "evidence content", "Summary 2", 3)
        database.add_evidence("uid-3", "retaliation", "evidence content", "Summary 3", 4)

        yield database
        database.close()


@pytest.fixture()
def db_empty():
    """Database with no evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_empty.db")
        database = EmailDatabase(db_path)
        yield database
        database.close()


@pytest.fixture()
def gen(db):
    """DossierGenerator with populated database."""
    return DossierGenerator(db)


@pytest.fixture()
def gen_empty(db_empty):
    """DossierGenerator with empty database."""
    return DossierGenerator(db_empty)
