"""Row builders and cursor-level persistence steps for message writes."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from mailarium.model import Message
from mailarium.model.attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from mailarium.model.attachment_surfaces import attachment_surface_rows_for_attachment
from mailarium.model.body_normalization import BODY_NORMALIZATION_VERSION

from ..sql import sql_in_placeholders as _sql_in_placeholders
from ..sql import validate_sql_identifiers as _validate_sql_identifiers
from .custody import compute_content_hash
from .message_enrichment import (
    contact_row,
    edge_row,
    execute_contact_upserts,
    execute_edge_upserts,
    infer_and_persist_match,
    recipient_rows_for_type,
    segment_rows_for_email,
    upsert_communication_edge,
    upsert_contact,
)

_EMAIL_INSERT_COLUMNS = (
    "uid",
    "message_id",
    "subject",
    "sender_name",
    "sender_email",
    "date",
    "folder",
    "email_type",
    "has_attachments",
    "attachment_count",
    "priority",
    "is_read",
    "conversation_id",
    "in_reply_to",
    "base_subject",
    "body_length",
    "body_text",
    "body_html",
    "raw_body_text",
    "raw_body_html",
    "raw_source",
    "raw_source_headers_json",
    "forensic_body_text",
    "forensic_body_source",
    "normalized_body_source",
    "body_normalization_version",
    "body_kind",
    "body_empty_reason",
    "recovery_strategy",
    "recovery_confidence",
    "to_identities_json",
    "cc_identities_json",
    "bcc_identities_json",
    "recipient_identity_source",
    "reply_context_from",
    "reply_context_to_json",
    "reply_context_subject",
    "reply_context_date",
    "reply_context_source",
    "meeting_data_json",
    "exchange_extracted_links_json",
    "exchange_extracted_emails_json",
    "exchange_extracted_contacts_json",
    "exchange_extracted_meetings_json",
    "inferred_parent_uid",
    "inferred_thread_id",
    "inferred_match_reason",
    "inferred_match_confidence",
    "content_sha256",
    "categories",
    "thread_topic",
    "inference_classification",
    "is_calendar_message",
    "references_json",
    "ingestion_run_id",
)
_EMAIL_INSERT_COLUMNS_VALIDATED = _validate_sql_identifiers(list(_EMAIL_INSERT_COLUMNS))
EMAIL_INSERT_SQL = f"""INSERT INTO emails ({", ".join(_EMAIL_INSERT_COLUMNS_VALIDATED)})
VALUES ({_sql_in_placeholders(_EMAIL_INSERT_COLUMNS_VALIDATED)})"""
EMAIL_INSERT_OR_IGNORE_SQL = EMAIL_INSERT_SQL.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)


def build_email_insert_row(email: Message, ingestion_run_id: int | None):
    """Build the tuple row for inserting an email into the database.

    Extracts all fields from an Message object, serializes JSON fields,
    computes content hashes, and returns a flat tuple matching the
    email insert SQL column order.

    Args:
        email: The Message object to serialize.
        ingestion_run_id: Optional ingestion run identifier.

    Returns:
        A tuple of all email column values in insert order.
    """
    return (
        *_email_core_insert_values(email),
        *_email_body_insert_values(email),
        *_email_identity_insert_values(email),
        *_email_exchange_insert_values(email),
        *_email_inference_insert_values(email),
        compute_content_hash(email.clean_body) if email.clean_body else None,
        _json_attr(email, "categories", []),
        _attr(email, "thread_topic", ""),
        _attr(email, "inference_classification", ""),
        int(getattr(email, "is_calendar_message", False)),
        _json_attr(email, "references", []),
        ingestion_run_id,
    )


def build_v7_email_update_row(email: Message) -> tuple[Any, ...]:
    """Build the metadata row used by the schema-v7 email update statement."""
    return (
        _json_attr(email, "categories", []),
        _attr(email, "thread_topic", ""),
        _attr(email, "inference_classification", ""),
        int(getattr(email, "is_calendar_message", False)),
        _json_attr(email, "references", []),
        *_email_exchange_insert_values(email),
        email.uid,
    )


def _attr(value: Any, name: str, default: Any) -> Any:
    """Read an attribute while converting missing or falsey values to the default."""
    return getattr(value, name, default) or default


def _json_attr(value: Any, name: str, default: Any, *, ensure_ascii: bool = True) -> str:
    """Serialize an optional object attribute for a JSON database column."""
    return json.dumps(_attr(value, name, default), ensure_ascii=ensure_ascii)


def _email_core_insert_values(email: Message) -> tuple[Any, ...]:
    """Order core identity and envelope fields for the email insert statement."""
    return (
        email.uid,
        email.message_id,
        email.subject,
        email.sender_name,
        email.sender_email,
        email.date,
        email.folder,
        email.email_type,
        int(email.has_attachments),
        len(email.attachment_names),
        email.priority,
        int(email.is_read),
        email.conversation_id,
        email.in_reply_to,
        email.base_subject,
        len(email.clean_body),
    )


def _email_body_insert_values(email: Message) -> tuple[Any, ...]:
    """Order body, recovery, and source-text fields for persistence."""
    return (
        email.clean_body,
        email.body_html,
        _attr(email, "raw_body_text", ""),
        _attr(email, "raw_body_html", ""),
        _attr(email, "raw_source", ""),
        _json_attr(email, "raw_source_headers", {}),
        _attr(email, "forensic_body_text", ""),
        _attr(email, "forensic_body_source", ""),
        _attr(email, "clean_body_source", "body_text"),
        _attr(email, "body_normalization_version", BODY_NORMALIZATION_VERSION),
        _attr(email, "body_kind", "content"),
        _attr(email, "body_empty_reason", ""),
        _attr(email, "recovery_strategy", ""),
        float(_attr(email, "recovery_confidence", 0.0)),
    )


def _email_identity_insert_values(email: Message) -> tuple[Any, ...]:
    """Order sender and recipient identity fields for persistence."""
    return (
        _json_attr(email, "to_identities", []),
        _json_attr(email, "cc_identities", []),
        _json_attr(email, "bcc_identities", []),
        _attr(email, "recipient_identity_source", ""),
        _attr(email, "reply_context_from", ""),
        _json_attr(email, "reply_context_to", []),
        _attr(email, "reply_context_subject", ""),
        _attr(email, "reply_context_date", ""),
        _attr(email, "reply_context_source", ""),
    )


def _email_exchange_insert_values(email: Message) -> tuple[Any, ...]:
    """Order Exchange transport metadata for persistence."""
    return (
        _json_attr(email, "meeting_data", {}, ensure_ascii=False),
        _json_attr(email, "exchange_extracted_links", [], ensure_ascii=False),
        _json_attr(email, "exchange_extracted_emails", [], ensure_ascii=False),
        _json_attr(email, "exchange_extracted_contacts", [], ensure_ascii=False),
        _json_attr(email, "exchange_extracted_meetings", [], ensure_ascii=False),
    )


def _email_inference_insert_values(email: Message) -> tuple[Any, ...]:
    """Order inferred thread and classification fields for persistence."""
    return (
        _attr(email, "inferred_parent_uid", ""),
        _attr(email, "inferred_thread_id", ""),
        _attr(email, "inferred_match_reason", ""),
        float(_attr(email, "inferred_match_confidence", 0.0)),
    )


def collect_category_rows(email: Message) -> list[tuple[str, str]]:
    """Collect category rows for an email.

    Args:
        email: The Message object to extract categories from.

    Returns:
        A list of tuples containing (email_uid, category) for each category
        associated with the email.
    """
    return [(email.uid, cat) for cat in (getattr(email, "categories", []) or [])]


def collect_attachment_rows(email: Message) -> list[tuple]:
    """Collect attachment rows for an email.

    Args:
        email: The Message object to extract attachments from.

    Returns:
        A list of tuples containing all attachment data for database insertion,
        including metadata, extracted text, and normalization information.
    """
    return [_attachment_insert_row(email.uid, attachment) for attachment in _attr(email, "attachments", [])]


def _attachment_insert_row(email_uid: str, attachment: dict[str, Any]) -> tuple[Any, ...]:
    """Convert one attachment into the tuple expected by the attachment insert."""
    attachment_id, content_sha256 = ensure_attachment_identity(attachment)
    extracted_text = str(attachment.get("extracted_text", "") or "")
    normalized_text = str(attachment.get("normalized_text", "") or "") or normalize_attachment_search_text(extracted_text)
    normalization_version = int(attachment.get("text_normalization_version") or 0)
    if normalized_text and normalization_version <= 0:
        normalization_version = ATTACHMENT_TEXT_NORMALIZATION_VERSION
    return (
        email_uid,
        attachment.get("name", ""),
        attachment_id,
        attachment.get("mime_type", ""),
        attachment.get("size", 0),
        content_sha256,
        attachment.get("content_id", ""),
        int(attachment.get("is_inline", False)),
        _mapping_value(attachment, "extraction_state", ""),
        _mapping_value(attachment, "evidence_strength", ""),
        int(bool(attachment.get("ocr_used", False))),
        _mapping_value(attachment, "ocr_engine", ""),
        _mapping_value(attachment, "ocr_lang", ""),
        float(_mapping_value(attachment, "ocr_confidence", 0.0)),
        _mapping_value(attachment, "failure_reason", ""),
        _mapping_value(attachment, "text_preview", ""),
        extracted_text,
        normalized_text,
        normalization_version,
        int(_mapping_value(attachment, "locator_version", 1)),
        _mapping_value(attachment, "text_source_path", ""),
        json.dumps(_mapping_value(attachment, "text_locator", {}), ensure_ascii=False),
    )


def _mapping_value(mapping: dict[str, Any], key: str, default: Any) -> Any:
    """Read a mapping key while converting missing or falsey values to the default."""
    return mapping.get(key, default) or default


def collect_attachment_surface_rows(
    email: Message,
) -> list[tuple]:
    """Collect attachment surface rows for an email.

    Args:
        email: The Message object to extract attachment surfaces from.

    Returns:
        A list of tuples containing attachment surface data for database insertion,
        including text extraction details and surface metadata for search.
    """
    rows: list[tuple] = []
    for att in getattr(email, "attachments", []) or []:
        attachment_id, _content_sha256 = ensure_attachment_identity(att)
        extracted_text = str(att.get("extracted_text", "") or "")
        normalized_text = str(att.get("normalized_text", "") or "") or normalize_attachment_search_text(extracted_text)
        rows.extend(
            attachment_surface_rows_for_attachment(
                email_uid=email.uid,
                attachment_name=str(att.get("name", "") or ""),
                attachment_id=attachment_id,
                extracted_text=extracted_text,
                normalized_text=normalized_text,
                text_locator=att.get("text_locator") or {},
                extraction_state=str(att.get("extraction_state") or ""),
                evidence_strength=str(att.get("evidence_strength") or ""),
                ocr_used=bool(att.get("ocr_used")),
                ocr_confidence=float(att.get("ocr_confidence") or 0.0),
                surfaces=att.get("surfaces"),
            )
        )
    return rows


def collect_recipients_and_pairs(email: Message) -> tuple[list[tuple], list[tuple[str, str]]]:
    """Collect recipient rows and all-recipient pairs for an email.

    Builds recipient rows for to, cc, and bcc fields and also returns
    a flat list of (display_name, email_address) pairs.

    Args:
        email: The Message object.

    Returns:
        A tuple of (recipient_rows, all_recipients) where recipient_rows
        is a list of (email_uid, address, display_name, type) tuples and
        all_recipients is a list of (display_name, email_address) tuples.
    """
    recipient_rows: list[tuple] = []
    all_recipients: list[tuple[str, str]] = []
    for rows in (
        recipient_rows_for_type(email.uid, email.to, getattr(email, "to_identities", []) or [], "to"),
        recipient_rows_for_type(email.uid, email.cc, getattr(email, "cc_identities", []) or [], "cc"),
        recipient_rows_for_type(email.uid, email.bcc, getattr(email, "bcc_identities", []) or [], "bcc"),
    ):
        recipient_rows.extend(rows)
        all_recipients.extend((row[2], row[1]) for row in rows)
    return recipient_rows, all_recipients


def persist_single_related_rows(cur, email: Message, *, infer_parent: bool = True) -> None:
    """Persist all related rows (categories, attachments, surfaces, etc.) for a single email.

    Inserts categories, attachments, attachment surfaces, recipients,
    message segments, thread inference, contacts, and communication edges
    using the given cursor.

    Args:
        cur: An active sqlite3.Cursor.
        email: The Message object.
        infer_parent: Whether to run thread inference. Defaults to True.
    """
    categories = collect_category_rows(email)
    if categories:
        cur.executemany(
            "INSERT OR IGNORE INTO email_categories(email_uid, category) VALUES(?,?)",
            categories,
        )

    _persist_single_attachments(cur, email)
    _recipient_rows, all_recipients = _persist_single_recipients(cur, email)
    if infer_parent:
        infer_and_persist_match(cur, email)
    _persist_single_contacts(cur, email, all_recipients)


def _persist_single_attachments(cur: Any, email: Message) -> None:
    """Persist single attachments while preserving the invariants of email database persistence."""
    attachments = collect_attachment_rows(email)
    attachment_surfaces = collect_attachment_surface_rows(email)
    if attachments:
        cur.executemany(
            "INSERT INTO attachments(email_uid, name, attachment_id, mime_type, size, content_sha256, content_id, "
            "is_inline, extraction_state, evidence_strength, ocr_used, ocr_engine, ocr_lang, ocr_confidence, "
            "failure_reason, text_preview, extracted_text, normalized_text, text_normalization_version, locator_version, "
            "text_source_path, text_locator_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            attachments,
        )
    if attachment_surfaces:
        cur.executemany(
            "INSERT OR REPLACE INTO attachment_surfaces("
            "surface_id, attachment_id, email_uid, attachment_name, surface_kind, origin_kind, text, normalized_text, "
            "alignment_map_json, language, language_confidence, ocr_confidence, surface_hash, locator_json, quality_json"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            attachment_surfaces,
        )


def _persist_single_recipients(cur: Any, email: Message) -> tuple[list[tuple], list[tuple[str, str]]]:
    """Persist single recipients while preserving the invariants of email database persistence."""
    recipient_rows, all_recipients = collect_recipients_and_pairs(email)
    if recipient_rows:
        cur.executemany(
            "INSERT OR IGNORE INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)",
            recipient_rows,
        )

    segment_rows = segment_rows_for_email(email.uid, getattr(email, "segments", []) or [])
    if segment_rows:
        cur.executemany(
            """INSERT INTO message_segments(
               email_uid, ordinal, segment_type, depth, text, source_surface, provenance_json
            ) VALUES(?,?,?,?,?,?,?)""",
            segment_rows,
        )
    return recipient_rows, all_recipients


def _persist_single_contacts(cur: Any, email: Message, all_recipients: list[tuple[str, str]]) -> None:
    """Persist single contacts while preserving the invariants of email database persistence."""
    if email.sender_email:
        upsert_contact(cur, email.sender_email, email.sender_name, email.date, "sender")
    for name, em in all_recipients:
        if em:
            upsert_contact(cur, em, name, email.date, "recipient")

    if email.sender_email:
        for _, em in all_recipients:
            if em:
                upsert_communication_edge(cur, email.sender_email, em, email.date)


@dataclass
class BatchRows:
    """Group related database rows so a batch can be persisted atomically."""

    recipients: list[tuple] = field(default_factory=list)
    categories: list[tuple] = field(default_factory=list)
    attachments: list[tuple] = field(default_factory=list)
    attachment_surfaces: list[tuple] = field(default_factory=list)
    contacts: list[tuple] = field(default_factory=list)
    edges: list[tuple] = field(default_factory=list)
    segments: list[tuple] = field(default_factory=list)


def collect_batch_related_rows(cur: Any, email: Message, rows: BatchRows) -> None:
    """Collect attachment, recipient, and contact rows for a batch transaction."""
    rows.categories.extend(collect_category_rows(email))
    rows.attachments.extend(collect_attachment_rows(email))
    rows.attachment_surfaces.extend(collect_attachment_surface_rows(email))
    recipient_rows, all_recipients = collect_recipients_and_pairs(email)
    rows.recipients.extend(recipient_rows)
    rows.segments.extend(segment_rows_for_email(email.uid, _attr(email, "segments", [])))
    infer_and_persist_match(cur, email)
    if email.sender_email:
        rows.contacts.append(contact_row(email.sender_email, email.sender_name, email.date, "sender"))
    for name, recipient in all_recipients:
        if recipient:
            rows.contacts.append(contact_row(recipient, name, email.date, "recipient"))
    if email.sender_email:
        rows.edges.extend(edge_row(email.sender_email, recipient, email.date) for _, recipient in all_recipients if recipient)


def persist_batch_rows(cur: Any, rows: BatchRows) -> None:
    """Persist batch rows while preserving the invariants of email database persistence."""
    statements = (
        ("INSERT OR IGNORE INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)", rows.recipients),
        (
            """INSERT INTO message_segments(
               email_uid, ordinal, segment_type, depth, text, source_surface, provenance_json
            ) VALUES(?,?,?,?,?,?,?)""",
            rows.segments,
        ),
        ("INSERT OR IGNORE INTO email_categories(email_uid, category) VALUES(?,?)", rows.categories),
        (
            "INSERT INTO attachments(email_uid, name, attachment_id, mime_type, size, content_sha256, content_id, "
            "is_inline, extraction_state, evidence_strength, ocr_used, ocr_engine, ocr_lang, ocr_confidence, "
            "failure_reason, text_preview, extracted_text, normalized_text, text_normalization_version, locator_version, "
            "text_source_path, text_locator_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows.attachments,
        ),
        (
            "INSERT OR REPLACE INTO attachment_surfaces("
            "surface_id, attachment_id, email_uid, attachment_name, surface_kind, origin_kind, text, normalized_text, "
            "alignment_map_json, language, language_confidence, ocr_confidence, surface_hash, locator_json, quality_json"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows.attachment_surfaces,
        ),
    )
    for statement, values in statements:
        if values:
            cur.executemany(statement, values)
    execute_contact_upserts(cur, rows.contacts)
    execute_edge_upserts(cur, rows.edges)


def replace_mailbox_body_evidence(conn: Any, email: Message) -> None:
    """Persist the complete EWS surface and its quoted-message segmentation."""
    existing = conn.execute("SELECT raw_source FROM emails WHERE uid=?", (email.uid,)).fetchone()
    if existing is not None and str(existing["raw_source"] or "") not in {"", "ews"}:
        return
    if email.raw_body_text or email.raw_body_html:
        conn.execute(
            "UPDATE emails SET raw_body_text=?,raw_body_html=?,forensic_body_text=?,forensic_body_source=? WHERE uid=?",
            (
                email.raw_body_text,
                email.raw_body_html,
                email.forensic_body_text,
                email.forensic_body_source,
                email.uid,
            ),
        )
    segments: list[object] = list(email.segments)
    segment_rows = segment_rows_for_email(email.uid, segments)
    if not segment_rows:
        return
    conn.execute("DELETE FROM message_segments WHERE email_uid=?", (email.uid,))
    conn.executemany(
        "INSERT INTO message_segments(email_uid,ordinal,segment_type,depth,text,source_surface,provenance_json) "
        "VALUES(?,?,?,?,?,?,?)",
        segment_rows,
    )


def replace_mailbox_recipients(conn: Any, email: Message) -> None:
    """Replace envelope recipients for a changed mailbox item."""
    conn.execute("DELETE FROM recipients WHERE email_uid=?", (email.uid,))
    rows = [
        (email.uid, address, "", kind)
        for kind, values in (("to", email.to), ("cc", email.cc), ("bcc", email.bcc))
        for address in values
        if address
    ]
    if rows:
        conn.executemany(
            "INSERT OR IGNORE INTO recipients(email_uid,address,display_name,type) VALUES(?,?,?,?)",
            rows,
        )


def _attachment_key(att: dict[str, Any]) -> tuple[str, str, int, str, int]:
    """Build the stable identity tuple used to reconcile attachment rows."""
    return (
        str(att.get("name") or ""),
        str(att.get("mime_type") or ""),
        int(att.get("size") or 0),
        str(att.get("content_id") or ""),
        int(att.get("is_inline") or 0),
    )


def _attachment_existing_indexes(
    attachments: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, int, str, int], dict[str, Any]], dict[str, dict[str, Any]]]:
    """Index existing attachments by stable ID, content hash, and ordinal."""
    by_key = {_attachment_key(att): att for att in attachments}
    by_id = {attachment_id: att for att in attachments if (attachment_id := str(att.get("attachment_id") or ""))}
    return by_key, by_id


def _attachment_value(att: dict[str, Any], existing: dict[str, Any], key: str, default: Any = "") -> Any:
    """Read an attachment field from either a mapping or object."""
    return att.get(key) or existing.get(key, default)


def _attachment_ocr_used(att: dict[str, Any], existing: dict[str, Any]) -> bool:
    """Normalize legacy and current OCR flags to one boolean."""
    value = att.get("ocr_used")
    return bool(value if value is not None else existing.get("ocr_used", False))


def _attachment_persistence_rows(
    email_uid: str, att: dict[str, Any], existing: dict[str, Any]
) -> tuple[tuple[object, ...], list[tuple]]:
    """Convert attachment objects into normalized rows for replacement persistence."""
    attachment_id, content_sha256 = ensure_attachment_identity(att)
    extracted_text = str(_attachment_value(att, existing, "extracted_text"))
    normalized_text = str(_attachment_value(att, existing, "normalized_text"))
    if extracted_text and not normalized_text:
        normalized_text = normalize_attachment_search_text(extracted_text)
    normalization_version = int(_attachment_value(att, existing, "text_normalization_version", 0))
    if normalized_text and normalization_version <= 0:
        normalization_version = ATTACHMENT_TEXT_NORMALIZATION_VERSION
    text_locator = _attachment_value(att, existing, "text_locator", {})
    ocr_used = _attachment_ocr_used(att, existing)
    row = (
        email_uid,
        att.get("name", ""),
        attachment_id,
        att.get("mime_type", ""),
        att.get("size", 0),
        content_sha256,
        att.get("content_id", ""),
        int(att.get("is_inline", False)),
        _attachment_value(att, existing, "extraction_state"),
        _attachment_value(att, existing, "evidence_strength"),
        int(ocr_used),
        _attachment_value(att, existing, "ocr_engine"),
        _attachment_value(att, existing, "ocr_lang"),
        float(_attachment_value(att, existing, "ocr_confidence", 0.0)),
        _attachment_value(att, existing, "failure_reason"),
        _attachment_value(att, existing, "text_preview"),
        extracted_text,
        normalized_text,
        normalization_version,
        int(_attachment_value(att, existing, "locator_version", 1)),
        _attachment_value(att, existing, "text_source_path"),
        json.dumps(text_locator, ensure_ascii=False),
    )
    surfaces = attachment_surface_rows_for_attachment(
        email_uid=email_uid,
        attachment_name=str(att.get("name", "") or ""),
        attachment_id=attachment_id,
        extracted_text=extracted_text,
        normalized_text=normalized_text,
        text_locator=text_locator,
        extraction_state=str(_attachment_value(att, existing, "extraction_state")),
        evidence_strength=str(_attachment_value(att, existing, "evidence_strength")),
        ocr_used=ocr_used,
        ocr_confidence=float(_attachment_value(att, existing, "ocr_confidence", 0.0)),
        surfaces=_attachment_value(att, existing, "surfaces", None),
    )
    return row, surfaces


def replace_v7_categories(cur: sqlite3.Cursor, email: Message) -> None:
    """Replace v7 categories while preserving the invariants of database lifecycle management."""
    cur.execute("DELETE FROM email_categories WHERE email_uid = ?", (email.uid,))
    categories = getattr(email, "categories", []) or []
    if categories:
        cur.executemany(
            "INSERT OR IGNORE INTO email_categories(email_uid, category) VALUES(?,?)",
            [(email.uid, category) for category in categories],
        )


def replace_v7_attachments(cur: sqlite3.Cursor, email: Message, existing_attachments: list[dict[str, Any]]) -> None:
    """Replace v7 attachments while preserving extraction metadata from *existing_attachments*."""
    existing_by_key, existing_by_id = _attachment_existing_indexes(existing_attachments)
    cur.execute("DELETE FROM attachment_surfaces WHERE email_uid = ?", (email.uid,))
    cur.execute("DELETE FROM attachments WHERE email_uid = ?", (email.uid,))
    attachments = getattr(email, "attachments", []) or []
    if not attachments:
        return
    attachment_rows: list[tuple[object, ...]] = []
    surface_rows: list[tuple] = []
    for attachment in attachments:
        attachment_id, _content_sha256 = ensure_attachment_identity(attachment)
        existing = existing_by_key.get(_attachment_key(attachment)) or existing_by_id.get(attachment_id, {})
        row, surfaces = _attachment_persistence_rows(email.uid, attachment, existing)
        attachment_rows.append(row)
        surface_rows.extend(surfaces)
    _insert_v7_attachments(cur, attachment_rows, surface_rows)


def _insert_v7_attachments(cur: sqlite3.Cursor, attachment_rows: list[tuple[object, ...]], surface_rows: list[tuple]) -> None:
    """Insert v7 attachments while preserving the invariants of database lifecycle management."""
    cur.executemany(
        "INSERT INTO attachments(email_uid, name, attachment_id, mime_type, size, content_sha256, content_id, "
        "is_inline, extraction_state, evidence_strength, ocr_used, ocr_engine, ocr_lang, ocr_confidence, "
        "failure_reason, text_preview, extracted_text, normalized_text, text_normalization_version, locator_version, "
        "text_source_path, text_locator_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        attachment_rows,
    )
    if surface_rows:
        cur.executemany(
            "INSERT OR REPLACE INTO attachment_surfaces("
            "surface_id, attachment_id, email_uid, attachment_name, surface_kind, origin_kind, text, normalized_text, "
            "alignment_map_json, language, language_confidence, ocr_confidence, surface_hash, locator_json, quality_json"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            surface_rows,
        )


def update_v7_email_row(cur: sqlite3.Cursor, email: Message) -> bool:
    """Update v7 email row while preserving the invariants of database lifecycle management."""
    cur.execute(
        """UPDATE emails
           SET categories = ?, thread_topic = ?, inference_classification = ?,
               is_calendar_message = ?, references_json = ?, meeting_data_json = ?,
               exchange_extracted_links_json = ?, exchange_extracted_emails_json = ?,
               exchange_extracted_contacts_json = ?, exchange_extracted_meetings_json = ?
         WHERE uid = ?""",
        build_v7_email_update_row(email),
    )
    return cur.rowcount > 0
