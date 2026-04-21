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


class _EmbedPipeline:
    """Background thread that embeds and writes batches while parsing continues."""

    def __init__(
        self,
        embedder: EmailEmbedder | None,
        email_db: EmailDatabase | None,
        entity_extractor_fn: Callable[[str, str], list[Any]] | None,
        batch_size: int,
        ingestion_run_id: int | None = None,
    ) -> None:
        self._embedder = embedder
        self._email_db = email_db
        self._entity_extractor_fn = entity_extractor_fn
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
        self._queue.put(_SENTINEL)
        if self._thread is not None:
            self._thread.join()
        if self._error is not None:
            raise self._error

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

    def _process_batch(self, chunks: list[EmailChunk], emails: list[Email]) -> None:
        if self._email_db and emails:
            t0 = time.monotonic()
            inserted_uids = self._email_db.insert_emails_batch(
                emails,
                ingestion_run_id=self._ingestion_run_id,
            )
            self.sqlite_inserted += len(inserted_uids)
            dt_sqlite = time.monotonic() - t0
            self.sqlite_seconds += dt_sqlite

            new_emails = [email for email in emails if email.uid in inserted_uids]
            if len(new_emails) < len(emails):
                logger.debug(
                    "Skipped %d already-inserted emails for entity/analytics processing",
                    len(emails) - len(new_emails),
                )

            t1 = time.monotonic()
            has_entities = False
            if self._entity_extractor_fn:
                for email in new_emails:
                    if not email.clean_body:
                        continue
                    entities = self._entity_extractor_fn(email.clean_body, email.sender_email)
                    if entities:
                        self._email_db.insert_entities_batch(
                            email.uid,
                            [(entity.text, entity.entity_type, entity.normalized_form) for entity in entities],
                            commit=False,
                        )
                        has_entities = True
            for email in new_emails:
                exchange_entities = _exchange_entities_from_email(email)
                if exchange_entities:
                    self._email_db.insert_entities_batch(email.uid, exchange_entities, commit=False)
                    has_entities = True
            if has_entities:
                self._email_db.conn.commit()
            dt_entity = time.monotonic() - t1
            self.entity_seconds += dt_entity

            t2 = time.monotonic()
            self._compute_analytics(new_emails)
            dt_analytics = time.monotonic() - t2
            self.analytics_seconds += dt_analytics

            self.write_seconds += dt_sqlite + dt_entity + dt_analytics

        if self._embedder and chunks:
            t0 = time.monotonic()
            added = self._embedder.add_chunks(chunks, batch_size=self._batch_size)
            dt_embed = time.monotonic() - t0
            self.chunks_added += added
            self.batches_written += 1
            self.embed_seconds += dt_embed
            rate = len(chunks) / dt_embed if dt_embed > 0 else 0
            logger.info(
                "Batch %d: %d chunks embedded in %.1fs (%.0f chunks/s)",
                self.batches_written,
                len(chunks),
                dt_embed,
                rate,
            )

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

    def _compute_analytics(self, emails: list[Email]) -> None:
        """Detect language and sentiment for emails in this batch."""
        if not self._email_db:
            return
        from .language_detector import detect_language
        from .sentiment_analyzer import analyze as analyze_sentiment

        rows: list[tuple[str | None, str | None, float | None, str]] = []
        for email in emails:
            body = email.clean_body
            if not body or len(body.strip()) < 20:
                continue
            lang = detect_language(body)
            sentiment = analyze_sentiment(body)
            rows.append(
                (
                    lang if lang != "unknown" else None,
                    sentiment.sentiment,
                    sentiment.score,
                    email.uid,
                )
            )
        if rows:
            self._email_db.update_analytics_batch(rows)


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
