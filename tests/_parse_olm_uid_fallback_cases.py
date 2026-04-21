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


class TestEmailUidFallback:
    def test_uid_without_message_id_uses_subject_date_sender(self):
        """When message_id is empty, uid falls back to subject|date|sender."""
        email = Email(
            message_id="",
            subject="Test",
            sender_name="Alice",
            sender_email="employee@example.test",
            to=[],
            cc=[],
            bcc=[],
            date="2024-01-01",
            body_text="",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
        uid = email.uid
        assert uid  # non-empty
        assert len(uid) == 32  # md5 hex

    def test_uid_with_message_id(self):
        email = Email(
            message_id="<abc@example.com>",
            subject="Test",
            sender_name="",
            sender_email="",
            to=[],
            cc=[],
            bcc=[],
            date="",
            body_text="",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
        uid = email.uid
        assert uid
        assert len(uid) == 32

    def test_uid_fallback_deterministic(self):
        """Same subject/date/sender always produces same uid."""
        kwargs = {
            "message_id": "",
            "subject": "Test",
            "sender_name": "",
            "sender_email": "a@example.test",
            "to": [],
            "cc": [],
            "bcc": [],
            "date": "2024-01-01",
            "body_text": "",
            "body_html": "",
            "folder": "Inbox",
            "has_attachments": False,
        }
        e1 = Email(**kwargs)
        e2 = Email(**kwargs)
        assert e1.uid == e2.uid
