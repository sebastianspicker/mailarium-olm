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


def test_to_dict_includes_new_fields():
    email = Email(
        message_id="7",
        subject="RE: Test",
        sender_name="Alice",
        sender_email="a@example.test",
        to=["b@example.test"],
        cc=[],
        bcc=[],
        date="2025-01-01",
        body_text="hi",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        conversation_id="conv-123",
        in_reply_to="msg-456",
        references=["msg-111", "msg-222"],
        priority=2,
        is_read=False,
    )
    d = email.to_dict()
    assert d["conversation_id"] == "conv-123"
    assert d["in_reply_to"] == "msg-456"
    assert d["references"] == ["msg-111", "msg-222"]
    assert d["priority"] == 2
    assert d["is_read"] is False
    assert d["email_type"] == "reply"
    assert d["base_subject"] == "Test"


def test_to_dict_includes_attribution_fields():
    email = Email(
        message_id="7b",
        subject="RE: Test",
        sender_name="Alice",
        sender_email="a@example.test",
        to=["Bob"],
        cc=[],
        bcc=[],
        date="2025-01-01",
        body_text="Current reply.\n\nFrom: Carol <carol@example.com>\nTo: Alice <a@example.test>\nSubject: Test",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        to_identities=["bob@example.com"],
        recipient_identity_source="source_header",
        reply_context_from="carol@example.com",
        reply_context_to=["a@example.test"],
        reply_context_subject="Test",
        reply_context_source="body_text",
    )
    d = email.to_dict()
    assert d["to_identities"] == ["bob@example.com"]
    assert d["recipient_identity_source"] == "source_header"
    assert d["reply_context_from"] == "carol@example.com"
    assert d["reply_context_to"] == ["a@example.test"]
    assert d["reply_context_subject"] == "Test"
    assert d["reply_context_source"] == "body_text"
    assert d["body_kind"] == "content"


def test_to_dict_includes_body_recovery_fields():
    email = Email(
        message_id="8a",
        subject="AW: Empty",
        sender_name="Alice",
        sender_email="employee@example.test",
        to=["bob@example.com"],
        cc=[],
        bcc=[],
        date="2025-01-01",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        in_reply_to="parent@example.com",
    )
    d = email.to_dict()
    assert d["body_kind"] == "content"
    assert d["body_empty_reason"] == "metadata_only_reply"
    assert d["recovery_strategy"] == "metadata_summary"
    assert d["recovery_confidence"] == 0.2


def test_extract_attachments_attribute_format():
    """Attachments using XML attribute format (same pattern as addresses)."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attachment test</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment OPFAttachmentName="report.pdf"
      OPFAttachmentContentType="application/pdf"
      OPFAttachmentContentFileSize="12345" />
    <messageAttachment OPFAttachmentName="image.png"
      OPFAttachmentContentType="image/png" />
  </OPFMessageCopyAttachmentList>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.has_attachments is True
    assert parsed.attachment_names == ["report.pdf", "image.png"]


def test_extract_attachments_child_element_format():
    """Attachments using child element format still work."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attachment test</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>doc.docx</OPFAttachmentName>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.has_attachments is True
    assert parsed.attachment_names == ["doc.docx"]


def test_parse_bcc_from_xml():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>BCC test</OPFMessageCopySubject>
  <OPFMessageCopyBCCAddresses>
    <emailAddress OPFContactEmailAddressAddress="secret@example.com"
                  OPFContactEmailAddressName="Secret User" />
  </OPFMessageCopyBCCAddresses>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.bcc == ["Secret User <secret@example.com>"]


def test_parse_bcc_from_source_header_fallback():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySource>Subject: BCC test
BCC: hidden@example.com

Body text.</OPFMessageCopySource>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.bcc == ["hidden@example.com"]


def test_parse_bcc_defaults_empty():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>No BCC</OPFMessageCopySubject>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.bcc == []


def test_to_dict_includes_bcc():
    email = Email(
        message_id="b1",
        subject="Test",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=["hidden@example.com"],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    d = email.to_dict()
    assert d["bcc"] == ["hidden@example.com"]


def test_attachment_metadata_extracted():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attachments</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment OPFAttachmentName="report.pdf"
      OPFAttachmentContentType="application/pdf"
      OPFAttachmentContentFileSize="12345" />
    <messageAttachment OPFAttachmentName="image.png"
      OPFAttachmentContentType="image/png" />
  </OPFMessageCopyAttachmentList>
</email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert len(parsed.attachments) == 2
    att0 = parsed.attachments[0]
    assert att0["name"] == "report.pdf"
    assert att0["mime_type"] == "application/pdf"
    assert att0["size"] == 12345
    assert att0["content_id"] == ""
    assert att0["is_inline"] is False
    att1 = parsed.attachments[1]
    assert att1["name"] == "image.png"
    assert att1["mime_type"] == "image/png"
    assert att1["size"] == 0


def test_to_dict_includes_attachment_count():
    email = Email(
        message_id="a1",
        subject="Test",
        sender_name="",
        sender_email="a@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=True,
        attachment_names=["a.pdf", "b.txt"],
    )
    d = email.to_dict()
    assert d["attachment_count"] == 2


def test_email_type_reply_via_in_reply_to():
    """Email without RE: prefix but with in_reply_to is classified as reply."""
    email = Email(
        message_id="irt1",
        subject="Meeting notes",
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
        in_reply_to="parent-msg-id@example.com",
    )
    assert email.email_type == "reply"


def test_parse_categories_from_xml():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Category test</OPFMessageCopySubject>
  <OPFMessageCopyCategoryList>
    <category>Meeting</category>
    <category>Project X</category>
  </OPFMessageCopyCategoryList>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.categories == ["Meeting", "Project X"]


def test_parse_categories_defaults_empty():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>No categories</OPFMessageCopySubject>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.categories == []


def test_parse_thread_topic_and_index():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Thread test</OPFMessageCopySubject>
  <OPFMessageCopyThreadTopic>Budget Discussion Q4</OPFMessageCopyThreadTopic>
  <OPFMessageCopyThreadIndex>AQHbMnRk</OPFMessageCopyThreadIndex>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.thread_topic == "Budget Discussion Q4"
    assert parsed.thread_index == "AQHbMnRk"


def test_parse_inference_classification():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Focused test</OPFMessageCopySubject>
  <OPFMessageCopyInferenceClassification>Focused</OPFMessageCopyInferenceClassification>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.inference_classification == "Focused"


def test_parse_is_calendar_message():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Meeting invite</OPFMessageCopySubject>
  <OPFMessageCopyIsCalendarMessage>true</OPFMessageCopyIsCalendarMessage>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.is_calendar_message is True


def test_parse_is_calendar_message_default_false():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Normal email</OPFMessageCopySubject>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.is_calendar_message is False


def test_parse_meeting_data():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Meeting data test</OPFMessageCopySubject>
  <OPFMessageCopyMeetingData>
    <location>Conference Room B</location>
    <startTime>2025-01-15T10:00:00</startTime>
    <endTime>2025-01-15T11:00:00</endTime>
  </OPFMessageCopyMeetingData>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.meeting_data["location"] == "Conference Room B"
    assert parsed.meeting_data["startTime"] == "2025-01-15T10:00:00"


def test_parse_exchange_extracted_emails():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Exchange extracted</OPFMessageCopySubject>
  <OPFMessageGetExchangeExtractedEmails>
    <email>employee@example.test</email>
    <email>bob@example.com</email>
  </OPFMessageGetExchangeExtractedEmails>
  <OPFMessageGetExchangeExtractedContacts>
    <contact>Alice Wonderland</contact>
  </OPFMessageGetExchangeExtractedContacts>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.exchange_extracted_emails == ["employee@example.test", "bob@example.com"]
    assert parsed.exchange_extracted_contacts == ["Alice Wonderland"]


def test_parse_attachment_content_id():
    """Attachments with content_id are marked as inline."""
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Inline image</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment OPFAttachmentName="logo.png"
      OPFAttachmentContentType="image/png"
      OPFAttachmentContentID="abc123@example.test" />
    <messageAttachment OPFAttachmentName="report.pdf"
      OPFAttachmentContentType="application/pdf" />
  </OPFMessageCopyAttachmentList>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.attachments[0]["content_id"] == "abc123@example.test"
    assert parsed.attachments[0]["is_inline"] is True
    assert parsed.attachments[1]["content_id"] == ""
    assert parsed.attachments[1]["is_inline"] is False


def test_parse_attachment_attributes_ignore_xml_space_namespace_name_collision():
    """Attachment attribute extraction must not confuse xml:space with OPFAttachmentName."""
    xml = b"""<?xml version="1.0"?>
<emails xml:space="preserve"><email xml:space="preserve">
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attachment attr collision</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList xml:space="preserve">
    <messageAttachment xml:space="preserve"
      OPFAttachmentName="report.pdf"
      OPFAttachmentContentType="application/pdf"
      OPFAttachmentContentID="abc123@example.test" />
  </OPFMessageCopyAttachmentList>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert parsed.attachment_names == ["report.pdf"]
    assert parsed.attachments[0]["name"] == "report.pdf"
    assert parsed.attachments[0]["mime_type"] == "application/pdf"


def test_to_dict_includes_new_metadata_fields():
    email = Email(
        message_id="m1",
        subject="Test",
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
        categories=["Important", "Finance"],
        thread_topic="Q4 Budget",
        inference_classification="Focused",
        is_calendar_message=True,
    )
    d = email.to_dict()
    assert d["categories"] == ["Important", "Finance"]
    assert d["thread_topic"] == "Q4 Budget"
    assert d["inference_classification"] == "Focused"
    assert d["is_calendar_message"] is True
