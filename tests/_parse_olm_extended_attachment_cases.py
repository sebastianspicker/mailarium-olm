# pylint: disable=no-member,c-extension-no-member


"""OLM attachment parsing across namespaces, archive paths, and malformed payloads."""

from __future__ import annotations

import base64
import zipfile
from pathlib import Path

from lxml import etree

from mailarium.olm_xml_helpers import (
    _extract_attachment_contents,
    _extract_attachment_field,
)
from mailarium.parse_olm import (
    _NS_OUTLOOK,
    _parse_email_xml,
    parse_olm,
)

# ── Email.uid fallback (lines 98-99) ─────────────────────────


def _extract_from_archive(tmp_path: Path, archive_name: str, xml_content: bytes, *, attachments=None):
    """Write an OLM fixture, then extract attachment content from its message XML."""
    archive = tmp_path / archive_name
    xml_path = "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(xml_path, xml_content)
        for path, content in ({} if attachments is None else attachments).items():
            zf.writestr(path, content)
    with zipfile.ZipFile(archive, "r") as zf:
        return _extract_attachment_contents(xml_content, xml_path, zf)


class TestExtractAttachmentFieldNamespaced:
    def test_attachment_field_namespaced_child(self):
        xml = b"""<messageAttachment xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFAttachmentName>report.pdf</OPFAttachmentName>
  <OPFAttachmentContentType>application/pdf</OPFAttachmentContentType>
  <OPFAttachmentContentFileSize>1024</OPFAttachmentContentFileSize>
</messageAttachment>"""
        el = etree.fromstring(xml)
        ns = _NS_OUTLOOK
        name = _extract_attachment_field(el, ns, "OPFAttachmentName", attr_hint="name")
        assert name == "report.pdf"

    def test_attachment_field_attribute_fallback(self):
        """When child element is missing, fall back to attribute matching."""
        xml = b'<messageAttachment OPFAttachmentName="doc.docx"></messageAttachment>'
        el = etree.fromstring(xml)
        name = _extract_attachment_field(el, {}, "OPFAttachmentName", attr_hint="name")
        assert name == "doc.docx"


class TestExtractAttachments:
    def test_extracts_attachment_metadata(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attach test</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>file.pdf</OPFAttachmentName>
      <OPFAttachmentContentType>application/pdf</OPFAttachmentContentType>
      <OPFAttachmentContentFileSize>2048</OPFAttachmentContentFileSize>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert parsed.has_attachments is True
        assert parsed.attachment_names == ["file.pdf"]
        assert len(parsed.attachments) == 1
        assert parsed.attachments[0]["name"] == "file.pdf"
        assert parsed.attachments[0]["size"] == 2048

    def test_extracts_namespaced_attachment(self):
        xml = b"""<?xml version="1.0"?>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>NS Attach</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>image.png</OPFAttachmentName>
      <OPFAttachmentContentType>image/png</OPFAttachmentContentType>
      <OPFAttachmentContentID>cid123</OPFAttachmentContentID>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert parsed.has_attachments is True
        assert parsed.attachments[0]["content_id"] == "cid123"
        assert parsed.attachments[0]["is_inline"] is True


class TestExtractAttachmentContents:
    def test_extract_inline_base64_attachment(self, tmp_path: Path):
        """Extract attachment content from inline base64 data."""
        content = b"Hello World!"
        b64 = base64.b64encode(content).decode()
        xml_content = f"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attach content</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>hello.txt</OPFAttachmentName>
      <OPFAttachmentContentData>{b64}</OPFAttachmentContentData>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email></emails>""".encode()

        archive = tmp_path / "attach.olm"
        xml_path = "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(xml_path, xml_content)

        with zipfile.ZipFile(archive, "r") as zf:
            result = _extract_attachment_contents(xml_content, xml_path, zf)

        assert len(result) == 1
        assert result[0][0] == "hello.txt"
        assert result[0][1] == content

    def test_extract_attachment_from_zip_path(self, tmp_path: Path):
        """Extract attachment content via relative path in ZIP."""
        xml_content = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attach file</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>data.bin</OPFAttachmentName>
      <OPFAttachmentURL>data.bin</OPFAttachmentURL>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email></emails>"""
        att_path = "Accounts/a/com.microsoft.__Messages/Inbox/data.bin"
        result = _extract_from_archive(
            tmp_path,
            "attach_url.olm",
            xml_content,
            attachments={att_path: b"binary data here"},
        )

        assert len(result) == 1
        assert result[0][0] == "data.bin"
        assert result[0][1] == b"binary data here"

    def test_extract_attachment_from_zip_path_ignores_xml_space_name_collision(self, tmp_path: Path):
        """Attachment filenames from attributes must not resolve to xml:space='preserve'."""
        xml_content = b"""<?xml version="1.0"?>
<emails xml:space="preserve"><email xml:space="preserve">
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>Attach file</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList xml:space="preserve">
    <messageAttachment xml:space="preserve"
      OPFAttachmentName="data.bin"
      OPFAttachmentURL="data.bin" />
  </OPFMessageCopyAttachmentList>
</email></emails>"""
        att_path = "Accounts/a/com.microsoft.__Messages/Inbox/data.bin"
        result = _extract_from_archive(
            tmp_path,
            "attach_url_collision.olm",
            xml_content,
            attachments={att_path: b"binary data here"},
        )

        assert len(result) == 1
        assert result[0][0] == "data.bin"
        assert result[0][1] == b"binary data here"

    def test_extract_attachment_skips_unnamed(self, tmp_path: Path):
        """Attachments without a name are skipped."""
        xml_content = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentContentData>dGVzdA==</OPFAttachmentContentData>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email></emails>"""
        result = _extract_from_archive(tmp_path, "noname.olm", xml_content)
        assert result == []

    def test_extract_attachment_invalid_xml(self, tmp_path: Path):
        """Malformed XML returns empty list."""
        result = _extract_from_archive(tmp_path, "badxml.olm", b"<email")
        assert result == []

    def test_extract_attachment_invalid_base64(self, tmp_path: Path):
        """Invalid base64 is handled gracefully; fallback to URL path."""
        xml_content = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>bad.txt</OPFAttachmentName>
      <OPFAttachmentContentData>!!!not_base64!!!</OPFAttachmentContentData>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email></emails>"""
        result = _extract_from_archive(tmp_path, "badb64.olm", xml_content)
        # Invalid base64 should be logged but not crash; no URL fallback so empty
        assert result == []

    def test_parse_olm_with_extract_attachments(self, tmp_path: Path):
        """parse_olm with extract_attachments=True populates attachment_contents."""
        content = b"attachment data"
        b64 = base64.b64encode(content).decode()
        xml_content = f"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>With attach</OPFMessageCopySubject>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>file.dat</OPFAttachmentName>
      <OPFAttachmentContentData>{b64}</OPFAttachmentContentData>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email></emails>""".encode()
        archive = tmp_path / "with_attach.olm"
        xml_path = "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(xml_path, xml_content)

        emails = list(parse_olm(str(archive), extract_attachments=True))
        assert len(emails) == 1
        assert len(emails[0].attachment_contents) == 1
        assert emails[0].attachment_contents[0][0] == "file.dat"
        assert emails[0].attachment_contents[0][1] == content
