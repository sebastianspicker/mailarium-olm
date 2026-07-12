"""Extended tests for src/parse_olm.py — targeting uncovered lines."""

from __future__ import annotations

from src.parse_olm import (
    Email,
)

# ── Email.uid fallback (lines 98-99) ─────────────────────────


class TestEmailTypeImplicitReply:
    def test_email_type_implicit_reply_via_in_reply_to(self):
        """No RE: prefix but has in_reply_to -> classified as reply."""
        email = Email(
            message_id="<m@test>",
            subject="Project Discussion",
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
            in_reply_to="<parent@test>",
        )
        assert email.email_type == "reply"
