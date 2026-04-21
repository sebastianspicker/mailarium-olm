"""Data integrity tests: schema idempotency, SQLite/ChromaDB consistency,
SQL injection surface, data type contracts, and foreign key enforcement."""

import json
import sqlite3

import pytest

from src.db_schema import _SCHEMA_VERSION, _escape_like, _table_columns, init_schema
from src.email_db import EmailDatabase
from src.parse_olm import Email


def _make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Hello",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-15T10:30:00",
        "body_text": "Test body text for integrity checking",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


# =====================================================================
# 1. Schema migration idempotency
# =====================================================================


class TestSchemaIdempotency:
    """Verify that init_schema can be called twice without error."""

    def test_init_schema_twice_no_error(self):
        """Running init_schema twice on the same connection must not raise."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        # Second call should be a no-op
        init_schema(conn)
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        assert row["v"] == _SCHEMA_VERSION
        conn.close()

    def test_init_schema_preserves_data(self):
        """Re-running init_schema must not drop existing data."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        conn.execute(
            "INSERT INTO emails (uid, subject, sender_email, date, folder) "
            "VALUES ('test1', 'Sub', 'a@b.com', '2024-01-01', 'Inbox')"
        )
        conn.commit()
        # Re-run migrations
        init_schema(conn)
        row = conn.execute("SELECT COUNT(*) AS c FROM emails").fetchone()
        assert row["c"] == 1
        conn.close()

    def test_all_migrations_use_if_not_exists(self):
        """Smoke test: a fresh DB gets all CREATE TABLE IF NOT EXISTS."""
        conn = sqlite3.connect(":memory:")
        init_schema(conn)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        expected = {
            "schema_version",
            "emails",
            "message_segments",
            "conversation_edges",
            "recipients",
            "contacts",
            "communication_edges",
            "entities",
            "entity_mentions",
            "email_keywords",
            "topics",
            "email_topics",
            "email_clusters",
            "cluster_info",
            "ingestion_runs",
            "evidence_items",
            "custody_chain",
            "sparse_vectors",
            "attachments",
            "email_categories",
        }
        assert expected.issubset(tables)
        conn.close()

    def test_table_columns_helper_works(self):
        """_table_columns returns correct column names."""
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        init_schema(conn)
        cols = _table_columns(cur, "emails")
        assert "uid" in cols
        assert "subject" in cols
        assert "ingestion_run_id" in cols  # v9 column
        assert "normalized_body_source" in cols
        assert "body_normalization_version" in cols
        assert "body_kind" in cols
        assert "body_empty_reason" in cols
        assert "recovery_strategy" in cols
        assert "recovery_confidence" in cols
        assert "to_identities_json" in cols
        assert "cc_identities_json" in cols
        assert "bcc_identities_json" in cols
        assert "recipient_identity_source" in cols
        assert "reply_context_from" in cols
        assert "reply_context_to_json" in cols
        assert "reply_context_subject" in cols
        assert "reply_context_date" in cols
        assert "reply_context_source" in cols
        assert "inferred_parent_uid" in cols
        assert "inferred_thread_id" in cols
        assert "inferred_match_reason" in cols
        assert "inferred_match_confidence" in cols
        conn.close()

    def test_schema_version_matches_current_schema(self):
        db = EmailDatabase(":memory:")
        row = db.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        assert row["v"] == _SCHEMA_VERSION
        db.close()


# =====================================================================
# 2. SQLite/ChromaDB consistency
# =====================================================================


class TestConsistencyCheck:
    """Verify the consistency_check method."""

    def test_consistent_state(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        uid = _make_email().uid
        chromadb_ids = {f"{uid}__0", f"{uid}__1"}
        result = db.consistency_check(chromadb_ids)
        assert result["is_consistent"] is True
        assert result["sqlite_only_count"] == 0
        assert result["chromadb_only_count"] == 0
        db.close()

    def test_sqlite_only(self):
        """Email in SQLite but no chunks in ChromaDB."""
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        result = db.consistency_check(set())
        assert result["sqlite_only_count"] == 1
        assert result["chromadb_only_count"] == 0
        assert result["is_consistent"] is False
        db.close()

    def test_chromadb_only(self):
        """Chunks in ChromaDB but no matching email in SQLite."""
        db = EmailDatabase(":memory:")
        orphan_uid = "deadbeef1234"
        chromadb_ids = {f"{orphan_uid}__0"}
        result = db.consistency_check(chromadb_ids)
        assert result["chromadb_only_count"] == 1
        assert result["is_consistent"] is False
        assert orphan_uid in result["chromadb_only"]
        db.close()

    def test_mixed_consistency(self):
        """Both SQLite-only and ChromaDB-only orphans."""
        db = EmailDatabase(":memory:")
        email = _make_email()
        db.insert_email(email)
        # Add a different email to DB only
        db.insert_email(_make_email(message_id="<msg2@example.com>"))
        # ChromaDB has only email1's chunks + an orphan
        uid1 = _make_email(message_id="<msg1@example.com>").uid
        chromadb_ids = {f"{uid1}__0", "orphan_uid__0"}
        result = db.consistency_check(chromadb_ids)
        assert result["chromadb_only_count"] >= 1
        assert "orphan_uid" in result["chromadb_only"]
        db.close()


# =====================================================================
# 3. SQL injection surface
# =====================================================================


class TestSqlInjectionSurface:
    """Verify _escape_like and parameterized queries prevent injection."""

    def test_escape_like_percent(self):
        assert _escape_like("100%") == "100\\%"

    def test_escape_like_underscore(self):
        assert _escape_like("a_b") == "a\\_b"

    def test_escape_like_backslash(self):
        assert _escape_like("a\\b") == "a\\\\b"

    def test_escape_like_combined(self):
        assert _escape_like("a%b_c\\d") == "a\\%b\\_c\\\\d"

    def test_emails_by_sender_uses_escape(self):
        """sender filter with LIKE wildcards must not match extra rows."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<m1@ex.com>",
                sender_email="alice_admin@example.com",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<m2@ex.com>",
                sender_email="alicexadmin@example.com",
            )
        )
        # Search for literal underscore — should match only alice_admin
        results = db.emails_by_sender("alice_admin")
        emails = [r["sender_email"] for r in results]
        assert "alice_admin@example.com" in emails
        # alicexadmin should not match because _ is escaped
        assert "alicexadmin@example.com" not in emails
        db.close()

    def test_sort_by_injection_blocked(self):
        """list_emails_paginated rejects unknown sort_by values."""
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        # Attempt SQL injection via sort_by
        result = db.list_emails_paginated(sort_by="uid; DROP TABLE emails--")
        # Should fall back to "date" safely
        assert result["total"] == 1
        # Table still exists
        count = db.conn.execute("SELECT COUNT(*) AS c FROM emails").fetchone()["c"]
        assert count == 1
        db.close()

    def test_update_evidence_rejects_unknown_fields(self):
        """update_evidence ignores fields not in the allowed set."""
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        uid = _make_email().uid
        item = db.add_evidence(uid, "general", "Test body", "summary", 3)
        # Try to inject via field name
        result = db.update_evidence(item["id"], email_uid="injected", summary="new summary")
        assert result is True
        # email_uid should NOT have changed
        updated = db.get_evidence(item["id"])
        assert updated["email_uid"] == uid
        assert updated["summary"] == "new summary"
        db.close()


# =====================================================================
# 4. Data type contracts
# =====================================================================


class TestDataTypeContracts:
    """Verify UIDs are strings, JSON columns are valid, booleans are 0/1."""

    def test_uid_is_string(self):
        email = _make_email()
        assert isinstance(email.uid, str)
        assert len(email.uid) == 32  # md5 hexdigest

    def test_uid_stored_as_string(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        row = db.conn.execute("SELECT uid, typeof(uid) AS t FROM emails").fetchone()
        assert row["t"] == "text"
        db.close()

    def test_has_attachments_stored_as_integer(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(has_attachments=True))
        row = db.conn.execute("SELECT has_attachments, typeof(has_attachments) AS t FROM emails").fetchone()
        assert row["t"] == "integer"
        assert row["has_attachments"] in (0, 1)
        db.close()

    def test_is_read_stored_as_integer(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        row = db.conn.execute("SELECT is_read, typeof(is_read) AS t FROM emails").fetchone()
        assert row["t"] == "integer"
        db.close()

    def test_is_calendar_stored_as_integer(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        email.is_calendar_message = True
        db.insert_email(email)
        row = db.conn.execute("SELECT is_calendar_message, typeof(is_calendar_message) AS t FROM emails").fetchone()
        assert row["t"] == "integer"
        assert row["is_calendar_message"] == 1
        db.close()

    def test_categories_json_valid(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        email.categories = ["Red Category", "Blue Category"]
        db.insert_email(email)
        row = db.conn.execute("SELECT categories FROM emails").fetchone()
        parsed = json.loads(row["categories"])
        assert parsed == ["Red Category", "Blue Category"]
        db.close()

    def test_references_json_valid(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        email.references = ["<ref1@ex.com>", "<ref2@ex.com>"]
        db.insert_email(email)
        row = db.conn.execute("SELECT references_json FROM emails").fetchone()
        parsed = json.loads(row["references_json"])
        assert parsed == ["<ref1@ex.com>", "<ref2@ex.com>"]
        db.close()

    def test_empty_categories_is_valid_json(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        row = db.conn.execute("SELECT categories FROM emails").fetchone()
        parsed = json.loads(row["categories"])
        assert parsed == []
        db.close()

    def test_priority_stored_as_integer(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        row = db.conn.execute("SELECT priority, typeof(priority) AS t FROM emails").fetchone()
        assert row["t"] == "integer"
        db.close()

    def test_batch_insert_uid_types(self):
        """Batch-inserted UIDs should all be strings."""
        db = EmailDatabase(":memory:")
        emails = [_make_email(message_id=f"<m{i}@ex.com>") for i in range(3)]
        inserted = db.insert_emails_batch(emails)
        assert all(isinstance(uid, str) for uid in inserted)
        db.close()


# =====================================================================
# 5. Foreign key enforcement
# =====================================================================


class TestForeignKeys:
    """Verify PRAGMA foreign_keys=ON is active."""

    def test_foreign_keys_enabled(self):
        db = EmailDatabase(":memory:")
        row = db.conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1
        db.close()

    def test_recipient_fk_enforced(self):
        """Inserting a recipient with a non-existent email_uid should fail."""
        db = EmailDatabase(":memory:")
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO recipients (email_uid, address, type) VALUES ('nonexistent_uid', 'test@example.com', 'to')"
            )
        db.close()

    def test_entity_mention_fk_enforced(self):
        """entity_mentions.email_uid must reference an existing email."""
        db = EmailDatabase(":memory:")
        # First insert an entity
        db.conn.execute("INSERT INTO entities (entity_text, entity_type, normalized_form) VALUES ('Test', 'person', 'test')")
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute("INSERT INTO entity_mentions (entity_id, email_uid) VALUES (1, 'nonexistent_uid')")
        db.close()

    def test_evidence_fk_enforced(self):
        """evidence_items.email_uid must reference an existing email."""
        db = EmailDatabase(":memory:")
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO evidence_items (email_uid, category, key_quote, summary, relevance) "
                "VALUES ('nonexistent_uid', 'general', 'quote', 'summary', 3)"
            )
        db.close()

    def test_attachment_fk_enforced(self):
        """attachments.email_uid must reference an existing email."""
        db = EmailDatabase(":memory:")
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute("INSERT INTO attachments (email_uid, name) VALUES ('nonexistent_uid', 'file.pdf')")
        db.close()

    def test_email_categories_fk_enforced(self):
        """email_categories.email_uid must reference an existing email."""
        db = EmailDatabase(":memory:")
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute("INSERT INTO email_categories (email_uid, category) VALUES ('nonexistent_uid', 'Red')")
        db.close()


# =====================================================================
# 6. Ingest pipeline write ordering
# =====================================================================


class TestPipelineWriteOrdering:
    """Verify SQLite is written before ChromaDB in _process_batch."""

    def test_sqlite_before_chromadb(self):
        """If SQLite insert fails, ChromaDB add_chunks should not be called."""
        call_order = []

        class FakeEmbedder:
            def add_chunks(self, chunks, batch_size=500):
                call_order.append("chromadb")
                return len(chunks)

        class FakeDB:
            conn = None

            def insert_emails_batch(self, emails, ingestion_run_id=None):
                call_order.append("sqlite")
                raise RuntimeError("SQLite failure")

        from src.ingest import _EmbedPipeline

        pipeline = _EmbedPipeline(
            embedder=FakeEmbedder(),
            email_db=FakeDB(),
            entity_extractor_fn=None,
            batch_size=100,
        )
        with pytest.raises(RuntimeError, match="SQLite failure"):
            pipeline._process_batch(["chunk1"], ["email1"])

        # SQLite was attempted, but ChromaDB was NOT called
        assert call_order == ["sqlite"]
