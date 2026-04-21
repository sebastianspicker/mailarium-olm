"""Tests for NLP entity extraction with spaCy and regex fallback."""


# ── Extraction logic tests (mock spaCy) ──────────────────────


class _FakeEnt:
    """Minimal spaCy entity mock."""

    def __init__(self, text: str, label: str):
        self.text = text
        self.label_ = label


class _FakeDoc:
    """Minimal spaCy Doc mock."""

    def __init__(self, ents: list[_FakeEnt]):
        self.ents = ents


def _fake_nlp(text):
    """Fake spaCy nlp() that returns controlled entities."""
    return _FakeDoc(
        [
            _FakeEnt("John Smith", "PERSON"),
            _FakeEnt("Acme Corp", "ORG"),
            _FakeEnt("Berlin", "GPE"),
            _FakeEnt("$50,000", "MONEY"),
            _FakeEnt("CES 2024", "EVENT"),
            _FakeEnt("January 15", "DATE"),  # should be skipped
            _FakeEnt("3", "CARDINAL"),  # should be skipped
        ]
    )


def _setup_module_with_fake_nlp():
    """Reset and set up the nlp_entity_extractor module with a fake NLP model."""
    import src.nlp_entity_extractor as mod

    mod.reset_model_cache()
    mod._nlp_models["en"] = _fake_nlp
    mod._nlp_load_attempted = True
    return mod


class TestExtractSpacyEntities:
    def test_extracts_person(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("text about John Smith at Acme")
        people = [e for e in entities if e.entity_type == "person"]
        assert len(people) == 1
        assert people[0].text == "John Smith"
        assert people[0].normalized_form == "john smith"

    def test_extracts_organization(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("text about Acme Corp")
        orgs = [e for e in entities if e.entity_type == "organization"]
        assert len(orgs) == 1
        assert orgs[0].text == "Acme Corp"

    def test_extracts_location(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("meeting in Berlin")
        locs = [e for e in entities if e.entity_type == "location"]
        assert len(locs) == 1
        assert locs[0].text == "Berlin"

    def test_extracts_money(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("deal worth $50,000")
        money = [e for e in entities if e.entity_type == "money"]
        assert len(money) == 1
        assert money[0].text == "$50,000"

    def test_extracts_event(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("attending CES 2024")
        events = [e for e in entities if e.entity_type == "event"]
        assert len(events) == 1

    def test_skips_date_and_cardinal(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("January 15, item 3")
        types = {e.entity_type for e in entities}
        assert "date" not in types  # DATE skipped
        # No cardinal type in our schema

    def test_empty_text(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("")
        assert entities == []

    def test_short_text(self):
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_spacy_entities("Hi")
        assert entities == []

    def test_deduplication(self):
        """Duplicate entities are deduplicated by normalized form + type."""
        mod = _setup_module_with_fake_nlp()

        # Create a fake NLP that returns duplicates
        def _dup_nlp(text):
            return _FakeDoc(
                [
                    _FakeEnt("John Smith", "PERSON"),
                    _FakeEnt("john smith", "PERSON"),
                    _FakeEnt("JOHN SMITH", "PERSON"),
                ]
            )

        mod._nlp_models["en"] = _dup_nlp
        entities = mod.extract_spacy_entities("John Smith John Smith")
        people = [e for e in entities if e.entity_type == "person"]
        assert len(people) == 1

    def test_person_title_normalization(self):
        mod = _setup_module_with_fake_nlp()

        def _title_nlp(text):
            return _FakeDoc(
                [
                    _FakeEnt("Dr. Mueller", "PERSON"),
                    _FakeEnt("Prof. Johnson", "PERSON"),
                ]
            )

        mod._nlp_models["en"] = _title_nlp
        entities = mod.extract_spacy_entities("Dr. Mueller and Prof. Johnson")
        people = [e for e in entities if e.entity_type == "person"]
        assert len(people) == 2
        norms = {e.normalized_form for e in people}
        assert "mueller" in norms
        assert "johnson" in norms


# ── Fallback tests ───────────────────────────────────────────


class TestFallbackToRegex:
    def test_falls_back_when_spacy_unavailable(self):
        """extract_nlp_entities falls back to regex when spaCy is not available."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models.clear()
        mod._nlp_load_attempted = True

        entities = mod.extract_nlp_entities("Visit https://example.com", sender_email="john@example.test")
        types = {e.entity_type for e in entities}
        assert "url" in types
        assert "organization" in types

    def test_regex_only_no_person_entities(self):
        """Regex fallback does not produce person entities."""
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models.clear()
        mod._nlp_load_attempted = True

        entities = mod.extract_nlp_entities("John Smith from Acme discussed the deal")
        people = [e for e in entities if e.entity_type == "person"]
        assert len(people) == 0

    def test_is_spacy_available_returns_false(self):
        import src.nlp_entity_extractor as mod

        mod.reset_model_cache()
        mod._nlp_models.clear()
        mod._nlp_load_attempted = True
        assert mod.is_spacy_available() is False


# ── Merge tests ──────────────────────────────────────────────


class TestMergeSpacyAndRegex:
    def test_merge_combines_nlp_and_regex(self):
        """NLP entities (person, org) + regex entities (url, phone) are merged."""
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_nlp_entities(
            "John Smith from Acme Corp at https://acme.com called +49 89 1234567",
            sender_email="info@example.test",
        )
        types = {e.entity_type for e in entities}
        assert "person" in types  # from spaCy
        assert "url" in types  # from regex
        assert "phone" in types  # from regex

    def test_spacy_org_takes_priority_over_regex_domain(self):
        """When spaCy finds ORG, it appears alongside regex domain org."""
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_nlp_entities("Acme Corp", sender_email="john@example.test")
        orgs = [e for e in entities if e.entity_type == "organization"]
        # Should have spaCy "Acme Corp" and regex "acme-corp.com"
        assert len(orgs) >= 1
        org_norms = {e.normalized_form for e in orgs}
        assert "acme corp" in org_norms

    def test_no_duplicate_across_sources(self):
        """Same entity from spaCy and regex is deduplicated."""
        mod = _setup_module_with_fake_nlp()

        # Both spaCy and regex might find the same org
        def _overlap_nlp(text):
            return _FakeDoc(
                [
                    _FakeEnt("acme-corp.com", "ORG"),
                ]
            )

        mod._nlp_models["en"] = _overlap_nlp
        entities = mod.extract_nlp_entities("Hello", sender_email="john@example.test")
        orgs = [e for e in entities if e.entity_type == "organization"]
        # Should deduplicate by normalized form
        org_norms = [e.normalized_form for e in orgs]
        assert len(set(org_norms)) == len(org_norms)

    def test_empty_text_returns_empty(self):
        """Empty text returns no entities (regex returns [] for empty text)."""
        mod = _setup_module_with_fake_nlp()
        entities = mod.extract_nlp_entities("", sender_email="alice@example.test")
        # Regex extract_entities returns [] for empty text, so no entities
        assert entities == []


# ── DB query tests ───────────────────────────────────────────


class TestPeopleInEmails:
    def test_find_people(self):
        from src.email_db import EmailDatabase
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        email = Email(
            message_id="<m1@test>",
            subject="Meeting",
            sender_name="Alice",
            sender_email="alice@example.test",
            to=["bob@example.test"],
            cc=[],
            bcc=[],
            date="2024-01-15T10:00:00",
            body_text="Discussion with John Smith about the project",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
        db.insert_email(email)
        db.insert_entities_batch(
            email.uid,
            [
                ("John Smith", "person", "john smith"),
            ],
        )

        results = db.people_in_emails("john")
        assert len(results) == 1
        assert results[0]["person_name"] == "John Smith"
        assert results[0]["subject"] == "Meeting"

    def test_find_people_no_match(self):
        from src.email_db import EmailDatabase

        db = EmailDatabase(":memory:")
        results = db.people_in_emails("nonexistent")
        assert results == []

    def test_find_people_partial_match(self):
        from src.email_db import EmailDatabase
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        email = Email(
            message_id="<m2@test>",
            subject="Report",
            sender_name="Bob",
            sender_email="bob@example.test",
            to=["alice@example.test"],
            cc=[],
            bcc=[],
            date="2024-02-01T09:00:00",
            body_text="Dr. Mueller reviewed the report",
            body_html="",
            folder="Sent",
            has_attachments=False,
        )
        db.insert_email(email)
        db.insert_entities_batch(
            email.uid,
            [
                ("Dr. Mueller", "person", "mueller"),
            ],
        )

        results = db.people_in_emails("muel")
        assert len(results) == 1

    def test_find_people_respects_limit(self):
        from src.email_db import EmailDatabase
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        for i in range(5):
            email = Email(
                message_id=f"<m{i}@test>",
                subject=f"Email {i}",
                sender_name="Sender",
                sender_email="sender@example.test",
                to=["recv@example.test"],
                cc=[],
                bcc=[],
                date=f"2024-01-{i + 10:02d}T10:00:00",
                body_text="John Smith mentioned here",
                body_html="",
                folder="Inbox",
                has_attachments=False,
            )
            db.insert_email(email)
            db.insert_entities_batch(
                email.uid,
                [
                    ("John Smith", "person", "john smith"),
                ],
            )

        results = db.people_in_emails("john", limit=2)
        assert len(results) == 2


class TestEntityTimeline:
    def test_timeline_monthly(self):
        from src.email_db import EmailDatabase
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        dates = ["2024-01-15T10:00:00", "2024-01-20T11:00:00", "2024-02-10T09:00:00"]
        for i, date in enumerate(dates):
            email = Email(
                message_id=f"<t{i}@test>",
                subject=f"Email {i}",
                sender_name="Alice",
                sender_email="alice@example.test",
                to=["bob@example.test"],
                cc=[],
                bcc=[],
                date=date,
                body_text="Acme Corp mentioned",
                body_html="",
                folder="Inbox",
                has_attachments=False,
            )
            db.insert_email(email)
            db.insert_entities_batch(
                email.uid,
                [
                    ("Acme Corp", "organization", "acme corp"),
                ],
            )

        results = db.entity_timeline("acme", period="month")
        assert len(results) == 2
        assert results[0]["period"] == "2024-01"
        assert results[0]["count"] == 2
        assert results[1]["period"] == "2024-02"
        assert results[1]["count"] == 1

    def test_timeline_daily(self):
        from src.email_db import EmailDatabase
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        email = Email(
            message_id="<td1@test>",
            subject="Daily",
            sender_name="Alice",
            sender_email="alice@example.test",
            to=["bob@example.test"],
            cc=[],
            bcc=[],
            date="2024-03-15T10:00:00",
            body_text="Project Alpha update",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
        db.insert_email(email)
        db.insert_entities_batch(
            email.uid,
            [
                ("Project Alpha", "organization", "project alpha"),
            ],
        )

        results = db.entity_timeline("project alpha", period="day")
        assert len(results) == 1
        assert results[0]["period"] == "2024-03-15"

    def test_timeline_empty(self):
        from src.email_db import EmailDatabase

        db = EmailDatabase(":memory:")
        results = db.entity_timeline("nonexistent")
        assert results == []

    def test_timeline_weekly(self):
        from src.email_db import EmailDatabase
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        email = Email(
            message_id="<tw1@test>",
            subject="Weekly",
            sender_name="Alice",
            sender_email="alice@example.test",
            to=["bob@example.test"],
            cc=[],
            bcc=[],
            date="2024-03-15T10:00:00",
            body_text="Acme mentioned",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
        db.insert_email(email)
        db.insert_entities_batch(
            email.uid,
            [
                ("Acme", "organization", "acme"),
            ],
        )

        results = db.entity_timeline("acme", period="week")
        assert len(results) == 1
        assert "W" in results[0]["period"]


# ── MCP tool integration tests ───────────────────────────────


class TestMCPTools:
    def test_find_people_tool_importable(self):
        from src.tools import entities

        assert callable(entities.register)

    def test_entity_timeline_tool_importable(self):
        from src.tools import entities

        assert callable(entities.register)

    def test_entity_timeline_input_model(self):
        from src.mcp_models import EntityTimelineInput

        inp = EntityTimelineInput(entity="Acme", period="week")
        assert inp.entity == "Acme"
        assert inp.period == "week"

    def test_entity_timeline_input_default_period(self):
        from src.mcp_models import EntityTimelineInput

        inp = EntityTimelineInput(entity="Acme")
        assert inp.period == "month"
