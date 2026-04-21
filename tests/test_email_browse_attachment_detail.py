"""Detail, attachment, and full-body browse tests split from the RF10 catch-all."""

from __future__ import annotations

import struct

from src.email_db import EmailDatabase
from src.parse_olm import BODY_NORMALIZATION_VERSION
from tests._email_browse_cases import make_email


def test_body_text_stored_on_insert():
    db = EmailDatabase(":memory:")
    email = make_email(
        body_text="Full email body here",
        body_html="<p>Full email body</p>",
        raw_body_text="Original plain body here",
        raw_body_html="<p>Original html body</p>",
        raw_source="Subject: Hello\n\nRaw source body",
        raw_source_headers={"Subject": "Hello"},
        forensic_body_text="Original plain body here",
        forensic_body_source="raw_body_text",
        to_identities=["bob@example.com"],
        recipient_identity_source="structured_xml",
    )
    db.insert_email(email)

    row = db.conn.execute(
        (
            "SELECT body_text, body_html, raw_body_text, raw_body_html, raw_source, "
            "raw_source_headers_json, forensic_body_text, forensic_body_source, "
            "normalized_body_source, body_normalization_version, body_kind, "
            "body_empty_reason, recovery_strategy, recovery_confidence, "
            "to_identities_json, cc_identities_json, bcc_identities_json, "
            "recipient_identity_source FROM emails WHERE uid = ?"
        ),
        (email.uid,),
    ).fetchone()
    assert row["body_text"] == "Full email body here"
    assert row["body_html"] == "<p>Full email body</p>"
    assert row["raw_body_text"] == "Original plain body here"
    assert row["raw_body_html"] == "<p>Original html body</p>"
    assert row["raw_source"] == "Subject: Hello\n\nRaw source body"
    assert row["raw_source_headers_json"] == '{"Subject": "Hello"}'
    assert row["forensic_body_text"] == "Original plain body here"
    assert row["forensic_body_source"] == "raw_body_text"
    assert row["normalized_body_source"] == "body_text"
    assert row["body_normalization_version"] == BODY_NORMALIZATION_VERSION
    assert row["body_kind"] == "content"
    assert row["body_empty_reason"] == ""
    assert row["recovery_strategy"] == ""
    assert row["recovery_confidence"] == 1.0
    assert row["to_identities_json"] == '["bob@example.com"]'
    assert row["cc_identities_json"] == "[]"
    assert row["bcc_identities_json"] == "[]"
    assert row["recipient_identity_source"] == "structured_xml"
    db.close()


def test_body_recovery_fields_stored_on_insert():
    db = EmailDatabase(":memory:")
    email = make_email(
        subject="Preview rescue",
        body_text="<html><body><div></div></body></html>",
        body_html="<html><body><div></div></body></html>",
        preview_text="Visible preview summary.",
    )
    db.insert_email(email)

    row = db.conn.execute(
        (
            "SELECT body_text, normalized_body_source, body_kind, body_empty_reason, "
            "recovery_strategy, recovery_confidence FROM emails WHERE uid = ?"
        ),
        (email.uid,),
    ).fetchone()
    assert row["body_text"] == "Visible preview summary."
    assert row["normalized_body_source"] == "preview"
    assert row["body_kind"] == "content"
    assert row["body_empty_reason"] == "html_shell_only"
    assert row["recovery_strategy"] == "preview"
    assert row["recovery_confidence"] == 0.7
    db.close()


def test_body_text_stored_without_reply_quote_tail():
    db = EmailDatabase(":memory:")
    email = make_email(
        subject="RE: Hello",
        body_text="Latest answer.\n\nOn Mon, Jan 1, 2025 at 10:00 AM Alice wrote:\n> Older line 1\n> Older line 2",
        body_html="",
    )
    db.insert_email(email)

    row = db.conn.execute(
        "SELECT body_text, normalized_body_source, body_normalization_version FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["body_text"] == "Latest answer."
    assert row["normalized_body_source"] == "body_text"
    assert row["body_normalization_version"] == BODY_NORMALIZATION_VERSION
    db.close()


def test_body_text_stored_without_reply_header_tail():
    db = EmailDatabase(":memory:")
    email = make_email(
        subject="RE: Hello",
        body_text=(
            "Latest answer.\n\n"
            "From: Alice <employee@example.test>\n"
            "Sent: Monday, January 1, 2025 10:00 AM\n"
            "To: Bob <bob@example.com>\n"
            "Subject: Hello"
        ),
        body_html="",
    )
    db.insert_email(email)

    row = db.conn.execute(
        "SELECT body_text, normalized_body_source, body_normalization_version FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["body_text"] == "Latest answer."
    assert row["normalized_body_source"] == "body_text"
    assert row["body_normalization_version"] == BODY_NORMALIZATION_VERSION
    db.close()


def test_body_text_stored_without_german_reply_header_tail():
    db = EmailDatabase(":memory:")
    email = make_email(
        subject="AW: Hallo",
        body_text=(
            "Aktuelle Antwort.\n\n"
            "Von: Alice <employee@example.test>\n"
            "Gesendet: Montag, 1. Januar 2025 10:00\n"
            "An: Bob <bob@example.com>\n"
            "Betreff: Hallo"
        ),
        body_html="",
    )
    db.insert_email(email)

    row = db.conn.execute(
        "SELECT body_text, normalized_body_source, body_normalization_version FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["body_text"] == "Aktuelle Antwort."
    assert row["normalized_body_source"] == "body_text"
    assert row["body_normalization_version"] == BODY_NORMALIZATION_VERSION
    db.close()


def test_body_text_stored_without_portuguese_reply_header_tail():
    db = EmailDatabase(":memory:")
    email = make_email(
        subject="RE: Ola",
        body_text=(
            "Resposta atual.\n\n"
            "De: Alice <employee@example.test>\n"
            "Enviado: segunda-feira, 1 de janeiro de 2025 10:00\n"
            "Para: Bob <bob@example.com>\n"
            "Assunto: Ola"
        ),
        body_html="",
    )
    db.insert_email(email)

    row = db.conn.execute(
        "SELECT body_text, normalized_body_source, body_normalization_version FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["body_text"] == "Resposta atual."
    assert row["normalized_body_source"] == "body_text"
    assert row["body_normalization_version"] == BODY_NORMALIZATION_VERSION
    db.close()


def test_body_text_stored_without_get_outlook_ios_footer():
    db = EmailDatabase(":memory:")
    email = make_email(
        body_text="Please see the attached file.\n\nGet Outlook for iOS",
        body_html="",
    )
    db.insert_email(email)

    row = db.conn.execute(
        "SELECT body_text, normalized_body_source, body_normalization_version FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["body_text"] == "Please see the attached file."
    assert row["normalized_body_source"] == "body_text"
    assert row["body_normalization_version"] == BODY_NORMALIZATION_VERSION
    db.close()


def test_body_text_stored_on_batch_insert():
    db = EmailDatabase(":memory:")
    emails = [
        make_email(message_id="<m1@example.test>", body_text="Body one"),
        make_email(message_id="<m2@example.test>", body_text="Body two"),
    ]
    db.insert_emails_batch(emails)

    rows = db.conn.execute("SELECT body_text FROM emails ORDER BY uid").fetchall()
    texts = sorted(row["body_text"] for row in rows)
    assert "Body one" in texts
    assert "Body two" in texts
    db.close()


def test_get_email_full_returns_body():
    db = EmailDatabase(":memory:")
    email = make_email(
        body_text="Complete body text",
        raw_body_text="Raw complete body text",
        raw_body_html="<p>Raw complete body text</p>",
        raw_source="Subject: Hello\n\nRaw source body",
        raw_source_headers={"Subject": "Hello"},
        forensic_body_text="Raw complete body text",
        forensic_body_source="raw_body_text",
        to=["Bob Example"],
        to_identities=["bob@example.com"],
        recipient_identity_source="source_header",
        reply_context_from="carol@example.com",
        reply_context_to=["employee@example.test"],
        reply_context_subject="Original topic",
        reply_context_date="2025-01-01T10:00:00",
        reply_context_source="body_text",
    )
    db.insert_email(email)

    full = db.get_email_full(email.uid)
    assert full is not None
    assert full["body_text"] == "Complete body text"
    assert full["raw_body_text"] == "Raw complete body text"
    assert full["raw_body_html"] == "<p>Raw complete body text</p>"
    assert full["raw_source"] == "Subject: Hello\n\nRaw source body"
    assert full["raw_source_headers_json"] == '{"Subject": "Hello"}'
    assert full["forensic_body_text"] == "Raw complete body text"
    assert full["forensic_body_source"] == "raw_body_text"
    assert full["body_kind"] == "content"
    assert full["body_empty_reason"] == ""
    assert full["recovery_strategy"] == ""
    assert full["recovery_confidence"] == 1.0
    assert full["to_identities_json"] == '["bob@example.com"]'
    assert full["recipient_identity_source"] == "source_header"
    assert full["reply_context_from"] == "carol@example.com"
    assert full["reply_context_to_json"] == '["employee@example.test"]'
    assert full["reply_context_subject"] == "Original topic"
    assert full["reply_context_date"] == "2025-01-01T10:00:00"
    assert full["reply_context_source"] == "body_text"
    assert full["subject"] == "Hello"
    assert full["sender_email"] == "employee@example.test"
    assert full["to"] == ["Bob Example <bob@example.com>"]
    db.close()


def test_get_email_full_includes_recipients():
    db = EmailDatabase(":memory:")
    email = make_email(
        to=["Bob <bob@example.com>"],
        cc=["Carol <carol@example.com>"],
        bcc=["Dave <dave@example.com>"],
    )
    db.insert_email(email)

    full = db.get_email_full(email.uid)
    assert full is not None
    assert len(full["to"]) == 1
    assert "bob@example.com" in full["to"][0]
    assert len(full["cc"]) == 1
    assert "carol@example.com" in full["cc"][0]
    assert len(full["bcc"]) == 1
    assert "dave@example.com" in full["bcc"][0]
    db.close()


def test_update_body_text_success():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="")
    db.insert_email(email)

    ok = db.update_body_text(
        email.uid,
        "New body",
        "<p>New body</p>",
        normalized_body_source="body_html",
        body_normalization_version=BODY_NORMALIZATION_VERSION,
    )
    assert ok is True

    full = db.get_email_full(email.uid)
    assert full["body_text"] == "New body"
    assert full["body_html"] == "<p>New body</p>"
    assert full["normalized_body_source"] == "body_html"
    assert full["body_normalization_version"] == BODY_NORMALIZATION_VERSION
    db.close()


def test_update_headers_success():
    db = EmailDatabase(":memory:")
    email = make_email(subject="=?utf-8?Q?old?=", sender_name="Old")
    db.insert_email(email)

    ok = db.update_headers(
        email.uid,
        subject="Decoded Subject",
        sender_name="New Name",
        sender_email="new@example.com",
        base_subject="Decoded Subject",
        email_type="reply",
    )
    assert ok is True

    row = db.conn.execute(
        "SELECT subject, sender_name, sender_email, base_subject, email_type FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["subject"] == "Decoded Subject"
    assert row["sender_name"] == "New Name"
    assert row["sender_email"] == "new@example.com"
    assert row["base_subject"] == "Decoded Subject"
    assert row["email_type"] == "reply"
    db.close()


def test_delete_sparse_by_uid():
    db = EmailDatabase(":memory:")
    email = make_email()
    db.insert_email(email)
    for i in range(2):
        chunk_id = f"{email.uid}__{i}"
        token_blob = struct.pack("<1i", 42)
        weight_blob = struct.pack("<1f", 0.5)
        db.conn.execute(
            "INSERT INTO sparse_vectors(chunk_id, token_ids, weights, num_tokens) VALUES(?,?,?,?)",
            (chunk_id, token_blob, weight_blob, 1),
        )
    db.conn.commit()

    deleted = db.delete_sparse_by_uid(email.uid)
    assert deleted == 2
    remaining = db.conn.execute("SELECT COUNT(*) FROM sparse_vectors").fetchone()[0]
    assert remaining == 0
    db.close()


def test_get_email_for_reembed_returns_dict():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Hello world")
    db.insert_email(email)

    result = db.get_email_for_reembed(email.uid)
    assert result is not None
    assert result["uid"] == email.uid
    assert result["body"] == "Hello world"
    assert result["subject"] == email.subject
    assert result["email_type"] == "original"
    db.close()
