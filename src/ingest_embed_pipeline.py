"""Embedding/write pipeline helpers extracted from ``src.ingest``."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .chunker import EmailChunk
from .parse_olm import Email

if TYPE_CHECKING:
    from .email_db import EmailDatabase
    from .embedder import EmailEmbedder

logger = logging.getLogger(__name__)

_SENTINEL = object()
EXCHANGE_ENTITY_EXTRACTOR_KEY = "exchange_metadata"
EXCHANGE_ENTITY_EXTRACTION_VERSION = "1"


def _attachment_completion_status(email: Email) -> str:
    attachment_requested = bool(getattr(email, "_ingest_attachment_requested", False))
    if not attachment_requested:
        return "not_requested"
    attachments = getattr(email, "attachments", None) or []
    if not attachments or not bool(getattr(email, "has_attachments", False)):
        return "completed"
    normalized_states = {str(att.get("extraction_state") or "").strip().lower() for att in attachments if isinstance(att, dict)}
    if "unsupported" in normalized_states:
        return "unsupported"
    if normalized_states & {
        "binary_only",
        "image_embedding_only",
        "ocr_failed",
        "extraction_failed",
        "archive_inventory_extracted",
        "sidecar_text_extracted",
    }:
        return "degraded"
    if any(
        str(att.get("evidence_strength") or "").strip().lower() == "weak_reference"
        for att in attachments
        if isinstance(att, dict)
    ):
        return "degraded"
    return "pending"


def _image_completion_status(email: Email) -> str:
    image_requested = bool(getattr(email, "_ingest_image_requested", False))
    if not image_requested:
        return "not_requested"
    attachments = getattr(email, "attachments", None) or []
    if not attachments or not bool(getattr(email, "has_attachments", False)):
        return "completed"
    image_chunk_count = int(getattr(email, "_ingest_image_chunk_count", 0) or 0)
    image_attachments = [
        att
        for att in attachments
        if isinstance(att, dict) and str(att.get("extraction_state") or "").strip().lower() == "image_embedding_only"
    ]
    if not image_attachments:
        return "completed"
    if image_chunk_count > 0:
        return "pending"
    return "degraded"


def _ingest_state_rows(emails: list[Email]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for email in emails:
        email_uid = str(getattr(email, "uid", "") or "")
        if not email_uid:
            continue
        rows.append(
            {
                "email_uid": email_uid,
                "body_chunk_count": int(getattr(email, "_ingest_body_chunk_count", 0) or 0),
                "attachment_chunk_count": int(getattr(email, "_ingest_attachment_chunk_count", 0) or 0),
                "image_chunk_count": int(getattr(email, "_ingest_image_chunk_count", 0) or 0),
                "vector_chunk_count": (
                    int(getattr(email, "_ingest_body_chunk_count", 0) or 0)
                    + int(getattr(email, "_ingest_attachment_chunk_count", 0) or 0)
                    + int(getattr(email, "_ingest_image_chunk_count", 0) or 0)
                ),
                "attachment_status": _attachment_completion_status(email),
                "image_status": _image_completion_status(email),
            }
        )
    return rows


def _completed_ingest_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    completed_rows: list[dict[str, object]] = []
    for row in rows:
        completed = dict(row)
        if str(completed.get("attachment_status") or "") == "pending":
            completed["attachment_status"] = "completed"
        if str(completed.get("image_status") or "") == "pending":
            completed["image_status"] = "completed"
        completed_rows.append(completed)
    return completed_rows


def _chunk_batches(chunks: list[EmailChunk], *, max_chunks: int) -> list[list[EmailChunk]]:
    """Split one batch into bounded chunk sub-batches for embedding throughput."""
    bounded = max(int(max_chunks), 1)
    return [chunks[index : index + bounded] for index in range(0, len(chunks), bounded)]


def _chunk_uid(chunk: Any) -> str:
    if isinstance(chunk, dict):
        metadata = chunk.get("metadata")
        if isinstance(metadata, dict) and metadata.get("uid"):
            return str(metadata.get("uid") or "")
        direct_uid = str(chunk.get("uid") or "")
        if direct_uid:
            return direct_uid
        chunk_id = str(chunk.get("chunk_id") or "")
        if "__" in chunk_id:
            return chunk_id.split("__", 1)[0]
        return ""
    return str(getattr(chunk, "uid", "") or "")


def _chunk_id(chunk: Any) -> str:
    if isinstance(chunk, dict):
        return str(chunk.get("chunk_id") or "")
    return str(getattr(chunk, "chunk_id", "") or "")


class _EmbedPipeline:
    """Background thread that embeds and writes batches while parsing continues."""

    def __init__(
        self,
        embedder: EmailEmbedder | None,
        email_db: EmailDatabase | None,
        entity_extractor_fn: Callable[[str, str], list[Any]] | None,
        batch_size: int,
        ingestion_run_id: int | None = None,
        entity_extractor_key: str = "",
        entity_extraction_version: str = "",
    ) -> None:
        self._embedder = embedder
        self._email_db = email_db
        self._entity_extractor_fn = entity_extractor_fn
        self._entity_extractor_key = str(entity_extractor_key or "")
        self._entity_extraction_version = str(entity_extraction_version or "")
        self._batch_size = batch_size
        self._ingestion_run_id = ingestion_run_id
        self._queue: queue.Queue = queue.Queue(maxsize=4)
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

        self._detailed_timing = False
        self._cooldown = float(os.environ.get("INGEST_BATCH_COOLDOWN", "0"))
        self._wal_checkpoint_interval = int(os.environ.get("INGEST_WAL_CHECKPOINT_INTERVAL", "10"))

        self.chunks_added = 0
        self.sqlite_inserted = 0
        self.batches_written = 0
        self.embed_seconds = 0.0
        self.write_seconds = 0.0
        self.sqlite_seconds = 0.0
        self.entity_seconds = 0.0
        self.analytics_seconds = 0.0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, chunks: list[EmailChunk], emails: list[Email]) -> None:
        """Enqueue a batch for the consumer. Blocks if queue is full."""
        if not chunks and not emails:
            return
        if self._error is not None:
            raise self._error
        self._queue.put((chunks, emails))

    def finish(self) -> None:
        """Signal end-of-input and wait for consumer to drain."""
        if self._error is None:
            self._queue.put(_SENTINEL)
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self._error is not None:
            raise self._error

    def abort(self) -> BaseException | None:
        """Best-effort producer-side shutdown without raising consumer failures."""
        if self._thread is not None:
            if self._error is None:
                self._queue.put(_SENTINEL)
            self._thread.join()
            self._thread = None
        return self._error

    def _run(self) -> None:
        """Consumer loop — runs in background thread."""
        try:
            while True:
                item = self._queue.get()
                if item is _SENTINEL:
                    break
                chunks, emails = item
                self._process_batch(chunks, emails)
        except BaseException as exc:
            self._error = exc
            while True:
                try:
                    item = self._queue.get_nowait()
                    if item is _SENTINEL:
                        break
                except Exception:
                    break

    def _cleanup_vector_batch(self, chunk_ids: list[str]) -> None:
        filtered_ids = [chunk_id for chunk_id in chunk_ids if chunk_id]
        if not filtered_ids:
            return

        if self._email_db and hasattr(self._email_db, "delete_sparse_by_chunk_ids"):
            try:
                self._email_db.delete_sparse_by_chunk_ids(filtered_ids)
            except Exception:
                logger.warning("Failed to remove sparse vectors for failed ingest batch", exc_info=True)

        if self._embedder is None:
            return

        try:
            collection = getattr(self._embedder, "collection", None)
            delete = getattr(collection, "delete", None) if collection is not None else None
            if callable(delete):
                delete(ids=filtered_ids)
        except Exception:
            logger.warning("Failed to remove dense vectors for failed ingest batch", exc_info=True)

        try:
            get_existing_ids = getattr(self._embedder, "get_existing_ids", None)
            if callable(get_existing_ids):
                cached_ids = get_existing_ids(refresh=False)
                if isinstance(cached_ids, set):
                    cached_ids.difference_update(filtered_ids)
            touch_revision = getattr(self._embedder, "_touch_collection_revision", None)
            if callable(touch_revision):
                touch_revision()
        except Exception:
            logger.debug("Failed to refresh embedder cache after failed ingest cleanup", exc_info=True)

    def _mark_batch_failed(self, email_uids: list[str], *, error_message: str) -> None:
        if not self._email_db or not email_uids or not hasattr(self._email_db, "mark_ingest_batch_failed"):
            return
        try:
            self._email_db.mark_ingest_batch_failed(email_uids, error_message=error_message)
        except Exception:
            logger.warning("Failed to persist ingest-batch failure state", exc_info=True)

    def _process_batch(self, chunks: list[EmailChunk], emails: list[Email]) -> None:
        ingest_rows = _ingest_state_rows(emails)
        inserted_ingest_rows: list[dict[str, object]] = []
        new_chunks: list[EmailChunk] = list(chunks)
        batch_chunk_ids: list[str] = [_chunk_id(chunk) for chunk in new_chunks if _chunk_id(chunk)]
        email_commit_pending = False
        relational_transaction_open = False
        conn = getattr(self._email_db, "conn", None) if self._email_db else None
        supports_manual_transaction = all(hasattr(conn, attr) for attr in ("execute", "commit", "rollback"))
        try:
            if self._email_db and emails:
                t0 = time.monotonic()
                if supports_manual_transaction:
                    assert conn is not None
                    logger.debug(
                        "Opening SQLite ingest transaction (run_id=%s, emails=%s, chunks=%s)",
                        self._ingestion_run_id,
                        len(emails),
                        len(chunks),
                    )
                    conn.execute("BEGIN IMMEDIATE")
                    relational_transaction_open = True
                    inserted_uids = self._email_db.insert_emails_batch(
                        emails,
                        ingestion_run_id=self._ingestion_run_id,
                        commit=False,
                    )
                else:
                    inserted_uids = self._email_db.insert_emails_batch(
                        emails,
                        ingestion_run_id=self._ingestion_run_id,
                    )
                self.sqlite_inserted += len(inserted_uids)
                dt_sqlite = time.monotonic() - t0
                self.sqlite_seconds += dt_sqlite
                inserted_ingest_rows = [row for row in ingest_rows if str(row.get("email_uid") or "") in inserted_uids]
                if hasattr(self._email_db, "mark_ingest_batch_pending"):
                    if inserted_ingest_rows:
                        if supports_manual_transaction:
                            self._email_db.mark_ingest_batch_pending(inserted_ingest_rows, commit=False)
                        else:
                            self._email_db.mark_ingest_batch_pending(inserted_ingest_rows)

                new_emails = [email for email in emails if email.uid in inserted_uids]
                new_chunks = [chunk for chunk in chunks if _chunk_uid(chunk) in inserted_uids]
                batch_chunk_ids = [_chunk_id(chunk) for chunk in new_chunks if _chunk_id(chunk)]
                if len(new_emails) < len(emails):
                    logger.debug(
                        "Skipped %d already-inserted emails for entity/analytics processing",
                        len(emails) - len(new_emails),
                    )
                if len(new_chunks) < len(chunks):
                    logger.debug(
                        "Skipped %d already-indexed email chunks for vector persistence",
                        len(chunks) - len(new_chunks),
                    )

                t1 = time.monotonic()
                event_rows: list[tuple[object, ...]] = []
                if self._email_db and hasattr(self._email_db, "upsert_event_records"):
                    from .event_extractor import extract_event_rows_from_email

                    for email in new_emails:
                        event_rows.extend(extract_event_rows_from_email(email))
                    if event_rows:
                        self._email_db.upsert_event_records(event_rows, commit=False)

                if self._entity_extractor_fn:
                    from .entity_occurrence_extractor import extract_entity_occurrence_rows_from_email
                    from .language_analytics import select_entity_text_from_email

                    for email in new_emails:
                        attachments = getattr(email, "attachments", None) or []
                        has_entity_body_surface = any(
                            str(getattr(email, field, "") or "").strip()
                            for field in ("forensic_body_text", "clean_body", "raw_body_text")
                        ) or any(
                            str((attachment or {}).get(key) or "").strip()
                            for attachment in attachments
                            if isinstance(attachment, dict)
                            for key in ("extracted_text", "text_preview")
                        )
                        if not has_entity_body_surface:
                            continue
                        entity_text, _entity_source = select_entity_text_from_email(email)
                        if not entity_text:
                            continue
                        entities = self._entity_extractor_fn(entity_text, email.sender_email)
                        if entities:
                            normalized_entities = [
                                (entity.text, entity.entity_type, entity.normalized_form) for entity in entities
                            ]
                            self._email_db.insert_entities_batch(
                                email.uid,
                                normalized_entities,
                                extractor_key=self._entity_extractor_key,
                                extraction_version=self._entity_extraction_version,
                                commit=False,
                            )
                            if hasattr(self._email_db, "insert_entity_occurrences"):
                                occurrence_rows = extract_entity_occurrence_rows_from_email(email, normalized_entities)
                                if occurrence_rows:
                                    self._email_db.insert_entity_occurrences(
                                        email.uid,
                                        occurrence_rows,
                                        extractor_key=self._entity_extractor_key,
                                        extraction_version=self._entity_extraction_version,
                                        commit=False,
                                    )
                for email in new_emails:
                    exchange_entities = _exchange_entities_from_email(email)
                    if exchange_entities:
                        self._email_db.insert_entities_batch(
                            email.uid,
                            exchange_entities,
                            extractor_key=EXCHANGE_ENTITY_EXTRACTOR_KEY,
                            extraction_version=EXCHANGE_ENTITY_EXTRACTION_VERSION,
                            commit=False,
                        )
                dt_entity = time.monotonic() - t1
                self.entity_seconds += dt_entity

                t2 = time.monotonic()
                self._compute_analytics(new_emails, commit=False)
                dt_analytics = time.monotonic() - t2
                self.analytics_seconds += dt_analytics

                self.write_seconds += dt_sqlite + dt_entity + dt_analytics
                email_commit_pending = bool(inserted_ingest_rows)

                if inserted_ingest_rows and (not self._embedder or not new_chunks):
                    if hasattr(self._email_db, "mark_ingest_batch_completed"):
                        if supports_manual_transaction:
                            self._email_db.mark_ingest_batch_completed(inserted_ingest_rows, commit=False)
                        else:
                            self._email_db.mark_ingest_batch_completed(inserted_ingest_rows)
                    if supports_manual_transaction:
                        assert conn is not None
                        logger.debug(
                            "Committing SQLite ingest transaction without vector write (run_id=%s, emails=%s)",
                            self._ingestion_run_id,
                            len(inserted_ingest_rows),
                        )
                        conn.commit()
                    relational_transaction_open = False
                    email_commit_pending = False
                elif supports_manual_transaction and relational_transaction_open and not new_chunks:
                    assert conn is not None
                    logger.debug(
                        "Committing empty SQLite ingest transaction after dedupe (run_id=%s)",
                        self._ingestion_run_id,
                    )
                    conn.commit()
                    relational_transaction_open = False
                    email_commit_pending = False
            if self._embedder and new_chunks:
                t0 = time.monotonic()
                added = 0
                for chunk_group in _chunk_batches(new_chunks, max_chunks=self._batch_size):
                    try:
                        added += self._embedder.add_chunks(
                            chunk_group,
                            batch_size=self._batch_size,
                            skip_existing_check=True,
                        )
                    except TypeError as exc:
                        if "skip_existing_check" not in str(exc):
                            raise
                        added += self._embedder.add_chunks(
                            chunk_group,
                            batch_size=self._batch_size,
                        )
                dt_embed = time.monotonic() - t0
                self.chunks_added += added
                self.batches_written += 1
                self.embed_seconds += dt_embed
                if self._email_db and inserted_ingest_rows and email_commit_pending:
                    completed_rows = _completed_ingest_rows(inserted_ingest_rows)
                    self._email_db.mark_ingest_batch_completed(completed_rows, commit=True)
                    relational_transaction_open = False
                    email_commit_pending = False
                elif self._email_db and inserted_ingest_rows and not supports_manual_transaction:
                    completed_rows = _completed_ingest_rows(inserted_ingest_rows)
                    if hasattr(self._email_db, "mark_ingest_batch_completed"):
                        self._email_db.mark_ingest_batch_completed(completed_rows)
                    email_commit_pending = False
                rate = len(new_chunks) / dt_embed if dt_embed > 0 else 0
                logger.info(
                    "Batch %d: %d chunks embedded in %.1fs (%.0f chunks/s)",
                    self.batches_written,
                    len(new_chunks),
                    dt_embed,
                    rate,
                )
        except Exception as exc:
            if relational_transaction_open:
                assert conn is not None
                logger.debug(
                    "Rolling back SQLite ingest transaction after batch failure (run_id=%s)",
                    self._ingestion_run_id,
                    exc_info=True,
                )
                conn.rollback()
                relational_transaction_open = False
            self._cleanup_vector_batch(batch_chunk_ids)
            email_uids = [str(row.get("email_uid") or "") for row in inserted_ingest_rows if str(row.get("email_uid") or "")]
            self._mark_batch_failed(email_uids, error_message=str(exc))
            raise

        wal_due = (
            self._wal_checkpoint_interval > 0
            and self._email_db
            and self.batches_written > 0
            and self.batches_written % self._wal_checkpoint_interval == 0
        )
        if wal_due:
            self._checkpoint_wal()

        if self._cooldown > 0:
            time.sleep(self._cooldown)

    def _checkpoint_wal(self) -> None:
        """Run a passive WAL checkpoint on the email SQLite database."""
        try:
            if self._email_db is not None:
                self._email_db.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            logger.debug("SQLite WAL checkpoint completed (batch %d)", self.batches_written)
        except Exception:
            logger.debug("WAL checkpoint failed (non-critical)", exc_info=True)

    def _compute_analytics(self, emails: list[Email], *, commit: bool = True) -> None:
        """Detect language and sentiment for emails in this batch."""
        if not self._email_db:
            return
        from .language_analytics import (
            build_analytics_update_row,
            build_surface_language_rows_from_email,
            select_analytics_text_from_email,
        )

        rows: list[tuple[object, ...]] = []
        surface_rows: list[tuple[object, ...]] = []
        for email in emails:
            body, source = select_analytics_text_from_email(email)
            if not body:
                continue
            rows.append(build_analytics_update_row(uid=email.uid, text=body, source=source))
            surface_rows.extend(build_surface_language_rows_from_email(email))
        if rows:
            try:
                self._email_db.update_analytics_batch(rows, commit=commit)
            except TypeError as exc:
                if "commit" not in str(exc):
                    raise
                self._email_db.update_analytics_batch(rows)
        if surface_rows and hasattr(self._email_db, "upsert_language_surface_analytics"):
            try:
                self._email_db.upsert_language_surface_analytics(surface_rows, commit=commit)
            except TypeError as exc:
                if "commit" not in str(exc):
                    raise
                self._email_db.upsert_language_surface_analytics(surface_rows)


def _exchange_entities_from_email(email: Email) -> list[tuple[str, str, str]]:
    """Extract entity tuples from Exchange-extracted fields on an Email object."""
    entities: list[tuple[str, str, str]] = []

    for link in getattr(email, "exchange_extracted_links", []):
        url = link.get("url", "").strip()
        if url:
            entities.append((url, "url", url.lower()))

    for address in getattr(email, "exchange_extracted_emails", []):
        address = address.strip()
        if address:
            entities.append((address, "email", address.lower()))

    for contact in getattr(email, "exchange_extracted_contacts", []):
        contact = contact.strip()
        if contact:
            entities.append((contact, "person", contact.lower()))

    for meeting in getattr(email, "exchange_extracted_meetings", []):
        subject = meeting.get("subject", "").strip()
        if subject:
            entities.append((subject, "event", subject.lower()))

    return entities
