"""Offline public contracts for archive input and safe text rendering."""

from __future__ import annotations

from zipfile import ZipFile

from mailarium.ingestion import ParsedMessage
from mailarium.ingestion.olm.parse_olm import parse_olm
from mailarium.model import MESSAGE_UID_ALGORITHM, MESSAGE_UID_VERSION, Message
from mailarium.model.html_text import html_to_text
from mailarium.platform.sanitization import sanitize_untrusted_text

_MESSAGE_UID_V1: dict[str, object] = {
    "version": 1,
    "algorithm": "sha256-v1",
    "message": {
        "message_id": "message@example.test",
        "subject": "Direct XML",
        "sender_name": "Sender",
        "sender_email": "sender@example.test",
        "to": [],
        "cc": [],
        "bcc": [],
        "date": "2026-08-20T10:00:00",
        "body_text": "Local body",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    },
    "uid": "c1f995a29bbd0cc1f6959c59913eda3ef56635b4bde5d0f98417da80a55dff6f",
}


def test_olm_archive_parser_preserves_one_local_message(tmp_path) -> None:
    uid_fixture = _MESSAGE_UID_V1
    archive_path = tmp_path / "mail.olm"
    xml = b"""<emails><email>
    <OPFMessageCopyMessageID>message@example.test</OPFMessageCopyMessageID>
    <OPFMessageCopySubject>Direct XML</OPFMessageCopySubject>
    <OPFMessageCopySenderAddress>sender@example.test</OPFMessageCopySenderAddress>
    <OPFMessageCopySentTime>2026-08-20T10:00:00</OPFMessageCopySentTime>
    <OPFMessageCopyBody>Local body</OPFMessageCopyBody>
    </email></emails>"""
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("Accounts/a/com.microsoft.__Messages/Inbox/message.xml", xml)

    (parsed,) = tuple(parse_olm(str(archive_path)))

    assert (parsed.subject, parsed.sender_email, parsed.body_text) == ("Direct XML", "sender@example.test", "Local body")
    assert isinstance(parsed, ParsedMessage)
    assert uid_fixture["version"] == MESSAGE_UID_VERSION
    assert uid_fixture["algorithm"] == MESSAGE_UID_ALGORITHM
    message = Message(**uid_fixture["message"])
    parsed_message = ParsedMessage(**uid_fixture["message"])
    assert message.uid == parsed_message.uid == parsed.uid == uid_fixture["uid"]


def test_html_and_terminal_sanitization_remove_untrusted_active_content() -> None:
    assert html_to_text("<p>Hello <strong>local</strong></p><script>alert(1)</script>") == "Hello local"
    assert "\x1b" not in sanitize_untrusted_text("notice\x1b[31mred\x1b[0m\u202eevil")
