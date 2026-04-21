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


def test_extract_header_simple():
    source = "Subject: Hello World\nFrom: test@example.com\n\nBody"
    assert _extract_header(source, "Subject") == "Hello World"


def test_extract_header_with_continuation():
    source = "Subject: This is\n a long subject\nFrom: test@example.com\n\nBody"
    assert _extract_header(source, "Subject") == "This is a long subject"


def test_extract_email_from_header_angle_brackets():
    source = 'From: "Alice Bob" <employee@example.test>\nSubject: Test\n\nBody'
    assert _extract_email_from_header(source, "From") == "employee@example.test"


def test_extract_email_from_header_html_encoded():
    source = 'From: "Alice" &lt;employee@example.test&gt;\nSubject: Test\n\nBody'
    assert _extract_email_from_header(source, "From") == "employee@example.test"


def test_extract_name_from_header_quoted():
    source = 'From: "John, Petra" <petra@example.com>\nSubject: Test\n\nBody'
    assert _extract_name_from_header(source, "From") == "John, Petra"


def test_parse_address_list():
    raw = '"Alice" <alice@example.test>, bob@example.test, "Carol D" <carol@example.test>'
    result = _parse_address_list(raw)
    assert result == ["alice@example.test", "bob@example.test", "carol@example.test"]


def test_parse_address_element_child_elements():
    """_parse_address_element handles child-element format (older OLM)."""
    xml = b"""<emailAddress>
      <OPFContactEmailAddressName>Alice</OPFContactEmailAddressName>
      <OPFContactEmailAddressAddress>employee@example.test</OPFContactEmailAddressAddress>
    </emailAddress>"""
    el = etree.fromstring(xml)
    name, email = _parse_address_element(el)
    assert name == "Alice"
    assert email == "employee@example.test"


def test_parse_address_element_attributes():
    """_parse_address_element handles attribute format (newer OLM / Sent Items)."""
    xml = b"""<emailAddress xml:space="preserve"
      OPFContactEmailAddressAddress="bob@example.com"
      OPFContactEmailAddressName="Bob Smith"
      OPFContactEmailAddressType="0">
    </emailAddress>"""
    el = etree.fromstring(xml)
    name, email = _parse_address_element(el)
    assert name == "Bob Smith"
    assert email == "bob@example.com"


def test_parse_address_element_fuzzy_child_tags():
    """Fuzzy matching works for non-standard child element names."""
    xml = b"""<recipient>
      <displayName>Charlie</displayName>
      <emailAddress>charlie@example.com</emailAddress>
    </recipient>"""
    el = etree.fromstring(xml)
    name, email = _parse_address_element(el)
    assert name == "Charlie"
    assert email == "charlie@example.com"


def test_extract_addresses_includes_display_name():
    """Addresses include display name in 'Name <email>' format."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Name test</OPFMessageCopySubject>
  <OPFMessageCopyToAddresses>
    <emailAddress>
      <OPFContactEmailAddressName>Alice Wonderland</OPFContactEmailAddressName>
      <OPFContactEmailAddressAddress>employee@example.test</OPFContactEmailAddressAddress>
    </emailAddress>
  </OPFMessageCopyToAddresses>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.to == ["Alice Wonderland <employee@example.test>"]


def test_extract_addresses_fuzzy_tags():
    """Address extraction works even with non-standard child element names."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Fuzzy test</OPFMessageCopySubject>
  <OPFMessageCopyToAddresses>
    <recipient>
      <recipientName>Charlie Brown</recipientName>
      <recipientAddress>charlie@example.com</recipientAddress>
    </recipient>
  </OPFMessageCopyToAddresses>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Sent Items/msg.xml")
    assert parsed is not None
    assert parsed.to == ["Charlie Brown <charlie@example.com>"]


def test_sent_items_sender_from_from_addresses():
    """Sent Items without SenderAddress/SenderName get sender from FromAddresses."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Sent item</OPFMessageCopySubject>
  <OPFMessageCopyFromAddresses>
    <emailAddress>
      <OPFContactEmailAddressName>Target Person</OPFContactEmailAddressName>
      <OPFContactEmailAddressAddress>sender.one@example.com</OPFContactEmailAddressAddress>
    </emailAddress>
  </OPFMessageCopyFromAddresses>
  <OPFMessageCopyToAddresses>
    <emailAddress>
      <OPFContactEmailAddressName>Recipient</OPFContactEmailAddressName>
      <OPFContactEmailAddressAddress>recipient@example.com</OPFContactEmailAddressAddress>
    </emailAddress>
  </OPFMessageCopyToAddresses>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Sent Items/msg.xml")
    assert parsed is not None
    assert parsed.sender_name == "Target Person"
    assert parsed.sender_email == "sender.one@example.com"
    assert parsed.to == ["Recipient <recipient@example.com>"]


def test_sent_items_attribute_format_addresses():
    """Sent Items with addresses in XML attributes (real-world OLM format)."""
    xml = b"""<?xml version="1.0"?>
<emails xml:space="preserve" elementCount="1"><email xml:space="preserve">
  <OPFMessageCopySentTime>2025-12-05T12:51:03</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Sprachkurs Lautstaerke</OPFMessageCopySubject>
  <OPFMessageCopyCCAddresses xml:space="preserve">
    <emailAddress xml:space="preserve"
      OPFContactEmailAddressAddress="cc.one@example.com"
      OPFContactEmailAddressName="CC, One"
      OPFContactEmailAddressType="0"></emailAddress>
  </OPFMessageCopyCCAddresses>
  <OPFMessageCopyDisplayTo xml:space="preserve">Kobler, Sabrina</OPFMessageCopyDisplayTo>
  <OPFMessageCopyFromAddresses xml:space="preserve">
    <emailAddress xml:space="preserve"
      OPFContactEmailAddressAddress="sender.one@example.com"
      OPFContactEmailAddressName="Sender, One"
      OPFContactEmailAddressType="0"></emailAddress>
  </OPFMessageCopyFromAddresses>
  <OPFMessageCopyToAddresses xml:space="preserve">
    <emailAddress xml:space="preserve"
      OPFContactEmailAddressAddress="sabrina@example.com"
      OPFContactEmailAddressName="Kobler, Sabrina"
      OPFContactEmailAddressType="0"></emailAddress>
  </OPFMessageCopyToAddresses>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Sent Items/msg.xml")
    assert parsed is not None
    assert parsed.sender_name == "Sender, One"
    assert parsed.sender_email == "sender.one@example.com"
    assert parsed.to == ["Kobler, Sabrina <sabrina@example.com>"]
    assert parsed.cc == ["CC, One <cc.one@example.com>"]


def test_display_to_fallback_when_no_to_addresses():
    """Falls back to OPFMessageCopyDisplayTo when ToAddresses is missing."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Display To test</OPFMessageCopySubject>
  <OPFMessageCopyDisplayTo>Mueller, Hans</OPFMessageCopyDisplayTo>
  <OPFMessageCopyFromAddresses xml:space="preserve">
    <emailAddress xml:space="preserve"
      OPFContactEmailAddressAddress="sender@example.com"
      OPFContactEmailAddressName="Sender Name"
      OPFContactEmailAddressType="0"></emailAddress>
  </OPFMessageCopyFromAddresses>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Sent Items/msg.xml")
    assert parsed is not None
    assert parsed.to == ["Mueller, Hans"]
    assert parsed.sender_email == "sender@example.com"


def test_display_to_fallback_multiple_recipients():
    """OPFMessageCopyDisplayTo with semicolon-separated names."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Multi recipient</OPFMessageCopySubject>
  <OPFMessageCopyDisplayTo>Alice; Bob; Carol</OPFMessageCopyDisplayTo>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Sent Items/msg.xml")
    assert parsed is not None
    assert parsed.to == ["Alice", "Bob", "Carol"]


def test_display_to_preserves_names_but_recovers_identity_from_source_header():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Display To plus source</OPFMessageCopySubject>
  <OPFMessageCopyDisplayTo>Mueller, Hans</OPFMessageCopyDisplayTo>
  <OPFMessageCopySource>From: Sender Name &lt;sender@example.com&gt;
To: "Mueller, Hans" &lt;colleague@example.test&gt;
Subject: Display To plus source

Body.</OPFMessageCopySource>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Sent Items/msg.xml")
    assert parsed is not None
    assert parsed.to == ["Mueller, Hans"]
    assert parsed.to_identities == ["colleague@example.test"]
    assert parsed.recipient_identity_source == "source_header"


def test_email_type_original():
    email = Email(
        message_id="1",
        subject="Hello World",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    assert email.email_type == "original"
    assert email.base_subject == "Hello World"


def test_email_type_reply_re():
    email = Email(
        message_id="2",
        subject="RE: Hello World",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    assert email.email_type == "reply"
    assert email.base_subject == "Hello World"


def test_email_type_reply_aw():
    email = Email(
        message_id="3",
        subject="AW: AW: Betreff",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    assert email.email_type == "reply"
    assert email.base_subject == "Betreff"


def test_email_type_forward_fw():
    email = Email(
        message_id="4",
        subject="FW: Some Message",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    assert email.email_type == "forward"
    assert email.base_subject == "Some Message"


def test_email_type_forward_wg():
    email = Email(
        message_id="5",
        subject="WG: Weitergeleitete Nachricht",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    assert email.email_type == "forward"
    assert email.base_subject == "Weitergeleitete Nachricht"


def test_base_subject_strips_mixed_prefixes():
    email = Email(
        message_id="6",
        subject="RE: FW: AW: WG: Deep Thread",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    assert email.base_subject == "Deep Thread"


def test_parse_email_xml_threading_fields():
    """Parse conversation_id, in_reply_to, references, priority, is_read from XML."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>RE: Thread test</OPFMessageCopySubject>
  <OPFMessageCopyExchangeConversationId>AAQkADc1NjJk</OPFMessageCopyExchangeConversationId>
  <OPFMessageCopyInReplyTo>&lt;parent-msg-id@example.com&gt;</OPFMessageCopyInReplyTo>
  <OPFMessageCopyReferences>&lt;root@example.com&gt; &lt;parent@example.com&gt;</OPFMessageCopyReferences>
  <OPFMessageGetPriority>2</OPFMessageGetPriority>
  <OPFMessageGetIsRead>false</OPFMessageGetIsRead>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.conversation_id == "AAQkADc1NjJk"
    assert parsed.in_reply_to == "<parent-msg-id@example.com>"
    assert parsed.references == ["root@example.com", "parent@example.com"]
    assert parsed.priority == 2
    assert parsed.is_read is False
    assert parsed.email_type == "reply"
    assert parsed.base_subject == "Thread test"


def test_parse_email_xml_defaults_for_new_fields():
    """New fields default sensibly when not present in XML."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Simple email</OPFMessageCopySubject>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.conversation_id == ""
    assert parsed.in_reply_to == ""
    assert parsed.references == []
    assert parsed.priority == 0
    assert parsed.is_read is True
    assert parsed.email_type == "original"


def test_parse_email_xml_threading_from_source_headers():
    """Extract In-Reply-To and References from raw RFC 2822 source as fallback."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySource>Subject: RE: From source
In-Reply-To: &lt;parent-id@example.com&gt;
References: &lt;root-id@example.com&gt; &lt;parent-id@example.com&gt;

Body text.</OPFMessageCopySource>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.in_reply_to == "parent-id@example.com"
    assert parsed.references == ["root-id@example.com", "parent-id@example.com"]


def test_parse_references_angle_brackets():
    assert _parse_references("<a@example.test> <c@example.test>") == ["a@example.test", "c@example.test"]


def test_parse_references_empty():
    assert _parse_references("") == []
    assert _parse_references("   ") == []


def test_parse_references_mixed_bracketed_and_bare():
    raw = "<id1@example.test> bare@example.test <id3@example.test>"
    result = _parse_references(raw)
    assert "id1@example.test" in result
    assert "bare@example.test" in result
    assert "id3@example.test" in result
    assert len(result) == 3


def test_parse_references_bare_only():
    raw = "id1@example.test id2@example.test"
    result = _parse_references(raw)
    assert result == ["id1@example.test", "id2@example.test"]


def test_parse_references_no_duplicates():
    raw = "<id1@example.test> id1@example.test"
    result = _parse_references(raw)
    assert result == ["id1@example.test"]


def test_extract_name_from_header_escaped_quotes():
    source = 'From: "John \\"Johnny\\" Smith" <john@example.com>\n\nBody'
    name = _extract_name_from_header(source, "From")
    assert "Johnny" in name
    assert "John" in name


def test_extract_name_from_header_unquoted():
    source = "From: John Smith <john@example.com>\n\nBody"
    name = _extract_name_from_header(source, "From")
    assert name == "John Smith"


def test_sender_email_normalized_lowercase():
    """Sender email from OLM XML should be lowercased."""
    xml = b"""<?xml version="1.0"?>
    <email>
      <OPFMessageCopySubject>Test</OPFMessageCopySubject>
      <OPFMessageCopySentTime>2024-01-01T00:00:00</OPFMessageCopySentTime>
      <OPFMessageCopySenderAddress>John.Smith@Example.COM</OPFMessageCopySenderAddress>
      <OPFMessageCopySenderName>John Smith</OPFMessageCopySenderName>
      <OPFMessageCopyBody>Body</OPFMessageCopyBody>
    </email>"""
    email = _parse_email_xml(xml, "test.xml")
    assert email.sender_email == "john.smith@example.com"
