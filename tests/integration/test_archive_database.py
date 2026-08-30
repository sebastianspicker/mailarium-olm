"""Small SQLite integration checks for local archive persistence."""

from __future__ import annotations

from mailarium.archive import open_archive_database
from mailarium.archive.db_schema import init_schema
from mailarium.ingestion.records import ParsedMessage


def _email(
    *,
    message_id: str = "message@example.test",
    subject: str = "Direct database contract",
    body_text: str = "local evidence",
    attachments: bool = False,
) -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        subject=subject,
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date="2026-08-20T10:00:00",
        body_text=body_text,
        body_html="",
        folder="Inbox",
        has_attachments=attachments,
        attachment_names=["evidence.txt"] if attachments else [],
        attachments=[{"name": "evidence.txt", "size": 4, "extracted_text": "proof"}] if attachments else [],
    )


def test_sqlite_archive_preserves_one_email_in_a_temporary_database(tmp_path) -> None:
    database = open_archive_database(str(tmp_path / "archive.db"))
    email = _email()

    assert database.insert_email(email)
    stored = database.get_email_full(email.uid)
    assert stored is not None and stored["subject"] == "Direct database contract"
    database.close()


def test_archive_related_rows_custody_and_schema_upgrade_stay_transactional(tmp_path) -> None:
    database = open_archive_database(str(tmp_path / "archive.db"))
    email = _email(
        message_id="atomic@example.test",
        subject="Atomic archive contract",
        body_text="committed local evidence",
        attachments=True,
    )

    database.conn.execute(
        "CREATE TRIGGER reject_attachment BEFORE INSERT ON attachments BEGIN SELECT RAISE(ABORT, 'attachment rejected'); END"
    )
    assert not database.insert_email(email)
    tables = ("emails", "recipients", "attachments")
    assert [database.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables] == [0, 0, 0]
    database.conn.execute("DROP TRIGGER reject_attachment")

    assert database.insert_email(email)
    assert not database.insert_email(email)
    database.log_custody_event("ingested", "email", email.uid, {"source": "direct"})
    assert [database.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables] == [1, 1, 1]
    assert database.email_provenance(email.uid)["custody_events"][0]["action"] == "ingested"

    database.conn.execute("DELETE FROM schema_version")
    database.conn.execute("INSERT INTO schema_version(version) VALUES (35)")
    database.conn.commit()
    init_schema(database.conn)
    migrated = database.get_email_full(email.uid)
    assert migrated is not None and migrated["subject"] == "Atomic archive contract"
    assert database.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 36
    database.close()
