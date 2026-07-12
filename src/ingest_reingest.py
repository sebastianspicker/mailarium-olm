"""Reingest, reembed, and reset helpers for the ingestion CLI."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
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
    """Generate a chunk ID prefix for an email attachment.

    Args:
        email_uid: The unique identifier of the parent email.
        filename: The attachment filename.
        att_index: The attachment index within the email.
        attachment_id: Optional attachment identifier.

    Returns:
        A string prefix for attachment chunk IDs.
    """
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
    fields = (("exchange_extracted_emails_json", "email"), ("exchange_extracted_contacts_json", "person"))
    entities = [entity for field, kind in fields for entity in _simple_exchange_entities(_json_list(row[field]), kind)]
    entities.extend(_dict_exchange_entities(_json_list(row["exchange_extracted_links_json"]), "url", "url"))
    entities.extend(_dict_exchange_entities(_json_list(row["exchange_extracted_meetings_json"]), "subject", "event"))
    return entities


def _simple_exchange_entities(values: list[Any], kind: str) -> list[tuple[str, str, str]]:
    return [(text, kind, text.lower()) for value in values if (text := str(value or "").strip())]


def _dict_exchange_entities(values: list[Any], field: str, kind: str) -> list[tuple[str, str, str]]:
    return [
        (text, kind, text.lower())
        for value in values
        if isinstance(value, dict) and (text := str(value.get(field) or "").strip())
    ]


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

    if parse_olm_fn is None:
        from .parse_olm import parse_olm

        parser = parse_olm
    else:
        parser = parse_olm_fn
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
    if parse_olm_fn is None:
        from .parse_olm import parse_olm

        parser = parse_olm
    else:
        parser = parse_olm_fn
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

    progress = _EntityReextractProgress()
    for row in rows:
        progress.inserted += _reextract_entity_row(email_db, row, entity_extractor_fn, extractor_key, extraction_version)
        progress.updated += 1
        progress.rows_since_commit += 1
        if progress.rows_since_commit >= 200:
            email_db.conn.commit()
            progress.rows_since_commit = 0
    email_db.conn.commit()
    email_db.close()
    return {
        "updated": progress.updated,
        "total_candidates": total_candidates,
        "inserted_mentions": progress.inserted,
        "extractor_key": extractor_key,
        "extraction_version": extraction_version,
        "message": (
            f"Re-extracted entities for {progress.updated} emails using {extractor_key or 'unknown'} "
            f"(version {extraction_version or 'unknown'})."
        ),
    }


@dataclass
class _EntityReextractProgress:
    updated: int = 0
    inserted: int = 0
    rows_since_commit: int = 0


def _coerce_entity(entity: tuple[str, str, str] | Any) -> tuple[str, str, str]:
    if isinstance(entity, tuple) and len(entity) == 3:
        return tuple(str(value) for value in entity)  # type: ignore[return-value]
    values = (getattr(entity, "text", None), getattr(entity, "entity_type", None), getattr(entity, "normalized_form", None))
    if any(value is None for value in values):
        raise TypeError(f"Unsupported entity row: {entity!r}")
    return tuple(str(value) for value in values)  # type: ignore[return-value]


def _reextract_entity_row(email_db: Any, row: Any, extractor: Any, extractor_key: str, extraction_version: str) -> int:
    from .ingest_embed_pipeline import EXCHANGE_ENTITY_EXTRACTION_VERSION, EXCHANGE_ENTITY_EXTRACTOR_KEY

    uid = str(row["uid"])
    from .language_analytics import select_entity_text_from_row

    body_text, _source = select_entity_text_from_row(row)
    body_entities = extractor(body_text, str(row["sender_email"] or ""))
    sources = (
        (_exchange_entities_from_row(row), EXCHANGE_ENTITY_EXTRACTOR_KEY, EXCHANGE_ENTITY_EXTRACTION_VERSION),
        (body_entities, extractor_key, extraction_version),
    )
    canonical = _canonical_entity_rows(sources)
    email_db.delete_entity_mentions_for_email(uid, commit=False)
    for (key, version), entries in _entities_by_provenance(canonical).items():
        email_db.insert_entities_batch_idempotent(uid, entries, extractor_key=key, extraction_version=version, commit=False)
    return len(canonical)


def _canonical_entity_rows(sources: tuple[tuple[Any, str, str], ...]) -> dict[tuple[str, str], tuple[str, str, str, str, str]]:
    canonical: dict[tuple[str, str], tuple[str, str, str, str, str]] = {}
    for entities, key, version in sources:
        for entity in entities:
            text, kind, normalized = _coerce_entity(entity)
            canonical[(normalized, kind)] = (text, kind, normalized, key, version)
    return canonical


def _entities_by_provenance(
    canonical: dict[tuple[str, str], tuple[str, str, str, str, str]],
) -> dict[tuple[str, str], list[tuple[str, str, str]]]:
    grouped: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for text, kind, normalized, key, version in canonical.values():
        grouped.setdefault((key, version), []).append((text, kind, normalized))
    return grouped


@dataclass(frozen=True)
class _ReprocessRequest:
    olm_path: str
    chromadb_path: str | None
    sqlite_path: str | None
    batch_size: int
    force: bool


@dataclass(frozen=True)
class _ReprocessDependencies:
    parse_olm: Any
    chunk_attachment: Any
    extract_text: Any
    extract_ocr: Any


@dataclass
class _ReprocessProgress:
    updated: int = 0
    recovered_attachments: int = 0
    ocr_recovered: int = 0
    chunks_added: int = 0
    chunks_deleted: int = 0


@dataclass
class _ReprocessRuntime:
    request: _ReprocessRequest
    dependencies: _ReprocessDependencies
    email_db: Any
    embedder: Any
    target_uids: set[str]
    attachment_ids_by_uid: dict[str, list[str]]
    progress: _ReprocessProgress
    pending_chunks: list[Any]
    pending_emails: list[Any]
    pending_completion_rows: list[dict[str, object]]
    pending_delete_ids: set[str]


def _select_reprocess_uids(email_db: Any, *, force: bool) -> set[str]:
    if force:
        rows = email_db.conn.execute("SELECT DISTINCT email_uid FROM attachments").fetchall()
    else:
        rows = email_db.conn.execute(
            "SELECT email_uid FROM email_ingest_state WHERE attachment_status IN ('degraded', 'unsupported')"
        ).fetchall()
    return {str(row["email_uid"]) for row in rows if str(row["email_uid"] or "")}


def _attachment_chunk_ids_by_uid(embedder: Any) -> dict[str, list[str]]:
    getter = getattr(embedder, "get_existing_ids", None)
    raw_ids = getter(refresh=False) if callable(getter) else set()
    result: dict[str, list[str]] = {}
    for raw_chunk_id in raw_ids if isinstance(raw_ids, set) else set():
        chunk_id = str(raw_chunk_id or "")
        email_uid, marker, _remainder = chunk_id.partition("__att_")
        if marker and email_uid:
            result.setdefault(email_uid, []).append(chunk_id)
    return result


def _initialize_reprocess_runtime(
    request: _ReprocessRequest,
    dependencies: _ReprocessDependencies,
) -> _ReprocessRuntime:
    from .email_db import EmailDatabase
    from .embedder import EmailEmbedder

    settings = get_settings()
    email_db = EmailDatabase(request.sqlite_path or settings.sqlite_path)
    embedder = EmailEmbedder(chromadb_path=request.chromadb_path)
    embedder.set_sparse_db(email_db)
    return _ReprocessRuntime(
        request=request,
        dependencies=dependencies,
        email_db=email_db,
        embedder=embedder,
        target_uids=_select_reprocess_uids(email_db, force=request.force),
        attachment_ids_by_uid=_attachment_chunk_ids_by_uid(embedder),
        progress=_ReprocessProgress(),
        pending_chunks=[],
        pending_emails=[],
        pending_completion_rows=[],
        pending_delete_ids=set(),
    )


def _set_reprocessed_attachment_text(
    email: Any,
    *,
    att_index: int,
    filename: str,
    attachment_id: str,
    content_sha256: str,
    text: str,
    state: str,
    ocr_used: bool,
) -> str:
    from .ingest_pipeline import _attachment_text_preview, _mailbox_attachment_locator, _set_attachment_evidence

    normalized = normalize_attachment_search_text(text)
    ocr_lang = str(os.environ.get("ATTACHMENT_OCR_LANG", DEFAULT_ATTACHMENT_OCR_LANG) or "").strip()
    ocr_lang = ocr_lang or DEFAULT_ATTACHMENT_OCR_LANG
    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state=state,
        evidence_strength="strong_text",
        ocr_used=ocr_used,
        ocr_engine="tesseract" if ocr_used else "",
        ocr_lang=ocr_lang if ocr_used else "",
        ocr_confidence=0.0,
        failure_reason=None,
        text_preview=_attachment_text_preview(text),
        extracted_text=text,
        normalized_text=normalized,
        text_normalization_version=ATTACHMENT_TEXT_NORMALIZATION_VERSION if normalized else 0,
        text_source_path=f"attachment://{email.uid}/{att_index}/{filename}",
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state=state,
            attachment_id=attachment_id,
            content_sha256=content_sha256,
            extracted_text=text,
        ),
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        locator_version=2,
    )
    return normalized


def _set_reprocessed_attachment_failure(
    email: Any,
    *,
    att_index: int,
    filename: str,
    attachment_id: str,
    content_sha256: str,
    state: str,
    reason: str | None,
) -> None:
    from .ingest_pipeline import _mailbox_attachment_locator, _set_attachment_evidence

    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state=state,
        evidence_strength="weak_reference",
        ocr_used=False,
        failure_reason=reason,
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state=state,
            attachment_id=attachment_id,
            content_sha256=content_sha256,
        ),
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        locator_version=2,
    )


def _extract_reprocessed_attachment(
    runtime: _ReprocessRuntime,
    email: Any,
    att_index: int,
    filename: str,
    content: bytes,
) -> list[Any]:
    from .attachment_extractor import attachment_ocr_available_for, classify_text_extraction_state
    from .ingest_pipeline import _textless_attachment_state_with_ocr

    attachments = getattr(email, "attachments", None) or []
    metadata = attachments[att_index] if 0 <= att_index < len(attachments) else {}
    mime_type = str((metadata or {}).get("mime_type") or "")
    attachment_id, content_sha256 = ensure_attachment_identity(metadata, content_bytes=content)
    text = runtime.dependencies.extract_text(filename, content, mime_type=mime_type)
    ocr_used = False
    state, reason = "text_extracted", None
    if not text:
        text = runtime.dependencies.extract_ocr(filename, content) if runtime.dependencies.extract_ocr else None
        ocr_used = bool(text)
    if not text:
        state, reason = _textless_attachment_state_with_ocr(
            filename=filename,
            mime_type=mime_type,
            ocr_attempted=bool(runtime.dependencies.extract_ocr),
            ocr_available=attachment_ocr_available_for(filename, mime_type=mime_type),
        )
        _set_reprocessed_attachment_failure(
            email,
            att_index=att_index,
            filename=filename,
            attachment_id=attachment_id,
            content_sha256=content_sha256,
            state=state,
            reason=reason,
        )
        return []
    state = classify_text_extraction_state(filename, text, ocr_used=ocr_used)
    normalized = _set_reprocessed_attachment_text(
        email,
        att_index=att_index,
        filename=filename,
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        text=text,
        state=state,
        ocr_used=ocr_used,
    )
    runtime.progress.recovered_attachments += 1
    runtime.progress.ocr_recovered += int(ocr_used)
    return runtime.dependencies.chunk_attachment(
        email.uid,
        filename,
        text,
        email.to_dict(),
        att_index=att_index,
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        normalized_text=normalized,
        extraction_state=state,
        evidence_strength="strong_text",
        ocr_used=ocr_used,
    )


def _reprocess_completion_row(runtime: _ReprocessRuntime, email: Any, chunk_count: int) -> dict[str, object]:
    from .ingest_embed_pipeline import _attachment_completion_status

    state_row = runtime.email_db.conn.execute(
        "SELECT body_chunk_count, image_chunk_count FROM email_ingest_state WHERE email_uid = ?",
        (email.uid,),
    ).fetchone()
    body_count = int((state_row["body_chunk_count"] if state_row else 0) or 0)
    image_count = int((state_row["image_chunk_count"] if state_row else 0) or 0)
    email._ingest_body_chunk_count = body_count
    email._ingest_attachment_chunk_count = chunk_count
    email._ingest_image_chunk_count = image_count
    email._ingest_attachment_requested = True
    email._ingest_image_requested = bool(image_count)
    status = _attachment_completion_status(email)
    return {
        "email_uid": email.uid,
        "body_chunk_count": body_count,
        "attachment_chunk_count": chunk_count,
        "image_chunk_count": image_count,
        "vector_chunk_count": body_count + chunk_count + image_count,
        "attachment_status": "completed" if status == "pending" else status,
        "image_status": "completed" if image_count else "not_requested",
    }


def _queue_reprocessed_email(runtime: _ReprocessRuntime, email: Any, chunks: list[Any]) -> None:
    from .ingest_pipeline import _attachments_safe_for_stale_cleanup, _normalize_unprocessed_attachments

    _normalize_unprocessed_attachments(email, extraction_requested=True)
    old_ids = runtime.attachment_ids_by_uid.get(email.uid, [])
    new_ids = {str(chunk.chunk_id) for chunk in chunks if str(getattr(chunk, "chunk_id", "") or "")}
    if old_ids and _attachments_safe_for_stale_cleanup(email):
        runtime.pending_delete_ids.update(chunk_id for chunk_id in old_ids if chunk_id not in new_ids)
    runtime.pending_chunks.extend(chunks)
    runtime.pending_emails.append(email)
    runtime.pending_completion_rows.append(_reprocess_completion_row(runtime, email, len(chunks)))
    runtime.progress.updated += 1


def _flush_reprocess_batch(runtime: _ReprocessRuntime) -> None:
    if not any((runtime.pending_chunks, runtime.pending_emails, runtime.pending_completion_rows, runtime.pending_delete_ids)):
        return
    if runtime.pending_chunks:
        writer = getattr(runtime.embedder, "upsert_chunks", None) or runtime.embedder.add_chunks
        runtime.progress.chunks_added += writer(runtime.pending_chunks, batch_size=runtime.request.batch_size)
    if runtime.pending_delete_ids:
        runtime.progress.chunks_deleted += _delete_chunk_ids(
            embedder=runtime.embedder,
            email_db=runtime.email_db,
            chunk_ids=sorted(runtime.pending_delete_ids),
            commit_sparse=False,
        )
    for email in runtime.pending_emails:
        runtime.email_db.update_v7_metadata(email, commit=False)
    if runtime.pending_completion_rows:
        runtime.email_db.mark_ingest_batch_completed(runtime.pending_completion_rows, commit=False)
    runtime.email_db.conn.commit()
    runtime.pending_chunks.clear()
    runtime.pending_emails.clear()
    runtime.pending_completion_rows.clear()
    runtime.pending_delete_ids.clear()


def _run_attachment_reprocessing(runtime: _ReprocessRuntime) -> None:
    parser = runtime.dependencies.parse_olm(runtime.request.olm_path, extract_attachments=True)
    threshold = max(int(runtime.request.batch_size), 1)
    for email in parser:
        if email.uid not in runtime.target_uids:
            continue
        chunks: list[Any] = []
        for att_index, (filename, content) in enumerate(getattr(email, "attachment_contents", []) or []):
            chunks.extend(_extract_reprocessed_attachment(runtime, email, att_index, filename, content))
        _queue_reprocessed_email(runtime, email, chunks)
        if len(runtime.pending_chunks) >= threshold or len(runtime.pending_emails) >= threshold:
            _flush_reprocess_batch(runtime)
    _flush_reprocess_batch(runtime)


def _close_reprocess_runtime(runtime: _ReprocessRuntime) -> None:
    close_embedder = getattr(runtime.embedder, "close", None)
    if callable(close_embedder):
        close_embedder()
    runtime.email_db.close()


def _reprocess_result(runtime: _ReprocessRuntime) -> dict[str, Any]:
    progress = runtime.progress
    return {
        "updated": progress.updated,
        "total_candidates": len(runtime.target_uids),
        "recovered_attachments": progress.recovered_attachments,
        "ocr_recovered": progress.ocr_recovered,
        "chunks_deleted": progress.chunks_deleted,
        "chunks_added": progress.chunks_added,
        "message": (
            f"Reprocessed degraded attachments for {progress.updated} emails; "
            f"recovered {progress.recovered_attachments} attachments ({progress.ocr_recovered} via OCR)."
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
    if parse_olm_fn is None or chunk_attachment_fn is None or attachment_text_extractor is None:
        return {"updated": 0, "total_candidates": 0, "message": "Attachment reprocessing dependencies are unavailable."}
    request = _ReprocessRequest(olm_path, chromadb_path, sqlite_path, batch_size, force)
    dependencies = _ReprocessDependencies(
        parse_olm_fn,
        chunk_attachment_fn,
        attachment_text_extractor,
        attachment_ocr_extractor,
    )
    runtime = _initialize_reprocess_runtime(request, dependencies)
    try:
        if not runtime.target_uids:
            return {"updated": 0, "total_candidates": 0, "message": "No degraded attachment rows require reprocessing."}
        _run_attachment_reprocessing(runtime)
        return _reprocess_result(runtime)
    finally:
        _close_reprocess_runtime(runtime)


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
        result = _reembed_email(email_db, embedder, uid, body_chunk_ids_by_uid, batch_size, chunk_email)
        if result is None:
            skipped_no_body += 1
            continue
        added, deleted = result
        chunks_added += added
        chunks_deleted += deleted
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


def _reembed_email(
    email_db: Any, embedder: Any, uid: str, ids_by_uid: dict[str, list[str]], batch_size: int, chunker: Any
) -> tuple[int, int] | None:
    email_dict = email_db.get_email_for_reembed(uid)
    if email_dict is None:
        return None
    chunks = chunker(email_dict)
    new_ids = {str(chunk.chunk_id) for chunk in chunks if str(getattr(chunk, "chunk_id", "") or "")}
    obsolete = [chunk_id for chunk_id in ids_by_uid.get(uid, []) if chunk_id not in new_ids]
    deleted = _delete_chunk_ids(embedder=embedder, email_db=email_db, chunk_ids=obsolete) if obsolete else 0
    return embedder.upsert_chunks(chunks, batch_size=batch_size), deleted


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
