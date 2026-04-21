"""Tests for the SQLite EmailDatabase."""

from src.email_db import EmailDatabase, _parse_address
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
        "body_text": "Test body",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


class TestParseAddress:
    def test_name_and_email(self):
        assert _parse_address("Alice <alice@example.com>") == ("Alice", "alice@example.com")

    def test_quoted_name(self):
        assert _parse_address('"Alice B" <alice@example.com>') == ("Alice B", "alice@example.com")

    def test_bare_email(self):
        assert _parse_address("alice@example.com") == ("", "alice@example.com")

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

        sender = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'alice@example.com'").fetchone()
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
        db.insert_email(_make_email(message_id="<m1@ex.com>", date="2024-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@ex.com>", date="2024-06-01T00:00:00"))

        sender = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'alice@example.com'").fetchone()
        assert sender["sent_count"] == 2
        assert sender["first_seen"] == "2024-01-01T00:00:00"
        assert sender["last_seen"] == "2024-06-01T00:00:00"
        db.close()

    def test_communication_edges(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>"))
        db.insert_email(_make_email(message_id="<m2@ex.com>"))

        edge = db.conn.execute("SELECT * FROM communication_edges WHERE sender_email='alice@example.com'").fetchone()
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
        db.insert_email(_make_email(message_id="<m1@ex.com>"))
        db.insert_email(_make_email(message_id="<m2@ex.com>"))
        db.insert_email(
            _make_email(
                message_id="<m3@ex.com>",
                sender_email="eve@example.com",
                sender_name="Eve",
            )
        )
        senders = db.top_senders(limit=10)
        assert senders[0]["sender_email"] == "alice@example.com"
        assert senders[0]["message_count"] == 2
        assert senders[1]["sender_email"] == "eve@example.com"
        db.close()

    def test_date_range(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>", date="2023-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@ex.com>", date="2024-12-31T23:59:59"))
        min_d, max_d = db.date_range()
        assert min_d == "2023-01-01T00:00:00"
        assert max_d == "2024-12-31T23:59:59"
        db.close()

    def test_folder_counts(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>", folder="Inbox"))
        db.insert_email(_make_email(message_id="<m2@ex.com>", folder="Inbox"))
        db.insert_email(_make_email(message_id="<m3@ex.com>", folder="Sent"))
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
            _make_email(message_id="<m1@ex.com>"),
            _make_email(message_id="<m2@ex.com>"),
            _make_email(message_id="<m3@ex.com>"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 3
        assert db.email_count() == 3
        db.close()

    def test_batch_skips_duplicates(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>"))
        emails = [
            _make_email(message_id="<m1@ex.com>"),  # duplicate
            _make_email(message_id="<m2@ex.com>"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 1
        assert db.email_count() == 2
        db.close()

    def test_unique_sender_count(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>"))
        db.insert_email(_make_email(message_id="<m2@ex.com>", sender_email="bob@example.com"))
        assert db.unique_sender_count() == 2
        db.close()

    def test_batch_insert_contact_accumulation(self):
        """Batch insert should accumulate sent_count correctly for repeated senders."""
        db = EmailDatabase(":memory:")
        emails = [
            _make_email(message_id="<m1@ex.com>", date="2024-01-01T00:00:00"),
            _make_email(message_id="<m2@ex.com>", date="2024-06-01T00:00:00"),
            _make_email(message_id="<m3@ex.com>", date="2024-03-01T00:00:00"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 3

        sender = db.conn.execute("SELECT * FROM contacts WHERE email_address = 'alice@example.com'").fetchone()
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
            _make_email(message_id="<m1@ex.com>", date="2024-01-01T00:00:00"),
            _make_email(message_id="<m2@ex.com>", date="2024-06-01T00:00:00"),
        ]
        inserted = db.insert_emails_batch(emails)
        assert len(inserted) == 2

        edge = db.conn.execute("SELECT * FROM communication_edges WHERE sender_email='alice@example.com'").fetchone()
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


class TestNetworkQueries:
    def test_top_contacts(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>", to=["Bob <bob@example.com>"]))
        db.insert_email(_make_email(message_id="<m2@ex.com>", to=["Bob <bob@example.com>"]))
        db.insert_email(_make_email(message_id="<m3@ex.com>", to=["Carol <carol@example.com>"]))
        contacts = db.top_contacts("alice@example.com", limit=10)
        assert contacts[0]["partner"] == "bob@example.com"
        assert contacts[0]["total"] == 2
        assert contacts[1]["partner"] == "carol@example.com"
        db.close()

    def test_top_contacts_empty(self):
        db = EmailDatabase(":memory:")
        assert db.top_contacts("nobody@example.com") == []
        db.close()

    def test_communication_between(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>", to=["Bob <bob@example.com>"]))
        db.insert_email(
            _make_email(
                message_id="<m2@ex.com>",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <alice@example.com>"],
            )
        )
        result = db.communication_between("alice@example.com", "bob@example.com")
        assert result["a_to_b"] == 1
        assert result["b_to_a"] == 1
        assert result["total"] == 2
        db.close()

    def test_communication_between_no_relationship(self):
        db = EmailDatabase(":memory:")
        result = db.communication_between("a@example.com", "b@example.com")
        assert result["total"] == 0
        db.close()

    def test_all_edges(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>", to=["Bob <bob@example.com>"]))
        edges = db.all_edges()
        assert len(edges) == 1
        assert edges[0] == ("alice@example.com", "bob@example.com", 1)
        db.close()


class TestTemporalQueries:
    def test_email_dates(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>", date="2024-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@ex.com>", date="2024-06-01T00:00:00"))
        dates = db.email_dates()
        assert len(dates) == 2
        db.close()

    def test_email_dates_filtered(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@ex.com>", date="2024-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@ex.com>", date="2024-06-01T00:00:00"))
        dates = db.email_dates(date_from="2024-03-01")
        assert len(dates) == 1
        db.close()

    def test_response_pairs(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<orig@ex.com>",
                date="2024-01-01T10:00:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<reply@ex.com>",
                subject="RE: Hello",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <alice@example.com>"],
                in_reply_to="<orig@ex.com>",
                date="2024-01-01T11:00:00",
            )
        )
        pairs = db.response_pairs()
        assert len(pairs) == 1
        assert pairs[0]["reply_sender"] == "bob@example.com"
        assert pairs[0]["original_sender"] == "alice@example.com"
        db.close()

    def test_response_pairs_with_limit(self):
        """response_pairs should accept int limit without type error."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<orig@ex.com>",
                date="2024-01-01T10:00:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<reply@ex.com>",
                subject="RE: Hello",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <alice@example.com>"],
                in_reply_to="<orig@ex.com>",
                date="2024-01-01T11:00:00",
            )
        )
        pairs = db.response_pairs(limit=5)
        assert len(pairs) == 1
        db.close()


class TestEntityOperations:
    def test_insert_and_search(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email())
        email = _make_email()
        entities = [
            ("acme.com", "organization", "acme.com"),
            ("https://example.com", "url", "https://example.com"),
        ]
        db.insert_entities_batch(email.uid, entities)

        results = db.search_by_entity("acme", entity_type="organization")
        assert len(results) == 1
        assert results[0]["entity_text"] == "acme.com"

    def test_top_entities(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<m1@ex.com>")
        e2 = _make_email(message_id="<m2@ex.com>")
        db.insert_email(e1)
        db.insert_email(e2)
        db.insert_entities_batch(e1.uid, [("acme.com", "organization", "acme.com")])
        db.insert_entities_batch(e2.uid, [("acme.com", "organization", "acme.com")])

        top = db.top_entities(entity_type="organization")
        assert top[0]["entity_text"] == "acme.com"
        assert top[0]["email_count"] == 2

    def test_co_occurrences(self):
        db = EmailDatabase(":memory:")
        email = _make_email()
        db.insert_email(email)
        db.insert_entities_batch(
            email.uid,
            [
                ("acme.com", "organization", "acme.com"),
                ("https://example.org/page", "url", "https://example.org/page"),
            ],
        )
        co = db.entity_co_occurrences("acme.com")
        assert len(co) == 1
        assert co[0]["entity_type"] == "url"
        db.close()


# ── Schema v7: categories, calendar, attachments, references ──


class TestSchemaV7:
    def test_migration_adds_new_columns(self):
        db = EmailDatabase(":memory:")
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()}
        assert "categories" in cols
        assert "thread_topic" in cols
        assert "inference_classification" in cols
        assert "is_calendar_message" in cols
        assert "references_json" in cols
        db.close()

    def test_migration_creates_new_tables(self):
        db = EmailDatabase(":memory:")
        tables = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "attachments" in tables
        assert "email_categories" in tables
        db.close()

    def test_insert_populates_categories(self):
        db = EmailDatabase(":memory:")
        email = _make_email(categories=["Meeting", "Finance"])
        db.insert_email(email)
        cats = db.category_counts()
        assert len(cats) == 2
        names = {c["category"] for c in cats}
        assert "Meeting" in names
        assert "Finance" in names
        db.close()

    def test_emails_by_category(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<m1>", categories=["Finance"])
        e2 = _make_email(message_id="<m2>", categories=["HR"])
        db.insert_email(e1)
        db.insert_email(e2)
        finance = db.emails_by_category("Finance")
        assert len(finance) == 1
        assert finance[0]["uid"] == e1.uid
        db.close()

    def test_insert_populates_attachments_table(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["doc.pdf"],
            attachments=[
                {"name": "doc.pdf", "mime_type": "application/pdf", "size": 1000, "content_id": "", "is_inline": False},
                {"name": "logo.png", "mime_type": "image/png", "size": 500, "content_id": "cid123", "is_inline": True},
            ],
        )
        db.insert_email(email)
        atts = db.attachments_for_email(email.uid)
        assert len(atts) == 2
        assert atts[0]["name"] == "doc.pdf"
        assert atts[0]["is_inline"] == 0
        assert atts[1]["content_id"] == "cid123"
        assert atts[1]["is_inline"] == 1
        db.close()

    def test_insert_populates_attachment_evidence_fields(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["scan.pdf"],
            attachments=[
                {
                    "name": "scan.pdf",
                    "mime_type": "application/pdf",
                    "size": 1000,
                    "content_id": "",
                    "is_inline": False,
                    "extraction_state": "ocr_text_extracted",
                    "evidence_strength": "strong_text",
                    "ocr_used": True,
                    "failure_reason": None,
                    "text_preview": "Scanned invoice total: 123.45 EUR",
                }
            ],
        )
        db.insert_email(email)
        atts = db.attachments_for_email(email.uid)
        assert len(atts) == 1
        assert atts[0]["extraction_state"] == "ocr_text_extracted"
        assert atts[0]["evidence_strength"] == "strong_text"
        assert atts[0]["ocr_used"] == 1
        assert atts[0]["failure_reason"] in (None, "")
        assert atts[0]["text_preview"] == "Scanned invoice total: 123.45 EUR"
        db.close()

    def test_calendar_emails(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<cal1>", is_calendar_message=True, date="2025-01-10T10:00:00")
        e2 = _make_email(message_id="<cal2>", is_calendar_message=False, date="2025-01-11T10:00:00")
        db.insert_email(e1)
        db.insert_email(e2)
        cals = db.calendar_emails()
        assert len(cals) == 1
        assert cals[0]["uid"] == e1.uid
        db.close()

    def test_references_json_stored(self):
        db = EmailDatabase(":memory:")
        email = _make_email(references=["ref1@example.com", "ref2@example.com"])
        db.insert_email(email)
        full = db.get_email_full(email.uid)
        assert full["references"] == ["ref1@example.com", "ref2@example.com"]
        db.close()

    def test_thread_by_references(self):
        db = EmailDatabase(":memory:")
        email = _make_email(references=["root@example.com", "parent@example.com"])
        db.insert_email(email)
        found = db.thread_by_references("root@example.com")
        assert len(found) == 1
        assert found[0]["uid"] == email.uid
        db.close()

    def test_thread_by_topic(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<t1>", thread_topic="Budget Q4")
        e2 = _make_email(message_id="<t2>", thread_topic="Budget Q4")
        e3 = _make_email(message_id="<t3>", thread_topic="Other")
        db.insert_email(e1)
        db.insert_email(e2)
        db.insert_email(e3)
        found = db.thread_by_topic("Budget Q4")
        assert len(found) == 2
        db.close()

    def test_batch_insert_populates_v7_fields(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(
            message_id="<b1>",
            categories=["Important"],
            is_calendar_message=True,
            references=["r1@example.com"],
            attachments=[{"name": "a.txt", "mime_type": "text/plain", "size": 100, "content_id": "", "is_inline": False}],
        )
        inserted = db.insert_emails_batch([e1])
        assert len(inserted) == 1
        cats = db.category_counts()
        assert len(cats) == 1
        atts = db.attachments_for_email(e1.uid)
        assert len(atts) == 1
        full = db.get_email_full(e1.uid)
        assert full["is_calendar_message"] == 1
        assert full["references"] == ["r1@example.com"]
        db.close()

    def test_get_email_full_includes_attachments(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["report.pdf"],
            attachments=[
                {"name": "report.pdf", "mime_type": "application/pdf", "size": 2000, "content_id": "", "is_inline": False},
            ],
        )
        db.insert_email(email)
        full = db.get_email_full(email.uid)
        assert "attachments" in full
        assert len(full["attachments"]) == 1
        assert full["attachments"][0]["name"] == "report.pdf"
        db.close()

    def test_get_email_for_reembed_populates_attachments(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["report.pdf"],
            attachments=[
                {"name": "report.pdf", "mime_type": "application/pdf", "size": 2000, "content_id": "", "is_inline": False},
            ],
        )
        db.insert_email(email)
        result = db.get_email_for_reembed(email.uid)
        assert result is not None
        assert result["attachment_names"] == ["report.pdf"]
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["name"] == "report.pdf"
        db.close()


class TestSchemaV9:
    def test_migration_adds_ingestion_run_id_column(self):
        db = EmailDatabase(":memory:")
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()}
        assert "ingestion_run_id" in cols
        db.close()

    def test_batch_insert_stores_ingestion_run_id(self):
        db = EmailDatabase(":memory:")
        run_id = db.record_ingestion_start("test.olm")
        db.record_ingestion_complete(run_id, {"emails_parsed": 1, "emails_inserted": 1})
        emails = [_make_email(message_id="<run1@ex.com>")]
        db.insert_emails_batch(emails, ingestion_run_id=run_id)
        row = db.conn.execute(
            "SELECT ingestion_run_id FROM emails WHERE uid = ?",
            (emails[0].uid,),
        ).fetchone()
        assert row["ingestion_run_id"] == run_id
        db.close()

    def test_batch_insert_without_run_id(self):
        db = EmailDatabase(":memory:")
        emails = [_make_email(message_id="<norun@ex.com>")]
        db.insert_emails_batch(emails)
        row = db.conn.execute(
            "SELECT ingestion_run_id FROM emails WHERE uid = ?",
            (emails[0].uid,),
        ).fetchone()
        assert row["ingestion_run_id"] is None
        db.close()


class TestSchemaV8:
    def test_migration_adds_analytics_columns(self):
        db = EmailDatabase(":memory:")
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()}
        assert "detected_language" in cols
        assert "sentiment_label" in cols
        assert "sentiment_score" in cols
        db.close()

    def test_update_analytics_batch(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<a1@ex.com>"))
        db.insert_email(_make_email(message_id="<a2@ex.com>", sender_email="bob@example.com"))
        e1_uid = _make_email(message_id="<a1@ex.com>").uid
        e2_uid = _make_email(message_id="<a2@ex.com>", sender_email="bob@example.com").uid
        updated = db.update_analytics_batch(
            [
                ("en", "positive", 0.8, e1_uid),
                ("de", "neutral", 0.0, e2_uid),
            ]
        )
        assert updated == 2
        row = db.conn.execute(
            "SELECT detected_language, sentiment_label, sentiment_score FROM emails WHERE uid=?",
            (e1_uid,),
        ).fetchone()
        assert row["detected_language"] == "en"
        assert row["sentiment_label"] == "positive"
        assert abs(row["sentiment_score"] - 0.8) < 0.01
        db.close()


class TestAttachmentQueries:
    def _make_db_with_attachments(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(
            message_id="<a1@ex.com>",
            has_attachments=True,
            attachments=[
                {"name": "report.pdf", "mime_type": "application/pdf", "size": 5000, "content_id": "", "is_inline": False},
                {
                    "name": "budget.xlsx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size": 12000,
                    "content_id": "",
                    "is_inline": False,
                },
            ],
        )
        e2 = _make_email(
            message_id="<a2@ex.com>",
            sender_email="bob@example.com",
            sender_name="Bob",
            has_attachments=True,
            attachments=[
                {"name": "slides.pdf", "mime_type": "application/pdf", "size": 8000, "content_id": "", "is_inline": False},
            ],
        )
        e3 = _make_email(message_id="<a3@ex.com>", has_attachments=False)
        db.insert_email(e1)
        db.insert_email(e2)
        db.insert_email(e3)
        return db

    def test_attachment_stats_empty(self):
        db = EmailDatabase(":memory:")
        stats = db.attachment_stats()
        assert stats["total_attachments"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["emails_with_attachments"] == 0
        db.close()

    def test_attachment_stats_with_data(self):
        db = self._make_db_with_attachments()
        stats = db.attachment_stats()
        assert stats["total_attachments"] == 3
        assert stats["total_size_bytes"] == 25000
        assert stats["emails_with_attachments"] == 2
        assert len(stats["by_extension"]) > 0
        assert len(stats["top_filenames"]) > 0
        db.close()

    def test_attachment_stats_extension_includes_dot(self):
        """Extension extraction SQL should include the leading dot."""
        db = self._make_db_with_attachments()
        stats = db.attachment_stats()
        extensions = {e["extension"] for e in stats["by_extension"]}
        # All non-empty extensions should start with '.'
        for ext in extensions:
            if ext:
                assert ext.startswith("."), f"Extension '{ext}' missing leading dot"
        assert ".pdf" in extensions
        assert ".xlsx" in extensions
        db.close()

    def test_list_attachments_no_filter(self):
        db = self._make_db_with_attachments()
        result = db.list_attachments()
        assert result["total"] == 3
        assert len(result["attachments"]) == 3
        db.close()

    def test_list_attachments_filter_extension(self):
        db = self._make_db_with_attachments()
        result = db.list_attachments(extension="pdf")
        assert result["total"] == 2
        assert all("pdf" in a["name"].lower() for a in result["attachments"])
        db.close()

    def test_list_attachments_filter_sender(self):
        db = self._make_db_with_attachments()
        result = db.list_attachments(sender="bob")
        assert result["total"] == 1
        assert result["attachments"][0]["name"] == "slides.pdf"
        db.close()

    def test_search_emails_by_attachment_filename(self):
        db = self._make_db_with_attachments()
        results = db.search_emails_by_attachment(filename="report")
        assert len(results) == 1
        assert "report.pdf" in results[0]["matching_attachments"]
        db.close()

    def test_search_emails_by_attachment_extension(self):
        db = self._make_db_with_attachments()
        results = db.search_emails_by_attachment(extension="pdf")
        assert len(results) == 2
        db.close()


class TestGetEmailsFullBatch:
    def test_returns_all(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(
            message_id="<b1@ex.com>",
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
            has_attachments=True,
            attachments=[{"name": "f1.pdf", "mime_type": "application/pdf", "size": 100, "content_id": "", "is_inline": False}],
        )
        e2 = _make_email(
            message_id="<b2@ex.com>",
            sender_email="bob@example.com",
            to=["Alice <alice@example.com>"],
        )
        e3 = _make_email(
            message_id="<b3@ex.com>",
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
        e1 = _make_email(message_id="<b1@ex.com>")
        e2 = _make_email(message_id="<b2@ex.com>", sender_email="bob@example.com")
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
            message_id="<t1@ex.com>",
            conversation_id=conv_id,
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
            date="2024-01-01T10:00:00",
        )
        e2 = _make_email(
            message_id="<t2@ex.com>",
            sender_email="bob@example.com",
            sender_name="Bob",
            conversation_id=conv_id,
            to=["Alice <alice@example.com>"],
            bcc=["Dave <dave@example.com>"],
            date="2024-01-01T11:00:00",
        )
        e3 = _make_email(
            message_id="<t3@ex.com>",
            sender_email="carol@example.com",
            sender_name="Carol",
            conversation_id=conv_id,
            to=["Alice <alice@example.com>", "Bob <bob@example.com>"],
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
        e1 = _make_email(message_id="<s1@ex.com>", subject="Re: Hello", body_text="Body one")
        e2 = _make_email(message_id="<s2@ex.com>", subject="Re: Hello", body_text="Body two")
        db.insert_email(e1)
        db.insert_email(e2)
        results = db.emails_by_base_subject(min_group_size=2)
        assert len(results) >= 1
        _subject, emails = results[0]
        bodies = [body for _, body in emails]
        assert "Body one" in bodies
        assert "Body two" in bodies
        db.close()


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


class TestUpdateV7IsInline:
    def test_is_inline_uses_field_not_content_id(self):
        """is_inline should come from the attachment's is_inline field,
        not from bool(content_id)."""
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachments=[
                {
                    "name": "logo.png",
                    "mime_type": "image/png",
                    "size": 100,
                    "content_id": "cid:logo@example.com",
                    "is_inline": False,
                },
            ],
        )
        db.insert_email(email)
        # Now simulate update_v7_metadata with the same attachment
        db.update_v7_metadata(email)
        row = db.conn.execute("SELECT is_inline FROM attachments WHERE email_uid = ?", (email.uid,)).fetchone()
        # Despite having content_id, is_inline should be 0 because is_inline=False
        assert row["is_inline"] == 0
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


class TestAttachmentStatsMultiDotExtension:
    def test_multi_dot_filename_extracts_last_extension(self):
        """Filenames like 'report.v2.pdf' should extract '.pdf', not '.v2.pdf'."""
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachments=[
                {"name": "my.report.v2.pdf", "mime_type": "application/pdf", "size": 1000, "content_id": "", "is_inline": False},
                {"name": "backup.tar.gz", "mime_type": "application/gzip", "size": 2000, "content_id": "", "is_inline": False},
            ],
        )
        db.insert_email(email)
        stats = db.attachment_stats()
        extensions = {e["extension"] for e in stats["by_extension"]}
        assert ".pdf" in extensions
        assert ".gz" in extensions
        # Should NOT contain the wrong multi-dot extractions
        assert ".v2.pdf" not in extensions
        assert ".tar.gz" not in extensions
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
            message_id="<msg_1@test.com>",
            references=["<ref_abc@test.com>"],
        )
        e2 = _make_email(
            message_id="<msg_2@test.com>",
            references=["<refXabc@test.com>"],
        )
        db.insert_email(e1)
        db.insert_email(e2)
        results = db.thread_by_references("<ref_abc@test.com>")
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
            references=["<ref1@test.com>"],
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
        assert "<ref1@test.com>" in e["references"]
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
            references=["<ref1@test.com>"],
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
        assert "<ref1@test.com>" in item["references"]
        assert len(item["attachments"]) == 1
        assert item["attachments"][0]["name"] == "doc.pdf"
        assert "references_json" not in item
        db.close()


class TestGetEmailFullNoJsonLeak:
    """get_email_full and get_emails_full_batch should not leak references_json."""

    def test_get_email_full_no_references_json_key(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email(references=["<ref1@test.com>"])
        db.insert_email(email)
        result = db.get_email_full(email.uid)
        assert "references" in result
        assert isinstance(result["references"], list)
        assert "references_json" not in result
        db.close()

    def test_get_emails_full_batch_no_references_json_key(self, tmp_path):
        db = EmailDatabase(tmp_path / "test.db")
        email = _make_email(references=["<ref1@test.com>"])
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
