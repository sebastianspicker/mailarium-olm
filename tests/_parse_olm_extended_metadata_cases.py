# ruff: noqa: F401
"""Extended tests for src/parse_olm.py — targeting uncovered lines."""

from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from src.olm_xml_helpers import (
    _detect_namespace,
    _extract_attachment_contents,
    _extract_attachment_field,
    _extract_html_body,
    _find,
    _find_text,
)
from src.parse_olm import (
    _NS_OUTLOOK,
    Email,
    _parse_email_xml,
    parse_olm,
)
from src.parse_olm_normalization import BODY_NORMALIZATION_VERSION

# ── Email.uid fallback (lines 98-99) ─────────────────────────


class TestParseOlmOversizedXml:
    def test_skip_oversized_xml_file(self, monkeypatch, tmp_path: Path):
        """Files exceeding MAX_XML_BYTES are skipped."""
        import src.parse_olm as mod

        archive = tmp_path / "oversized.olm"
        xml_content = (
            b'<?xml version="1.0"?>\n'
            b'<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">\n'
            b"  <OPFMessageCopySenderAddress>a@example.com"
            b"</OPFMessageCopySenderAddress>\n"
            b"  <OPFMessageCopySentTime>2023-01-01T00:00:00Z"
            b"</OPFMessageCopySentTime>\n"
            b"</email>"
        )
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(
                "Accounts/a/com.microsoft.__Messages/Inbox/big.xml",
                xml_content,
            )

        # Set limit to less than the XML size
        monkeypatch.setattr(mod, "MAX_XML_BYTES", 10)
        parsed = list(mod.parse_olm(str(archive)))
        assert len(parsed) == 0

    def test_max_total_xml_bytes_mid_stream_break(self, monkeypatch, tmp_path: Path):
        """Stop parsing when cumulative bytes exceed MAX_TOTAL_XML_BYTES (mid-read)."""
        import src.parse_olm as mod

        archive = tmp_path / "total_limit.olm"
        xml_template = (
            b'<?xml version="1.0"?>\n'
            b'<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">\n'
            b"  <OPFMessageCopySenderAddress>a@example.com"
            b"</OPFMessageCopySenderAddress>\n"
            b"  <OPFMessageCopySentTime>2023-01-01T00:00:00Z"
            b"</OPFMessageCopySentTime>\n"
            b"</email>"
        )
        with zipfile.ZipFile(archive, "w") as zf:
            for i in range(5):
                zf.writestr(
                    f"Accounts/a/com.microsoft.__Messages/Inbox/msg-{i}.xml",
                    xml_template,
                )

        # Allow individual files but limit total to roughly 1 file's worth
        monkeypatch.setattr(mod, "MAX_XML_BYTES", 50_000_000)
        monkeypatch.setattr(mod, "MAX_TOTAL_XML_BYTES", len(xml_template) + 10)
        parsed = list(mod.parse_olm(str(archive)))
        # Should parse just 1 file then stop on the second
        assert len(parsed) == 1


class TestParseOlmFileNotFound:
    def test_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            list(parse_olm("/nonexistent/archive.olm"))


class TestDetectNamespace:
    def test_detect_namespace_via_subject_tag(self):
        """Detect namespace when Subject element is present but SentTime is not."""
        xml = b"""<?xml version="1.0"?>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySubject>Test</OPFMessageCopySubject>
</email>"""
        root = etree.fromstring(xml)
        ns = _detect_namespace(root)
        assert ns == _NS_OUTLOOK

    def test_detect_no_namespace(self):
        xml = b"""<?xml version="1.0"?>
<email>
  <OPFMessageCopySubject>Test</OPFMessageCopySubject>
</email>"""
        root = etree.fromstring(xml)
        ns = _detect_namespace(root)
        assert ns == {}


class TestExtractAddressesNameOnly:
    def test_address_with_name_only_no_email(self):
        """When an address element has only a name, return name alone."""
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Name only test</OPFMessageCopySubject>
  <OPFMessageCopyToAddresses>
    <emailAddress>
      <OPFContactEmailAddressName>Just A Name</OPFContactEmailAddressName>
    </emailAddress>
  </OPFMessageCopyToAddresses>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert "Just A Name" in parsed.to


class TestExtractExchangeSmartLinks:
    def test_extracts_smart_links_with_attributes_and_children(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Links test</OPFMessageCopySubject>
  <OPFMessageGetExchangeExtractedSmartLinks>
    <link href="https://example.com">https://example.com/page</link>
    <link>
      <url>https://example.com/sub</url>
      <title>Example</title>
    </link>
  </OPFMessageGetExchangeExtractedSmartLinks>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        links = parsed.exchange_extracted_links
        assert len(links) == 2
        # First link has attribute + text
        assert links[0]["href"] == "https://example.com"
        assert links[0]["url"] == "https://example.com/page"
        # Second link has child elements
        assert links[1]["url"] == "https://example.com/sub"
        assert links[1]["title"] == "Example"


class TestExtractExchangeMeetings:
    def test_extracts_meetings_with_attributes_and_children(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Meeting test</OPFMessageCopySubject>
  <OPFMessageGetExchangeExtractedMeetings>
    <meeting status="accepted">
      <subject>Standup</subject>
      <location>Room 42</location>
    </meeting>
  </OPFMessageGetExchangeExtractedMeetings>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        meetings = parsed.exchange_extracted_meetings
        assert len(meetings) == 1
        assert meetings[0]["status"] == "accepted"
        assert meetings[0]["subject"] == "Standup"
        assert meetings[0]["location"] == "Room 42"


class TestExtractCategories:
    def test_extracts_categories(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Cat test</OPFMessageCopySubject>
  <OPFMessageCopyCategoryList>
    <category>Important</category>
    <category>Work</category>
    <category>   </category>
  </OPFMessageCopyCategoryList>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert parsed.categories == ["Important", "Work"]


class TestExtractMeetingData:
    def test_extracts_meeting_data(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Meeting data</OPFMessageCopySubject>
  <OPFMessageCopyIsCalendarMessage>true</OPFMessageCopyIsCalendarMessage>
  <OPFMessageCopyMeetingData>
    <OPFMeetingStartDate>2025-01-15T10:00:00</OPFMeetingStartDate>
    <OPFMeetingEndDate>2025-01-15T11:00:00</OPFMeetingEndDate>
    <OPFMeetingLocation>Room A</OPFMeetingLocation>
  </OPFMessageCopyMeetingData>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert parsed.is_calendar_message is True
        assert parsed.meeting_data["OPFMeetingStartDate"] == "2025-01-15T10:00:00"
        assert parsed.meeting_data["OPFMeetingLocation"] == "Room A"


class TestExtractHtmlBody:
    def test_html_body_with_child_elements(self):
        xml = b"""<OPFMessageCopyHTMLBody>
  Before <p>Hello</p> After <br/> End
</OPFMessageCopyHTMLBody>"""
        el = etree.fromstring(xml)
        result = _extract_html_body(el)
        assert "<p>" in result
        assert "Hello" in result
        assert "Before" in result

    def test_html_body_pure_text(self):
        xml = b"<OPFMessageCopyHTMLBody>Just plain text</OPFMessageCopyHTMLBody>"
        el = etree.fromstring(xml)
        result = _extract_html_body(el)
        assert result == "Just plain text"


class TestSourceFallbackHeaders:
    def test_source_fallback_bcc_in_reply_to_references(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-06-25T08:52:47</OPFMessageCopySentTime>
  <OPFMessageCopySource>From: sender@example.com
To: to@example.com
BCC: bcc@example.com
In-Reply-To: &lt;parent@example.com&gt;
References: &lt;ref1@example.com&gt; &lt;ref2@example.com&gt;
Subject: Test

Body text here.</OPFMessageCopySource>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert parsed.bcc == ["bcc@example.com"]
        assert parsed.in_reply_to == "parent@example.com"
        assert "ref1@example.com" in parsed.references
        assert "ref2@example.com" in parsed.references


class TestBodyFromSource:
    def test_body_extracted_from_raw_source(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySource>From: sender@example.com
Subject: Test
Date: Wed, 01 Jan 2025 00:00:00 +0000

This is the extracted body from the raw source.</OPFMessageCopySource>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        # Body should be extracted from raw source
        assert "extracted body" in parsed.body_text or "extracted body" in parsed.body_html


class TestExtractExchangeList:
    def test_extracts_exchange_emails_and_contacts(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Exchange list</OPFMessageCopySubject>
  <OPFMessageGetExchangeExtractedEmails>
    <email>employee@example.test</email>
    <email>bob@example.com</email>
  </OPFMessageGetExchangeExtractedEmails>
  <OPFMessageGetExchangeExtractedContacts>
    <contact>Alice Smith</contact>
  </OPFMessageGetExchangeExtractedContacts>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert parsed.exchange_extracted_emails == ["employee@example.test", "bob@example.com"]
        assert parsed.exchange_extracted_contacts == ["Alice Smith"]


class TestFindHelpers:
    def test_find_with_namespace(self):
        xml = b"""<?xml version="1.0"?>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySubject>Test</OPFMessageCopySubject>
</email>"""
        root = etree.fromstring(xml)
        el = _find(root, "OPFMessageCopySubject", _NS_OUTLOOK)
        assert el is not None
        assert el.text == "Test"

    def test_find_without_namespace(self):
        xml = b"<email><OPFMessageCopySubject>Test</OPFMessageCopySubject></email>"
        root = etree.fromstring(xml)
        el = _find(root, "OPFMessageCopySubject", {})
        assert el is not None

    def test_find_text_default(self):
        xml = b"<email></email>"
        root = etree.fromstring(xml)
        result = _find_text(root, "NonExistent", {}, default="fallback")
        assert result == "fallback"
