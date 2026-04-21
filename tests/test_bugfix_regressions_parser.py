"""Parser and text-pipeline regression tests split out from the RF8 catch-all."""

from __future__ import annotations


class TestP1ISODatesNormalizedToUTC:
    """P1 fix #9: ISO dates with timezone info normalized to UTC."""

    def test_iso_date_with_positive_offset_normalized_to_utc(self):
        from src.rfc2822 import _normalize_date

        result = _normalize_date("2024-01-15T10:30:00+02:00")
        assert "+00:00" in result or result.endswith("Z") or "08:30:00" in result
        assert "2024-01-15" in result

    def test_iso_date_with_negative_offset_normalized_to_utc(self):
        from src.rfc2822 import _normalize_date

        result = _normalize_date("2024-01-15T10:30:00-05:00")
        assert "15:30:00" in result

    def test_iso_date_without_timezone_preserved(self):
        from src.rfc2822 import _normalize_date

        result = _normalize_date("2024-01-15T10:30:00")
        assert result == "2024-01-15T10:30:00"

    def test_rfc2822_date_normalized_to_utc(self):
        from src.rfc2822 import _normalize_date

        result = _normalize_date("Wed, 25 Jun 2025 10:52:47 +0200")
        assert "08:52:47" in result
        assert "+00:00" in result or result.endswith("Z")


class TestP1UnparseableDatesReturnEmpty:
    """P1 fix #10: unparseable dates return empty string."""

    def test_garbage_date_returns_empty(self):
        from src.rfc2822 import _normalize_date

        assert _normalize_date("not-a-date") == ""

    def test_partial_date_returns_empty(self):
        from src.rfc2822 import _normalize_date

        assert _normalize_date("Monday something") == ""


class TestP1ExtractPerDocumentAlignment:
    """P1 fix #16: extract_per_document alignment with empty docs."""

    def test_alignment_with_empty_documents(self):
        from src.keyword_extractor import KeywordExtractor

        extractor = KeywordExtractor(min_df=1)
        texts = [
            "",
            "Machine learning algorithms for prediction models training",
            "   ",
            "Database optimization and query performance tuning indexes",
        ]
        results = extractor.extract_per_document(texts, top_n=3)
        assert len(results) == 4
        assert results[0] == []
        assert results[2] == []
        assert len(results[1]) > 0
        assert len(results[3]) > 0
        kw1_texts = {kw for kw, _ in results[1]}
        kw3_texts = {kw for kw, _ in results[3]}
        assert kw1_texts != kw3_texts


class TestP2CalendarContentPreserved:
    """P2: Calendar content must not be lost when text/plain exists."""

    def test_multipart_plain_plus_calendar(self):
        from email.message import EmailMessage

        from src.rfc2822 import _extract_body_from_source

        msg = EmailMessage()
        msg.make_mixed()
        plain_part = EmailMessage()
        plain_part.set_content("Please see the meeting invite.", subtype="plain")
        cal_part = EmailMessage()
        cal_part.set_content(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Team Standup\nEND:VEVENT\nEND:VCALENDAR",
            subtype="calendar",
        )
        msg.attach(plain_part)
        msg.attach(cal_part)

        body_text, _ = _extract_body_from_source(msg.as_string())
        assert "meeting invite" in body_text.lower()
        assert "standup" in body_text.lower() or "calendar" in body_text.lower()


class TestP3SentenceSplitterEllipsis:
    """P3: Ellipsis (...) must not be treated as sentence boundary."""

    def test_ellipsis_not_split(self):
        from src.writing_analyzer import _split_sentences

        result = _split_sentences("I wonder... maybe not")
        assert len(result) == 1
        assert "wonder... maybe" in result[0]

    def test_normal_period_still_splits(self):
        from src.writing_analyzer import _split_sentences

        result = _split_sentences("First sentence. Second sentence.")
        assert len(result) == 2


class TestP3PhoneRegexNoIPFalsePositives:
    """P3: Phone regex must not match IP addresses."""

    def test_ip_address_not_extracted_as_phone(self):
        from src.entity_extractor import extract_entities

        entities = extract_entities("Server at 192.168.1.100 is down")
        phone_entities = [entity for entity in entities if entity.entity_type == "phone"]
        assert len(phone_entities) == 0

    def test_real_phone_still_extracted(self):
        from src.entity_extractor import extract_entities

        entities = extract_entities("Call me at +49 30 12345678")
        phone_entities = [entity for entity in entities if entity.entity_type == "phone"]
        assert len(phone_entities) >= 1
