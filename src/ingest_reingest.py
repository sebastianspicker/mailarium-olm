"""Reingest, reembed, and reset helpers for the ingestion CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from typing import Any

from .attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    DEFAULT_ATTACHMENT_OCR_LANG,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from .chunker import attachment_chunk_token
from .config import get_settings
from .repo_paths import validate_runtime_path


def _attachment_chunk_prefix(email_uid: str, filename: str, att_index: int, *, attachment_id: str = "") -> str:
    token = attachment_chunk_token(attachment_id=attachment_id, filename=filename, att_index=att_index)
    return f"{email_uid}__att_{token}__"


def _json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _exchange_entities_from_row(row: Any) -> list[tuple[str, str, str]]:
    entities: list[tuple[str, str, str]] = []

    for link in _json_list(row["exchange_extracted_links_json"]):
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "").strip()
        if url:
            entities.append((url, "url", url.lower()))

    for address in _json_list(row["exchange_extracted_emails_json"]):
        normalized = str(address or "").strip()
        if normalized:
            entities.append((normalized, "email", normalized.lower()))

    for contact in _json_list(row["exchange_extracted_contacts_json"]):
        normalized = str(contact or "").strip()
        if normalized:
            entities.append((normalized, "person", normalized.lower()))

    for meeting in _json_list(row["exchange_extracted_meetings_json"]):
        if not isinstance(meeting, dict):
            continue
        subject = str(meeting.get("subject") or "").strip()
        if subject:
            entities.append((subject, "event", subject.lower()))

    return entities


def _delete_chunk_ids(*, embedder: Any, email_db: Any, chunk_ids: list[str], commit_sparse: bool = True) -> int:
    filtered_ids = [chunk_id for chunk_id in chunk_ids if chunk_id]
    if not filtered_ids:
        return 0
    collection = getattr(embedder, "collection", None)
    delete = getattr(collection, "delete", None) if collection is not None else None
    if callable(delete):
        delete(ids=filtered_ids)
    if hasattr(email_db, "delete_sparse_by_chunk_ids"):
        try:
            email_db.delete_sparse_by_chunk_ids(filtered_ids, commit=commit_sparse)
        except TypeError:
            email_db.delete_sparse_by_chunk_ids(filtered_ids)
    existing_ids = getattr(embedder, "get_existing_ids", None)
    if callable(existing_ids):
        cached_ids = existing_ids(refresh=False)
        if isinstance(cached_ids, set):
            cached_ids.difference_update(filtered_ids)
    touch_revision = getattr(embedder, "_touch_collection_revision", None)
    if callable(touch_revision):
        touch_revision()
    return len(filtered_ids)


def reingest_bodies_impl(
    olm_path: str,
    sqlite_path: str | None = None,
    force: bool = False,
    parse_olm_fn=None,
) -> dict[str, Any]:
    """Backfill body_text/body_html for emails missing them in SQLite."""
    settings = get_settings()
    from .email_db import EmailDatabase

    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = EmailDatabase(resolved_sqlite)

    parser = parse_olm_fn
    if parser is None:
        from .parse_olm import parse_olm as parser
    assert parser is not None

    if force:
        all_uids = email_db.all_uids()
        if not all_uids:
            email_db.close()
            return {"updated": 0, "total": 0, "message": "No emails in database."}
        updated = 0
        batch_size = 200
        for email in parser(olm_path):
            if email.uid in all_uids:
                email_db.update_body_text(
                    email.uid,
                    email.clean_body,
                    email.body_html,
                    normalized_body_source=email.clean_body_source,
                    body_normalization_version=email.body_normalization_version,
                    commit=False,
                )
                email_db.update_headers(
                    email.uid,
                    subject=email.subject,
                    sender_name=email.sender_name,
                    sender_email=email.sender_email,
                    base_subject=email.base_subject,
                    email_type=email.email_type,
                    commit=False,
                )
                updated += 1
                if updated % batch_size == 0:
                    email_db.conn.commit()
        email_db.conn.commit()
        email_db.close()
        return {
            "updated": updated,
            "total": len(all_uids),
            "message": f"Force-updated {updated} of {len(all_uids)} emails (bodies + headers).",
        }

    missing_uids = email_db.uids_missing_body()

    if not missing_uids:
        email_db.close()
        return {"updated": 0, "total_missing": 0, "message": "All emails already have body text."}

    updated = 0
    batch_size = 200
    for email in parser(olm_path):
        if email.uid in missing_uids:
            email_db.update_body_text(
                email.uid,
                email.clean_body,
                email.body_html,
                normalized_body_source=email.clean_body_source,
                body_normalization_version=email.body_normalization_version,
                commit=False,
            )
            updated += 1
            if updated % batch_size == 0:
                email_db.conn.commit()

    email_db.conn.commit()
    email_db.close()
    return {
        "updated": updated,
        "total_missing": len(missing_uids),
        "message": f"Updated {updated} of {len(missing_uids)} emails with body text.",
    }


def reingest_metadata_impl(
    olm_path: str,
    sqlite_path: str | None = None,
    exchange_entities_from_email=None,
    parse_olm_fn=None,
) -> dict[str, Any]:
    """Backfill schema-v7 metadata for existing emails in SQLite."""
    settings = get_settings()
    from .email_db import EmailDatabase

    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = EmailDatabase(resolved_sqlite)

    all_uids = email_db.all_uids()
    if not all_uids:
        email_db.close()
        return {"updated": 0, "total": 0, "message": "No emails in database."}

    updated = 0
    exchange_entities_inserted = 0
    batch_size = 200
    rows_since_commit = 0
    from .ingest_embed_pipeline import EXCHANGE_ENTITY_EXTRACTION_VERSION, EXCHANGE_ENTITY_EXTRACTOR_KEY

    extractor = exchange_entities_from_email
    parser = parse_olm_fn
    if parser is None:
        from .parse_olm import parse_olm as parser
    assert parser is not None
    for email in parser(olm_path):
        if email.uid not in all_uids:
            continue

        if email_db.update_v7_metadata(email, commit=False):
            updated += 1

        exchange_entities = extractor(email) if extractor else []
        if exchange_entities:
            email_db.insert_entities_batch_idempotent(
                email.uid,
                exchange_entities,
                extractor_key=EXCHANGE_ENTITY_EXTRACTOR_KEY,
                extraction_version=EXCHANGE_ENTITY_EXTRACTION_VERSION,
                commit=False,
            )
            exchange_entities_inserted += len(exchange_entities)

        rows_since_commit += 1
        if rows_since_commit >= batch_size:
            email_db.conn.commit()
            rows_since_commit = 0

    email_db.conn.commit()
    email_db.close()
    return {
        "updated": updated,
        "total": len(all_uids),
        "exchange_entities_inserted": exchange_entities_inserted,
        "message": (
            f"Updated {updated} of {len(all_uids)} emails with v7 metadata. "
            f"{exchange_entities_inserted} Exchange entities inserted."
        ),
    }


def reingest_analytics_impl(sqlite_path: str | None = None) -> dict[str, Any]:
    """Backfill detected_language and sentiment for emails missing analytics."""
    settings = get_settings()
    from .email_db import EmailDatabase
    from .language_analytics import (
        build_analytics_update_row,
        build_surface_language_rows_from_row,
        select_analytics_text_from_row,
    )

    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = EmailDatabase(resolved_sqlite)

    rows = email_db.conn.execute(
        "SELECT uid, subject, forensic_body_text, forensic_body_source, body_text, normalized_body_source, raw_body_text, "
        "(SELECT GROUP_CONCAT(COALESCE(normalized_text, extracted_text, text_preview, name), '\n') "
        "   FROM attachments a WHERE a.email_uid = emails.uid) AS attachment_text "
        ", (SELECT GROUP_CONCAT(ms.text, '\n') FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid AND ms.segment_type = 'authored_body') AS authored_segment_text "
        ", (SELECT MIN(ms.ordinal) FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid AND ms.segment_type = 'authored_body') AS authored_segment_ordinal "
        ", (SELECT GROUP_CONCAT(ms.text, '\n') FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid "
        "      AND ms.segment_type IN ('quoted_reply', 'forwarded_message')) AS quoted_segment_text "
        ", (SELECT MIN(ms.ordinal) FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid "
        "      AND ms.segment_type IN ('quoted_reply', 'forwarded_message')) AS quoted_segment_ordinal "
        ", (SELECT GROUP_CONCAT(ms.text, '\n') FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid AND ms.segment_type = 'header_block') AS forwarded_header_text "
        ", (SELECT MIN(ms.ordinal) FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid AND ms.segment_type = 'header_block') AS forwarded_header_ordinal "
        ", (SELECT GROUP_CONCAT(ms.text, '\n') FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid) AS segment_text "
        ", (SELECT MIN(ms.ordinal) FROM message_segments ms "
        "    WHERE ms.email_uid = emails.uid) AS segment_ordinal "
        "FROM emails "
        "WHERE ("
        "detected_language IS NULL OR sentiment_label IS NULL "
        "OR detected_language_confidence IS NULL OR detected_language_reason IS NULL "
        "OR COALESCE(detected_language_source, '') = '' OR detected_language_token_count IS NULL "
        "OR NOT EXISTS (SELECT 1 FROM language_surface_analytics lsa WHERE lsa.email_uid = emails.uid)"
        ") "
    ).fetchall()

    total_missing = len(rows)
    if not total_missing:
        email_db.close()
        return {"updated": 0, "total_missing": 0, "message": "All emails already have analytics data."}

    batch: list[tuple[object, ...]] = []
    surface_batch: list[tuple[object, ...]] = []
    low_confidence = 0
    skipped_empty_text_rows = 0
    short_text_reason_count = 0
    for row in rows:
        body, source = select_analytics_text_from_row(row)
        surface_batch.extend(build_surface_language_rows_from_row(row))
        if not body:
            skipped_empty_text_rows += 1
            continue
        analytics_row = build_analytics_update_row(uid=str(row["uid"]), text=body, source=source)
        confidence = str(analytics_row[1] or "")
        reason = str(analytics_row[2] or "")
        if confidence == "low":
            low_confidence += 1
        if reason.startswith("short_text_"):
            short_text_reason_count += 1
        batch.append(analytics_row)

    updated = email_db.update_analytics_batch(batch)
    surface_updated = 0
    if surface_batch and hasattr(email_db, "upsert_language_surface_analytics"):
        try:
            surface_updated = email_db.upsert_language_surface_analytics(surface_batch)
        except sqlite3.OperationalError:
            surface_updated = 0
    email_db.close()
    return {
        "updated": updated,
        "surface_rows_upserted": surface_updated,
        "total_missing": total_missing,
        "low_confidence_language_guesses": low_confidence,
        "skipped_empty_text_rows": skipped_empty_text_rows,
        "short_text_signal_limited_rows": short_text_reason_count,
        "message": f"Computed language and sentiment for {updated} emails; {surface_updated} surface rows upserted.",
    }


def reextract_entities_impl(
    *,
    sqlite_path: str | None = None,
    entity_extractor_fn=None,
    extractor_key: str = "",
    extraction_version: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Backfill or rebuild entity mentions from stored email bodies."""
    settings = get_settings()
    from .email_db import EmailDatabase
    from .language_analytics import select_entity_text_from_row

    if entity_extractor_fn is None:
        return {"updated": 0, "total_candidates": 0, "message": "Entity extraction is unavailable."}

    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = EmailDatabase(resolved_sqlite)
    query = (
        "SELECT uid, subject, forensic_body_text, body_text, raw_body_text, sender_email, "
        "exchange_extracted_links_json, exchange_extracted_emails_json, "
        "exchange_extracted_contacts_json, exchange_extracted_meetings_json, "
        "(SELECT GROUP_CONCAT(COALESCE(extracted_text, text_preview, name), '\n') "
        "   FROM attachments a WHERE a.email_uid = emails.uid) AS attachment_text "
        "FROM emails "
        "WHERE 1=1"
    )
    if not force:
        query += (
            " AND ("
            " uid NOT IN (SELECT DISTINCT email_uid FROM entity_mentions)"
            " OR uid IN (SELECT DISTINCT email_uid FROM entity_mentions WHERE COALESCE(extractor_key, '') = '')"
            " )"
        )
    rows = email_db.conn.execute(query).fetchall()
    rows = [row for row in rows if select_entity_text_from_row(row)[0] or _exchange_entities_from_row(row)]
    total_candidates = len(rows)
    if not rows:
        email_db.close()
        return {
            "updated": 0,
            "total_candidates": 0,
            "message": "All emails already have entity provenance metadata.",
        }

    updated = 0
    inserted_mentions = 0
    rows_since_commit = 0
    batch_size = 200
    from .ingest_embed_pipeline import EXCHANGE_ENTITY_EXTRACTION_VERSION, EXCHANGE_ENTITY_EXTRACTOR_KEY

    def _coerce_entity(entity: tuple[str, str, str] | Any) -> tuple[str, str, str]:
        if isinstance(entity, tuple) and len(entity) == 3:
            text, entity_type, normalized_form = entity
            return str(text), str(entity_type), str(normalized_form)
        text = getattr(entity, "text", None)
        entity_type = getattr(entity, "entity_type", None)
        normalized_form = getattr(entity, "normalized_form", None)
        if text is None or entity_type is None or normalized_form is None:
            raise TypeError(f"Unsupported entity row: {entity!r}")
        return str(text), str(entity_type), str(normalized_form)

    for row in rows:
        uid = str(row["uid"])
        entity_text, _entity_source = select_entity_text_from_row(row)
        sender_email = str(row["sender_email"] or "")
        body_entities_raw = entity_extractor_fn(entity_text, sender_email)
        exchange_entities_raw = _exchange_entities_from_row(row)
        canonical_entities: dict[tuple[str, str], tuple[str, str, str, str, str]] = {}
        for exchange_entity in exchange_entities_raw:
            text, entity_type, normalized_form = _coerce_entity(exchange_entity)
            canonical_entities[(normalized_form, entity_type)] = (
                text,
                entity_type,
                normalized_form,
                EXCHANGE_ENTITY_EXTRACTOR_KEY,
                EXCHANGE_ENTITY_EXTRACTION_VERSION,
            )
        for body_entity in body_entities_raw:
            text, entity_type, normalized_form = _coerce_entity(body_entity)
            canonical_entities[(normalized_form, entity_type)] = (
                text,
                entity_type,
                normalized_form,
                extractor_key,
                extraction_version,
            )

        email_db.delete_entity_mentions_for_email(uid, commit=False)
        if canonical_entities:
            entities_by_provenance: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
            for text, entity_type, normalized_form, prov_key, prov_version in canonical_entities.values():
                entities_by_provenance.setdefault((prov_key, prov_version), []).append((text, entity_type, normalized_form))
            for (prov_key, prov_version), entities_batch in entities_by_provenance.items():
                email_db.insert_entities_batch_idempotent(
                    uid,
                    entities_batch,
                    extractor_key=prov_key,
                    extraction_version=prov_version,
                    commit=False,
                )
            inserted_mentions += len(canonical_entities)
        updated += 1
        rows_since_commit += 1
        if rows_since_commit >= batch_size:
            email_db.conn.commit()
            rows_since_commit = 0
    email_db.conn.commit()
    email_db.close()
    return {
        "updated": updated,
        "total_candidates": total_candidates,
        "inserted_mentions": inserted_mentions,
        "extractor_key": extractor_key,
        "extraction_version": extraction_version,
        "message": (
            f"Re-extracted entities for {updated} emails using {extractor_key or 'unknown'} "
            f"(version {extraction_version or 'unknown'})."
        ),
    }


def reprocess_degraded_attachments_impl(
    olm_path: str,
    *,
    chromadb_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 100,
    force: bool = False,
    parse_olm_fn=None,
    chunk_attachment_fn=None,
    attachment_text_extractor=None,
    attachment_ocr_extractor=None,
) -> dict[str, Any]:
    """Re-parse degraded mailbox attachments and attempt OCR recovery for image attachments."""
    settings = get_settings()
    from .attachment_extractor import attachment_ocr_available_for, classify_text_extraction_state
    from .email_db import EmailDatabase
    from .embedder import EmailEmbedder
    from .ingest_embed_pipeline import _attachment_completion_status
    from .ingest_pipeline import (
        _attachment_text_preview,
        _attachments_safe_for_stale_cleanup,
        _mailbox_attachment_locator,
        _normalize_unprocessed_attachments,
        _set_attachment_evidence,
        _textless_attachment_state_with_ocr,
    )

    if parse_olm_fn is None or chunk_attachment_fn is None or attachment_text_extractor is None:
        return {"updated": 0, "total_candidates": 0, "message": "Attachment reprocessing dependencies are unavailable."}

    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = EmailDatabase(resolved_sqlite)
    embedder = EmailEmbedder(chromadb_path=chromadb_path)
    embedder.set_sparse_db(email_db)

    if force:
        target_rows = email_db.conn.execute("SELECT DISTINCT email_uid FROM attachments").fetchall()
    else:
        target_rows = email_db.conn.execute(
            "SELECT email_uid FROM email_ingest_state WHERE attachment_status IN ('degraded', 'unsupported')"
        ).fetchall()
    target_uids = {str(row["email_uid"]) for row in target_rows if str(row["email_uid"] or "")}
    if not target_uids:
        close_embedder = getattr(embedder, "close", None)
        if callable(close_embedder):
            close_embedder()
        email_db.close()
        return {"updated": 0, "total_candidates": 0, "message": "No degraded attachment rows require reprocessing."}

    updated = 0
    ocr_recovered = 0
    chunks_added = 0
    recovered_attachments = 0
    total_chunks_deleted = 0
    flush_threshold = max(int(batch_size), 1)

    existing_ids_getter = getattr(embedder, "get_existing_ids", None)
    existing_ids_raw = existing_ids_getter(refresh=False) if callable(existing_ids_getter) else set()
    existing_ids = existing_ids_raw if isinstance(existing_ids_raw, set) else set()
    attachment_ids_by_uid: dict[str, list[str]] = {}
    for chunk_id in existing_ids:
        normalized_chunk_id = str(chunk_id or "")
        if "__att_" not in normalized_chunk_id:
            continue
        email_uid, marker, _remainder = normalized_chunk_id.partition("__att_")
        if not marker or not email_uid:
            continue
        attachment_ids_by_uid.setdefault(email_uid, []).append(normalized_chunk_id)

    pending_chunks: list[Any] = []
    pending_emails: list[Any] = []
    pending_completion_rows: list[dict[str, object]] = []
    pending_delete_ids: set[str] = set()

    def _flush_pending() -> None:
        nonlocal chunks_added, total_chunks_deleted

        if not pending_chunks and not pending_emails and not pending_completion_rows and not pending_delete_ids:
            return

        if pending_chunks:
            if hasattr(embedder, "upsert_chunks"):
                chunks_added += embedder.upsert_chunks(pending_chunks, batch_size=batch_size)
            else:
                chunks_added += embedder.add_chunks(pending_chunks, batch_size=batch_size)

        if pending_delete_ids:
            total_chunks_deleted += _delete_chunk_ids(
                embedder=embedder,
                email_db=email_db,
                chunk_ids=sorted(pending_delete_ids),
                commit_sparse=False,
            )

        for pending_email in pending_emails:
            email_db.update_v7_metadata(pending_email, commit=False)
        if pending_completion_rows:
            email_db.mark_ingest_batch_completed(pending_completion_rows, commit=False)
        email_db.conn.commit()

        pending_chunks.clear()
        pending_emails.clear()
        pending_completion_rows.clear()
        pending_delete_ids.clear()

    assert parse_olm_fn is not None
    parser = parse_olm_fn(olm_path, extract_attachments=True)
    for email in parser:
        if email.uid not in target_uids:
            continue
        attachment_chunks = []
        for att_i, (att_name, att_bytes) in enumerate(getattr(email, "attachment_contents", []) or []):
            attachments = getattr(email, "attachments", None) or []
            mime_type = str((attachments[att_i] or {}).get("mime_type") or "") if 0 <= att_i < len(attachments) else ""
            attachment_meta = attachments[att_i] if 0 <= att_i < len(attachments) else {}
            attachment_id, content_sha256 = ensure_attachment_identity(attachment_meta, content_bytes=att_bytes)
            att_text = attachment_text_extractor(att_name, att_bytes, mime_type=mime_type)
            ocr_used = False
            extraction_state = "text_extracted"
            failure_reason = None
            if not att_text:
                ocr_text = attachment_ocr_extractor(att_name, att_bytes) if attachment_ocr_extractor else None
                if ocr_text:
                    att_text = ocr_text
                    ocr_used = True
                    extraction_state = "ocr_text_extracted"
                else:
                    extraction_state, failure_reason = _textless_attachment_state_with_ocr(
                        filename=att_name,
                        mime_type=mime_type,
                        ocr_attempted=bool(attachment_ocr_extractor),
                        ocr_available=attachment_ocr_available_for(att_name, mime_type=mime_type),
                    )
            if att_text:
                extraction_state = classify_text_extraction_state(att_name, att_text, ocr_used=ocr_used)
                normalized_text = normalize_attachment_search_text(att_text)
                ocr_lang = str(os.environ.get("ATTACHMENT_OCR_LANG", DEFAULT_ATTACHMENT_OCR_LANG) or "").strip()
                if not ocr_lang:
                    ocr_lang = DEFAULT_ATTACHMENT_OCR_LANG
                locator = _mailbox_attachment_locator(
                    email_uid=email.uid,
                    att_index=att_i,
                    filename=att_name,
                    extraction_state=extraction_state,
                    attachment_id=attachment_id,
                    content_sha256=content_sha256,
                    extracted_text=att_text,
                )
                _set_attachment_evidence(
                    email,
                    att_index=att_i,
                    extraction_state=extraction_state,
                    evidence_strength="strong_text",
                    ocr_used=ocr_used,
                    ocr_engine="tesseract" if ocr_used else "",
                    ocr_lang=ocr_lang if ocr_used else "",
                    ocr_confidence=0.0,
                    failure_reason=None,
                    text_preview=_attachment_text_preview(att_text),
                    extracted_text=att_text,
                    normalized_text=normalized_text,
                    text_normalization_version=(ATTACHMENT_TEXT_NORMALIZATION_VERSION if normalized_text else 0),
                    text_source_path=f"attachment://{email.uid}/{att_i}/{att_name}",
                    text_locator=locator,
                    attachment_id=attachment_id,
                    content_sha256=content_sha256,
                    locator_version=2,
                )
                attachment_chunks.extend(
                    chunk_attachment_fn(
                        email.uid,
                        att_name,
                        att_text,
                        email.to_dict(),
                        att_index=att_i,
                        attachment_id=attachment_id,
                        content_sha256=content_sha256,
                        normalized_text=normalized_text,
                        extraction_state=extraction_state,
                        evidence_strength="strong_text",
                        ocr_used=ocr_used,
                    )
                )
                recovered_attachments += 1
                if ocr_used:
                    ocr_recovered += 1
            else:
                _set_attachment_evidence(
                    email,
                    att_index=att_i,
                    extraction_state=extraction_state,
                    evidence_strength="weak_reference",
                    ocr_used=False,
                    ocr_engine="",
                    ocr_lang="",
                    ocr_confidence=0.0,
                    failure_reason=failure_reason,
                    text_preview="",
                    extracted_text="",
                    normalized_text="",
                    text_normalization_version=0,
                    text_source_path="",
                    text_locator=_mailbox_attachment_locator(
                        email_uid=email.uid,
                        att_index=att_i,
                        filename=att_name,
                        extraction_state=extraction_state,
                        attachment_id=attachment_id,
                        content_sha256=content_sha256,
                    ),
                    attachment_id=attachment_id,
                    content_sha256=content_sha256,
                    locator_version=2,
                )
        _normalize_unprocessed_attachments(
            email,
            extraction_requested=True,
        )
        attachment_ids = attachment_ids_by_uid.get(email.uid, [])
        new_chunk_ids = {str(chunk.chunk_id) for chunk in attachment_chunks if str(getattr(chunk, "chunk_id", "") or "")}
        if attachment_ids and _attachments_safe_for_stale_cleanup(email):
            pending_delete_ids.update(chunk_id for chunk_id in attachment_ids if chunk_id not in new_chunk_ids)

        state_row = email_db.conn.execute(
            """SELECT body_chunk_count, image_chunk_count
               FROM email_ingest_state WHERE email_uid = ?""",
            (email.uid,),
        ).fetchone()
        body_chunk_count = int((state_row["body_chunk_count"] if state_row else 0) or 0)
        image_chunk_count = int((state_row["image_chunk_count"] if state_row else 0) or 0)
        attachment_chunk_count = len(attachment_chunks)
        email._ingest_body_chunk_count = body_chunk_count
        email._ingest_attachment_chunk_count = attachment_chunk_count
        email._ingest_image_chunk_count = image_chunk_count
        email._ingest_attachment_requested = True
        email._ingest_image_requested = bool(image_chunk_count)
        attachment_status = _attachment_completion_status(email)
        if attachment_status == "pending":
            attachment_status = "completed"
        pending_chunks.extend(attachment_chunks)
        pending_emails.append(email)
        pending_completion_rows.append(
            {
                "email_uid": email.uid,
                "body_chunk_count": body_chunk_count,
                "attachment_chunk_count": attachment_chunk_count,
                "image_chunk_count": image_chunk_count,
                "vector_chunk_count": body_chunk_count + attachment_chunk_count + image_chunk_count,
                "attachment_status": attachment_status,
                "image_status": "completed" if image_chunk_count else "not_requested",
            }
        )
        updated += 1
        if len(pending_chunks) >= flush_threshold or len(pending_emails) >= flush_threshold:
            _flush_pending()

    _flush_pending()
    close_embedder = getattr(embedder, "close", None)
    if callable(close_embedder):
        close_embedder()
    email_db.close()
    return {
        "updated": updated,
        "total_candidates": len(target_uids),
        "recovered_attachments": recovered_attachments,
        "ocr_recovered": ocr_recovered,
        "chunks_deleted": total_chunks_deleted,
        "chunks_added": chunks_added,
        "message": (
            f"Reprocessed degraded attachments for {updated} emails; "
            f"recovered {recovered_attachments} attachments ({ocr_recovered} via OCR)."
        ),
    }


def reembed_impl(
    chromadb_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Re-chunk and re-embed all emails from corrected SQLite body text."""
    from .chunker import chunk_email
    from .email_db import EmailDatabase
    from .embedder import EmailEmbedder

    settings = get_settings()
    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = EmailDatabase(resolved_sqlite)
    embedder = EmailEmbedder(chromadb_path=chromadb_path)
    embedder.set_sparse_db(email_db)

    all_uids = email_db.all_uids()
    if not all_uids:
        email_db.close()
        return {"reembedded": 0, "total": 0, "message": "No emails in database."}

    reembedded = 0
    chunks_deleted = 0
    chunks_added = 0
    skipped_no_body = 0
    existing_ids = embedder.get_existing_ids(refresh=False)
    body_chunk_ids_by_uid: dict[str, list[str]] = {}
    for chunk_id in existing_ids:
        if "__att_" in chunk_id or "__img_" in chunk_id:
            continue
        uid = chunk_id.split("__", 1)[0]
        body_chunk_ids_by_uid.setdefault(uid, []).append(chunk_id)

    for uid in sorted(all_uids):
        email_dict = email_db.get_email_for_reembed(uid)
        if email_dict is None:
            skipped_no_body += 1
            continue

        body_chunk_ids = body_chunk_ids_by_uid.get(uid, [])
        chunks = chunk_email(email_dict)
        new_chunk_ids = {str(chunk.chunk_id) for chunk in chunks if str(getattr(chunk, "chunk_id", "") or "")}
        added = embedder.upsert_chunks(chunks, batch_size=batch_size)
        obsolete_chunk_ids = [chunk_id for chunk_id in body_chunk_ids if chunk_id not in new_chunk_ids]
        if obsolete_chunk_ids:
            chunks_deleted += _delete_chunk_ids(
                embedder=embedder,
                email_db=email_db,
                chunk_ids=obsolete_chunk_ids,
            )
        chunks_added += added
        reembedded += 1

    embedder.close()
    email_db.close()
    return {
        "reembedded": reembedded,
        "total": len(all_uids),
        "chunks_deleted": chunks_deleted,
        "chunks_added": chunks_added,
        "skipped_no_body": skipped_no_body,
        "message": (
            f"Re-embedded {reembedded} of {len(all_uids)} emails "
            f"({chunks_added} chunks). {skipped_no_body} skipped (no body text)."
        ),
    }


def reset_index_impl(args: argparse.Namespace) -> None:
    """Delete ChromaDB collection and SQLite DB file."""
    settings = get_settings()
    sqlite_file = args.sqlite_path or settings.sqlite_path
    validate_runtime_path(sqlite_file, field_name="sqlite_path")
    if os.path.exists(sqlite_file):
        os.remove(sqlite_file)
        print(f"Deleted SQLite DB: {sqlite_file}")
    chromadb_dir = args.chromadb_path or settings.chromadb_path
    validate_runtime_path(chromadb_dir, field_name="chromadb_path")
    if os.path.isdir(chromadb_dir):
        shutil.rmtree(chromadb_dir)
        print(f"Deleted ChromaDB: {chromadb_dir}")
