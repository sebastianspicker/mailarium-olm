# ruff: noqa: F401
"""Tests for the SQLite EmailDatabase."""

from src.email_db import EmailDatabase, _parse_address
from src.parse_olm import Email

from .helpers.email_db_builders import _make_email


class TestParseAddress:
    def test_name_and_email(self):
        assert _parse_address("Alice <employee@example.test>") == ("Alice", "employee@example.test")

    def test_quoted_name(self):
        assert _parse_address('"Alice B" <employee@example.test>') == ("Alice B", "employee@example.test")

    def test_bare_email(self):
        assert _parse_address("employee@example.test") == ("", "employee@example.test")

    def test_name_only(self):
        assert _parse_address("Alice") == ("Alice", "")

    def test_empty(self):
        assert _parse_address("") == ("", "")


class TestEmailDatabase:
    def test_schema_created(self):
        db = EmailDatabase(":memory:")
        tables = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r["name"] for r in tables}
        assert "emails" in names
        assert "recipients" in names
        assert "contacts" in names
        assert "communication_edges" in names
        assert "schema_version" in names
        db.close()

    def test_insert_email(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        assert db.insert_email(email) is True
        assert db.email_count() == 1
        db.close()

    def test_insert_duplicate(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        assert db.insert_email(email) is True
        assert db.insert_email(email) is False
        assert db.email_count() == 1
        db.close()

    def test_recipients_populated(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
            bcc=["dave@example.com"],
        )
        db.insert_email(email)
        rows = db.conn.execute("SELECT address, type FROM recipients ORDER BY type").fetchall()
        result = [(r["address"], r["type"]) for r in rows]
        assert ("dave@example.com", "bcc") in result
        assert ("carol@example.com", "cc") in result
        assert ("bob@example.com", "to") in result
        db.close()

    def test_recipients_prefer_identity_addresses_over_display_only_values(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            to=["Bob Example"],
            cc=["Carol Example"],
            bcc=["Dave Example"],
            to_identities=["bob@example.com"],
            cc_identities=["carol@example.com"],
            bcc_identities=["dave@example.com"],
            recipient_identity_source="source_header",
        )
        db.insert_email(email)
        rows = db.conn.execute("SELECT address, display_name, type FROM recipients ORDER BY type").fetchall()
        result = {(r["type"], r["address"], r["display_name"]) for r in rows}
        assert ("to", "bob@example.com", "Bob Example") in result
        assert ("cc", "carol@example.com", "Carol Example") in result
        assert ("bcc", "dave@example.com", "Dave Example") in result
        db.close()

    def test_contacts_upserted(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        db.insert_email(email)

        sender = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'employee@example.test'").fetchone()
        assert sender is not None
        assert sender["sent_count"] == 1
        assert sender["received_count"] == 0

        recipient = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'bob@example.com'").fetchone()
        assert recipient is not None
        assert recipient["received_count"] == 1
        assert recipient["sent_count"] == 0
        db.close()

    def test_contacts_accumulate(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>", date="2024-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@example.test>", date="2024-06-01T00:00:00"))

        sender = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'employee@example.test'").fetchone()
        assert sender["sent_count"] == 2
        assert sender["first_seen"] == "2024-01-01T00:00:00"
        assert sender["last_seen"] == "2024-06-01T00:00:00"
        db.close()

    def test_communication_edges(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>"))
        db.insert_email(_make_email(message_id="<m2@example.test>"))

        edge = db.conn.execute("SELECT * FROM communication_edges WHERE sender_email='employee@example.test'").fetchone()
        assert edge is not None
        assert edge["email_count"] == 2
        assert edge["recipient_email"] == "bob@example.com"
        db.close()

    def test_email_count(self):
        db = EmailDatabase(":memory:")
        assert db.email_count() == 0
        db.insert_email(_make_email())
        assert db.email_count() == 1
        db.close()

    def test_top_senders(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>"))
        db.insert_email(_make_email(message_id="<m2@example.test>"))
        db.insert_email(
            _make_email(
                message_id="<m3@example.test>",
                sender_email="eve@example.com",
                sender_name="Eve",
            )
        )
        senders = db.top_senders(limit=10)
        assert senders[0]["sender_email"] == "employee@example.test"
        assert senders[0]["message_count"] == 2
        assert senders[1]["sender_email"] == "eve@example.com"
        db.close()

    def test_date_range(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>", date="2023-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@example.test>", date="2024-12-31T23:59:59"))
        min_d, max_d = db.date_range()
        assert min_d == "2023-01-01T00:00:00"
        assert max_d == "2024-12-31T23:59:59"
        db.close()

    def test_folder_counts(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>", folder="Inbox"))
        db.insert_email(_make_email(message_id="<m2@example.test>", folder="Inbox"))
        db.insert_email(_make_email(message_id="<m3@example.test>", folder="Sent"))
        counts = db.folder_counts()
        assert counts["Inbox"] == 2
        assert counts["Sent"] == 1
        db.close()

    def test_email_exists(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        db.insert_email(email)
        assert db.email_exists(email.uid) is True
        assert db.email_exists("nonexistent") is False
        db.close()

    def test_batch_insert(self):
        db = EmailDatabase(":memory:")
        emails = [
            _make_email(message_id="<m1@example.test>"),
            _make_email(message_id="<m2@example.test>"),
            _make_email(message_id="<m3@example.test>"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 3
        assert db.email_count() == 3
        db.close()

    def test_batch_skips_duplicates(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>"))
        emails = [
            _make_email(message_id="<m1@example.test>"),  # duplicate
            _make_email(message_id="<m2@example.test>"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 1
        assert db.email_count() == 2
        db.close()

    def test_unique_sender_count(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>"))
        db.insert_email(_make_email(message_id="<m2@example.test>", sender_email="bob@example.com"))
        assert db.unique_sender_count() == 2
        db.close()

    def test_batch_insert_contact_accumulation(self):
        """Batch insert should accumulate sent_count correctly for repeated senders."""
        db = EmailDatabase(":memory:")
        emails = [
            _make_email(message_id="<m1@example.test>", date="2024-01-01T00:00:00"),
            _make_email(message_id="<m2@example.test>", date="2024-06-01T00:00:00"),
            _make_email(message_id="<m3@example.test>", date="2024-03-01T00:00:00"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 3

        sender = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'employee@example.test'").fetchone()
        assert sender["sent_count"] == 3
        assert sender["first_seen"] == "2024-01-01T00:00:00"
        assert sender["last_seen"] == "2024-06-01T00:00:00"

        recipient = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'bob@example.com'").fetchone()
        assert recipient["received_count"] == 3
        db.close()

    def test_batch_insert_edge_accumulation(self):
        """Batch insert should accumulate email_count for repeated sender→recipient pairs."""
        db = EmailDatabase(":memory:")
        emails = [
            _make_email(message_id="<m1@example.test>", date="2024-01-01T00:00:00"),
            _make_email(message_id="<m2@example.test>", date="2024-06-01T00:00:00"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 2

        edge = db.conn.execute("SELECT * FROM communication_edges WHERE sender_email='employee@example.test'").fetchone()
        assert edge is not None
        assert edge["email_count"] == 2
        assert edge["first_date"] == "2024-01-01T00:00:00"
        assert edge["last_date"] == "2024-06-01T00:00:00"
        db.close()

    def test_migration_v5_to_v6_creates_composite_indexes(self):
        db = EmailDatabase(":memory:")
        indexes = db.conn.execute("PRAGMA index_list(emails)").fetchall()
        index_names = {row["name"] for row in indexes}
        assert "idx_emails_sender_date" in index_names
        assert "idx_emails_folder_date" in index_names
        db.close()


class TestGetEmailsFullBatch:
    def test_returns_all(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(
            message_id="<b1@example.test>",
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
            has_attachments=True,
            attachments=[{"name": "f1.pdf", "mime_type": "application/pdf", "size": 100, "content_id": "", "is_inline": False}],
        )
        e2 = _make_email(
            message_id="<b2@example.test>",
            sender_email="bob@example.com",
            to=["Alice <employee@example.test>"],
        )
        e3 = _make_email(
            message_id="<b3@example.test>",
            sender_email="carol@example.com",
            bcc=["Dave <dave@example.com>"],
        )
        db.insert_email(e1)
        db.insert_email(e2)
        db.insert_email(e3)
        batch = db.get_emails_full_batch([e1.uid, e2.uid, e3.uid])
        assert len(batch) == 3
        assert batch[e1.uid]["to"] == ["Bob <bob@example.com>"]
        assert batch[e1.uid]["cc"] == ["Carol <carol@example.com>"]
        assert len(batch[e1.uid]["attachments"]) == 1
        assert batch[e3.uid]["bcc"] == ["Dave <dave@example.com>"]
        db.close()

    def test_partial_uids(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<b1@example.test>")
        e2 = _make_email(message_id="<b2@example.test>", sender_email="bob@example.com")
        db.insert_email(e1)
        db.insert_email(e2)
        batch = db.get_emails_full_batch([e1.uid, e2.uid, "nonexistent-uid"])
        assert len(batch) == 2
        assert "nonexistent-uid" not in batch
        db.close()

    def test_empty_list(self):
        db = EmailDatabase(":memory:")
        assert db.get_emails_full_batch([]) == {}
        db.close()

    def test_matches_single(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
            has_attachments=True,
            attachments=[{"name": "doc.pdf", "mime_type": "application/pdf", "size": 500, "content_id": "", "is_inline": False}],
            references=["ref1@example.com"],
            categories=["Important"],
        )
        db.insert_email(email)
        single = db.get_email_full(email.uid)
        batch = db.get_emails_full_batch([email.uid])
        batch_email = batch[email.uid]
        # Compare key fields
        for key in ("uid", "subject", "sender_email", "to", "cc", "bcc", "references"):
            assert batch_email[key] == single[key], f"Mismatch on {key}"
        assert len(batch_email["attachments"]) == len(single["attachments"])
        assert batch_email["attachments"][0]["name"] == single["attachments"][0]["name"]
        assert batch_email["categories"] == single["categories"]
        db.close()


class TestGetThreadEmailsBatchRecipients:
    def test_batch_recipients(self):
        db = EmailDatabase(":memory:")
        conv_id = "thread-123"
        e1 = _make_email(
            message_id="<t1@example.test>",
            conversation_id=conv_id,
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
            date="2024-01-01T10:00:00",
        )
        e2 = _make_email(
            message_id="<t2@example.test>",
            sender_email="bob@example.com",
            sender_name="Bob",
            conversation_id=conv_id,
            to=["Alice <employee@example.test>"],
            bcc=["Dave <dave@example.com>"],
            date="2024-01-01T11:00:00",
        )
        e3 = _make_email(
            message_id="<t3@example.test>",
            sender_email="carol@example.com",
            sender_name="Carol",
            conversation_id=conv_id,
            to=["Alice <employee@example.test>", "Bob <bob@example.com>"],
            date="2024-01-01T12:00:00",
        )
        db.insert_email(e1)
        db.insert_email(e2)
        db.insert_email(e3)
        thread = db.get_thread_emails(conv_id)
        assert len(thread) == 3
        assert thread[0]["to"] == ["Bob <bob@example.com>"]
        assert thread[0]["cc"] == ["Carol <carol@example.com>"]
        assert thread[1]["bcc"] == ["Dave <dave@example.com>"]
        assert len(thread[2]["to"]) == 2
        db.close()


class TestEmailsByBaseSubject:
    def test_returns_body_text(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<s1@example.test>", subject="Re: Hello", body_text="Body one")
        e2 = _make_email(message_id="<s2@example.test>", subject="Re: Hello", body_text="Body two")
        db.insert_email(e1)
        db.insert_email(e2)
        results = db.emails_by_base_subject(min_group_size=2)
        assert len(results) >= 1
        _subject, emails = results[0]
        bodies = [body for _, body in emails]
        assert "Body one" in bodies
        assert "Body two" in bodies
        db.close()


class TestGetEmailForReembedNullSafety:
    """Regression: get_email_for_reembed must not pass None values through.

    SQLite returns None for NULL columns, and dict.get("key", default)
    returns None (not the default) when the key exists with a None value.
    chunk_email() and ChromaDB metadata require strings, not None.
    """

    def test_reembed_null_subject_becomes_empty_string(self):
        """Null subject in SQLite should become '' in reembed dict."""
        db = EmailDatabase(":memory:")
        email = _make_email(body_text="Some body text for re-embedding")
        db.insert_email(email)
        # Simulate NULL subject in SQLite
        db.conn.execute("UPDATE emails SET subject = NULL WHERE uid = ?", (email.uid,))
        db.conn.commit()

        result = db.get_email_for_reembed(email.uid)
        assert result is not None
        assert result["subject"] == ""
        assert result["subject"] is not None
        db.close()

    def test_reembed_null_folder_becomes_empty_string(self):
        db = EmailDatabase(":memory:")
        email = _make_email(body_text="Some body text for re-embedding")
        db.insert_email(email)
        db.conn.execute("UPDATE emails SET folder = NULL WHERE uid = ?", (email.uid,))
        db.conn.commit()

        result = db.get_email_for_reembed(email.uid)
        assert result is not None
        assert result["folder"] == ""
        db.close()

    def test_reembed_null_conversation_id_becomes_empty_string(self):
        db = EmailDatabase(":memory:")
        email = _make_email(body_text="Some body text for re-embedding")
        db.insert_email(email)
        db.conn.execute("UPDATE emails SET conversation_id = NULL WHERE uid = ?", (email.uid,))
        db.conn.commit()

        result = db.get_email_for_reembed(email.uid)
        assert result is not None
        assert result["conversation_id"] == ""
        db.close()

    def test_reembed_null_priority_becomes_zero(self):
        db = EmailDatabase(":memory:")
        email = _make_email(body_text="Some body text for re-embedding")
        db.insert_email(email)
        db.conn.execute("UPDATE emails SET priority = NULL WHERE uid = ?", (email.uid,))
        db.conn.commit()

        result = db.get_email_for_reembed(email.uid)
        assert result is not None
        assert result["priority"] == 0
        db.close()

    def test_reembed_no_none_string_values(self):
        """No string field in the reembed dict should be None."""
        db = EmailDatabase(":memory:")
        email = _make_email(body_text="Some body text for re-embedding")
        db.insert_email(email)
        # Set many columns to NULL
        db.conn.execute(
            "UPDATE emails SET subject=NULL, folder=NULL, conversation_id=NULL, "
            "in_reply_to=NULL, base_subject=NULL, email_type=NULL, "
            "sender_name=NULL, message_id=NULL, thread_topic=NULL, "
            "inference_classification=NULL WHERE uid=?",
            (email.uid,),
        )
        db.conn.commit()

        result = db.get_email_for_reembed(email.uid)
        assert result is not None
        string_fields = [
            "uid",
            "message_id",
            "subject",
            "sender_name",
            "sender_email",
            "date",
            "body",
            "folder",
            "conversation_id",
            "in_reply_to",
            "email_type",
            "base_subject",
            "thread_topic",
            "inference_classification",
        ]
        for field in string_fields:
            assert result[field] is not None, f"Field {field!r} is None"
            assert isinstance(result[field], str), f"Field {field!r} is {type(result[field])}, expected str"
        db.close()
