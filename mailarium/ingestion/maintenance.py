"""Maintenance operations for parsed archive records."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mailarium.platform.repo_paths import validate_runtime_path
from mailarium.platform.settings import get_settings

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


def _maintenance_sqlite_path(sqlite_path: str | None) -> str:
    """Resolve maintenance storage through the product runtime-path policy."""
    selected = sqlite_path or get_settings().sqlite_path
    return str(validate_runtime_path(str(selected), field_name="sqlite_path"))


def _json_list(value: object) -> list[Any]:
    """Decode a JSON list while tolerating missing or malformed legacy values."""
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
    """Decode Exchange entity payloads stored on an email row."""
    fields = (("exchange_extracted_emails_json", "email"), ("exchange_extracted_contacts_json", "person"))
    entities = [entity for field, kind in fields for entity in _simple_exchange_entities(_json_list(row[field]), kind)]
    entities.extend(_dict_exchange_entities(_json_list(row["exchange_extracted_links_json"]), "url", "url"))
    entities.extend(_dict_exchange_entities(_json_list(row["exchange_extracted_meetings_json"]), "subject", "event"))
    return entities


def _simple_exchange_entities(values: list[Any], kind: str) -> list[tuple[str, str, str]]:
    """Normalize a simple list of Exchange entity values."""
    return [(text, kind, text.lower()) for value in values if (text := str(value or "").strip())]


def _dict_exchange_entities(values: list[Any], field: str, kind: str) -> list[tuple[str, str, str]]:
    """Normalize typed Exchange entity mappings into a flat list."""
    return [
        (text, kind, text.lower())
        for value in values
        if isinstance(value, dict) and (text := str(value.get(field) or "").strip())
    ]


def _delete_chunk_ids(*, embedder: Any, email_db: ArchiveDatabase, chunk_ids: list[str], commit_sparse: bool = True) -> int:
    """Delete chunk ids while preserving the invariants of attachment reprocessing."""
    filtered_ids = [chunk_id for chunk_id in chunk_ids if chunk_id]
    if not filtered_ids:
        return 0
    collection = getattr(embedder, "collection", None)
    delete = getattr(collection, "delete", None) if collection is not None else None
    if callable(delete):
        delete(ids=filtered_ids)
    email_db.sparse.delete_sparse_by_chunk_ids(filtered_ids, commit=commit_sparse)
    existing_ids = getattr(embedder, "get_existing_ids", None)
    if callable(existing_ids):
        cached_ids = existing_ids(refresh=False)
        if isinstance(cached_ids, set):
            cached_ids.difference_update(filtered_ids)
    touch_revision = getattr(embedder, "_touch_collection_revision", None)
    if callable(touch_revision):
        touch_revision()
    return len(filtered_ids)


def reingest_bodies(
    olm_path: str,
    sqlite_path: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Backfill body_text/body_html for emails missing them in SQLite."""
    from mailarium.archive import open_archive_database

    email_db = open_archive_database(_maintenance_sqlite_path(sqlite_path))
    try:
        if force:
            all_uids = email_db.queries.all_uids()
            if not all_uids:
                return {"updated": 0, "total": 0, "message": "No emails in database."}
            updated = _reingest_matching_bodies(email_db, olm_path, all_uids, update_headers=True)
            email_db.commit()
            return {
                "updated": updated,
                "total": len(all_uids),
                "message": f"Force-updated {updated} of {len(all_uids)} emails (bodies + headers).",
            }

        missing_uids = email_db.queries.uids_missing_body()
        if not missing_uids:
            return {"updated": 0, "total_missing": 0, "message": "All emails already have body text."}

        updated = _reingest_matching_bodies(email_db, olm_path, missing_uids, update_headers=False)
        email_db.commit()
        return {
            "updated": updated,
            "total_missing": len(missing_uids),
            "message": f"Updated {updated} of {len(missing_uids)} emails with body text.",
        }
    finally:
        email_db.close()


def _reingest_matching_bodies(
    email_db: ArchiveDatabase,
    olm_path: str,
    target_uids: set[str],
    *,
    update_headers: bool,
) -> int:
    """Update only requested messages from the OLM stream, committing periodically."""
    from mailarium.ingestion.olm.parser import parse_olm

    updated = 0
    for email in parse_olm(olm_path):
        if email.uid not in target_uids:
            continue
        _update_reingested_email(email_db, email, update_headers=update_headers)
        updated += 1
        if updated % 200 == 0:
            email_db.commit()
    return updated


def _update_reingested_email(email_db: ArchiveDatabase, email: Any, *, update_headers: bool) -> None:
    """Update reingested email while preserving the invariants of attachment reprocessing."""
    email_db.messages.update_body_text(
        email.uid,
        email.clean_body,
        email.body_html,
        normalized_body_source=email.clean_body_source,
        body_normalization_version=email.body_normalization_version,
        commit=False,
    )
    if update_headers:
        email_db.messages.update_headers(
            email.uid,
            subject=email.subject,
            sender_name=email.sender_name,
            sender_email=email.sender_email,
            base_subject=email.base_subject,
            email_type=email.email_type,
            commit=False,
        )


def reingest_metadata(
    olm_path: str,
    sqlite_path: str | None = None,
    *,
    extract_exchange_entities: bool = False,
) -> dict[str, Any]:
    """Backfill schema-v7 metadata for existing emails in SQLite.

    With ``extract_exchange_entities``, entities derived from Exchange fields
    are inserted idempotently alongside the metadata backfill.
    """
    from mailarium.archive import open_archive_database
    from mailarium.ingestion.olm.parser import parse_olm

    resolved_sqlite = _maintenance_sqlite_path(sqlite_path)
    email_db = open_archive_database(resolved_sqlite)
    try:
        all_uids = email_db.queries.all_uids()
        if not all_uids:
            return {"updated": 0, "total": 0, "message": "No emails in database."}

        updated = 0
        exchange_entities_inserted = 0
        batch_size = 200
        rows_since_commit = 0
        from .ingest_embed_pipeline import (
            EXCHANGE_ENTITY_EXTRACTION_VERSION,
            EXCHANGE_ENTITY_EXTRACTOR_KEY,
            _exchange_entities_from_email,
        )

        for email in parse_olm(olm_path):
            if email.uid not in all_uids:
                continue

            if email_db.messages.update_v7_metadata(email, commit=False):
                updated += 1

            exchange_entities = _exchange_entities_from_email(email) if extract_exchange_entities else []
            if exchange_entities:
                email_db.entities.insert_entities_batch_idempotent(
                    email.uid,
                    exchange_entities,
                    extractor_key=EXCHANGE_ENTITY_EXTRACTOR_KEY,
                    extraction_version=EXCHANGE_ENTITY_EXTRACTION_VERSION,
                    commit=False,
                )
                exchange_entities_inserted += len(exchange_entities)

            rows_since_commit += 1
            if rows_since_commit >= batch_size:
                email_db.commit()
                rows_since_commit = 0

        email_db.commit()
        return {
            "updated": updated,
            "total": len(all_uids),
            "exchange_entities_inserted": exchange_entities_inserted,
            "message": (
                f"Updated {updated} of {len(all_uids)} emails with v7 metadata. "
                f"{exchange_entities_inserted} Exchange entities inserted."
            ),
        }
    finally:
        email_db.close()


def reingest_analytics(sqlite_path: str | None = None) -> dict[str, Any]:
    """Backfill missing analytics using bounded candidate and surface batches."""
    from mailarium.archive import open_archive_database
    from mailarium.ingestion.enrichment.language_analytics import (
        build_analytics_update_row,
        build_surface_language_rows_from_row,
        select_analytics_text_from_row,
    )

    email_db = open_archive_database(_maintenance_sqlite_path(sqlite_path))
    updated = surface_updated = total_missing = low_confidence = skipped_empty_text_rows = short_text_reason_count = 0
    try:
        for rows in email_db.analytics.iter_analytics_batches():
            total_missing += len(rows)
            batch: list[tuple[object, ...]] = []
            surface_batch: list[tuple[object, ...]] = []
            for row in rows:
                body, source = select_analytics_text_from_row(row)
                surface_batch.extend(build_surface_language_rows_from_row(row))
                if not body:
                    skipped_empty_text_rows += 1
                    continue
                analytics_row = build_analytics_update_row(uid=str(row["uid"]), text=body, source=source)
                low_confidence += str(analytics_row[1] or "") == "low"
                short_text_reason_count += str(analytics_row[2] or "").startswith("short_text_")
                batch.append(analytics_row)
            updated += email_db.analytics.update_analytics_batch(batch)
            if surface_batch:
                try:
                    surface_updated += email_db.analytics.upsert_language_surface_analytics(surface_batch)
                except sqlite3.OperationalError:
                    pass  # Legacy stores without the optional surface table remain backfillable.
        if not total_missing:
            return {"updated": 0, "total_missing": 0, "message": "All emails already have analytics data."}
        return {
            "updated": updated,
            "surface_rows_upserted": surface_updated,
            "total_missing": total_missing,
            "low_confidence_language_guesses": low_confidence,
            "skipped_empty_text_rows": skipped_empty_text_rows,
            "short_text_signal_limited_rows": short_text_reason_count,
            "message": f"Computed language and sentiment for {updated} emails; {surface_updated} surface rows upserted.",
        }
    finally:
        email_db.close()


def reextract_entities(
    *,
    sqlite_path: str | None = None,
    entity_extractor_fn=None,
    extractor_key: str = "",
    extraction_version: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Backfill or rebuild entity mentions from stored email bodies."""
    from mailarium.archive import open_archive_database
    from mailarium.ingestion.enrichment.language_analytics import select_entity_text_from_row

    if entity_extractor_fn is None:
        return {"updated": 0, "total_candidates": 0, "message": "Entity extraction is unavailable."}

    resolved_sqlite = _maintenance_sqlite_path(sqlite_path)
    email_db = open_archive_database(resolved_sqlite)
    rows = email_db.entities.entity_reextraction_candidates(force=force)
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
            email_db.commit()
            progress.rows_since_commit = 0
    email_db.commit()
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
    """Track progress while entity extraction is rerun for stored messages."""

    updated: int = 0
    inserted: int = 0
    rows_since_commit: int = 0


def _coerce_entity(entity: tuple[str, str, str] | Any) -> tuple[str, str, str]:
    """Normalize tuple or entity-object results into canonical string triples."""
    if isinstance(entity, tuple) and len(entity) == 3:
        return tuple(str(value) for value in entity)  # type: ignore[return-value]
    values = (getattr(entity, "text", None), getattr(entity, "entity_type", None), getattr(entity, "normalized_form", None))
    if any(value is None for value in values):
        raise TypeError(f"Unsupported entity row: {entity!r}")
    return tuple(str(value) for value in values)  # type: ignore[return-value]


def _reextract_entity_row(
    email_db: ArchiveDatabase, row: Any, extractor: Any, extractor_key: str, extraction_version: str
) -> int:
    """Re-run entity extraction for one stored email and return canonical rows."""
    from .ingest_embed_pipeline import EXCHANGE_ENTITY_EXTRACTION_VERSION, EXCHANGE_ENTITY_EXTRACTOR_KEY

    uid = str(row["uid"])
    from mailarium.ingestion.enrichment.language_analytics import select_entity_text_from_row

    body_text, _source = select_entity_text_from_row(row)
    body_entities = extractor(body_text, str(row["sender_email"] or ""))
    sources = (
        (_exchange_entities_from_row(row), EXCHANGE_ENTITY_EXTRACTOR_KEY, EXCHANGE_ENTITY_EXTRACTION_VERSION),
        (body_entities, extractor_key, extraction_version),
    )
    canonical = _canonical_entity_rows(sources)
    email_db.entities.delete_entity_mentions_for_email(uid, commit=False)
    for (key, version), entries in _entities_by_provenance(canonical).items():
        email_db.entities.insert_entities_batch_idempotent(
            uid, entries, extractor_key=key, extraction_version=version, commit=False
        )
    return len(canonical)


def _canonical_entity_rows(sources: tuple[tuple[Any, str, str], ...]) -> dict[tuple[str, str], tuple[str, str, str, str, str]]:
    """Deduplicate entity rows by normalized value and type while retaining provenance."""
    canonical: dict[tuple[str, str], tuple[str, str, str, str, str]] = {}
    for entities, key, version in sources:
        for entity in entities:
            text, kind, normalized = _coerce_entity(entity)
            canonical[(normalized, kind)] = (text, kind, normalized, key, version)
    return canonical


def _entities_by_provenance(
    canonical: dict[tuple[str, str], tuple[str, str, str, str, str]],
) -> dict[tuple[str, str], list[tuple[str, str, str]]]:
    """Group entity rows by their extraction provenance."""
    grouped: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for text, kind, normalized, key, version in canonical.values():
        grouped.setdefault((key, version), []).append((text, kind, normalized))
    return grouped
