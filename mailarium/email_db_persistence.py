"""Persistence helpers for EmailDatabase write paths."""
# pylint: disable=too-many-branches,too-many-locals

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from .attachment_surfaces import attachment_surface_rows_for_attachment
from .email_db_enrichment import (
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
from .parse_olm import BODY_NORMALIZATION_VERSION, Email


def build_email_insert_row(db, email: Email, ingestion_run_id: int | None):
    """Build the tuple row for inserting an email into the database.

    Extracts all fields from an Email object, serializes JSON fields,
    computes content hashes, and returns a flat tuple matching the
    email insert SQL column order.

    Args:
        db: The EmailDatabase instance (provides compute_content_hash).
        email: The Email object to serialize.
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
        db.compute_content_hash(email.clean_body) if email.clean_body else None,
        _json_attr(email, "categories", []),
        _attr(email, "thread_topic", ""),
        _attr(email, "inference_classification", ""),
        int(getattr(email, "is_calendar_message", False)),
        _json_attr(email, "references", []),
        ingestion_run_id,
    )


def _attr(value: Any, name: str, default: Any) -> Any:
    """Read an attribute while converting missing or falsey values to the default."""
    return getattr(value, name, default) or default


def _json_attr(value: Any, name: str, default: Any, *, ensure_ascii: bool = True) -> str:
    """Serialize an optional object attribute for a JSON database column."""
    return json.dumps(_attr(value, name, default), ensure_ascii=ensure_ascii)


def _email_core_insert_values(email: Email) -> tuple[Any, ...]:
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


def _email_body_insert_values(email: Email) -> tuple[Any, ...]:
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


def _email_identity_insert_values(email: Email) -> tuple[Any, ...]:
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


def _email_exchange_insert_values(email: Email) -> tuple[Any, ...]:
    """Order Exchange transport metadata for persistence."""
    return (
        _json_attr(email, "meeting_data", {}, ensure_ascii=False),
        _json_attr(email, "exchange_extracted_links", [], ensure_ascii=False),
        _json_attr(email, "exchange_extracted_emails", [], ensure_ascii=False),
        _json_attr(email, "exchange_extracted_contacts", [], ensure_ascii=False),
        _json_attr(email, "exchange_extracted_meetings", [], ensure_ascii=False),
    )


def _email_inference_insert_values(email: Email) -> tuple[Any, ...]:
    """Order inferred thread and classification fields for persistence."""
    return (
        _attr(email, "inferred_parent_uid", ""),
        _attr(email, "inferred_thread_id", ""),
        _attr(email, "inferred_match_reason", ""),
        float(_attr(email, "inferred_match_confidence", 0.0)),
    )


def collect_category_rows(email: Email) -> list[tuple[str, str]]:
    """Collect category rows for an email.

    Args:
        email: The Email object to extract categories from.

    Returns:
        A list of tuples containing (email_uid, category) for each category
        associated with the email.
    """
    return [(email.uid, cat) for cat in (getattr(email, "categories", []) or [])]


def collect_attachment_rows(email: Email) -> list[tuple]:
    """Collect attachment rows for an email.

    Args:
        email: The Email object to extract attachments from.

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
    email: Email,
) -> list[tuple]:
    """Collect attachment surface rows for an email.

    Args:
        email: The Email object to extract attachment surfaces from.

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


def collect_recipients_and_pairs(email: Email) -> tuple[list[tuple], list[tuple[str, str]]]:
    """Collect recipient rows and all-recipient pairs for an email.

    Builds recipient rows for to, cc, and bcc fields and also returns
    a flat list of (display_name, email_address) pairs.

    Args:
        email: The Email object.

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


def persist_single_related_rows(cur, db, email: Email, *, infer_parent: bool = True) -> None:
    """Persist all related rows (categories, attachments, surfaces, etc.) for a single email.

    Inserts categories, attachments, attachment surfaces, recipients,
    message segments, thread inference, contacts, and communication edges
    using the given cursor.

    Args:
        cur: An active sqlite3.Cursor.
        db: The EmailDatabase instance.
        email: The Email object.
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


def _persist_single_attachments(cur: Any, email: Email) -> None:
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


def _persist_single_recipients(cur: Any, email: Email) -> tuple[list[tuple], list[tuple[str, str]]]:
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


def _persist_single_contacts(cur: Any, email: Email, all_recipients: list[tuple[str, str]]) -> None:
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
class _BatchRows:
    """Group related database rows so a batch can be persisted atomically."""

    recipients: list[tuple] = field(default_factory=list)
    categories: list[tuple] = field(default_factory=list)
    attachments: list[tuple] = field(default_factory=list)
    attachment_surfaces: list[tuple] = field(default_factory=list)
    contacts: list[tuple] = field(default_factory=list)
    edges: list[tuple] = field(default_factory=list)
    segments: list[tuple] = field(default_factory=list)


def _collect_batch_related_rows(cur: Any, email: Email, rows: _BatchRows) -> None:
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


def _persist_batch_rows(cur: Any, rows: _BatchRows) -> None:
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


def insert_email_impl(db, email: Email, *, ingestion_run_id: int | None = None) -> bool:
    """Insert a single email and its related rows in a transaction.

    Returns False on integrity error (e.g., duplicate) without raising.

    Args:
        db: The EmailDatabase instance.
        email: The Email object to insert.
        ingestion_run_id: Optional ingestion run identifier.

    Returns:
        True if the email was inserted, False if it was a duplicate
        (integrity error).
    """
    cur = db.conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(db._email_insert_sql, build_email_insert_row(db, email, ingestion_run_id))
        persist_single_related_rows(cur, db, email)
        db.conn.commit()
    except db._sqlite_integrity_error:
        db.conn.rollback()
        return False
    except Exception:
        db.conn.rollback()
        raise
    return True


def insert_emails_batch_impl(
    db,
    emails: list[Email],
    *,
    ingestion_run_id: int | None = None,
    commit: bool = True,
) -> set[str]:
    """Insert multiple emails in batch, collecting all related rows.

    Uses a single transaction (when commit=True) to insert emails and
    bulk-insert all related categories, attachments, surfaces, recipients,
    segments, contacts, and edges.

    Args:
        db: The EmailDatabase instance.
        emails: List of Email objects to insert.
        ingestion_run_id: Optional ingestion run identifier.
        commit: Whether to commit the transaction. Defaults to True.

    Returns:
        A set of UIDs that were successfully inserted (new records only).
    """
    inserted_uids: set[str] = set()
    cur = db.conn.cursor()

    rows = _BatchRows()

    try:
        if commit:
            cur.execute("BEGIN IMMEDIATE")
        for email in emails:
            cur.execute(db._email_insert_or_ignore_sql, build_email_insert_row(db, email, ingestion_run_id))
            if cur.rowcount == 0:
                continue

            _collect_batch_related_rows(cur, email, rows)
            inserted_uids.add(email.uid)
        _persist_batch_rows(cur, rows)
        if commit:
            db.conn.commit()
    except Exception:
        if commit:
            db.conn.rollback()
        raise
    return inserted_uids
