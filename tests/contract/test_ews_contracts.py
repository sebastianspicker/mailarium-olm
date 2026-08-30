"""Offline EWS transport, gateway, and fail-closed policy contracts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from mailarium.mailbox.ews.errors import EWSConfigurationError, EWSValidationError
from mailarium.mailbox.ews.gateway import EWSGateway
from mailarium.mailbox.ews.transport import EWSTransport
from mailarium.mailbox.mailbox_runtime import MailboxRuntimePolicy
from mailarium.mailbox.mailbox_service import MailboxService
from mailarium.mailbox.mailbox_store import MailboxStore


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
    transport = EWSTransport("https://exchange.example.test/EWS", lambda: session, debug_sink=diagnostics.append)
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


def test_ews_remote_operations_require_process_and_account_grants(tmp_path) -> None:
    store = MailboxStore(tmp_path / "mailbox.db")
    service = MailboxService(store, policy=MailboxRuntimePolicy(read_enabled=False, write_enabled=False))
    service.configure_account(
        account_id="ops",
        mailbox_address="ops@example.test",
        endpoint="https://exchange.example.test/EWS/Exchange.asmx",
        auth_mode="ntlm",
        credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
        folders=["inbox"],
        read_enabled=True,
        write_enabled=True,
    )

    with pytest.raises(PermissionError, match="EWS reads are disabled"):
        service.sync("ops")

    write_gated = MailboxService(store, policy=MailboxRuntimePolicy(read_enabled=True, write_enabled=False))
    proposal = write_gated.propose_action(
        account_id="ops",
        folder_id="drafts",
        operation="create_draft",
        target_identity="",
        target_change_key="",
        parameters={"subject": "Local draft", "body_text": "Offline", "recipients": ["recipient@example.test"]},
    )
    write_gated.approve(proposal["proposal_id"])

    with pytest.raises(PermissionError, match="EWS writes are disabled"):
        write_gated.execute(proposal["proposal_id"])

    store.configure_account(
        "ops",
        "ews",
        mailbox_address="ops@example.test",
        endpoint="https://exchange.example.test/EWS/Exchange.asmx",
        auth_mode="ntlm",
        credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
        read_enabled=True,
        write_enabled=False,
    )
    account_gated = MailboxService(store, policy=MailboxRuntimePolicy(read_enabled=True, write_enabled=True))
    with pytest.raises(PermissionError, match="EWS writes are disabled"):
        account_gated.execute(proposal["proposal_id"])
