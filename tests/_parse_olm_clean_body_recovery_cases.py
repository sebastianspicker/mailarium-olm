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


class TestCleanBodyHtmlInBodyText:
    def test_clean_body_falls_back_to_preview_when_html_normalizes_empty(self):
        email = Email(
            message_id="<m@test>",
            subject="Rack photo",
            sender_name="",
            sender_email="",
            to=[],
            cc=[],
            bcc=[],
            date="",
            body_text="<html><body><div></div></body></html>",
            body_html="<html><body><div></div></body></html>",
            folder="Inbox",
            has_attachments=False,
            preview_text="Preview summary from Outlook.",
        )
        assert email.clean_body == "Preview summary from Outlook."
        assert email.clean_body_source == "preview"

    def test_clean_body_falls_back_to_preview_after_image_only_html(self):
        email = Email(
            message_id="<m@test>",
            subject="Manual",
            sender_name="",
            sender_email="",
            to=[],
            cc=[],
            bcc=[],
            date="",
            body_text='<html><body><div><img src="cid:1"></div></body></html>',
            body_html='<html><body><div><img src="cid:1"></div></body></html>',
            folder="Inbox",
            has_attachments=False,
            preview_text="Scanned manual attached.",
        )
        assert email.clean_body == "Scanned manual attached."
        assert email.clean_body_source == "preview"
        assert email.body_kind == "content"
        assert email.body_empty_reason == "image_only"
        assert email.recovery_strategy == "preview"
        assert email.recovery_confidence == 0.7

    def test_body_kind_metadata_only_for_bodyless_reply(self):
        email = Email(
            message_id="<m@test>",
            subject="AW: Status",
            sender_name="Alice",
            sender_email="employee@example.test",
            to=["bob@example.com"],
            cc=[],
            bcc=[],
            date="",
            body_text="",
            body_html="",
            folder="Inbox",
            has_attachments=False,
            in_reply_to="parent@example.com",
        )
        assert email.body_kind == "content"
        assert email.body_empty_reason == "metadata_only_reply"
        assert email.recovery_strategy == "metadata_summary"
        assert email.recovery_confidence == 0.2
        assert email.clean_body == "Metadata-only reply with no recoverable authored body text."

    def test_body_kind_image_only_summary_when_no_preview_exists(self):
        email = Email(
            message_id="<m@test>",
            subject="Photo",
            sender_name="Alice",
            sender_email="employee@example.test",
            to=["bob@example.com"],
            cc=[],
            bcc=[],
            date="",
            body_text='<html><body><div><img src="cid:1"></div></body></html>',
            body_html='<html><body><div><img src="cid:1"></div></body></html>',
            folder="Inbox",
            has_attachments=True,
        )
        assert email.body_kind == "content"
        assert email.body_empty_reason == "image_only"
        assert email.recovery_strategy == "image_summary"
        assert email.clean_body == "Image-only message with attachments and no recoverable body text."

    def test_body_kind_source_shell_summary_for_source_only_shell(self):
        email = Email(
            message_id="<m@test>",
            subject="Signed shell",
            sender_name="Alice",
            sender_email="employee@example.test",
            to=["bob@example.com"],
            cc=[],
            bcc=[],
            date="",
            body_text="",
            body_html="",
            folder="Inbox",
            has_attachments=False,
            raw_source=(
                "Subject: Signed shell\n"
                'Content-Type: multipart/signed; protocol="application/pkcs7-signature"; boundary="abc"\n\n'
                "--abc\n"
                "Content-Type: text/plain; charset=utf-8\n\n"
                "\n"
                "--abc\n"
                "Content-Type: application/pkcs7-signature\n\n"
                "<binary>\n"
                "--abc--\n"
            ),
        )
        assert email.body_kind == "content"
        assert email.body_empty_reason == "source_shell_only"
        assert email.recovery_strategy == "source_shell_summary"
        assert email.clean_body == "Source-shell message with no recoverable visible body text."

    def test_body_kind_attachment_only_for_empty_message_with_attachments(self):
        email = Email(
            message_id="<m@test>",
            subject="Attachment drop",
            sender_name="Alice",
            sender_email="employee@example.test",
            to=["bob@example.com"],
            cc=[],
            bcc=[],
            date="",
            body_text="",
            body_html="",
            folder="Inbox",
            has_attachments=True,
        )
        assert email.body_kind == "attachment_only"
        assert email.body_empty_reason == "attachment_only"
        assert email.recovery_strategy == ""

    def test_parse_email_xml_extracts_reply_context_candidates_without_thread_markers(self):
        xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>RE: Follow-up</OPFMessageCopySubject>
  <OPFMessageCopyBody>Current answer.

From: Alice &lt;employee@example.test&gt;
Sent: Monday, January 1, 2025 10:00 AM
To: Bob &lt;bob@example.com&gt;
Subject: Original topic

Prior body.</OPFMessageCopyBody>
</email></emails>"""
        parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
        assert parsed is not None
        assert parsed.email_type == "reply"
        assert parsed.in_reply_to == ""
        assert parsed.references == []
        assert parsed.reply_context_from == "employee@example.test"
        assert parsed.reply_context_to == ["bob@example.com"]
        assert parsed.reply_context_subject == "Original topic"
        assert parsed.reply_context_source == "body_text"
