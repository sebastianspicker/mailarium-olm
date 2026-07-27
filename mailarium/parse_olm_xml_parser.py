"""Archive traversal and XML parsing helpers for ``parse_olm``."""
# pylint: disable=no-member,c-extension-no-member


# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from logging import Logger
from typing import TYPE_CHECKING, Any, cast

from lxml import etree

from .body_forensics import extract_source_headers
from .olm_xml_helpers import (
    _apply_attachment_payload_metadata,
    _detect_namespace,
    _extract_address_details,
    _extract_addresses,
    _extract_attachment_contents,
    _extract_attachment_payloads,
    _extract_attachments,
    _extract_categories,
    _extract_exchange_list,
    _extract_exchange_meetings,
    _extract_exchange_smart_links,
    _extract_folder,
    _extract_html_body,
    _extract_meeting_data,
    _find,
    _find_text,
    _new_xml_parser,
    _parse_references,
    _read_limited_bytes,
)
from .parse_olm_postprocess import ParsedEmailEnrichments, ParsedEmailParts
from .rfc2822 import _normalize_date, _parse_int

if TYPE_CHECKING:
    from .parse_olm import Email


XmlNamespace = dict[str, str]


def parse_olm_archive_impl(
    olm_path: str,
    *,
    extract_attachments: bool,
    max_xml_files: int,
    max_total_xml_bytes: int,
    max_xml_bytes: int,
    logger: Logger,
    parse_email_xml_fn: Callable[[bytes, str], Email | None],
) -> Iterator[Email]:
    """Walk an OLM archive and yield parsed emails."""
    with zipfile.ZipFile(olm_path, "r") as zf:
        limits = _ArchiveLimits(max_xml_files, max_total_xml_bytes, max_xml_bytes)
        processed = _ArchiveProgress()
        for info in zf.infolist():
            if not _is_message_xml(info.filename):
                continue
            if _should_stop_archive_parse(info, processed, limits, logger):
                break
            email, size, xml_bytes = _parse_archive_member(zf, info, limits, logger, parse_email_xml_fn)
            if size is None:
                continue
            processed.files += 1
            processed.bytes += size
            if email:
                if extract_attachments:
                    _populate_attachment_contents(email, zf, info.filename, xml_bytes, logger)
                _clear_transient_xml(email)
                yield email


@dataclass
class _ArchiveProgress:
    """Track archive members and uncompressed bytes accepted during parsing."""

    files: int = 0
    bytes: int = 0


@dataclass(frozen=True)
class _ArchiveLimits:
    """Define per-archive and per-member limits that protect OLM extraction."""

    max_files: int
    max_total_bytes: int
    max_bytes: int


def _is_message_xml(path: str) -> bool:
    normalized = path.lower()
    return normalized.endswith(".xml") and "com.microsoft.__messages" in normalized


def _should_stop_archive_parse(info: zipfile.ZipInfo, progress: _ArchiveProgress, limits: _ArchiveLimits, logger: Logger) -> bool:
    if progress.files >= limits.max_files:
        logger.warning("Stopping parse due to MAX_XML_FILES limit (%s).", limits.max_files)
        return True
    if progress.bytes + info.file_size > limits.max_total_bytes:
        logger.warning("Stopping parse due to MAX_TOTAL_XML_BYTES limit (%s).", limits.max_total_bytes)
        return True
    return False


def _parse_archive_member(
    zf: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    limits: _ArchiveLimits,
    logger: Logger,
    parser: Callable[[bytes, str], Email | None],
) -> tuple[Email | None, int | None, bytes]:
    if info.file_size > limits.max_bytes:
        logger.warning("Skipping oversized XML payload (%s bytes): %s", info.file_size, info.filename)
        return None, None, b""
    try:
        with zf.open(info.filename) as file_obj:
            xml_bytes = _read_limited_bytes(file_obj, byte_limit=limits.max_bytes)
        if len(xml_bytes) > limits.max_total_bytes:
            logger.warning("Skipping XML payload exceeding MAX_TOTAL_XML_BYTES limit: %s", info.filename)
            return None, None, b""
        return parser(xml_bytes, info.filename), len(xml_bytes), xml_bytes
    except Exception as exc:  # pragma: no cover - defensive branch  # pylint: disable=broad-exception-caught
        logger.warning("Failed to parse %s: %s", info.filename, exc)
        return None, None, b""


def _populate_attachment_contents(email: Email, zf: zipfile.ZipFile, xml_path: str, xml_bytes: bytes, logger: Logger) -> None:
    """Attach bounded archive payloads to parsed attachment metadata in matching order."""
    transient = cast(Any, email)
    transient._attachment_payload_extraction_failed = False
    transient._attachment_payload_extraction_error = ""
    try:
        root = getattr(email, "_olm_root", None)
        ns = getattr(email, "_olm_ns", None)
        if isinstance(root, etree._Element) and isinstance(ns, dict):
            payloads = _extract_attachment_payloads(root, ns, xml_path, zf)
            email.attachment_contents = [
                (str(item.get("name") or ""), cast(bytes, item.get("content") or b""))
                for item in payloads
                if item.get("content") is not None and str(item.get("name") or "")
            ]
            _apply_attachment_payload_metadata(getattr(email, "attachments", []) or [], payloads)
        else:
            email.attachment_contents = _extract_attachment_contents(xml_bytes, xml_path, zf)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Attachment extraction failed for %s: %s", xml_path, exc)
        email.attachment_contents = []
        transient._attachment_payload_extraction_failed = True
        transient._attachment_payload_extraction_error = str(exc)


def _clear_transient_xml(email: Email) -> None:
    """Release XML-only references once durable parsed fields are extracted."""
    for attr_name in ("_olm_root", "_olm_ns"):
        if hasattr(email, attr_name):
            delattr(email, attr_name)


def build_parsed_email_from_parts_impl(
    parts: ParsedEmailParts,
    enrichments: ParsedEmailEnrichments,
    *,
    email_cls: type[Email],
) -> Email:
    """Construct an Email while preserving parsed fields and derived enrichment values."""
    attachment_names = [name for name in parts.attachment_names if isinstance(name, str)]
    return email_cls(
        message_id=parts.message_id,
        subject=parts.subject,
        sender_name=parts.sender_name,
        sender_email=parts.sender_email,
        to=parts.to_addresses,
        cc=parts.cc_addresses,
        bcc=parts.bcc_addresses,
        to_identities=parts.to_identities,
        cc_identities=parts.cc_identities,
        bcc_identities=parts.bcc_identities,
        recipient_identity_source=parts.recipient_identity_source,
        date=parts.date,
        body_text=parts.body_text,
        body_html=parts.body_html,
        folder=parts.folder,
        has_attachments=bool(attachment_names),
        preview_text=parts.preview,
        raw_body_text=parts.raw_body_text,
        raw_body_html=parts.raw_body_html,
        raw_source=parts.raw_source,
        raw_source_headers=parts.raw_source_headers,
        forensic_body_text=enrichments.forensic_body_text,
        forensic_body_source=enrichments.forensic_body_source,
        attachment_names=attachment_names,
        attachments=parts.attachments,
        conversation_id=parts.conversation_id,
        in_reply_to=parts.in_reply_to,
        references=parts.references,
        reply_context_from=enrichments.reply_context_from,
        reply_context_to=enrichments.reply_context_to,
        reply_context_subject=enrichments.reply_context_subject,
        reply_context_date=enrichments.reply_context_date,
        reply_context_source=enrichments.reply_context_source,
        segments=enrichments.segments,
        priority=parts.priority,
        is_read=parts.is_read,
        categories=parts.categories,
        thread_topic=parts.thread_topic,
        thread_index=parts.thread_index,
        inference_classification=parts.inference_classification,
        is_calendar_message=parts.is_calendar_message,
        meeting_data=parts.meeting_data,
        exchange_extracted_links=parts.exchange_extracted_links,
        exchange_extracted_emails=parts.exchange_extracted_emails,
        exchange_extracted_contacts=parts.exchange_extracted_contacts,
        exchange_extracted_meetings=parts.exchange_extracted_meetings,
    )


def parse_email_xml_impl(
    xml_bytes: bytes,
    source_path: str,
    *,
    logger: Logger,
    extract_identity_addresses_fn: Callable[[list[str]], list[str]],
    apply_source_header_fallbacks_fn: Callable[[ParsedEmailParts], None],
    finalize_parsed_email_parts_fn: Callable[[ParsedEmailParts], None],
    derive_email_enrichments_fn: Callable[[ParsedEmailParts, str], ParsedEmailEnrichments],
    build_parsed_email_from_parts_fn: Callable[[ParsedEmailParts, ParsedEmailEnrichments], Email],
) -> Email | None:
    """Parse a single email XML file from the OLM archive."""
    try:
        root = etree.fromstring(xml_bytes, parser=_new_xml_parser())
    except etree.XMLSyntaxError as exc:
        logger.warning("Failed to parse email XML %s: %s", source_path, exc)
        return None

    ns = _detect_namespace(root)
    parts = _parse_email_parts(root, ns, source_path, extract_identity_addresses_fn)
    apply_source_header_fallbacks_fn(parts)
    finalize_parsed_email_parts_fn(parts)
    enrichments = derive_email_enrichments_fn(parts, source_path)
    email = build_parsed_email_from_parts_fn(parts, enrichments)
    transient_email = cast(Any, email)
    transient_email._olm_root = root
    transient_email._olm_ns = ns
    return email


def _parse_email_parts(
    root: etree._Element, ns: XmlNamespace, source_path: str, identity_extractor: Callable[[list[str]], list[str]]
) -> ParsedEmailParts:
    fields = _email_text_fields(root, ns, source_path)
    fields.update(_email_recipient_fields(root, ns, identity_extractor))
    fields.update(_email_message_fields(root, ns))
    return ParsedEmailParts(**fields)


def _email_text_fields(root: etree._Element, ns: XmlNamespace, source_path: str) -> dict[str, Any]:
    body_text = _element_text(_find(root, "OPFMessageCopyBody", ns))
    body_html_element = _find(root, "OPFMessageCopyHTMLBody", ns)
    body_html = _extract_html_body(body_html_element) if body_html_element is not None else ""
    raw_source = _element_text(_find(root, "OPFMessageCopySource", ns))
    attachment_names, attachments = _extract_attachments(root, ns)
    return {
        "message_id": _find_text(root, "OPFMessageCopyMessageID", ns),
        "subject": _find_text(root, "OPFMessageCopySubject", ns),
        "date": _normalize_date(_find_text(root, "OPFMessageCopySentTime", ns)),
        "body_text": body_text,
        "body_html": body_html,
        "folder": _extract_folder(source_path),
        "preview": _find_text(root, "OPFMessageCopyPreview", ns),
        "raw_body_text": body_text,
        "raw_body_html": body_html,
        "raw_source": raw_source,
        "raw_source_headers": extract_source_headers(raw_source),
        "attachment_names": attachment_names,
        "attachments": attachments,
    }


def _email_recipient_fields(
    root: etree._Element, ns: XmlNamespace, identity_extractor: Callable[[list[str]], list[str]]
) -> dict[str, Any]:
    to_addresses = _extract_addresses(root, ns, "OPFMessageCopyToAddresses")
    if not to_addresses:
        to_addresses = [name.strip() for name in _find_text(root, "OPFMessageCopyDisplayTo", ns).split(";") if name.strip()]
    sender_name, sender_email = _sender_fields(root, ns)
    cc_addresses = _extract_addresses(root, ns, "OPFMessageCopyCCAddresses")
    bcc_addresses = _extract_addresses(root, ns, "OPFMessageCopyBCCAddresses")
    identities = (identity_extractor(to_addresses), identity_extractor(cc_addresses), identity_extractor(bcc_addresses))
    return {
        "sender_name": sender_name,
        "sender_email": sender_email,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
        "bcc_addresses": bcc_addresses,
        "to_identities": identities[0],
        "cc_identities": identities[1],
        "bcc_identities": identities[2],
        "recipient_identity_source": "structured_xml" if any(identities) else "",
    }


def _sender_fields(root: etree._Element, ns: XmlNamespace) -> tuple[str, str]:
    sender_email = _element_text(_find(root, "OPFMessageCopySenderAddress", ns))
    sender_name = _element_text(_find(root, "OPFMessageCopySenderName", ns))
    pairs = _extract_address_details(root, ns, "OPFMessageCopyFromAddresses")
    fallback_name, fallback_email = pairs[0] if pairs else ("", "")
    return sender_name or fallback_name, sender_email or fallback_email


def _email_message_fields(root: etree._Element, ns: XmlNamespace) -> dict[str, Any]:
    is_calendar_raw = _find_text(root, "OPFMessageCopyIsCalendarMessage", ns)
    return {
        "conversation_id": _find_text(root, "OPFMessageCopyExchangeConversationId", ns),
        "in_reply_to": _find_text(root, "OPFMessageCopyInReplyTo", ns),
        "references": _parse_references(_find_text(root, "OPFMessageCopyReferences", ns)),
        "priority": _parse_int(_find_text(root, "OPFMessageGetPriority", ns), default=0),
        "is_read": _find_text(root, "OPFMessageGetIsRead", ns).lower() != "false",
        "categories": _extract_categories(root, ns),
        "thread_topic": _find_text(root, "OPFMessageCopyThreadTopic", ns),
        "thread_index": _find_text(root, "OPFMessageCopyThreadIndex", ns),
        "inference_classification": _find_text(root, "OPFMessageCopyInferenceClassification", ns),
        "is_calendar_message": is_calendar_raw.lower() == "true" if is_calendar_raw else False,
        "meeting_data": _extract_meeting_data(root, ns),
        "exchange_extracted_links": _extract_exchange_smart_links(root, ns),
        "exchange_extracted_emails": _extract_exchange_list(root, ns, "OPFMessageGetExchangeExtractedEmails"),
        "exchange_extracted_contacts": _extract_exchange_list(root, ns, "OPFMessageGetExchangeExtractedContacts"),
        "exchange_extracted_meetings": _extract_exchange_meetings(root, ns),
    }


def _element_text(element: etree._Element | None) -> str:
    return "".join(str(part) for part in element.itertext()) if element is not None else ""
