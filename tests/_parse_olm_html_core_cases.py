# ruff: noqa: F401,I001
from pathlib import Path

from lxml import etree

from src.parse_olm import (
    Email,
    _clean_text,
    _extract_email_from_header,
    _extract_header,
    _extract_name_from_header,
    _html_to_text,
    _parse_address_element,
    _parse_address_list,
    _parse_email_xml,
)
from src.olm_xml_helpers import _extract_folder, _extract_html_body, _parse_references
from src.rfc2822 import _normalize_date


def test_html_to_text_strips_tags_and_scripts():
    html = "<html><body><script>alert(1)</script><p>Hello<br>World</p></body></html>"
    text = _html_to_text(html)
    assert "Hello" in text
    assert "World" in text
    assert "alert" not in text


def test_html_to_text_strips_hidden_preheader_and_head_text():
    html = (
        "<html><head><title>Noise title</title></head><body>"
        "<div style='display:none;font-size:0;max-height:0'>Hidden preview text</div>"
        "<p>Visible body</p></body></html>"
    )
    text = _html_to_text(html)
    assert "Visible body" in text
    assert "Hidden preview text" not in text
    assert "Noise title" not in text


def test_html_to_text_strips_gmail_quote_wrapper_tail():
    html = (
        "<html><body><p>Visible reply</p>"
        "<div class='gmail_quote'>On Mon Alice wrote:<blockquote>Prior content</blockquote></div>"
        "</body></html>"
    )
    text = _html_to_text(html)
    assert text == "Visible reply"


def test_html_to_text_strips_apple_mail_quote_wrapper_tail():
    html = "<html><body><p>Visible reply</p><blockquote class='AppleMailQuote'>Prior content</blockquote></body></html>"
    text = _html_to_text(html)
    assert text == "Visible reply"


def test_html_to_text_strips_outlook_reply_wrapper_tail():
    html = (
        "<html><body><p>Visible reply</p>"
        "<div id='divRplyFwdMsg'><div class='OutlookMessageHeader'>From: Alice</div><p>Prior content</p></div>"
        "</body></html>"
    )
    text = _html_to_text(html)
    assert text == "Visible reply"


def test_extract_folder_from_path():
    path = "Accounts/user/com.microsoft.__Messages/Inbox/msg.xml"
    assert _extract_folder(path) == "Inbox"


def test_extract_folder_preserves_nested_path():
    path = "Accounts/user/com.microsoft.__Messages/Inbox/Finance/Budgets/msg.xml"
    assert _extract_folder(path) == "Inbox/Finance/Budgets"


def test_parse_email_xml_falls_back_to_no_subject():
    xml = b"""<?xml version="1.0"?>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySenderAddress>a@example.com</OPFMessageCopySenderAddress>
  <OPFMessageCopySentTime>2023-01-01T00:00:00Z</OPFMessageCopySentTime>
</email>
"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.subject == "(no subject)"
    assert parsed.sender_email == "a@example.com"


def test_parse_email_xml_does_not_resolve_external_entities(tmp_path: Path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("super-secret-token", encoding="utf-8")

    xml = f"""<?xml version="1.0"?>
<!DOCTYPE email [
<!ENTITY xxe SYSTEM "file://{secret_file}">
]>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySubject>&xxe;</OPFMessageCopySubject>
  <OPFMessageCopySenderAddress>a@example.com</OPFMessageCopySenderAddress>
  <OPFMessageCopySentTime>2023-01-01T00:00:00Z</OPFMessageCopySentTime>
</email>
""".encode()

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.subject != "super-secret-token"


def test_parse_email_xml_non_namespaced_format():
    """Newer Outlook for Mac OLM exports use plain element names without namespace."""
    xml = b"""<?xml version="1.0"?>
<emails xml:space="preserve" elementCount="1"><email xml:space="preserve">
  <OPFMessageCopyMessageID>abc123@example.com</OPFMessageCopyMessageID>
  <OPFMessageCopySubject>Test Subject</OPFMessageCopySubject>
  <OPFMessageCopySenderAddress>sender@example.com</OPFMessageCopySenderAddress>
  <OPFMessageCopySenderName>Sender Name</OPFMessageCopySenderName>
  <OPFMessageCopySentTime>2025-06-25T08:52:47</OPFMessageCopySentTime>
  <OPFMessageCopyBody>Hello, this is the body text.</OPFMessageCopyBody>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.message_id == "abc123@example.com"
    assert parsed.subject == "Test Subject"
    assert parsed.sender_email == "sender@example.com"
    assert parsed.sender_name == "Sender Name"
    assert parsed.date == "2025-06-25T08:52:47"
    assert parsed.body_text == "Hello, this is the body text."


def test_parse_email_xml_non_namespaced_addresses():
    """Non-namespaced OLM format with structured To/CC/From address elements."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Addr test</OPFMessageCopySubject>
  <OPFMessageCopyFromAddresses>
    <emailAddress><OPFContactEmailAddressAddress>from@example.com</OPFContactEmailAddressAddress></emailAddress>
  </OPFMessageCopyFromAddresses>
  <OPFMessageCopyToAddresses>
    <emailAddress><OPFContactEmailAddressAddress>to@example.com</OPFContactEmailAddressAddress></emailAddress>
  </OPFMessageCopyToAddresses>
  <OPFMessageCopyCCAddresses>
    <emailAddress><OPFContactEmailAddressAddress>cc@example.com</OPFContactEmailAddressAddress></emailAddress>
  </OPFMessageCopyCCAddresses>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Sent Items/msg.xml")
    assert parsed is not None
    assert parsed.sender_email == "from@example.com"
    assert "to@example.com" in parsed.to[0]
    assert "cc@example.com" in parsed.cc[0]


def test_parse_email_xml_extracts_from_source_headers():
    """When structured XML fields are missing, extract from raw RFC 2822 source."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-06-25T08:52:47</OPFMessageCopySentTime>
  <OPFMessageCopySource>From: "John, Petra" &lt;petra@example.com&gt;
To: "Recipient, One" &lt;recipient.one@example.com&gt;
CC: "Admin Team" &lt;admin@example.com&gt;
Subject: AW: Lucom Dokumentation Zugriff
Date: Wed, 25 Jun 2025 10:52:47 +0200
Message-ID: &lt;470bdd8b@example.com&gt;

Body text here.</OPFMessageCopySource>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.message_id == "470bdd8b@example.com"
    assert parsed.subject == "AW: Lucom Dokumentation Zugriff"
    assert parsed.sender_email == "petra@example.com"
    assert parsed.sender_name == "John, Petra"
    assert parsed.to == ["recipient.one@example.com"]
    assert parsed.cc == ["admin@example.com"]


def test_parse_email_xml_preview_fallback_for_body():
    """When no Body or HTMLBody, fall back to OPFMessageCopyPreview."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Preview test</OPFMessageCopySubject>
  <OPFMessageCopyPreview>This is the preview text of the email.</OPFMessageCopyPreview>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.body_text == "This is the preview text of the email."


def test_parse_email_xml_preserves_raw_surfaces_and_forensic_body():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Forensic surface test</OPFMessageCopySubject>
  <OPFMessageCopyBody>Visible plain body.</OPFMessageCopyBody>
  <OPFMessageCopyHTMLBody><html><body><p>Visible <strong>HTML</strong> body.</p></body></html></OPFMessageCopyHTMLBody>
  <OPFMessageCopySource>From: Alice &lt;employee@example.test&gt;
Subject: Forensic surface test

Source body.</OPFMessageCopySource>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.raw_body_text == "Visible plain body."
    assert parsed.raw_body_html == "<html><body><p>Visible <strong>HTML</strong> body.</p></body></html>"
    assert "Source body." in parsed.raw_source
    assert parsed.raw_source_headers["Subject"] == "Forensic surface test"
    assert parsed.forensic_body_source == "raw_body_text"
    assert parsed.forensic_body_text == "Visible plain body."


def test_parse_email_xml_uses_preview_when_html_body_normalizes_empty():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Preview rescue</OPFMessageCopySubject>
  <OPFMessageCopyBody>&lt;html&gt;&lt;body&gt;&lt;div&gt;&lt;/div&gt;&lt;/body&gt;&lt;/html&gt;</OPFMessageCopyBody>
  <OPFMessageCopyHTMLBody><html><body><div></div></body></html></OPFMessageCopyHTMLBody>
  <OPFMessageCopyPreview>Visible preview summary.</OPFMessageCopyPreview>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.preview_text == "Visible preview summary."
    assert parsed.clean_body == "Visible preview summary."
    assert parsed.clean_body_source == "preview"
    assert parsed.body_kind == "content"
    assert parsed.body_empty_reason == "html_shell_only"
    assert parsed.recovery_strategy == "preview"
    assert parsed.recovery_confidence == 0.7
