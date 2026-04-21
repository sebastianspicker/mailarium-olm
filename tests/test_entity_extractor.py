"""Tests for entity extraction."""

from src.email_db import EmailDatabase
from src.entity_extractor import extract_entities
from src.parse_olm import Email


class TestExtractEntities:
    def test_extract_urls(self):
        entities = extract_entities("Visit https://example.com/page and http://test.org")
        urls = [e for e in entities if e.entity_type == "url"]
        assert len(urls) == 2
        assert any("example.com" in e.normalized_form for e in urls)

    def test_extract_emails(self):
        entities = extract_entities("Contact alice@example.com for details")
        emails = [e for e in entities if e.entity_type == "email"]
        assert len(emails) == 1
        assert emails[0].normalized_form == "alice@example.com"

    def test_extract_phone_german(self):
        entities = extract_entities("Call +49 89 1234567 or 089/1234567")
        phones = [e for e in entities if e.entity_type == "phone"]
        assert len(phones) >= 1

    def test_extract_phone_international(self):
        entities = extract_entities("Phone: +1 555-123-4567")
        phones = [e for e in entities if e.entity_type == "phone"]
        assert len(phones) == 1

    def test_extract_phone_min_digits(self):
        # Less than 7 digits should not match
        entities = extract_entities("Code: 12345")
        phones = [e for e in entities if e.entity_type == "phone"]
        assert len(phones) == 0

    def test_extract_mentions(self):
        entities = extract_entities("Thanks @alice and @bob_smith")
        mentions = [e for e in entities if e.entity_type == "mention"]
        assert len(mentions) == 2

    def test_extract_organization_from_sender(self):
        entities = extract_entities("Hello", sender_email="john@acme-corp.com")
        orgs = [e for e in entities if e.entity_type == "organization"]
        assert len(orgs) == 1
        assert orgs[0].normalized_form == "acme-corp.com"

    def test_common_providers_excluded(self):
        entities = extract_entities("Hello", sender_email="john@gmail.com")
        orgs = [e for e in entities if e.entity_type == "organization"]
        assert len(orgs) == 0

    def test_gmx_excluded(self):
        entities = extract_entities("Hello", sender_email="user@gmx.de")
        orgs = [e for e in entities if e.entity_type == "organization"]
        assert len(orgs) == 0

    def test_extract_url_with_balanced_parens(self):
        """Wikipedia-style URLs with balanced parens should be preserved."""
        entities = extract_entities("See https://en.wikipedia.org/wiki/Test_(foo) for details")
        urls = [e for e in entities if e.entity_type == "url"]
        assert len(urls) == 1
        assert urls[0].text == "https://en.wikipedia.org/wiki/Test_(foo)"

    def test_extract_url_strips_unbalanced_trailing_paren(self):
        """Trailing paren from surrounding text (unbalanced) should be stripped."""
        entities = extract_entities("(see https://example.com/page)")
        urls = [e for e in entities if e.entity_type == "url"]
        assert len(urls) == 1
        assert urls[0].text == "https://example.com/page"

    def test_extract_url_nested_parens(self):
        """URL with multiple balanced parens should be preserved."""
        entities = extract_entities("Check https://example.com/a(b)c(d) now")
        urls = [e for e in entities if e.entity_type == "url"]
        assert len(urls) == 1
        assert urls[0].text == "https://example.com/a(b)c(d)"

    def test_deduplication(self):
        entities = extract_entities("Visit https://example.com and https://example.com again")
        urls = [e for e in entities if e.entity_type == "url"]
        assert len(urls) == 1

    def test_empty_input(self):
        assert extract_entities("") == []
        assert extract_entities("", sender_email="x@y.com") == []

    def test_no_sender(self):
        entities = extract_entities("Hello world")
        orgs = [e for e in entities if e.entity_type == "organization"]
        assert len(orgs) == 0

    def test_phone_regex_skips_date_strings(self):
        """Date patterns like 2024-01-15 should not be extracted as phone numbers."""
        entities = extract_entities("Meeting on 2024-01-15 at the office")
        phones = [e for e in entities if e.entity_type == "phone"]
        assert len(phones) == 0

    def test_phone_regex_skips_slash_date(self):
        entities = extract_entities("Due date: 15/01/2024")
        phones = [e for e in entities if e.entity_type == "phone"]
        assert len(phones) == 0

    def test_phone_regex_skips_dot_date(self):
        entities = extract_entities("Deadline: 15.01.2024")
        phones = [e for e in entities if e.entity_type == "phone"]
        assert len(phones) == 0

    def test_phone_regex_still_matches_real_phones(self):
        """Real phone numbers should still be extracted after date exclusion."""
        entities = extract_entities("Call +49 89 1234567 about 2024-01-15 meeting")
        phones = [e for e in entities if e.entity_type == "phone"]
        assert len(phones) >= 1


class TestEntitySQLiteRoundtrip:
    def _make_email(self, **overrides) -> Email:
        defaults = {
            "message_id": "<msg1@example.com>",
            "subject": "Hello",
            "sender_name": "Alice",
            "sender_email": "alice@acme.com",
            "to": ["Bob <bob@example.com>"],
            "cc": [],
            "bcc": [],
            "date": "2024-01-15T10:30:00",
            "body_text": "Visit https://acme.com or call +49 89 1234567",
            "body_html": "",
            "folder": "Inbox",
            "has_attachments": False,
        }
        defaults.update(overrides)
        return Email(**defaults)

    def test_insert_and_search(self):
        db = EmailDatabase(":memory:")
        email = self._make_email()
        db.insert_email(email)

        entities = extract_entities(email.clean_body, email.sender_email)
        tuples = [(e.text, e.entity_type, e.normalized_form) for e in entities]
        db.insert_entities_batch(email.uid, tuples)

        results = db.search_by_entity("acme", entity_type="organization")
        assert len(results) >= 1

    def test_top_entities(self):
        db = EmailDatabase(":memory:")
        e1 = self._make_email(message_id="<m1@ex.com>")
        e2 = self._make_email(message_id="<m2@ex.com>")
        db.insert_email(e1)
        db.insert_email(e2)

        for email in [e1, e2]:
            entities = extract_entities(email.clean_body, email.sender_email)
            tuples = [(e.text, e.entity_type, e.normalized_form) for e in entities]
            db.insert_entities_batch(email.uid, tuples)

        top = db.top_entities(entity_type="url")
        assert len(top) >= 1

    def test_co_occurrences(self):
        db = EmailDatabase(":memory:")
        email = self._make_email()
        db.insert_email(email)

        entities = extract_entities(email.clean_body, email.sender_email)
        tuples = [(e.text, e.entity_type, e.normalized_form) for e in entities]
        db.insert_entities_batch(email.uid, tuples)

        co = db.entity_co_occurrences("acme.com")
        assert len(co) >= 1
