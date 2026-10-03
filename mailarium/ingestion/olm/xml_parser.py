"""Parse one OLM message XML member into a ``ParsedMessage``."""

from __future__ import annotations

import logging
from typing import Any, cast

from lxml import etree

from mailarium.ingestion.olm.xml_helpers import (
    _detect_namespace,
    _extract_address_details,
    _extract_addresses,
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
)
from mailarium.model.rfc2822 import extract_identity_addresses, normalize_date, parse_int

from ..records import ParsedMessage
from .body_forensics import extract_source_headers
from .postprocess import (
    ParsedEmailEnrichments,
    ParsedEmailParts,
    apply_source_header_fallbacks,
    derive_email_enrichments,
    finalize_parsed_email_parts,
)

logger = logging.getLogger(__name__)

XmlNamespace = dict[str, str]


def build_parsed_email_from_parts(parts: ParsedEmailParts, enrichments: ParsedEmailEnrichments) -> ParsedMessage:
    """Construct an ParsedMessage while preserving parsed fields and derived enrichment values."""
    attachment_names = [name for name in parts.attachment_names if isinstance(name, str)]
    return ParsedMessage(
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


def parse_email_xml(xml_bytes: bytes, source_path: str) -> ParsedMessage | None:
    """Parse a single email XML file from the OLM archive."""
    try:
        root = etree.fromstring(xml_bytes, parser=_new_xml_parser())
    except etree.XMLSyntaxError as exc:
        logger.warning("Failed to parse email XML %s: %s", source_path, exc)
        return None

    ns = _detect_namespace(root)
    parts = _parse_email_parts(root, ns, source_path)
    apply_source_header_fallbacks(parts)
    finalize_parsed_email_parts(parts)
    enrichments = derive_email_enrichments(parts, source_path)
    email = build_parsed_email_from_parts(parts, enrichments)
    transient_email = cast(Any, email)
    transient_email._olm_root = root
    transient_email._olm_ns = ns
    return email


def _parse_email_parts(root: etree._Element, ns: XmlNamespace, source_path: str) -> ParsedEmailParts:
    fields = _email_text_fields(root, ns, source_path)
    fields.update(_email_recipient_fields(root, ns))
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
        "date": normalize_date(_find_text(root, "OPFMessageCopySentTime", ns)),
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


def _email_recipient_fields(root: etree._Element, ns: XmlNamespace) -> dict[str, Any]:
    to_addresses = _extract_addresses(root, ns, "OPFMessageCopyToAddresses")
    if not to_addresses:
        to_addresses = [name.strip() for name in _find_text(root, "OPFMessageCopyDisplayTo", ns).split(";") if name.strip()]
    sender_name, sender_email = _sender_fields(root, ns)
    cc_addresses = _extract_addresses(root, ns, "OPFMessageCopyCCAddresses")
    bcc_addresses = _extract_addresses(root, ns, "OPFMessageCopyBCCAddresses")
    identities = (
        extract_identity_addresses(to_addresses),
        extract_identity_addresses(cc_addresses),
        extract_identity_addresses(bcc_addresses),
    )
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
        "priority": parse_int(_find_text(root, "OPFMessageGetPriority", ns), default=0),
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
