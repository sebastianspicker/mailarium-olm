# ruff: noqa: F401
"""Tests for the SQLite EmailDatabase."""

from src.email_db import EmailDatabase, _parse_address
from src.parse_olm import Email

from .helpers.email_db_builders import _make_email


class TestNetworkQueries:
    def test_top_contacts(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>", to=["Bob <bob@example.com>"]))
        db.insert_email(_make_email(message_id="<m2@example.test>", to=["Bob <bob@example.com>"]))
        db.insert_email(_make_email(message_id="<m3@example.test>", to=["Carol <carol@example.com>"]))
        contacts = db.top_contacts("employee@example.test", limit=10)
        assert contacts[0]["partner"] == "bob@example.com"
        assert contacts[0]["total"] == 2
        assert contacts[1]["partner"] == "carol@example.com"
        db.close()

    def test_top_contacts_excludes_self_and_gmail_aliases(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<m1@example.test>",
                sender_email="alice@example.test",
                sender_name="Alice",
                to=["Alice Alias <alice@example.test>"],
            )
        )
        db.insert_email(
            _make_email(
                message_id="<m2@example.test>",
                sender_email="alice@example.test",
                sender_name="Alice",
                to=["Bob <bob@example.com>"],
            )
        )
        contacts = db.top_contacts("alice@example.test", limit=10)
        assert contacts == [{"partner": "bob@example.com", "total": 1}]
        db.close()

    def test_top_contacts_empty(self):
        db = EmailDatabase(":memory:")
        assert db.top_contacts("nobody@example.com") == []
        db.close()

    def test_communication_between(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>", to=["Bob <bob@example.com>"]))
        db.insert_email(
            _make_email(
                message_id="<m2@example.test>",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <employee@example.test>"],
            )
        )
        result = db.communication_between("employee@example.test", "bob@example.com")
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
        db.insert_email(_make_email(message_id="<m1@example.test>", to=["Bob <bob@example.com>"]))
        edges = db.all_edges()
        assert len(edges) == 1
        assert edges[0] == ("employee@example.test", "bob@example.com", 1)
        db.close()


class TestTemporalQueries:
    def test_email_dates(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>", date="2024-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@example.test>", date="2024-06-01T00:00:00"))
        dates = db.email_dates()
        assert len(dates) == 2
        db.close()

    def test_email_dates_filtered(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<m1@example.test>", date="2024-01-01T00:00:00"))
        db.insert_email(_make_email(message_id="<m2@example.test>", date="2024-06-01T00:00:00"))
        dates = db.email_dates(date_from="2024-03-01")
        assert len(dates) == 1
        db.close()

    def test_response_pairs(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<orig@example.test>",
                date="2024-01-01T10:00:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<reply@example.test>",
                subject="RE: Hello",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <employee@example.test>"],
                in_reply_to="<orig@example.test>",
                date="2024-01-01T11:00:00",
            )
        )
        pairs = db.response_pairs()
        assert len(pairs) == 1
        assert pairs[0]["reply_sender"] == "bob@example.com"
        assert pairs[0]["original_sender"] == "employee@example.test"
        db.close()

    def test_response_pairs_with_limit(self):
        """response_pairs should accept int limit without type error."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<orig@example.test>",
                date="2024-01-01T10:00:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<reply@example.test>",
                subject="RE: Hello",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <employee@example.test>"],
                in_reply_to="<orig@example.test>",
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
        e1 = _make_email(message_id="<m1@example.test>")
        e2 = _make_email(message_id="<m2@example.test>")
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
