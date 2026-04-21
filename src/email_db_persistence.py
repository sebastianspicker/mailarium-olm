"""Persistence helpers for EmailDatabase write paths."""

from __future__ import annotations

import json

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
    content_sha256 = db.compute_content_hash(email.clean_body) if email.clean_body else None
    categories_json = json.dumps(getattr(email, "categories", []) or [])
    references_json = json.dumps(getattr(email, "references", []) or [])
    raw_source_headers_json = json.dumps(getattr(email, "raw_source_headers", {}) or {})
    to_identities_json = json.dumps(getattr(email, "to_identities", []) or [])
    cc_identities_json = json.dumps(getattr(email, "cc_identities", []) or [])
    bcc_identities_json = json.dumps(getattr(email, "bcc_identities", []) or [])
    recipient_identity_source = getattr(email, "recipient_identity_source", "") or ""
    reply_context_to_json = json.dumps(getattr(email, "reply_context_to", []) or [])
    meeting_data_json = json.dumps(getattr(email, "meeting_data", {}) or {}, ensure_ascii=False)
    exchange_extracted_links_json = json.dumps(getattr(email, "exchange_extracted_links", []) or [], ensure_ascii=False)
    exchange_extracted_emails_json = json.dumps(
        getattr(email, "exchange_extracted_emails", []) or [],
        ensure_ascii=False,
    )
    exchange_extracted_contacts_json = json.dumps(
        getattr(email, "exchange_extracted_contacts", []) or [],
        ensure_ascii=False,
    )
    exchange_extracted_meetings_json = json.dumps(
        getattr(email, "exchange_extracted_meetings", []) or [],
        ensure_ascii=False,
    )
    normalized_body_source = getattr(email, "clean_body_source", "body_text") or "body_text"
    body_normalization_version = (
        getattr(email, "body_normalization_version", BODY_NORMALIZATION_VERSION) or BODY_NORMALIZATION_VERSION
    )
    body_kind = getattr(email, "body_kind", "content") or "content"
    body_empty_reason = getattr(email, "body_empty_reason", "") or ""
    recovery_strategy = getattr(email, "recovery_strategy", "") or ""
    recovery_confidence = float(getattr(email, "recovery_confidence", 0.0) or 0.0)
    inferred_parent_uid = getattr(email, "inferred_parent_uid", "") or ""
    inferred_thread_id = getattr(email, "inferred_thread_id", "") or ""
    inferred_match_reason = getattr(email, "inferred_match_reason", "") or ""
    inferred_match_confidence = float(getattr(email, "inferred_match_confidence", 0.0) or 0.0)
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
        len(email.clean_body) if email.clean_body else 0,
        email.clean_body,
        email.body_html,
        getattr(email, "raw_body_text", "") or "",
        getattr(email, "raw_body_html", "") or "",
        getattr(email, "raw_source", "") or "",
        raw_source_headers_json,
        getattr(email, "forensic_body_text", "") or "",
        getattr(email, "forensic_body_source", "") or "",
        normalized_body_source,
        body_normalization_version,
        body_kind,
        body_empty_reason,
        recovery_strategy,
        recovery_confidence,
        to_identities_json,
        cc_identities_json,
        bcc_identities_json,
        recipient_identity_source,
        getattr(email, "reply_context_from", "") or "",
        reply_context_to_json,
        getattr(email, "reply_context_subject", "") or "",
        getattr(email, "reply_context_date", "") or "",
        getattr(email, "reply_context_source", "") or "",
        meeting_data_json,
        exchange_extracted_links_json,
        exchange_extracted_emails_json,
        exchange_extracted_contacts_json,
        exchange_extracted_meetings_json,
        inferred_parent_uid,
        inferred_thread_id,
        inferred_match_reason,
        inferred_match_confidence,
        content_sha256,
        categories_json,
        getattr(email, "thread_topic", "") or "",
        getattr(email, "inference_classification", "") or "",
        int(getattr(email, "is_calendar_message", False)),
        references_json,
        ingestion_run_id,
    )


def collect_category_rows(email: Email) -> list[tuple[str, str]]:
    return [(email.uid, cat) for cat in (getattr(email, "categories", []) or [])]


def collect_attachment_rows(email: Email) -> list[tuple]:
    rows: list[tuple] = []
    for att in getattr(email, "attachments", []) or []:
        attachment_id, content_sha256 = ensure_attachment_identity(att)
        extracted_text = str(att.get("extracted_text", "") or "")
        normalized_text = str(att.get("normalized_text", "") or "") or normalize_attachment_search_text(extracted_text)
        text_normalization_version = int(att.get("text_normalization_version") or 0)
        if normalized_text and text_normalization_version <= 0:
            text_normalization_version = ATTACHMENT_TEXT_NORMALIZATION_VERSION
        rows.append(
            (
                email.uid,
                att.get("name", ""),
                attachment_id,
                att.get("mime_type", ""),
                att.get("size", 0),
                content_sha256,
                att.get("content_id", ""),
                int(att.get("is_inline", False)),
                att.get("extraction_state", "") or "",
                att.get("evidence_strength", "") or "",
                int(bool(att.get("ocr_used", False))),
                att.get("ocr_engine", "") or "",
                att.get("ocr_lang", "") or "",
                float(att.get("ocr_confidence", 0.0) or 0.0),
                att.get("failure_reason", "") or "",
                att.get("text_preview", "") or "",
                extracted_text,
                normalized_text,
                text_normalization_version,
                int(att.get("locator_version", 1) or 1),
                att.get("text_source_path", "") or "",
                json.dumps(att.get("text_locator") or {}, ensure_ascii=False),
            )
        )
    return rows


def collect_attachment_surface_rows(
    email: Email,
) -> list[tuple]:
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
    categories = collect_category_rows(email)
    if categories:
        cur.executemany(
            "INSERT OR IGNORE INTO email_categories(email_uid, category) VALUES(?,?)",
            categories,
        )

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

    if infer_parent:
        infer_and_persist_match(cur, email)

    if email.sender_email:
        upsert_contact(cur, email.sender_email, email.sender_name, email.date, "sender")
    for name, em in all_recipients:
        if em:
            upsert_contact(cur, em, name, email.date, "recipient")

    if email.sender_email:
        for _, em in all_recipients:
            if em:
                upsert_communication_edge(cur, email.sender_email, em, email.date)


def insert_email_impl(db, email: Email, *, ingestion_run_id: int | None = None) -> bool:
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
    inserted_uids: set[str] = set()
    cur = db.conn.cursor()

    recipient_rows: list[tuple] = []
    category_rows: list[tuple] = []
    attachment_rows: list[tuple] = []
    attachment_surface_rows: list[tuple] = []
    contact_rows: list[tuple] = []
    edge_rows: list[tuple] = []
    segment_rows: list[tuple] = []

    try:
        if commit:
            cur.execute("BEGIN IMMEDIATE")
        for email in emails:
            cur.execute(db._email_insert_or_ignore_sql, build_email_insert_row(db, email, ingestion_run_id))
            if cur.rowcount == 0:
                continue

            category_rows.extend(collect_category_rows(email))
            attachment_rows.extend(collect_attachment_rows(email))
            attachment_surface_rows.extend(collect_attachment_surface_rows(email))
            email_recipient_rows, all_recipients = collect_recipients_and_pairs(email)
            recipient_rows.extend(email_recipient_rows)
            segment_rows.extend(segment_rows_for_email(email.uid, getattr(email, "segments", []) or []))

            inferred = infer_and_persist_match(cur, email)
            _ = inferred

            if email.sender_email:
                contact_rows.append(contact_row(email.sender_email, email.sender_name, email.date, "sender"))
            for name, em in all_recipients:
                if em:
                    contact_rows.append(contact_row(em, name, email.date, "recipient"))

            if email.sender_email:
                for _, em in all_recipients:
                    if em:
                        edge_rows.append(edge_row(email.sender_email, em, email.date))

            inserted_uids.add(email.uid)

        if recipient_rows:
            cur.executemany(
                "INSERT OR IGNORE INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)",
                recipient_rows,
            )
        if segment_rows:
            cur.executemany(
                """INSERT INTO message_segments(
                   email_uid, ordinal, segment_type, depth, text, source_surface, provenance_json
                ) VALUES(?,?,?,?,?,?,?)""",
                segment_rows,
            )
        if category_rows:
            cur.executemany(
                "INSERT OR IGNORE INTO email_categories(email_uid, category) VALUES(?,?)",
                category_rows,
            )
        if attachment_rows:
            cur.executemany(
                "INSERT INTO attachments(email_uid, name, attachment_id, mime_type, size, content_sha256, content_id, "
                "is_inline, extraction_state, evidence_strength, ocr_used, ocr_engine, ocr_lang, ocr_confidence, "
                "failure_reason, text_preview, extracted_text, normalized_text, text_normalization_version, locator_version, "
                "text_source_path, text_locator_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                attachment_rows,
            )
        if attachment_surface_rows:
            cur.executemany(
                "INSERT OR REPLACE INTO attachment_surfaces("
                "surface_id, attachment_id, email_uid, attachment_name, surface_kind, origin_kind, text, normalized_text, "
                "alignment_map_json, language, language_confidence, ocr_confidence, surface_hash, locator_json, quality_json"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                attachment_surface_rows,
            )

        execute_contact_upserts(cur, contact_rows)
        execute_edge_upserts(cur, edge_rows)
        if commit:
            db.conn.commit()
    except Exception:
        if commit:
            db.conn.rollback()
        raise
    return inserted_uids
