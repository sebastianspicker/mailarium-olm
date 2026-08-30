"""Compact SOAP gateway for the supported EWS mailbox operations."""

from __future__ import annotations

import re
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Iterable
from dataclasses import dataclass
from xml.etree.ElementTree import Element
from xml.sax.saxutils import escape

from defusedxml import ElementTree

from .errors import EWSFaultError, EWSHTTPError, EWSValidationError
from .paging import IndexedPage
from .transport import EWSTransport

_M = "http://schemas.microsoft.com/exchange/services/2006/messages"
_T = "http://schemas.microsoft.com/exchange/services/2006/types"
_NS = {"m": _M, "t": _T}
_NUMERIC_CHARACTER_REFERENCE = re.compile(rb"&#(?:(?P<decimal>[0-9]+)|[xX](?P<hexadecimal>[0-9A-Fa-f]+));")
# These mail-message types can occur in physical IPF.Note folders. CalendarItem
# is intentionally excluded so calendar reads continue to fail closed.
_MAIL_ITEM_TYPES = frozenset(
    {
        "Message",
        "MeetingMessage",
        "MeetingRequest",
        "MeetingResponse",
        "MeetingCancellation",
    }
)
_DISTINGUISHED_FOLDER_IDS = frozenset(
    {
        "archivemsgfolderroot",
        "calendar",
        "contacts",
        "deleteditems",
        "drafts",
        "inbox",
        "junkemail",
        "msgfolderroot",
        "outbox",
        "publicfoldersroot",
        "root",
        "sentitems",
        "tasks",
    }
)


@dataclass(frozen=True)
class EWSItem:
    """Represent the supported EWS message fields returned by mailbox reads."""

    item_id: str
    change_key: str | None
    subject: str
    sender: str | None = None
    body_text: str | None = None
    received_at: str | None = None
    internet_message_id: str | None = None
    recipients: tuple[str, ...] = ()
    cc_recipients: tuple[str, ...] = ()
    bcc_recipients: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    importance: str | None = None
    is_read: bool = True
    conversation_id: str | None = None
    attachments: tuple[EWSAttachment, ...] = ()


@dataclass(frozen=True)
class EWSItemRef:
    """Identify an EWS item and its optional concurrency change key."""

    item_id: str
    change_key: str | None


@dataclass(frozen=True)
class EWSFolder:
    """Represent one physical, mail-capable EWS folder."""

    folder_id: str
    display_name: str
    folder_class: str
    total_count: int


@dataclass(frozen=True)
class EWSOperationResult:
    """Capture item references returned by a completed EWS mutation."""

    operation: str
    items: tuple[EWSItemRef, ...] = ()

    @property
    def item_ids(self) -> tuple[str, ...]:
        """Return only the item identifiers from the mutation result."""
        return tuple(item.item_id for item in self.items)


@dataclass(frozen=True)
class EWSAttachment:
    """Represent bounded attachment metadata and optional decoded file content."""

    attachment_id: str
    name: str | None = None
    content_type: str | None = None
    size: int = 0
    is_inline: bool = False
    content: bytes | None = None
    attachment_type: str = "file"


@dataclass(frozen=True)
class EWSSyncDelta:
    """Represent one EWS synchronization page and its continuation watermark."""

    created: tuple[EWSItemRef, ...]
    updated: tuple[EWSItemRef, ...]
    deleted: tuple[EWSItemRef, ...]
    watermark: str | None
    has_more: bool
    raw_change_count: int | None = None


class EWSGateway:
    """Serializes a deliberately small EWS read/write surface."""

    def __init__(
        self,
        transport: EWSTransport,
        *,
        version: str = "Exchange2016",
        mailbox_address: str | None = None,
    ) -> None:
        self.transport = transport
        self.version = _required(version, "version")
        self.mailbox_address = _required(mailbox_address, "mailbox_address") if mailbox_address is not None else None

    def find_items(self, folder_id: str, *, page: IndexedPage | None = None) -> tuple[EWSItem, ...]:
        """List shallow message summaries from one bounded EWS folder page."""
        page = page or IndexedPage()
        body = (
            '<m:FindItem Traversal="Shallow"><m:ItemShape><t:BaseShape>IdOnly</t:BaseShape>'
            '<t:AdditionalProperties><t:FieldURI FieldURI="item:Subject"/>'
            '<t:FieldURI FieldURI="message:From"/></t:AdditionalProperties></m:ItemShape>'
            f'<m:IndexedPageItemView MaxEntriesReturned="{page.size}" Offset="{page.offset}" BasePoint="Beginning"/>'
            f"<m:ParentFolderIds>{self._folder_ref(folder_id, 'folder_id')}"
            "</m:ParentFolderIds></m:FindItem>"
        )
        root = self._execute("FindItem", body)
        items: list[EWSItem] = []
        for node in root.findall(".//t:Message", _NS):
            identifier = node.find("t:ItemId", _NS)
            if identifier is None or not identifier.get("Id"):
                continue
            items.append(_parse_item(node))
        return tuple(items)

    def find_items_by_proposal_id(self, folder_id: str, proposal_id: str) -> tuple[EWSItemRef, ...]:
        """Find draft/sent items carrying the durable proposal correlation value."""
        body = (
            '<m:FindItem Traversal="Shallow"><m:ItemShape><t:BaseShape>IdOnly</t:BaseShape></m:ItemShape>'
            "<m:Restriction><t:IsEqualTo>"
            '<t:ExtendedFieldURI DistinguishedPropertySetId="PublicStrings" '
            'PropertyName="MailariumProposalId" PropertyType="String"/>'
            f'<t:FieldURIOrConstant><t:Constant Value="{_attr(proposal_id, "proposal_id")}"/>'
            "</t:FieldURIOrConstant></t:IsEqualTo></m:Restriction>"
            f"<m:ParentFolderIds>{self._folder_ref(folder_id, 'folder_id')}"
            "</m:ParentFolderIds></m:FindItem>"
        )
        root = self._execute("FindItem", body)
        return _refs(root.findall(".//t:Message/t:ItemId", _NS))

    def find_mail_folders(self) -> tuple[EWSFolder, ...]:
        """List physical mail folders below the explicitly scoped mailbox root."""
        if self.mailbox_address is None:
            raise EWSValidationError("mailbox_address is required to discover mail folders")
        page = IndexedPage()
        folders: list[EWSFolder] = []
        while True:
            body = (
                '<m:FindFolder Traversal="Deep"><m:FolderShape><t:BaseShape>IdOnly</t:BaseShape>'
                '<t:AdditionalProperties><t:FieldURI FieldURI="folder:DisplayName"/>'
                '<t:FieldURI FieldURI="folder:FolderClass"/><t:FieldURI FieldURI="folder:TotalCount"/>'
                "</t:AdditionalProperties></m:FolderShape>"
                f'<m:IndexedPageFolderView MaxEntriesReturned="{page.size}" Offset="{page.offset}" BasePoint="Beginning"/>'
                f"<m:ParentFolderIds>{self._folder_ref('msgfolderroot', 'folder_id')}"
                "</m:ParentFolderIds></m:FindFolder>"
            )
            root = self._execute("FindFolder", body)
            root_folder = root.find(".//m:RootFolder", _NS)
            if root_folder is None:
                raise EWSFaultError("MalformedResponse", "missing EWS FindFolder root")
            nodes = tuple(root_folder.findall("t:Folders/*", _NS))
            folders.extend(folder for node in nodes if (folder := _parse_mail_folder(node)) is not None)
            if _includes_last_item(root_folder):
                return tuple(folders)
            if not nodes:
                raise EWSFaultError("MalformedResponse", "EWS FindFolder returned an empty partial page")
            page = IndexedPage(offset=_next_folder_page_offset(root_folder, page.offset), size=page.size)

    def get_items(self, item_ids: Iterable[EWSItemRef]) -> tuple[EWSItem, ...]:
        """Fetch complete supported message fields for the supplied EWS item references."""
        identifiers = tuple(item_ids)
        if not identifiers:
            raise EWSValidationError("at least one item is required")
        body = (
            "<m:GetItem><m:ItemShape><t:BaseShape>IdOnly</t:BaseShape><t:BodyType>Text</t:BodyType>"
            '<t:AdditionalProperties><t:FieldURI FieldURI="item:Subject"/><t:FieldURI FieldURI="item:Body"/>'
            '<t:FieldURI FieldURI="message:From"/><t:FieldURI FieldURI="message:ToRecipients"/>'
            '<t:FieldURI FieldURI="message:CcRecipients"/><t:FieldURI FieldURI="message:BccRecipients"/>'
            '<t:FieldURI FieldURI="message:InternetMessageId"/><t:FieldURI FieldURI="message:IsRead"/>'
            '<t:FieldURI FieldURI="item:DateTimeReceived"/><t:FieldURI FieldURI="item:ConversationId"/>'
            '<t:FieldURI FieldURI="item:Categories"/><t:FieldURI FieldURI="item:Importance"/>'
            '<t:FieldURI FieldURI="item:Attachments"/></t:AdditionalProperties></m:ItemShape><m:ItemIds>'
            + "".join(_item_ref(item.item_id, item.change_key) for item in identifiers)
            + "</m:ItemIds></m:GetItem>"
        )
        root = self._execute("GetItem", body)
        return tuple(_parse_item(node) for node in _mail_item_nodes(root))

    def update_item(
        self,
        item_id: str,
        change_key: str,
        *,
        is_read: bool | None = None,
        categories: Iterable[str] | None = None,
        importance: str | None = None,
        follow_up: bool | None = None,
        subject: str | None = None,
        body_text: str | None = None,
        recipients: Iterable[str] | None = None,
        proposal_id: str | None = None,
    ) -> EWSOperationResult:
        """Update supported message fields without overwriting conflicting remote changes."""
        updates = _update_fields(
            is_read=is_read,
            categories=categories,
            importance=importance,
            follow_up=follow_up,
            subject=subject,
            body_text=body_text,
            recipients=recipients,
            proposal_id=proposal_id,
        )
        if not updates:
            raise EWSValidationError("at least one supported item field is required")
        body = (
            '<m:UpdateItem ConflictResolution="NeverOverwrite" MessageDisposition="SaveOnly">'
            "<m:ItemChanges><t:ItemChange>"
            f"{_item_id(item_id, change_key)}<t:Updates>{updates}</t:Updates>"
            "</t:ItemChange></m:ItemChanges></m:UpdateItem>"
        )
        return self._mutation("UpdateItem", body)

    def move_item(self, item_id: str, change_key: str, destination_folder_id: str) -> EWSOperationResult:
        """Move one EWS item to the destination folder using its change key."""
        return self._item_destination("MoveItem", item_id, change_key, destination_folder_id)

    def copy_item(self, item_id: str, change_key: str, destination_folder_id: str) -> EWSOperationResult:
        """Copy one EWS item to the destination folder using its change key."""
        return self._item_destination("CopyItem", item_id, change_key, destination_folder_id)

    def delete_to_deleted_items(self, item_id: str, change_key: str) -> EWSOperationResult:
        """Move one EWS item into Deleted Items using its change key."""
        body = (
            f'<m:DeleteItem DeleteType="MoveToDeletedItems"><m:ItemIds>{_item_id(item_id, change_key)}</m:ItemIds></m:DeleteItem>'
        )
        return self._mutation("DeleteItem", body)

    def create_text_draft(
        self, subject: str, body_text: str, recipients: Iterable[str], *, proposal_id: str | None = None
    ) -> EWSOperationResult:
        """Create a text-only EWS draft in Drafts, optionally correlated to a proposal."""
        recipient_nodes = "".join(
            f"<t:Mailbox><t:EmailAddress>{escape(_required(value, 'recipient'))}</t:EmailAddress></t:Mailbox>"
            for value in recipients
        )
        if not recipient_nodes:
            raise EWSValidationError("at least one recipient is required")
        body = (
            '<m:CreateItem MessageDisposition="SaveOnly"><m:SavedItemFolderId>'
            f"{self._folder_ref('drafts', 'folder_id')}</m:SavedItemFolderId><m:Items><t:Message>"
            f"<t:Subject>{escape(_required(subject, 'subject'))}</t:Subject>"
            f'<t:Body BodyType="Text">{escape(_required(body_text, "body_text"))}</t:Body>'
            f"<t:ToRecipients>{recipient_nodes}</t:ToRecipients>{_proposal_property(proposal_id)}"
            "</t:Message></m:Items></m:CreateItem>"
        )
        return self._mutation("CreateItem", body)

    def send_existing_draft(self, item_id: str, change_key: str, *, proposal_id: str | None = None) -> EWSOperationResult:
        """Send an existing draft and preserve an optional proposal correlation value."""
        if proposal_id is not None:
            correlated = self.update_item(item_id, change_key, proposal_id=proposal_id)
            if correlated.items:
                item_id = correlated.items[0].item_id
                change_key = correlated.items[0].change_key or change_key
        body = (
            '<m:SendItem SaveItemToFolder="true"><m:ItemIds>'
            f"{_item_id(item_id, change_key)}</m:ItemIds><m:SavedItemFolderId>"
            f"{self._folder_ref('sentitems', 'folder_id')}</m:SavedItemFolderId></m:SendItem>"
        )
        return self._mutation("SendItem", body)

    def sync_folder_items(
        self,
        folder_id: str,
        *,
        watermark: str | None = None,
        max_changes: int = 100,
    ) -> EWSSyncDelta:
        """Return created, updated, and deleted references since a folder watermark."""
        if not 1 <= max_changes <= 100:
            raise EWSValidationError("max_changes must be 1..100")
        sync_state = f"<m:SyncState>{escape(watermark)}</m:SyncState>" if watermark else ""
        body = (
            "<m:SyncFolderItems><m:ItemShape><t:BaseShape>IdOnly</t:BaseShape></m:ItemShape>"
            f"<m:SyncFolderId>{self._folder_ref(folder_id, 'folder_id')}"
            f"</m:SyncFolderId>{sync_state}"
            f"<m:MaxChangesReturned>{max_changes}</m:MaxChangesReturned></m:SyncFolderItems>"
        )
        root = self._execute("SyncFolderItems", body)
        changes = root.find(".//m:Changes", _NS)
        if changes is None:
            raise EWSFaultError("MalformedResponse", "missing EWS sync changes")
        created, updated, deleted = _parse_sync_changes(changes)
        return EWSSyncDelta(
            created=created,
            updated=updated,
            deleted=deleted,
            watermark=root.findtext(".//m:SyncState", default=None, namespaces=_NS),
            has_more=root.findtext(".//m:IncludesLastItemInRange", default="true", namespaces=_NS).casefold() != "true",
            raw_change_count=len(changes),
        )

    def get_attachment(self, attachment_id: str, *, max_content_bytes: int = 1_000_000) -> EWSAttachment:
        """Fetch one file attachment while enforcing a decoded-content size limit."""
        if max_content_bytes < 1:
            raise EWSValidationError("max_content_bytes must be positive")
        body = (
            "<m:GetAttachment><m:AttachmentIds>"
            f'<t:AttachmentId Id="{_attr(attachment_id, "attachment_id")}"/>'
            "</m:AttachmentIds></m:GetAttachment>"
        )
        root = self._execute("GetAttachment", body)
        node = root.find(".//t:FileAttachment", _NS)
        if node is None:
            raise EWSFaultError("MalformedResponse", "missing EWS attachment")
        try:
            content = b64decode(node.findtext("t:Content", default="", namespaces=_NS), validate=True)
        except Base64Error as exc:
            raise EWSFaultError("MalformedResponse", "invalid EWS attachment content") from exc
        if len(content) > max_content_bytes:
            raise EWSValidationError("EWS attachment exceeds content limit")
        identifier = node.find("t:AttachmentId", _NS)
        return EWSAttachment(
            attachment_id=identifier.get("Id", attachment_id) if identifier is not None else attachment_id,
            name=node.findtext("t:Name", default=None, namespaces=_NS),
            content_type=node.findtext("t:ContentType", default=None, namespaces=_NS),
            size=len(content),
            is_inline=node.findtext("t:IsInline", default="false", namespaces=_NS).casefold() == "true",
            content=content,
        )

    def _item_destination(self, operation: str, item_id: str, change_key: str, folder_id: str) -> EWSOperationResult:
        body = (
            f"<m:{operation}><m:ToFolderId>{self._folder_ref(folder_id, 'destination_folder_id')}"
            f"</m:ToFolderId><m:ItemIds>{_item_id(item_id, change_key)}</m:ItemIds></m:{operation}>"
        )
        return self._mutation(operation, body)

    def _folder_ref(self, value: str, name: str) -> str:
        return _folder_ref(value, name, mailbox_address=self.mailbox_address)

    def _mutation(self, operation: str, body: str) -> EWSOperationResult:
        root = self._execute(operation, body)
        return EWSOperationResult(operation=operation, items=_refs(root.findall(".//t:ItemId", _NS)))

    def _execute(self, operation: str, body: str):
        envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:m="{_M}" xmlns:t="{_T}"><s:Header><t:RequestServerVersion Version="{_attr(self.version, "version")}"/>'
            f"</s:Header><s:Body>{body}</s:Body></s:Envelope>"
        ).encode()
        http_status: int | None = None
        try:
            response_body = self.transport.execute(operation, envelope)
        except EWSHTTPError as exc:
            response_body = exc.body
            http_status = exc.status_code
        try:
            root = ElementTree.fromstring(_replace_illegal_xml_numeric_character_references(response_body))
        except ElementTree.ParseError as exc:
            raise EWSFaultError(
                "MalformedResponse",
                "invalid EWS XML response",
                http_status=http_status,
            ) from exc
        fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
        if fault is not None:
            raise EWSFaultError(
                "SOAPFault",
                fault.findtext("faultstring", default="EWS SOAP fault"),
                http_status=http_status,
            )
        message = root.find(".//m:ResponseMessages/*", _NS)
        if message is None:
            raise EWSFaultError(
                "MalformedResponse",
                "missing EWS response message",
                http_status=http_status,
            )
        code = message.findtext("m:ResponseCode", default="ErrorUnknown", namespaces=_NS)
        if message.get("ResponseClass") != "Success" or code != "NoError":
            detail = message.findtext("m:MessageText", default="EWS operation failed", namespaces=_NS)
            raise EWSFaultError(code, detail, http_status=http_status)
        return root


def _refs(nodes: Iterable[Element]) -> tuple[EWSItemRef, ...]:
    return tuple(
        EWSItemRef(item_id=node.get("Id", ""), change_key=node.get("ChangeKey"))
        for node in nodes
        if getattr(node, "get", lambda *_: None)("Id")
    )


def _parse_sync_changes(
    changes: Iterable[Element],
) -> tuple[
    tuple[EWSItemRef, ...],
    tuple[EWSItemRef, ...],
    tuple[EWSItemRef, ...],
]:
    created: list[EWSItemRef] = []
    updated: list[EWSItemRef] = []
    deleted: list[EWSItemRef] = []
    for change in changes:
        change_type = str(change.tag).rsplit("}", 1)[-1]
        if change_type in {"Create", "Update"}:
            identifier = _sync_mail_item_id(change)
        elif change_type in {"Delete", "ReadFlagChange"}:
            identifier = change.find("t:ItemId", _NS)
        else:
            raise EWSFaultError(
                "UnsupportedSyncChange",
                "EWS returned an unsupported synchronization change type",
            )
        if identifier is None or not identifier.get("Id"):
            raise EWSFaultError(
                "UnsupportedSyncChange",
                "EWS synchronization change lacks a supported message identity",
            )
        ref = EWSItemRef(identifier.get("Id", ""), identifier.get("ChangeKey"))
        if change_type == "Create":
            created.append(ref)
        elif change_type == "Delete":
            deleted.append(ref)
        else:
            updated.append(ref)
    return tuple(created), tuple(updated), tuple(deleted)


def _mail_item_nodes(root: Element) -> tuple[Element, ...]:
    """Return direct GetItem results from the supported EWS mail-item family."""
    return tuple(item for items in root.findall(".//m:Items", _NS) for item in items if _element_type(item) in _MAIL_ITEM_TYPES)


def _sync_mail_item_id(change: Element) -> Element | None:
    """Return the identity of a direct, supported mail item in a sync change."""
    for item in change:
        if _element_type(item) in _MAIL_ITEM_TYPES:
            return item.find("t:ItemId", _NS)
    return None


def _element_type(node: Element) -> str:
    """Return an EWS element's local name without accepting a namespace wildcard."""
    return str(node.tag).rsplit("}", 1)[-1]


def _replace_illegal_xml_numeric_character_references(response_body: bytes) -> bytes:
    """Replace only XML 1.0-invalid numeric references before safe XML parsing."""

    def replace(match: re.Match[bytes]) -> bytes:
        decimal = match.group("decimal")
        digits = decimal or match.group("hexadecimal")
        base = 10 if decimal is not None else 16
        codepoint = _numeric_character_reference_value(digits, base)
        return match.group(0) if _is_xml_10_character(codepoint) else b"&#xFFFD;"

    return _NUMERIC_CHARACTER_REFERENCE.sub(replace, response_body)


def _numeric_character_reference_value(digits: bytes, base: int) -> int:
    """Parse a numeric reference without converting arbitrarily large integers."""
    start = next((index for index, digit in enumerate(digits) if digit != ord("0")), len(digits))
    significant_length = len(digits) - start
    maximum_digits = 7 if base == 10 else 6
    if significant_length > maximum_digits:
        return -1
    return int(digits[start:], base) if significant_length else 0


def _is_xml_10_character(codepoint: int) -> bool:
    """Return whether a Unicode code point may appear in an XML 1.0 character reference."""
    return (
        codepoint in {0x9, 0xA, 0xD}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _parse_mail_folder(node: Element) -> EWSFolder | None:
    """Project only physical IPF.Note folders from a FindFolder result."""
    if _element_type(node) != "Folder":
        return None
    identifier = node.find("t:FolderId", _NS)
    folder_id = identifier.get("Id") if identifier is not None else None
    folder_class = node.findtext("t:FolderClass", default=None, namespaces=_NS)
    if not folder_id or not folder_class or not folder_class.startswith("IPF.Note"):
        return None
    total_count = _folder_total_count(node)
    return EWSFolder(
        folder_id=folder_id,
        display_name=node.findtext("t:DisplayName", default="", namespaces=_NS),
        folder_class=folder_class,
        total_count=total_count,
    )


def _folder_total_count(node: Element) -> int:
    """Return a non-negative mail-folder count, defaulting an omitted count to zero."""
    value = node.findtext("t:TotalCount", default=None, namespaces=_NS)
    if value is None:
        return 0
    try:
        total_count = int(value)
    except ValueError as exc:
        raise EWSFaultError("MalformedResponse", "invalid EWS folder total count") from exc
    if total_count < 0:
        raise EWSFaultError("MalformedResponse", "invalid EWS folder total count")
    return total_count


def _includes_last_item(root_folder: Element) -> bool:
    """Read a required FindFolder continuation marker without assuming completion."""
    value = root_folder.get("IncludesLastItemInRange")
    if value is None or value.casefold() not in {"true", "false"}:
        raise EWSFaultError("MalformedResponse", "invalid EWS FindFolder continuation marker")
    return value.casefold() == "true"


def _next_folder_page_offset(root_folder: Element, current_offset: int) -> int:
    """Require a forward server paging offset for an incomplete folder page."""
    try:
        next_offset = int(root_folder.get("IndexedPagingOffset", ""))
    except ValueError as exc:
        raise EWSFaultError("MalformedResponse", "missing EWS FindFolder paging offset") from exc
    if next_offset <= current_offset:
        raise EWSFaultError("MalformedResponse", "EWS FindFolder returned a non-advancing partial page")
    return next_offset


def _parse_item(node) -> EWSItem:
    identifier = node.find("t:ItemId", _NS)
    if identifier is None or not identifier.get("Id"):
        raise EWSFaultError("MalformedResponse", "item response lacks ItemId")
    attachment_nodes = node.findall("t:Attachments/*", _NS)
    attachments = tuple(_parse_attachment_metadata(child) for child in attachment_nodes)
    return EWSItem(
        item_id=identifier.get("Id", ""),
        change_key=identifier.get("ChangeKey"),
        subject=node.findtext("t:Subject", default="", namespaces=_NS),
        sender=node.findtext("t:From/t:Mailbox/t:EmailAddress", default=None, namespaces=_NS),
        body_text=node.findtext("t:Body", default=None, namespaces=_NS),
        received_at=node.findtext("t:DateTimeReceived", default=None, namespaces=_NS),
        internet_message_id=node.findtext("t:InternetMessageId", default=None, namespaces=_NS),
        recipients=_text_values(node, "t:ToRecipients/t:Mailbox/t:EmailAddress"),
        cc_recipients=_text_values(node, "t:CcRecipients/t:Mailbox/t:EmailAddress"),
        bcc_recipients=_text_values(node, "t:BccRecipients/t:Mailbox/t:EmailAddress"),
        categories=_text_values(node, "t:Categories/t:String"),
        importance=node.findtext("t:Importance", default=None, namespaces=_NS),
        is_read=node.findtext("t:IsRead", default="true", namespaces=_NS).casefold() == "true",
        conversation_id=_conversation_id(node),
        attachments=attachments,
    )


def _text_values(node, path: str) -> tuple[str, ...]:
    """Return text values from a repeated EWS element path in document order."""
    return tuple(element.text or "" for element in node.findall(path, _NS))


def _conversation_id(node) -> str | None:
    """Return the optional EWS conversation identifier."""
    conversation = node.find("t:ConversationId", _NS)
    return conversation.get("Id") if conversation is not None else None


def _parse_attachment_metadata(node) -> EWSAttachment:
    identifier = node.find("t:AttachmentId", _NS)
    attachment_type = "item" if str(node.tag).endswith("ItemAttachment") else "file"
    return EWSAttachment(
        attachment_id=identifier.get("Id", "") if identifier is not None else "",
        name=node.findtext("t:Name", default=None, namespaces=_NS),
        content_type=node.findtext("t:ContentType", default=None, namespaces=_NS),
        size=int(node.findtext("t:Size", default="0", namespaces=_NS) or 0),
        is_inline=node.findtext("t:IsInline", default="false", namespaces=_NS).casefold() == "true",
        attachment_type=attachment_type,
    )


def _proposal_property(proposal_id: str | None) -> str:
    if proposal_id is None:
        return ""
    return (
        '<t:ExtendedProperty><t:ExtendedFieldURI DistinguishedPropertySetId="PublicStrings" '
        'PropertyName="MailariumProposalId" PropertyType="String"/>'
        f"<t:Value>{escape(_required(proposal_id, 'proposal_id'))}</t:Value></t:ExtendedProperty>"
    )


def _update_fields(
    *,
    is_read: bool | None,
    categories: Iterable[str] | None,
    importance: str | None,
    follow_up: bool | None,
    subject: str | None,
    body_text: str | None,
    recipients: Iterable[str] | None,
    proposal_id: str | None,
) -> str:
    fields = (
        _read_update(is_read),
        _categories_update(categories),
        _importance_update(importance),
        _follow_up_update(follow_up),
        _subject_update(subject),
        _body_update(body_text),
        _recipients_update(recipients),
        _proposal_update(proposal_id),
    )
    return "".join(field for field in fields if field)


def _read_update(is_read: bool | None) -> str:
    if is_read is None:
        return ""
    return _set_field(
        "message:IsRead",
        f"<t:Message><t:IsRead>{str(is_read).lower()}</t:IsRead></t:Message>",
    )


def _categories_update(categories: Iterable[str] | None) -> str:
    if categories is None:
        return ""
    values = "".join(f"<t:String>{escape(_required(value, 'category'))}</t:String>" for value in categories)
    return _set_field(
        "item:Categories",
        f"<t:Message><t:Categories>{values}</t:Categories></t:Message>",
    )


def _importance_update(importance: str | None) -> str:
    if importance is None:
        return ""
    normalized = _required(importance, "importance")
    if normalized not in {"Low", "Normal", "High"}:
        raise EWSValidationError("importance must be Low, Normal, or High")
    return _set_field(
        "item:Importance",
        f"<t:Message><t:Importance>{normalized}</t:Importance></t:Message>",
    )


def _follow_up_update(follow_up: bool | None) -> str:
    if follow_up is None:
        return ""
    status = "Flagged" if follow_up else "NotFlagged"
    flag = f"<t:Flag><t:FlagStatus>{status}</t:FlagStatus></t:Flag>"
    return _set_field("item:Flag", f"<t:Message>{flag}</t:Message>")


def _subject_update(subject: str | None) -> str:
    if subject is None:
        return ""
    return _set_field(
        "item:Subject",
        f"<t:Message><t:Subject>{escape(_required(subject, 'subject'))}</t:Subject></t:Message>",
    )


def _body_update(body_text: str | None) -> str:
    if body_text is None:
        return ""
    return _set_field(
        "item:Body",
        f'<t:Message><t:Body BodyType="Text">{escape(_required(body_text, "body_text"))}</t:Body></t:Message>',
    )


def _recipients_update(recipients: Iterable[str] | None) -> str:
    if recipients is None:
        return ""
    addresses = "".join(
        f"<t:Mailbox><t:EmailAddress>{escape(_required(value, 'recipient'))}</t:EmailAddress></t:Mailbox>" for value in recipients
    )
    if not addresses:
        raise EWSValidationError("at least one recipient is required")
    return _set_field(
        "message:ToRecipients",
        f"<t:Message><t:ToRecipients>{addresses}</t:ToRecipients></t:Message>",
    )


def _proposal_update(proposal_id: str | None) -> str:
    if proposal_id is None:
        return ""
    return (
        "<t:SetItemField><t:ExtendedFieldURI "
        'DistinguishedPropertySetId="PublicStrings" '
        'PropertyName="MailariumProposalId" PropertyType="String"/>'
        f"<t:Message>{_proposal_property(proposal_id)}</t:Message></t:SetItemField>"
    )


def _set_field(field_uri: str, value: str) -> str:
    return f'<t:SetItemField><t:FieldURI FieldURI="{field_uri}"/>{value}</t:SetItemField>'


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EWSValidationError(f"{name} is required")
    return value


def _attr(value: str, name: str) -> str:
    return escape(_required(value, name), {'"': "&quot;"})


def _folder_ref(value: str, name: str, *, mailbox_address: str | None = None) -> str:
    folder_id = _required(value, name)
    normalized = folder_id.casefold()
    element = "DistinguishedFolderId" if normalized in _DISTINGUISHED_FOLDER_IDS else "FolderId"
    identifier = normalized if element == "DistinguishedFolderId" else folder_id
    if element == "FolderId" or mailbox_address is None:
        return f'<t:{element} Id="{_attr(identifier, name)}"/>'
    mailbox = escape(_required(mailbox_address, "mailbox_address"))
    return (
        f'<t:{element} Id="{_attr(identifier, name)}">'
        f"<t:Mailbox><t:EmailAddress>{mailbox}</t:EmailAddress></t:Mailbox>"
        f"</t:{element}>"
    )


def _item_id(item_id: str, change_key: str) -> str:
    return f'<t:ItemId Id="{_attr(item_id, "item_id")}" ChangeKey="{_attr(change_key, "change_key")}"/>'


def _item_ref(item_id: str, change_key: str | None) -> str:
    """Serialize an EWS item reference, permitting GetItem without a change key."""
    if change_key:
        return _item_id(item_id, change_key)
    return f'<t:ItemId Id="{_attr(item_id, "item_id")}"/>'
