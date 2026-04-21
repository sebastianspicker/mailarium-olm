"""Reingest, reembed, and reset helpers for the ingestion CLI."""

from __future__ import annotations

import argparse
import os
import shutil
from typing import Any

from .config import get_settings


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

    extractor = exchange_entities_from_email
    parser = parse_olm_fn
    for email in parser(olm_path):
        if email.uid not in all_uids:
            continue

        if email_db.update_v7_metadata(email, commit=False):
            updated += 1

        exchange_entities = extractor(email) if extractor else []
        if exchange_entities:
            email_db.insert_entities_batch(email.uid, exchange_entities, commit=False)
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
    from .language_detector import detect_language
    from .sentiment_analyzer import analyze as analyze_sentiment

    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = EmailDatabase(resolved_sqlite)

    rows = email_db.conn.execute(
        "SELECT uid, body_text FROM emails "
        "WHERE (detected_language IS NULL OR sentiment_label IS NULL) "
        "AND body_text IS NOT NULL AND LENGTH(TRIM(body_text)) >= 20"
    ).fetchall()

    total_missing = len(rows)
    if not total_missing:
        email_db.close()
        return {"updated": 0, "total_missing": 0, "message": "All emails already have analytics data."}

    batch: list[tuple[str | None, str | None, float | None, str]] = []
    for row in rows:
        body = row["body_text"]
        lang = detect_language(body)
        sent = analyze_sentiment(body)
        batch.append((lang if lang != "unknown" else None, sent.sentiment, sent.score, row["uid"]))

    updated = email_db.update_analytics_batch(batch)
    email_db.close()
    return {
        "updated": updated,
        "total_missing": total_missing,
        "message": f"Computed language and sentiment for {updated} emails.",
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

    for uid in sorted(all_uids):
        email_dict = email_db.get_email_for_reembed(uid)
        if email_dict is None:
            skipped_no_body += 1
            continue

        existing_ids = embedder.get_existing_ids(refresh=False)
        body_chunk_ids = [
            cid for cid in existing_ids if cid.startswith(f"{uid}__") and "__att_" not in cid and "__img_" not in cid
        ]
        if body_chunk_ids:
            embedder.collection.delete(ids=body_chunk_ids)
            existing_ids.difference_update(body_chunk_ids)
            chunks_deleted += len(body_chunk_ids)
        email_db.delete_sparse_by_uid(uid)

        chunks = chunk_email(email_dict)
        added = embedder.upsert_chunks(chunks, batch_size=batch_size)
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
    if os.path.exists(sqlite_file):
        os.remove(sqlite_file)
        print(f"Deleted SQLite DB: {sqlite_file}")
    chromadb_dir = args.chromadb_path or settings.chromadb_path
    if os.path.isdir(chromadb_dir):
        shutil.rmtree(chromadb_dir)
        print(f"Deleted ChromaDB: {chromadb_dir}")
