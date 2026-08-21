"""Small direct contracts for local archive safety boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from mailarium.db_schema import init_schema
from mailarium.email_db import EmailDatabase
from mailarium.ews.errors import EWSConfigurationError, EWSValidationError
from mailarium.ews.gateway import EWSGateway
from mailarium.ews.transport import EWSTransport
from mailarium.html_converter import html_to_text
from mailarium.parse_olm import Email, _parse_email_xml
from mailarium.privacy_scan_rules import TRACKED_FORBIDDEN_PATH_PATTERNS, path_matches
from mailarium.repo_paths import validate_output_path
from mailarium.sanitization import sanitize_untrusted_text


def test_olm_xml_parser_preserves_a_local_message_without_fixture_files() -> None:
    xml = b"""<emails><email>
    <OPFMessageCopyMessageID>message@example.test</OPFMessageCopyMessageID>
    <OPFMessageCopySubject>Direct XML</OPFMessageCopySubject>
    <OPFMessageCopySenderAddress>sender@example.test</OPFMessageCopySenderAddress>
    <OPFMessageCopySentTime>2026-08-20T10:00:00</OPFMessageCopySentTime>
    <OPFMessageCopyBody>Local body</OPFMessageCopyBody>
    </email></emails>"""

    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/message.xml")

    assert parsed is not None
    assert (parsed.subject, parsed.sender_email, parsed.body_text) == ("Direct XML", "sender@example.test", "Local body")


def test_html_and_terminal_sanitization_remove_untrusted_active_content() -> None:
    assert html_to_text("<p>Hello <strong>local</strong></p><script>alert(1)</script>") == "Hello local"
    assert "\x1b" not in sanitize_untrusted_text("notice\x1b[31mred\x1b[0m\u202eevil")


def test_sqlite_archive_preserves_one_email_in_a_temporary_database(tmp_path) -> None:
    database = EmailDatabase(str(tmp_path / "archive.db"))
    email = Email(
        message_id="message@example.test",
        subject="Direct database contract",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date="2026-08-20T10:00:00",
        body_text="local evidence",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )

    assert database.insert_email(email)
    stored = database.get_email_full(email.uid)
    assert stored is not None and stored["subject"] == "Direct database contract"
    database.close()


def test_archive_related_rows_custody_and_schema_upgrade_stay_transactional(tmp_path) -> None:
    database_path = tmp_path / "archive.db"
    database = EmailDatabase(str(database_path))
    email = Email(
        message_id="atomic@example.test",
        subject="Atomic archive contract",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date="2026-08-20T10:00:00",
        body_text="committed local evidence",
        body_html="",
        folder="Inbox",
        has_attachments=True,
        attachment_names=["evidence.txt"],
        attachments=[{"name": "evidence.txt", "size": 4, "extracted_text": "proof"}],
    )

    database.conn.execute(
        "CREATE TRIGGER reject_attachment BEFORE INSERT ON attachments BEGIN SELECT RAISE(ABORT, 'attachment rejected'); END"
    )
    assert not database.insert_email(email)
    tables = ("emails", "recipients", "attachments")
    assert [database.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables] == [0, 0, 0]
    database.conn.execute("DROP TRIGGER reject_attachment")

    assert database.insert_email(email)
    assert not database.insert_email(email)
    database.log_custody_event("ingested", "email", email.uid, {"source": "direct"})
    assert [database.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables] == [1, 1, 1]
    assert database.email_provenance(email.uid)["custody_events"][0]["action"] == "ingested"

    database.conn.execute("DELETE FROM schema_version")
    database.conn.execute("INSERT INTO schema_version(version) VALUES (35)")
    database.conn.commit()
    init_schema(database.conn)
    migrated = database.get_email_full(email.uid)
    assert migrated is not None and migrated["subject"] == "Atomic archive contract"
    assert database.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 36
    database.close()


def test_ews_gateway_parses_a_fake_local_transport_and_escapes_identifiers() -> None:
    class FakeTransport:
        request = b""

        def execute(self, _operation: str, envelope: bytes) -> bytes:
            self.request = envelope
            return (
                b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                b'xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages" '
                b'xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"><s:Body>'
                b"<m:FindItemResponse><m:ResponseMessages>"
                b'<m:FindItemResponseMessage ResponseClass="Success"><m:ResponseCode>NoError</m:ResponseCode>'
                b'<m:RootFolder><t:Items><t:Message><t:ItemId Id="item-1" ChangeKey="ck-1"/>'
                b"<t:Subject>Local item</t:Subject></t:Message></t:Items></m:RootFolder>"
                b"</m:FindItemResponseMessage></m:ResponseMessages></m:FindItemResponse></s:Body></s:Envelope>"
            )

    transport = FakeTransport()
    assert EWSGateway(cast(EWSTransport, transport)).find_items("inbox<&")[0].item_id == "item-1"
    assert b'Id="inbox&lt;&amp;"' in transport.request


def test_ews_transport_fails_closed_without_disclosing_soap_or_credentials() -> None:
    for endpoint in (
        "http://exchange.example.test/EWS",
        "https://user:secret@example.test/EWS",
        "https://exchange.example.test/EWS?token=secret",
    ):
        with pytest.raises(EWSConfigurationError):
            EWSTransport(endpoint, lambda: object())

    diagnostics: list[dict[str, object]] = []

    class FakeSession:
        def __init__(self, status_code: int, content: bytes) -> None:
            self.status_code = status_code
            self.content = content
            self.closed = False

        def post(self, *_args, **_kwargs):
            return SimpleNamespace(status_code=self.status_code, content=self.content)

        def close(self) -> None:
            self.closed = True

    session = FakeSession(302, b"redirect secret response")
    transport = EWSTransport(
        "https://exchange.example.test/EWS",
        lambda: session,
        debug_sink=diagnostics.append,
    )
    with pytest.raises(EWSValidationError, match="redirects"):
        transport.execute("FindItem", b"<secret-request/>")

    assert session.closed
    assert diagnostics == [
        {
            "host": "exchange.example.test",
            "operation": "FindItem",
            "status_code": 302,
            "request_size": 17,
            "response_size": 24,
        }
    ]
    assert "secret" not in repr(diagnostics)

    oversized = FakeSession(200, b"12345")
    bounded = EWSTransport("https://exchange.example.test/EWS", lambda: oversized, max_response_bytes=4)
    with pytest.raises(EWSValidationError, match="size limit"):
        bounded.execute("FindItem", b"<request/>")
    assert oversized.closed


def test_ews_mutations_escape_identifiers_and_preserve_destructive_guards() -> None:
    class FakeTransport:
        def __init__(self) -> None:
            self.requests: list[tuple[str, bytes]] = []

        def execute(self, operation: str, envelope: bytes) -> bytes:
            self.requests.append((operation, envelope))
            return (
                b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                b'xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">'
                b'<s:Body><m:Response><m:ResponseMessages><m:ResponseMessage ResponseClass="Success">'
                b"<m:ResponseCode>NoError</m:ResponseCode></m:ResponseMessage></m:ResponseMessages>"
                b"</m:Response></s:Body></s:Envelope>"
            )

    transport = FakeTransport()
    gateway = EWSGateway(cast(EWSTransport, transport))
    gateway.delete_to_deleted_items('item<&"', 'change<&"')
    gateway.update_item('item<&"', 'change<&"', subject="safe")

    delete_envelope = transport.requests[0][1]
    update_envelope = transport.requests[1][1]
    assert b'DeleteType="MoveToDeletedItems"' in delete_envelope
    assert b'Id="item&lt;&amp;&quot;" ChangeKey="change&lt;&amp;&quot;"' in delete_envelope
    assert b'ConflictResolution="NeverOverwrite"' in update_envelope


def test_output_paths_reject_tracked_repository_targets() -> None:
    try:
        validate_output_path("README.md")
    except ValueError as error:
        assert "Output path" in str(error)
    else:  # pragma: no cover - safety assertion
        raise AssertionError("tracked repository output was accepted")


def test_privacy_rules_allow_only_reviewed_codacy_configuration_paths() -> None:
    for path in (".codacy/codacy.config.json", ".codacy/codacy.yaml", ".codacy/codacy.yml"):
        assert not path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS)

    for path in (".codacy/private.json", ".agents/session.json", ".codex/config.toml"):
        assert path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS)
