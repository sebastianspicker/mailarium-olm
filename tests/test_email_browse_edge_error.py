"""Edge, error, and schema browse tests split from the RF10 catch-all."""

from __future__ import annotations

from src.email_db import EmailDatabase
from tests._email_browse_cases import make_email


def test_get_email_full_missing_uid():
    db = EmailDatabase(":memory:")
    assert db.get_email_full("nonexistent") is None
    db.close()


def test_update_body_text_nonexistent_uid():
    db = EmailDatabase(":memory:")
    ok = db.update_body_text("no_such_uid", "body", "html")
    assert ok is False
    db.close()


def test_update_headers_nonexistent_uid():
    db = EmailDatabase(":memory:")
    ok = db.update_headers("no_such_uid", "s", "n", "e", "b", "original")
    assert ok is False
    db.close()


def test_get_email_for_reembed_returns_none_for_empty_body():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="")
    db.insert_email(email)
    db.conn.execute("UPDATE emails SET body_text = '' WHERE uid = ?", (email.uid,))
    db.conn.commit()

    assert db.get_email_for_reembed(email.uid) is None
    db.close()


def test_get_email_for_reembed_returns_none_for_missing_uid():
    db = EmailDatabase(":memory:")
    assert db.get_email_for_reembed("nonexistent") is None
    db.close()


def test_uids_missing_body():
    db = EmailDatabase(":memory:")
    db.insert_email(make_email(message_id="<m1@ex.com>", body_text="has body"))

    db.conn.execute(
        "INSERT INTO emails(uid, message_id, subject, sender_email, date, folder) "
        "VALUES('uid_no_body', '<m2@ex.com>', 'No body', 'x@x.com', '2024-01-01', 'Inbox')"
    )
    db.conn.commit()

    missing = db.uids_missing_body()
    assert "uid_no_body" in missing
    assert len(missing) == 1
    db.close()


def test_schema_has_body_columns():
    db = EmailDatabase(":memory:")
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()}
    assert "body_text" in cols
    assert "body_html" in cols
    db.close()
