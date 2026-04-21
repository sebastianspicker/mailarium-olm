"""Archive traversal and XML parsing helpers for ``parse_olm``."""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Generator
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


def parse_olm_archive_impl(
    olm_path: str,
    *,
    extract_attachments: bool,
    max_xml_files: int,
    max_total_xml_bytes: int,
    max_xml_bytes: int,
    logger: Logger,
    parse_email_xml_fn: Callable[[bytes, str], Email | None],
) -> Generator[Email, None, None]:
    """Walk an OLM archive and yield parsed emails."""
    with zipfile.ZipFile(olm_path, "r") as zf:
        processed_xml_files = 0
        processed_xml_bytes = 0

        for info in zf.infolist():
            xml_path = info.filename
            normalized_path = xml_path.lower()
            if not normalized_path.endswith(".xml") or "com.microsoft.__messages" not in normalized_path:
                continue

            if processed_xml_files >= max_xml_files:
                logger.warning("Stopping parse due to MAX_XML_FILES limit (%s).", max_xml_files)
                break

            if processed_xml_bytes + info.file_size > max_total_xml_bytes:
                logger.warning("Stopping parse due to MAX_TOTAL_XML_BYTES limit (%s).", max_total_xml_bytes)
                break

            try:
                if info.file_size > max_xml_bytes:
                    logger.warning("Skipping oversized XML payload (%s bytes): %s", info.file_size, xml_path)
                    continue
                processed_xml_files += 1
                with zf.open(xml_path) as file_obj:
                    xml_bytes = _read_limited_bytes(file_obj, byte_limit=max_xml_bytes)
                    if processed_xml_bytes + len(xml_bytes) > max_total_xml_bytes:
                        logger.warning("Stopping parse due to MAX_TOTAL_XML_BYTES limit (%s).", max_total_xml_bytes)
                        break
                    processed_xml_bytes += len(xml_bytes)
                    email = parse_email_xml_fn(xml_bytes, xml_path)
                    if email and extract_attachments:
                        transient_email = cast(Any, email)
                        transient_email._attachment_payload_extraction_failed = False
                        transient_email._attachment_payload_extraction_error = ""
                        root = getattr(email, "_olm_root", None)
                        ns = getattr(email, "_olm_ns", None)
                        try:
                            if isinstance(root, etree._Element) and isinstance(ns, dict):
                                payloads = _extract_attachment_payloads(root, ns, xml_path, zf)
                                email.attachment_contents = [
                                    (
                                        str(payload.get("name") or ""),
                                        cast(bytes, payload.get("content") or b""),
                                    )
                                    for payload in payloads
                                    if payload.get("content") is not None and str(payload.get("name") or "")
                                ]
                                _apply_attachment_payload_metadata(getattr(email, "attachments", []) or [], payloads)
                            else:
                                email.attachment_contents = _extract_attachment_contents(xml_bytes, xml_path, zf)
                        except Exception as exc:
                            logger.warning("Attachment extraction failed for %s: %s", xml_path, exc)
                            email.attachment_contents = []
                            transient_email._attachment_payload_extraction_failed = True
                            transient_email._attachment_payload_extraction_error = str(exc)
                    if email:
                        for attr_name in ("_olm_root", "_olm_ns"):
                            if hasattr(email, attr_name):
                                delattr(email, attr_name)
                        yield email
            except Exception as exc:  # pragma: no cover - defensive branch
                logger.warning("Failed to parse %s: %s", xml_path, exc)


def build_parsed_email_from_parts_impl(
    parts: ParsedEmailParts,
    enrichments: ParsedEmailEnrichments,
    *,
    email_cls: type[Email],
) -> Email:
    """Build the public Email object from parsed parts and enrichments."""
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
    folder = _extract_folder(source_path)

    message_id = _find_text(root, "OPFMessageCopyMessageID", ns)
    subject = _find_text(root, "OPFMessageCopySubject", ns)
    date = _normalize_date(_find_text(root, "OPFMessageCopySentTime", ns))
    body_text_el = _find(root, "OPFMessageCopyBody", ns)
    body_text = "".join(str(part) for part in body_text_el.itertext()) if body_text_el is not None else ""
    body_html_el = _find(root, "OPFMessageCopyHTMLBody", ns)
    body_html = _extract_html_body(body_html_el) if body_html_el is not None else ""
    raw_body_text = body_text
    raw_body_html = body_html
    preview = _find_text(root, "OPFMessageCopyPreview", ns)

    sender_el = _find(root, "OPFMessageCopySenderAddress", ns)
    sender_name_el = _find(root, "OPFMessageCopySenderName", ns)
    sender_email = sender_el.text if sender_el is not None and sender_el.text else ""
    sender_name = sender_name_el.text if sender_name_el is not None and sender_name_el.text else ""

    to_addresses = _extract_addresses(root, ns, "OPFMessageCopyToAddresses")
    cc_addresses = _extract_addresses(root, ns, "OPFMessageCopyCCAddresses")
    bcc_addresses = _extract_addresses(root, ns, "OPFMessageCopyBCCAddresses")
    to_identities = extract_identity_addresses_fn(to_addresses)
    cc_identities = extract_identity_addresses_fn(cc_addresses)
    bcc_identities = extract_identity_addresses_fn(bcc_addresses)
    recipient_identity_source = "structured_xml" if (to_identities or cc_identities or bcc_identities) else ""

    if not to_addresses:
        display_to = _find_text(root, "OPFMessageCopyDisplayTo", ns)
        if display_to:
            to_addresses = [name.strip() for name in display_to.split(";") if name.strip()]

    if not sender_email or not sender_name:
        from_pairs = _extract_address_details(root, ns, "OPFMessageCopyFromAddresses")
        if from_pairs:
            if not sender_name and from_pairs[0][0]:
                sender_name = from_pairs[0][0]
            if not sender_email and from_pairs[0][1]:
                sender_email = from_pairs[0][1]

    conversation_id = _find_text(root, "OPFMessageCopyExchangeConversationId", ns)
    in_reply_to = _find_text(root, "OPFMessageCopyInReplyTo", ns)
    references_raw = _find_text(root, "OPFMessageCopyReferences", ns)
    references = _parse_references(references_raw)
    priority = _parse_int(_find_text(root, "OPFMessageGetPriority", ns), default=0)
    is_read = _find_text(root, "OPFMessageGetIsRead", ns).lower() != "false"

    categories = _extract_categories(root, ns)
    thread_topic = _find_text(root, "OPFMessageCopyThreadTopic", ns)
    thread_index = _find_text(root, "OPFMessageCopyThreadIndex", ns)
    inference_classification = _find_text(root, "OPFMessageCopyInferenceClassification", ns)
    is_calendar_raw = _find_text(root, "OPFMessageCopyIsCalendarMessage", ns)
    is_calendar_message = is_calendar_raw.lower() == "true" if is_calendar_raw else False
    meeting_data = _extract_meeting_data(root, ns)
    exchange_extracted_links = _extract_exchange_smart_links(root, ns)
    exchange_extracted_emails = _extract_exchange_list(root, ns, "OPFMessageGetExchangeExtractedEmails")
    exchange_extracted_contacts = _extract_exchange_list(root, ns, "OPFMessageGetExchangeExtractedContacts")
    exchange_extracted_meetings = _extract_exchange_meetings(root, ns)

    raw_source_el = _find(root, "OPFMessageCopySource", ns)
    raw_source = "".join(str(part) for part in raw_source_el.itertext()) if raw_source_el is not None else ""
    raw_source_headers = extract_source_headers(raw_source)
    attachment_names, attachments = _extract_attachments(root, ns)

    parts = ParsedEmailParts(
        message_id=message_id,
        subject=subject,
        sender_name=sender_name,
        sender_email=sender_email,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        to_identities=to_identities,
        cc_identities=cc_identities,
        bcc_identities=bcc_identities,
        recipient_identity_source=recipient_identity_source,
        date=date,
        body_text=body_text,
        body_html=body_html,
        folder=folder,
        preview=preview,
        raw_body_text=raw_body_text,
        raw_body_html=raw_body_html,
        raw_source=raw_source,
        raw_source_headers=raw_source_headers,
        attachment_names=attachment_names,
        attachments=attachments,
        conversation_id=conversation_id,
        in_reply_to=in_reply_to,
        references=references,
        priority=priority,
        is_read=is_read,
        categories=categories,
        thread_topic=thread_topic,
        thread_index=thread_index,
        inference_classification=inference_classification,
        is_calendar_message=is_calendar_message,
        meeting_data=meeting_data,
        exchange_extracted_links=exchange_extracted_links,
        exchange_extracted_emails=exchange_extracted_emails,
        exchange_extracted_contacts=exchange_extracted_contacts,
        exchange_extracted_meetings=exchange_extracted_meetings,
    )
    apply_source_header_fallbacks_fn(parts)
    finalize_parsed_email_parts_fn(parts)
    enrichments = derive_email_enrichments_fn(parts, source_path)
    email = build_parsed_email_from_parts_fn(parts, enrichments)
    transient_email = cast(Any, email)
    transient_email._olm_root = root
    transient_email._olm_ns = ns
    return email
