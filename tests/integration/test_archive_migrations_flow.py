"""Archive schema migration and reopen behavior over a real SQLite file."""

from __future__ import annotations

from mailarium.archive import open_archive_database
from mailarium.archive.db_schema import init_schema
from mailarium.ingestion.records import ParsedMessage


def test_schema_upgrade_preserves_email_then_reopens_at_current_version(tmp_path) -> None:
    """A supported pre-current schema marker upgrades without discarding archive state."""
    path = tmp_path / "archive.db"
    database = open_archive_database(str(path))
    email = ParsedMessage(
        message_id="migration@example.test",
        subject="Migration evidence",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date="2026-08-28T10:00:00",
        body_text="Schema migration must retain this record.",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    try:
        assert database.insert_email(email)
        database.conn.execute("DELETE FROM schema_version")
        database.conn.execute("INSERT INTO schema_version(version) VALUES (35)")
        database.conn.commit()
        init_schema(database.conn)
        assert database.get_email_full(email.uid)["subject"] == "Migration evidence"
    finally:
        database.close()

    reopened = open_archive_database(str(path))
    try:
        assert reopened.get_email_full(email.uid)["body_text"] == "Schema migration must retain this record."
        assert reopened.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 36
    finally:
        reopened.close()
