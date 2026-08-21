"""Run bounded embedding and persistence batches with rollback and checkpoint support."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-instance-attributes,too-many-locals,too-many-nested-blocks,too-many-positional-arguments,too-many-statements

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
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


@dataclass
class _BatchState:
    """Mutable state shared by the bounded ingest batch stages."""

    ingest_rows: list[dict[str, object]]
    inserted_ingest_rows: list[dict[str, object]] = field(default_factory=list)
    new_chunks: list[EmailChunk] = field(default_factory=list)
    batch_chunk_ids: list[str] = field(default_factory=list)
    email_commit_pending: bool = False
    relational_transaction_open: bool = False


def _attachment_completion_status(email: Email) -> str:
    """Derive attachment completion from requested extraction and chunk outcomes."""
    attachment_requested = bool(getattr(email, "_ingest_attachment_requested", False))
    if not attachment_requested:
        return "not_requested"
    attachments = getattr(email, "attachments", None) or []
    if not attachments or not bool(getattr(email, "has_attachments", False)):
        return "completed"
    normalized_states = {str(att.get("extraction_state") or "").strip().lower() for att in attachments if isinstance(att, dict)}
    return _attachment_extraction_outcome(
        normalized_states,
        has_weak_reference=any(
            str(att.get("evidence_strength") or "").strip().lower() == "weak_reference"
            for att in attachments
            if isinstance(att, dict)
        ),
    )


def _attachment_extraction_outcome(states: set[str], *, has_weak_reference: bool) -> str:
    """Map normalized attachment extraction states to the durable ingest status."""
    if "unsupported" in states:
        return "unsupported"
    degraded_states = {
        "binary_only",
        "image_embedding_only",
        "ocr_failed",
        "extraction_failed",
        "archive_inventory_extracted",
        "sidecar_text_extracted",
    }
    if states & degraded_states or has_weak_reference:
        return "degraded"
    return "pending"


def _image_completion_status(email: Email) -> str:
    """Derive image completion from request state and generated image chunks."""
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
    """Build completion-ledger rows from per-email chunk counters."""
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
    """Convert processed emails into final ingest-state rows."""
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
    """Return the parent email UID carried by a chunk."""
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
    """Return the stable chunk identifier used by vector and sparse indexes."""
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
        """Prepare the bounded producer-consumer pipeline without starting its worker thread."""
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
        """Start the background consumer before producers submit ingest batches."""
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
        """Consumer loop - runs in background thread."""
        try:
            while True:
                item = self._queue.get()
                if item is _SENTINEL:
                    break
                chunks, emails = item
                self._process_batch(chunks, emails)
        except BaseException as exc:  # pylint: disable=broad-exception-caught
            self._error = exc
            self._discard_queued_batches_after_consumer_error()

    def _discard_queued_batches_after_consumer_error(self) -> None:
        """Discard pending batches so producers cannot block after consumer failure."""
        while True:
            try:
                item = self._queue.get_nowait()
                if item is _SENTINEL:
                    break
            except queue.Empty:
                break

    def _cleanup_vector_batch(self, chunk_ids: list[str]) -> None:
        """Remove partially written vector and sparse data after a batch failure."""
        filtered_ids = [chunk_id for chunk_id in chunk_ids if chunk_id]
        if not filtered_ids:
            return

        self._cleanup_sparse_vectors(filtered_ids)
        if self._embedder is None:
            return
        self._cleanup_dense_vectors(filtered_ids)
        self._refresh_embedder_cache(filtered_ids)

    def _cleanup_sparse_vectors(self, chunk_ids: list[str]) -> None:
        """Delete sparse vectors for a failed batch and commit the sparse index."""
        if self._email_db and hasattr(self._email_db, "delete_sparse_by_chunk_ids"):
            try:
                self._email_db.delete_sparse_by_chunk_ids(chunk_ids)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to remove sparse vectors for failed ingest batch", exc_info=True)

    def _cleanup_dense_vectors(self, chunk_ids: list[str]) -> None:
        """Delete dense vectors for a failed batch when the backend supports deletion."""
        try:
            for collection_name in ("collection", "image_collection"):
                collection = getattr(self._embedder, collection_name, None)
                delete = getattr(collection, "delete", None) if collection is not None else None
                if callable(delete):
                    delete(ids=chunk_ids)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to remove dense vectors for failed ingest batch", exc_info=True)

    def _refresh_embedder_cache(self, chunk_ids: list[str]) -> None:
        """Refresh cached vector identifiers after cleanup to prevent stale deduplication."""
        try:
            get_existing_ids = getattr(self._embedder, "get_existing_ids", None)
            if callable(get_existing_ids):
                cached_ids = get_existing_ids(refresh=False)
                if isinstance(cached_ids, set):
                    cached_ids.difference_update(chunk_ids)
            touch_revision = getattr(self._embedder, "_touch_collection_revision", None)
            if callable(touch_revision):
                touch_revision()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Failed to refresh embedder cache after failed ingest cleanup", exc_info=True)

    def _mark_batch_failed(self, email_uids: list[str], *, error_message: str) -> None:
        """Persist failed ingest-state rows without hiding the original exception."""
        if not self._email_db or not email_uids or not hasattr(self._email_db, "mark_ingest_batch_failed"):
            return
        try:
            self._email_db.mark_ingest_batch_failed(email_uids, error_message=error_message)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to persist ingest-batch failure state", exc_info=True)

    def _process_batch(self, chunks: list[EmailChunk], emails: list[Email]) -> None:
        """Persist one queued batch across relational, sparse, and dense stores."""
        operation = getattr(self._email_db, "operation", None) if self._email_db else None
        operation_context = operation() if callable(operation) else nullcontext()
        with operation_context:
            state = _BatchState(
                ingest_rows=_ingest_state_rows(emails),
                new_chunks=list(chunks),
                batch_chunk_ids=[_chunk_id(chunk) for chunk in chunks if _chunk_id(chunk)],
            )
            conn = getattr(self._email_db, "conn", None) if self._email_db else None
            supports_manual_transaction = all(hasattr(conn, attr) for attr in ("execute", "commit", "rollback"))
            try:
                new_emails, dt_sqlite = self._persist_relational_batch(
                    chunks,
                    emails,
                    state,
                    conn,
                    supports_manual_transaction,
                )
                dt_entity, dt_analytics = self._persist_batch_metadata(new_emails)
                self.write_seconds += dt_sqlite + dt_entity + dt_analytics
                self._complete_relational_only_batch(state, conn, supports_manual_transaction)
                self._embed_batch_chunks(state, supports_manual_transaction)
            except Exception as exc:
                self._rollback_failed_batch(state, conn, exc)
                raise
            self._apply_batch_maintenance()

    def _persist_relational_batch(
        self,
        chunks: list[EmailChunk],
        emails: list[Email],
        state: _BatchState,
        conn: Any,
        supports_manual_transaction: bool,
    ) -> tuple[list[Email], float]:
        """Write email metadata and enrichment rows within one database transaction."""
        if not self._email_db or not emails:
            return [], 0.0
        started = time.monotonic()
        inserted_uids = self._insert_emails_for_batch(emails, chunks, state, conn, supports_manual_transaction)
        self.sqlite_inserted += len(inserted_uids)
        state.inserted_ingest_rows = [row for row in state.ingest_rows if str(row.get("email_uid") or "") in inserted_uids]
        self._mark_batch_pending(state, supports_manual_transaction)
        new_emails = [email for email in emails if email.uid in inserted_uids]
        state.new_chunks = [chunk for chunk in chunks if _chunk_uid(chunk) in inserted_uids]
        state.batch_chunk_ids = [_chunk_id(chunk) for chunk in state.new_chunks if _chunk_id(chunk)]
        self._log_deduplicated_batch(emails, chunks, new_emails, state.new_chunks)
        elapsed = time.monotonic() - started
        self.sqlite_seconds += elapsed
        state.email_commit_pending = bool(state.inserted_ingest_rows)
        return new_emails, elapsed

    def _insert_emails_for_batch(
        self,
        emails: list[Email],
        chunks: list[EmailChunk],
        state: _BatchState,
        conn: Any,
        supports_manual_transaction: bool,
    ) -> set[str]:
        """Insert new emails and return the subset eligible for downstream enrichment."""
        assert self._email_db is not None
        if not supports_manual_transaction:
            return self._email_db.insert_emails_batch(emails, ingestion_run_id=self._ingestion_run_id)
        assert conn is not None
        logger.debug(
            "Opening SQLite ingest transaction (run_id=%s, emails=%s, chunks=%s)",
            self._ingestion_run_id,
            len(emails),
            len(chunks),
        )
        conn.execute("BEGIN IMMEDIATE")
        state.relational_transaction_open = True
        return self._email_db.insert_emails_batch(emails, ingestion_run_id=self._ingestion_run_id, commit=False)

    def _mark_batch_pending(self, state: _BatchState, supports_manual_transaction: bool) -> None:
        """Record pending ingest state before vector writes begin."""
        if not self._email_db or not state.inserted_ingest_rows or not hasattr(self._email_db, "mark_ingest_batch_pending"):
            return
        if supports_manual_transaction:
            self._email_db.mark_ingest_batch_pending(state.inserted_ingest_rows, commit=False)
        else:
            self._email_db.mark_ingest_batch_pending(state.inserted_ingest_rows)

    @staticmethod
    def _log_deduplicated_batch(
        emails: list[Email], chunks: list[EmailChunk], new_emails: list[Email], new_chunks: list[EmailChunk]
    ) -> None:
        """Log how many emails and chunks were skipped as already indexed."""
        if len(new_emails) < len(emails):
            logger.debug("Skipped %d already-inserted emails for entity/analytics processing", len(emails) - len(new_emails))
        if len(new_chunks) < len(chunks):
            logger.debug("Skipped %d already-indexed email chunks for vector persistence", len(chunks) - len(new_chunks))

    def _persist_batch_metadata(self, emails: list[Email]) -> tuple[float, float]:
        """Persist events, entities, and communication metadata for new emails."""
        entity_started = time.monotonic()
        self._persist_events(emails)
        self._persist_extracted_entities(emails)
        self._persist_exchange_entities(emails)
        entity_elapsed = time.monotonic() - entity_started
        self.entity_seconds += entity_elapsed
        analytics_started = time.monotonic()
        self._compute_analytics(emails, commit=False)
        analytics_elapsed = time.monotonic() - analytics_started
        self.analytics_seconds += analytics_elapsed
        return entity_elapsed, analytics_elapsed

    def _persist_events(self, emails: list[Email]) -> None:
        """Extract and persist calendar-like events for a batch of emails."""
        if not self._email_db or not hasattr(self._email_db, "upsert_event_records"):
            return
        from .event_extractor import extract_event_rows_from_email

        event_rows = [row for email in emails for row in extract_event_rows_from_email(email)]
        if event_rows:
            self._email_db.upsert_event_records(event_rows, commit=False)

    def _persist_extracted_entities(self, emails: list[Email]) -> None:
        """Extract body entities and persist their occurrences and canonical rows."""
        if not self._email_db or not self._entity_extractor_fn:
            return
        from .entity_occurrence_extractor import extract_entity_occurrence_rows_from_email
        from .language_analytics import select_entity_text_from_email

        for email in emails:
            entity_text, _source = select_entity_text_from_email(email)
            if not self._has_entity_surface(email) or not entity_text:
                continue
            entities = self._entity_extractor_fn(entity_text, email.sender_email)
            normalized_entities = [(entity.text, entity.entity_type, entity.normalized_form) for entity in entities]
            if not normalized_entities:
                continue
            self._email_db.insert_entities_batch(
                email.uid,
                normalized_entities,
                extractor_key=self._entity_extractor_key,
                extraction_version=self._entity_extraction_version,
                commit=False,
            )
            self._persist_entity_occurrences(email, normalized_entities, extract_entity_occurrence_rows_from_email)

    @staticmethod
    def _has_entity_surface(email: Email) -> bool:
        body_fields = ("forensic_body_text", "clean_body", "raw_body_text")
        attachment_fields = ("extracted_text", "text_preview")
        if any(str(getattr(email, field, "") or "").strip() for field in body_fields):
            return True
        return any(
            str((attachment or {}).get(key) or "").strip()
            for attachment in (getattr(email, "attachments", None) or [])
            if isinstance(attachment, dict)
            for key in attachment_fields
        )

    def _persist_entity_occurrences(self, email: Email, entities: list[tuple[str, str, str]], extractor: Callable) -> None:
        """Write provenance-aware entity occurrences for each email."""
        if not self._email_db or not hasattr(self._email_db, "insert_entity_occurrences"):
            return
        occurrence_rows = extractor(email, entities)
        if occurrence_rows:
            self._email_db.insert_entity_occurrences(
                email.uid,
                occurrence_rows,
                extractor_key=self._entity_extractor_key,
                extraction_version=self._entity_extraction_version,
                commit=False,
            )

    def _persist_exchange_entities(self, emails: list[Email]) -> None:
        """Persist sender and recipient entities derived from Exchange metadata."""
        if not self._email_db:
            return
        for email in emails:
            entities = _exchange_entities_from_email(email)
            if entities:
                self._email_db.insert_entities_batch(
                    email.uid,
                    entities,
                    extractor_key=EXCHANGE_ENTITY_EXTRACTOR_KEY,
                    extraction_version=EXCHANGE_ENTITY_EXTRACTION_VERSION,
                    commit=False,
                )

    def _complete_relational_only_batch(self, state: _BatchState, conn: Any, supports_manual_transaction: bool) -> None:
        """Commit batches that contain no vector chunks and mark them complete."""
        if not state.inserted_ingest_rows or (self._embedder and state.new_chunks):
            self._commit_empty_transaction(state, conn, supports_manual_transaction)
            return
        assert self._email_db is not None
        if hasattr(self._email_db, "mark_ingest_batch_completed"):
            self._email_db.mark_ingest_batch_completed(state.inserted_ingest_rows, commit=not supports_manual_transaction)
        if supports_manual_transaction:
            assert conn is not None
            logger.debug(
                "Committing SQLite ingest transaction without vector write (run_id=%s, emails=%s)",
                self._ingestion_run_id,
                len(state.inserted_ingest_rows),
            )
            conn.commit()
        state.relational_transaction_open = False
        state.email_commit_pending = False

    def _commit_empty_transaction(self, state: _BatchState, conn: Any, supports_manual_transaction: bool) -> None:
        """Commit metadata-only work when no pending ingest rows exist."""
        if not supports_manual_transaction or not state.relational_transaction_open or state.new_chunks:
            return
        assert conn is not None
        logger.debug("Committing empty SQLite ingest transaction after dedupe (run_id=%s)", self._ingestion_run_id)
        conn.commit()
        state.relational_transaction_open = False
        state.email_commit_pending = False

    def _embed_batch_chunks(self, state: _BatchState, supports_manual_transaction: bool) -> None:
        """Write chunk vectors and return sparse, dense, and timing counts."""
        if not self._embedder or not state.new_chunks:
            return
        started = time.monotonic()
        added = sum(self._add_chunk_group(group) for group in _chunk_batches(state.new_chunks, max_chunks=self._batch_size))
        elapsed = time.monotonic() - started
        self.chunks_added += added
        self.batches_written += 1
        self.embed_seconds += elapsed
        self._complete_vector_batch(state, supports_manual_transaction)
        rate = len(state.new_chunks) / elapsed if elapsed > 0 else 0
        logger.info(
            "Batch %d: %d chunks embedded in %.1fs (%.0f chunks/s)",
            self.batches_written,
            len(state.new_chunks),
            elapsed,
            rate,
        )

    def _add_chunk_group(self, chunk_group: list[EmailChunk]) -> int:
        """Submit one chunk group to the embedder and accumulate write counts."""
        assert self._embedder is not None
        try:
            return self._embedder.add_chunks(chunk_group, batch_size=self._batch_size, skip_existing_check=True)
        except TypeError as exc:
            if "skip_existing_check" not in str(exc):
                raise
            return self._embedder.add_chunks(chunk_group, batch_size=self._batch_size)

    def _complete_vector_batch(self, state: _BatchState, supports_manual_transaction: bool) -> None:
        """Mark ingest state complete after all vector writes succeed."""
        if not self._email_db or not state.inserted_ingest_rows:
            return
        completed_rows = _completed_ingest_rows(state.inserted_ingest_rows)
        if state.email_commit_pending:
            self._email_db.mark_ingest_batch_completed(completed_rows, commit=True)
            state.relational_transaction_open = False
        elif not supports_manual_transaction and hasattr(self._email_db, "mark_ingest_batch_completed"):
            self._email_db.mark_ingest_batch_completed(completed_rows)
        state.email_commit_pending = False
        checkpoint = getattr(self._embedder, "checkpoint", None)
        if callable(checkpoint):
            checkpoint()

    def _rollback_failed_batch(self, state: _BatchState, conn: Any, exc: Exception) -> None:
        """Roll back relational state and delete vectors written by a failed batch."""
        if state.relational_transaction_open:
            assert conn is not None
            logger.debug(
                "Rolling back SQLite ingest transaction after batch failure (run_id=%s)",
                self._ingestion_run_id,
                exc_info=True,
            )
            conn.rollback()
        self._cleanup_vector_batch(state.batch_chunk_ids)
        email_uids = [str(row.get("email_uid") or "") for row in state.inserted_ingest_rows if str(row.get("email_uid") or "")]
        self._mark_batch_failed(email_uids, error_message=str(exc))

    def _apply_batch_maintenance(self) -> None:
        """Run scheduled checkpoints and optional cooldown after a successful batch."""
        wal_due = self._wal_checkpoint_interval > 0 and self._email_db and self.batches_written > 0
        if wal_due and self.batches_written % self._wal_checkpoint_interval == 0:
            self._checkpoint_wal()
        if self._cooldown > 0:
            time.sleep(self._cooldown)

    def _checkpoint_wal(self) -> None:
        """Run a passive WAL checkpoint on the email SQLite database."""
        try:
            if self._email_db is not None:
                self._email_db.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            logger.debug("SQLite WAL checkpoint completed (batch %d)", self.batches_written)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("WAL checkpoint failed (non-critical)", exc_info=True)

    @staticmethod
    def _write_analytics_rows(writer: Callable[..., Any], rows: list[tuple[object, ...]], *, commit: bool) -> None:
        """Write analytics rows while accepting legacy writers without ``commit``."""
        try:
            writer(rows, commit=commit)
        except TypeError as exc:
            if "unexpected keyword argument 'commit'" not in str(exc):
                raise
            writer(rows)

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
            self._write_analytics_rows(self._email_db.update_analytics_batch, rows, commit=commit)
        if surface_rows and hasattr(self._email_db, "upsert_language_surface_analytics"):
            self._write_analytics_rows(self._email_db.upsert_language_surface_analytics, surface_rows, commit=commit)


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
