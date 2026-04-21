# ruff: noqa: F401
"""Tests for the SQLite EmailDatabase."""

from src.email_db import EmailDatabase, _parse_address
from src.parse_olm import Email

from .helpers.email_db_builders import _make_email


class TestInsertEmailContentHash:
    def test_single_insert_computes_content_sha256(self):
        db = EmailDatabase(":memory:")
        email = _make_email(body_text="Hash me!")
        db.insert_email(email)
        row = db.conn.execute("SELECT content_sha256 FROM emails WHERE uid = ?", (email.uid,)).fetchone()
        assert row["content_sha256"] is not None
        assert len(row["content_sha256"]) == 64  # SHA-256 hex digest

    def test_single_insert_empty_body_null_hash(self):
        db = EmailDatabase(":memory:")
        email = _make_email(body_text="")
        db.insert_email(email)
        row = db.conn.execute("SELECT content_sha256 FROM emails WHERE uid = ?", (email.uid,)).fetchone()
        assert row["content_sha256"] is None
        db.close()


class TestInsertEmailNoneBody:
    def test_insert_email_with_none_body(self):
        """insert_email should handle None clean_body without crashing."""
        db = EmailDatabase(":memory:")
        email = _make_email(body_text=None)
        result = db.insert_email(email)
        assert result is True
        row = db.conn.execute("SELECT body_length FROM emails WHERE uid = ?", (email.uid,)).fetchone()
        assert row["body_length"] == 0
        db.close()


class TestLikeEscaping:
    """LIKE wildcards in user input must be escaped to prevent false matches."""

    def test_entity_search_escapes_underscore(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email()
        uid = email.uid  # MD5 hash of message_id
        db.insert_email(email)
        db.insert_entities_batch(
            uid,
            [("foo_bar", "org", "foo_bar"), ("fooXbar", "org", "fooxbar")],
        )
        # Searching for "foo_bar" should match only "foo_bar", not "fooXbar"
        results = db.search_by_entity("foo_bar", entity_type="org")
        matched_entities = {r["entity_text"] for r in results}
        assert "foo_bar" in matched_entities
        assert "fooXbar" not in matched_entities
        db.close()

    def test_entity_search_escapes_percent(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email()
        uid = email.uid
        db.insert_email(email)
        db.insert_entities_batch(
            uid,
            [("100%", "org", "100%"), ("100 widgets", "org", "100 widgets")],
        )
        results = db.search_by_entity("100%", entity_type="org")
        matched_entities = {r["entity_text"] for r in results}
        assert "100%" in matched_entities
        assert "100 widgets" not in matched_entities
        db.close()

    def test_thread_by_references_escapes_underscore(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        e1 = _make_email(
            message_id="<msg_1@example.test>",
            references=["<ref_abc@example.test>"],
        )
        e2 = _make_email(
            message_id="<msg_2@example.test>",
            references=["<refxabc@example.test>"],
        )
        db.insert_email(e1)
        db.insert_email(e2)
        results = db.thread_by_references("<ref_abc@example.test>")
        uids = {r["uid"] for r in results}
        assert e1.uid in uids
        assert e2.uid not in uids
        db.close()

    def test_delete_sparse_by_uid_escapes_underscore(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        # Insert sparse vectors for two UIDs with similar patterns
        db.conn.execute(
            "INSERT INTO sparse_vectors(chunk_id, token_ids, weights, num_tokens) VALUES(?, ?, ?, ?)",
            ("uid_a__0", b"", b"", 0),
        )
        db.conn.execute(
            "INSERT INTO sparse_vectors(chunk_id, token_ids, weights, num_tokens) VALUES(?, ?, ?, ?)",
            ("uidXa__0", b"", b"", 0),
        )
        db.conn.commit()
        deleted = db.delete_sparse_by_uid("uid_a")
        assert deleted == 1
        # The other row should still exist
        remaining = db.conn.execute("SELECT chunk_id FROM sparse_vectors").fetchall()
        assert len(remaining) == 1
        assert remaining[0]["chunk_id"] == "uidXa__0"
        db.close()


class TestGetThreadEmailsParsesJsonFields:
    """get_thread_emails should return parsed categories, references, and attachments."""

    def test_thread_emails_have_parsed_fields(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email(
            conversation_id="conv1",
            categories=["urgent", "review"],
            references=["<ref1@example.test>"],
            attachments=[
                {"name": "doc.pdf", "mime_type": "application/pdf", "size": 100, "content_id": "", "is_inline": False},
            ],
        )
        db.insert_email(email)
        thread = db.get_thread_emails("conv1")
        assert len(thread) == 1
        e = thread[0]
        # categories should be a parsed list, not a raw JSON string
        assert isinstance(e["categories"], list)
        assert "urgent" in e["categories"]
        # references should be a parsed list
        assert isinstance(e["references"], list)
        assert "<ref1@example.test>" in e["references"]
        # attachments should be fetched from the attachments table
        assert isinstance(e["attachments"], list)
        assert len(e["attachments"]) == 1
        assert e["attachments"][0]["name"] == "doc.pdf"
        # references_json raw key should NOT leak into the dict
        assert "references_json" not in e
        db.close()


class TestGetInferredThreadEmails:
    """get_inferred_thread_emails should hydrate inferred-only thread groups."""

    def test_inferred_thread_emails_have_parsed_fields(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email(
            conversation_id="",
            categories=["urgent"],
            references=["<ref1@example.test>"],
            attachments=[
                {"name": "doc.pdf", "mime_type": "application/pdf", "size": 100, "content_id": "", "is_inline": False},
            ],
        )
        email.inferred_thread_id = "thread-inferred-1"
        db.insert_email(email)
        thread = db.get_inferred_thread_emails("thread-inferred-1")
        assert len(thread) == 1
        item = thread[0]
        assert item["inferred_thread_id"] == "thread-inferred-1"
        assert isinstance(item["categories"], list)
        assert "urgent" in item["categories"]
        assert isinstance(item["references"], list)
        assert "<ref1@example.test>" in item["references"]
        assert len(item["attachments"]) == 1
        assert item["attachments"][0]["name"] == "doc.pdf"
        assert "references_json" not in item
        db.close()


class TestGetEmailFullNoJsonLeak:
    """get_email_full and get_emails_full_batch should not leak references_json."""

    def test_get_email_full_no_references_json_key(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email(references=["<ref1@example.test>"])
        db.insert_email(email)
        result = db.get_email_full(email.uid)
        assert "references" in result
        assert isinstance(result["references"], list)
        assert "references_json" not in result
        db.close()

    def test_get_emails_full_batch_no_references_json_key(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email(references=["<ref1@example.test>"])
        db.insert_email(email)
        result = db.get_emails_full_batch([email.uid])
        e = result[email.uid]
        assert "references" in e
        assert "references_json" not in e
        db.close()


class TestDateBoundaryBug:
    """Regression: SQL date_to comparisons must include the full day.

    Emails with datetime like '2024-01-15T10:30:00' were excluded by
    ``date <= '2024-01-15'`` because the T makes the datetime string
    lexicographically greater than the date-only string.
    """

    def test_calendar_emails_date_to_inclusive(self):
        """calendar_emails(date_to='2024-01-15') must include emails on that day."""
        db = EmailDatabase(":memory:")
        email = _make_email(
            date="2024-01-15T10:30:00",
            is_calendar_message=True,
        )
        db.insert_email(email)
        # Before fix: this returned [] because '2024-01-15T10:30:00' > '2024-01-15'
        results = db.calendar_emails(date_to="2024-01-15")
        assert len(results) == 1
        assert results[0]["uid"] == email.uid
        db.close()

    def test_calendar_emails_date_from_inclusive(self):
        """calendar_emails(date_from='2024-01-15') must include emails on that day."""
        db = EmailDatabase(":memory:")
        email = _make_email(
            date="2024-01-15T10:30:00",
            is_calendar_message=True,
        )
        db.insert_email(email)
        results = db.calendar_emails(date_from="2024-01-15")
        assert len(results) == 1
        db.close()

    def test_calendar_emails_date_range_same_day(self):
        """date_from == date_to on the same day as the email must match."""
        db = EmailDatabase(":memory:")
        email = _make_email(
            date="2024-01-15T23:59:59",
            is_calendar_message=True,
        )
        db.insert_email(email)
        results = db.calendar_emails(date_from="2024-01-15", date_to="2024-01-15")
        assert len(results) == 1
        db.close()

    def test_email_dates_date_to_inclusive(self):
        """email_dates(date_to='2024-01-15') must include emails on that day."""
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(date="2024-01-15T10:30:00"))
        dates = db.email_dates(date_to="2024-01-15")
        assert len(dates) == 1
        assert dates[0] == "2024-01-15T10:30:00"
        db.close()

    def test_email_dates_date_range_same_day(self):
        """email_dates with both bounds on the same day must include emails."""
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(date="2024-01-15T08:00:00"))
        dates = db.email_dates(date_from="2024-01-15", date_to="2024-01-15")
        assert len(dates) == 1
        db.close()

    def test_calendar_emails_excludes_next_day(self):
        """Emails on the next day must NOT be included in date_to filter."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                date="2024-01-16T00:00:01",
                is_calendar_message=True,
            )
        )
        results = db.calendar_emails(date_to="2024-01-15")
        assert len(results) == 0
        db.close()
