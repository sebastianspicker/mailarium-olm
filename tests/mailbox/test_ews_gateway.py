"""Exercise SOAP serialization, parsing, validation, and transport failure handling for EWS gateway operations."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from mailarium.ews.errors import EWSAuthenticationError, EWSFaultError, EWSValidationError
from mailarium.ews.gateway import EWSGateway, EWSItemRef
from mailarium.ews.paging import IndexedPage, next_page
from mailarium.ews.transport import EWSHTTPSSession, EWSTransport

FIXTURES = Path(__file__).parent / "fixtures"


class FixtureTransport:
    def __init__(self, response_name: str) -> None:
        self.response_name = response_name
        self.calls: list[tuple[str, bytes]] = []

    def execute(self, operation: str, envelope: bytes) -> bytes:
        self.calls.append((operation, envelope))
        return (FIXTURES / self.response_name).read_bytes()


def test_find_items_parses_public_fixture_and_serializes_bounded_page() -> None:
    transport = FixtureTransport("find_item_success.xml")

    items = EWSGateway(transport).find_items("inbox-id", page=IndexedPage(offset=10, size=20))

    assert items[0].item_id == "item-1"
    assert items[0].change_key == "ck-1"
    assert items[0].subject == "Fixture subject"
    request = transport.calls[0][1].decode()
    assert 'MaxEntriesReturned="20" Offset="10"' in request
    assert 'Id="inbox-id"' in request


def test_gateway_escapes_the_server_version_as_an_xml_attribute() -> None:
    transport = FixtureTransport("find_item_success.xml")

    EWSGateway(transport, version='Exchange"2016').find_items("inbox-id")

    assert b'Version="Exchange&amp;quot;2016"' not in transport.calls[0][1]
    assert b'Version="Exchange&quot;2016"' in transport.calls[0][1]


@pytest.mark.parametrize(
    ("method", "expected_operation", "needle"),
    [
        (lambda gateway: gateway.update_item("id", "ck", is_read=True), "UpdateItem", "<t:IsRead>true</t:IsRead>"),
        (lambda gateway: gateway.move_item("id", "ck", "archive"), "MoveItem", '<t:FolderId Id="archive"/>'),
        (lambda gateway: gateway.copy_item("id", "ck", "archive"), "CopyItem", '<t:FolderId Id="archive"/>'),
        (lambda gateway: gateway.delete_to_deleted_items("id", "ck"), "DeleteItem", 'DeleteType="MoveToDeletedItems"'),
        (
            lambda gateway: gateway.create_text_draft("subject", "plain body", ["person@example.test"]),
            "CreateItem",
            'BodyType="Text"',
        ),
        (lambda gateway: gateway.send_existing_draft("id", "ck"), "SendItem", 'SaveItemToFolder="true"'),
    ],
)
def test_supported_writes_serialize_against_fixture(method, expected_operation, needle) -> None:
    transport = FixtureTransport("mutation_success.xml")

    result = method(EWSGateway(transport))

    assert result.operation == expected_operation
    assert result.item_ids == ("result-1",)
    assert transport.calls[0][0] == expected_operation
    assert needle in transport.calls[0][1].decode()


def test_fault_fixture_becomes_typed_error() -> None:
    with pytest.raises(EWSFaultError, match="ErrorAccessDenied"):
        EWSGateway(FixtureTransport("fault_access_denied.xml")).send_existing_draft("id", "ck")


def test_rejects_empty_draft_body_and_nonadvancing_page() -> None:
    gateway = EWSGateway(FixtureTransport("mutation_success.xml"))
    with pytest.raises(EWSValidationError):
        gateway.create_text_draft("subject", "", ["person@example.test"])
    assert next_page(offset=0, returned=0, includes_last_item=False, cap=100) is None


def test_get_items_returns_full_message_metadata_from_fixture() -> None:
    transport = FixtureTransport("get_item_full.xml")

    item = EWSGateway(transport).get_items([EWSItemRef("item-1", "ck-1")])[0]

    assert item.body_text == "Full fixture body"
    assert item.recipients == ("recipient@example.test",)
    assert item.categories == ("blue", "follow-up")
    assert item.importance == "High"
    assert item.attachments[0].attachment_id == "att-1"
    assert b"item:Attachments" in transport.calls[0][1]


def test_sync_and_attachment_primitives_are_bounded_and_fixture_driven() -> None:
    sync_transport = FixtureTransport("sync_folder_items.xml")
    delta = EWSGateway(sync_transport).sync_folder_items("inbox", watermark="old-watermark", max_changes=10)
    assert delta.watermark == "next-watermark"
    assert delta.has_more is True
    assert delta.created == (EWSItemRef("created", "created-ck"),)
    assert delta.updated == (EWSItemRef("updated", "updated-ck"),)
    assert delta.deleted == (EWSItemRef("deleted", "deleted-ck"),)
    assert b'DistinguishedFolderId Id="inbox"' in sync_transport.calls[0][1]

    attachment = EWSGateway(FixtureTransport("get_attachment.xml")).get_attachment("att-1", max_content_bytes=4)
    assert attachment.content == b"test"
    with pytest.raises(EWSValidationError, match="exceeds"):
        EWSGateway(FixtureTransport("get_attachment.xml")).get_attachment("att-1", max_content_bytes=3)


def test_distinguished_folder_requests_scope_an_explicit_mailbox() -> None:
    transport = FixtureTransport("sync_folder_items.xml")

    EWSGateway(transport, mailbox_address="mailbox@example.test").sync_folder_items("inbox")

    request = transport.calls[0][1]
    assert b'DistinguishedFolderId Id="inbox"' in request
    assert b"<t:EmailAddress>mailbox@example.test</t:EmailAddress>" in request


def test_update_allowlist_and_proposal_correlation_are_serialized() -> None:
    transport = FixtureTransport("mutation_success.xml")
    gateway = EWSGateway(transport)
    result = gateway.update_item(
        "id",
        "ck",
        is_read=False,
        categories=["blue"],
        importance="High",
        follow_up=True,
        subject="draft",
        body_text="plain",
        recipients=["recipient@example.test"],
        proposal_id="proposal-42",
    )
    assert result.items == (EWSItemRef("result-1", "new-ck"),)
    request = transport.calls[0][1].decode()
    assert 'MessageDisposition="SaveOnly"' in request
    for needle in (
        "message:IsRead",
        "item:Categories",
        "item:Importance",
        "item:Flag",
        "item:Subject",
        "item:Body",
        "message:ToRecipients",
        "MailariumProposalId",
    ):
        assert needle in request

    gateway.send_existing_draft("id", "ck", proposal_id="proposal-42")
    assert [operation for operation, _ in transport.calls[-2:]] == ["UpdateItem", "SendItem"]


def test_correlation_reconciliation_search_is_scoped_and_read_only() -> None:
    transport = FixtureTransport("find_item_success.xml")

    refs = EWSGateway(transport).find_items_by_proposal_id("sentitems", "proposal-42")

    assert refs == (EWSItemRef("item-1", "ck-1"),)
    request = transport.calls[0][1].decode()
    assert "MailariumProposalId" in request
    assert 'DistinguishedFolderId Id="sentitems"' in request
    assert 'Constant Value="proposal-42"' in request


class Response:
    status_code = 200
    content = b"<not-logged/>"


class Session:
    def post(self, *args, **kwargs):
        return Response()

    def close(self) -> None:
        pass


class RedirectSession(Session):
    def post(self, *args, **kwargs):
        return type("RedirectResponse", (), {"status_code": 302, "content": b""})()


class StructuredErrorSession(Session):
    def post(self, *args, **kwargs):
        return type(
            "StructuredErrorResponse",
            (),
            {"status_code": 500, "content": (FIXTURES / "fault_access_denied.xml").read_bytes()},
        )()


class EmptyErrorSession(Session):
    def post(self, *args, **kwargs):
        return type("EmptyErrorResponse", (), {"status_code": 503, "content": b""})()


class ExpiredWatermarkSession(Session):
    def post(self, *args, **kwargs):
        content = b"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
 <s:Body><m:SyncFolderItemsResponse><m:ResponseMessages>
  <m:SyncFolderItemsResponseMessage ResponseClass="Error">
   <m:MessageText>Sync state expired</m:MessageText>
   <m:ResponseCode>ErrorInvalidSyncStateData</m:ResponseCode>
  </m:SyncFolderItemsResponseMessage>
 </m:ResponseMessages></m:SyncFolderItemsResponse></s:Body>
</s:Envelope>"""
        return type("ExpiredWatermarkResponse", (), {"status_code": 500, "content": content})()


def test_transport_diagnostics_are_size_only() -> None:
    diagnostics: list[dict[str, object]] = []
    body = EWSTransport(
        "https://exchange.example.test/EWS/Exchange.asmx",
        Session,
        debug_sink=diagnostics.append,
    ).execute("GetItem", b"secret request body")

    assert body == b"<not-logged/>"
    assert diagnostics == [
        {
            "host": "exchange.example.test",
            "operation": "GetItem",
            "status_code": 200,
            "request_size": 19,
            "response_size": 13,
        }
    ]


def test_transport_rejects_redirects() -> None:
    with pytest.raises(EWSValidationError, match="redirects"):
        EWSTransport(
            "https://exchange.example.test/EWS/Exchange.asmx",
            RedirectSession,
        ).execute("GetItem", b"request")


def test_transport_preserves_structured_http_errors_for_gateway_classification() -> None:
    gateway = EWSGateway(
        EWSTransport(
            "https://exchange.example.test/EWS/Exchange.asmx",
            StructuredErrorSession,
        )
    )

    with pytest.raises(EWSFaultError, match="ErrorAccessDenied"):
        gateway.send_existing_draft("id", "ck")


def test_empty_http_error_becomes_a_typed_malformed_response() -> None:
    gateway = EWSGateway(
        EWSTransport(
            "https://exchange.example.test/EWS/Exchange.asmx",
            EmptyErrorSession,
        )
    )

    with pytest.raises(EWSFaultError, match="MalformedResponse"):
        gateway.send_existing_draft("id", "ck")


def test_http_500_preserves_expired_watermark_code() -> None:
    gateway = EWSGateway(
        EWSTransport(
            "https://exchange.example.test/EWS/Exchange.asmx",
            ExpiredWatermarkSession,
        )
    )

    with pytest.raises(EWSFaultError) as error_info:
        gateway.sync_folder_items("inbox", watermark="expired")

    assert error_info.value.code == "ErrorInvalidSyncStateData"


def test_urllib_http_errors_reach_transport_status_classification() -> None:
    failure = HTTPError(
        "https://exchange.example.test/EWS/Exchange.asmx",
        401,
        "Unauthorized",
        None,
        BytesIO(b"not logged"),
    )
    opener = MagicMock()
    opener.open.side_effect = failure
    with patch("mailarium.ews.transport.request.build_opener", return_value=opener):
        with pytest.raises(EWSAuthenticationError):
            EWSTransport(
                "https://exchange.example.test/EWS/Exchange.asmx",
                EWSHTTPSSession(),
            ).execute("GetItem", b"request")

    assert failure.code == 401
