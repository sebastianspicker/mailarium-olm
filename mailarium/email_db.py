"""SQLite relational store for email metadata and relationships."""
# pylint: disable=too-many-arguments,too-many-instance-attributes,too-many-locals,too-many-positional-arguments,too-many-public-methods

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from functools import wraps
from inspect import ismethod
from pathlib import Path
from typing import Any

from .attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from .attachment_surfaces import attachment_surface_rows_for_attachment
from .db_analytics import AnalyticsMixin
from .db_attachments import AttachmentMixin
from .db_custody import CustodyMixin
from .db_entities import EntityMixin
from .db_events import EventMixin
from .db_evidence import EvidenceMixin
from .db_queries import QueryMixin
from .db_schema import _escape_like, _sql_in_placeholders, _validate_sql_identifiers, init_schema
from .email_db_enrichment import (
    upsert_communication_edge as _upsert_communication_edge_impl,
)
from .email_db_enrichment import (
    upsert_contact as _upsert_contact_impl,
)
from .email_db_persistence import (
    build_v7_email_update_row,
    insert_email_impl,
    insert_emails_batch_impl,
)
from .parse_olm import BODY_NORMALIZATION_VERSION, Email

logger = logging.getLogger(__name__)


def _int_value(value: object) -> int:
    """Coerce a database value to integer while preserving a caller default."""
    return int(value) if isinstance(value, int | float | str) else 0


def _decode_sparse_row(row: sqlite3.Row) -> tuple[str, dict[int, float]]:
    """Decode one packed sparse-vector row into its chunk identifier and weights."""
    import struct

    count = int(row["num_tokens"])
    token_ids = struct.unpack(f"<{count}i", row["token_ids"])
    weights = struct.unpack(f"<{count}f", row["weights"])
    return str(row["chunk_id"]), dict(zip(token_ids, weights, strict=True))


def _ingest_state_rows(
    rows: list[dict[str, object]],
    *,
    email_first: bool,
) -> list[tuple[object, ...]]:
    """Build pending or completed ingest-ledger rows from one canonical projection."""
    projected: list[tuple[object, ...]] = []
    for row in rows:
        email_uid = str(row.get("email_uid") or "")
        if not email_uid:
            continue
        state = (
            _int_value(row.get("body_chunk_count")),
            _int_value(row.get("attachment_chunk_count")),
            _int_value(row.get("image_chunk_count")),
            _int_value(row.get("vector_chunk_count")),
            str(row.get("attachment_status") or "not_requested"),
            str(row.get("image_status") or "not_requested"),
        )
        projected.append((email_uid, *state) if email_first else (*state, email_uid))
    return projected


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
_EMAIL_INSERT_SQL = f"""INSERT INTO emails ({", ".join(_EMAIL_INSERT_COLUMNS_VALIDATED)})
VALUES ({_sql_in_placeholders(_EMAIL_INSERT_COLUMNS_VALIDATED)})"""
_EMAIL_INSERT_OR_IGNORE_SQL = _EMAIL_INSERT_SQL.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)


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


def _replace_v7_categories(cur: sqlite3.Cursor, email: Email) -> None:
    """Replace v7 categories while preserving the invariants of database lifecycle management."""
    cur.execute("DELETE FROM email_categories WHERE email_uid = ?", (email.uid,))
    categories = getattr(email, "categories", []) or []
    if categories:
        cur.executemany(
            "INSERT OR IGNORE INTO email_categories(email_uid, category) VALUES(?,?)",
            [(email.uid, category) for category in categories],
        )


def _replace_v7_attachments(db: object, cur: sqlite3.Cursor, email: Email) -> None:
    """Replace v7 attachments while preserving the invariants of database lifecycle management."""
    existing_attachments = db.attachments_for_email(email.uid)  # type: ignore[attr-defined]
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


def _update_v7_email_row(cur: sqlite3.Cursor, email: Email) -> bool:
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


class EmailDatabase(  # pylint: disable=too-many-ancestors
    CustodyMixin,
    EvidenceMixin,
    EntityMixin,
    EventMixin,
    AnalyticsMixin,
    AttachmentMixin,
    QueryMixin,
):
    """SQLite-backed relational store for email metadata.

    Method groups are organized into mixins for maintainability:
    - ``CustodyMixin`` - chain-of-custody audit trail and ingestion tracking
    - ``EvidenceMixin`` - evidence item CRUD, verification, search
    - ``EntityMixin`` - NLP entity insert, search, timeline
    - ``EventMixin`` - extracted event persistence and lookups
    - ``AnalyticsMixin`` - clusters, topics, keywords, contacts, relationships
    - ``QueryMixin`` - read queries, full-body retrieval, browsing, consistency
    """

    def __init__(self, db_path: str = ":memory:", *, busy_timeout_ms: int = 5000) -> None:
        """Open the SQLite archive path and configure bounded database access."""
        self._db_path = db_path
        self._busy_timeout_ms = max(int(busy_timeout_ms), 0)
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()
        # SQLite permits this connection to be used from MCP worker threads, but
        # transactions on one connection must remain atomic with respect to one
        # another. RLock also permits public operations to call other database
        # methods without self-deadlocking.
        self._operation_lock = threading.RLock()
        self._email_insert_sql = _EMAIL_INSERT_SQL
        self._email_insert_or_ignore_sql = _EMAIL_INSERT_OR_IGNORE_SQL
        self._sqlite_integrity_error = sqlite3.IntegrityError

    def __getattribute__(self, name: str) -> Any:
        """Serialize complete public database operations on the shared connection."""
        value = super().__getattribute__(name)
        if name.startswith("_") or name in {"conn", "operation"} or not ismethod(value) or value.__self__ is not self:
            return value

        @wraps(value)
        def serialized_operation(*args: Any, **kwargs: Any) -> Any:
            with self._operation_lock:
                return value(*args, **kwargs)

        return serialized_operation

    @contextmanager
    def operation(self) -> Iterator[None]:
        """Hold the per-database operation lock for a complete DB facade call."""
        with self._operation_lock:
            yield

    @property
    def conn(self) -> sqlite3.Connection:  # type: ignore[override]  # mixin stubs declare as attribute
        # Fast path: connection already initialized (no lock needed).
        """Lazily create and return the shared SQLite connection under a lock."""
        if self._conn is not None:
            return self._conn
        # Slow path: first access - serialize with lock to prevent two
        # threads from racing to create the connection.  Only contends once.
        with self._conn_lock:
            if self._conn is None:
                if self._db_path != ":memory:":
                    Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
                connect_timeout = max(self._busy_timeout_ms / 1000.0, 0.1)
                self._conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=connect_timeout)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._conn.row_factory = sqlite3.Row
                init_schema(self._conn)
        return self._conn

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        """Best-effort close to avoid leaked SQLite handles during teardown."""
        with suppress(OSError, sqlite3.Error):
            self.close()

    # ------------------------------------------------------------------
    # Sparse vector storage

    def insert_sparse_batch(
        self,
        chunk_ids: list[str],
        sparse_vectors: list[dict[int, float]],
        *,
        model_id: str = "",
        model_revision: str = "",
        vocab_hash: str = "",
        generation: int = 1,
    ) -> int:
        """Insert sparse vectors for chunks. Returns count of inserted rows."""
        import struct

        if len(chunk_ids) != len(sparse_vectors):
            raise ValueError("chunk_ids and sparse_vectors must have same length")

        rows: list[tuple] = []
        for cid, sv in zip(chunk_ids, sparse_vectors, strict=True):
            if not sv:
                continue
            token_ids = sorted(sv.keys())
            weights = [sv[tid] for tid in token_ids]

            token_blob = struct.pack(f"<{len(token_ids)}i", *token_ids)
            weight_blob = struct.pack(f"<{len(weights)}f", *weights)

            rows.append(
                (
                    cid,
                    token_blob,
                    weight_blob,
                    len(token_ids),
                    model_id,
                    model_revision,
                    vocab_hash,
                    max(int(generation), 1),
                )
            )

        external_transaction = self.conn.in_transaction
        if rows:
            self.conn.executemany(
                """INSERT OR REPLACE INTO sparse_vectors(
                       chunk_id, token_ids, weights, num_tokens,
                       model_id, model_revision, vocab_hash, generation
                   ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            if not external_transaction:
                self.conn.commit()
        return len(rows)

    def get_sparse_vector(self, chunk_id: str) -> dict[int, float] | None:
        """Retrieve a single sparse vector by chunk_id."""
        import struct

        row = self.conn.execute(
            "SELECT token_ids, weights, num_tokens FROM sparse_vectors WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        if not row:
            return None

        n = row["num_tokens"]
        token_ids = list(struct.unpack(f"<{n}i", row["token_ids"]))
        weights = list(struct.unpack(f"<{n}f", row["weights"]))
        return dict(zip(token_ids, weights, strict=True))

    def sparse_vector_count(self) -> int:
        """Count of stored sparse vectors."""
        row = self.conn.execute("SELECT COUNT(*) AS c FROM sparse_vectors").fetchone()
        return row["c"] if row else 0

    def all_sparse_vectors(
        self,
        *,
        model_id: str | None = None,
        model_revision: str | None = None,
    ) -> dict[str, dict[int, float]]:
        """Load all sparse vectors into memory (for building inverted index)."""
        result = {}
        for row in self._iter_sparse_rows(model_id=model_id, model_revision=model_revision):
            chunk_id, vector = _decode_sparse_row(row)
            result[chunk_id] = vector
        return result

    def iter_sparse_vectors(
        self,
        *,
        model_id: str | None = None,
        model_revision: str | None = None,
    ):
        """Yield sparse vectors row-by-row to avoid full corpus materialization."""
        # A generator starts executing after the public-method wrapper has
        # returned, so it must retain the operation lock for iteration itself.
        with self.operation():
            for row in self._iter_sparse_rows(model_id=model_id, model_revision=model_revision):
                yield _decode_sparse_row(row)

    def _iter_sparse_rows(
        self,
        *,
        model_id: str | None,
        model_revision: str | None,
    ):
        """Yield sparse-index rows in bounded database batches."""
        sql = "SELECT chunk_id, token_ids, weights, num_tokens FROM sparse_vectors"
        conditions: list[str] = []
        params: list[str] = []
        if model_id is not None:
            conditions.append("model_id = ?")
            params.append(model_id)
        if model_revision is not None:
            conditions.append("model_revision = ?")
            params.append(model_revision)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return self.conn.execute(sql, params)

    # ------------------------------------------------------------------
    # Analytics batch update
    # ------------------------------------------------------------------

    def update_analytics_batch(
        self,
        rows: list[tuple[object, ...]],
        *,
        commit: bool = True,
    ) -> int:
        """Batch-update language and sentiment analytics by uid.

        Supported tuple shapes:
        - ``(detected_language, sentiment_label, sentiment_score, uid)``
        - ``(
              detected_language,
              detected_language_confidence,
              detected_language_reason,
              detected_language_source,
              detected_language_token_count,
              sentiment_label,
              sentiment_score,
              uid,
          )``
        Returns number of rows submitted for update.
        """
        if not rows:
            return 0
        first_row = rows[0]
        if len(first_row) == 4:
            self.conn.executemany(
                "UPDATE emails SET detected_language=?, sentiment_label=?, sentiment_score=? WHERE uid=?",
                rows,
            )
        elif len(first_row) == 8:
            self.conn.executemany(
                """
                UPDATE emails
                   SET detected_language=?,
                       detected_language_confidence=?,
                       detected_language_reason=?,
                       detected_language_source=?,
                       detected_language_token_count=?,
                       sentiment_label=?,
                       sentiment_score=?
                 WHERE uid=?
                """,
                rows,
            )
        else:
            raise ValueError(f"Unsupported analytics row shape: {len(first_row)}")
        if commit:
            self.conn.commit()
        return len(rows)

    def upsert_language_surface_analytics(
        self,
        rows: list[tuple[object, ...]],
        *,
        commit: bool = True,
    ) -> int:
        """Upsert per-surface language analytics rows for one batch."""
        if not rows:
            return 0
        self.conn.executemany(
            """
            INSERT INTO language_surface_analytics(
                email_uid,
                surface_scope,
                source_surface,
                segment_ordinal,
                text_hash,
                text_char_count,
                detected_language,
                detected_language_confidence,
                detected_language_reason,
                detected_language_token_count,
                detector_version,
                analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'stopword_v1', datetime('now'))
            ON CONFLICT(email_uid, surface_scope) DO UPDATE SET
                source_surface=excluded.source_surface,
                segment_ordinal=excluded.segment_ordinal,
                text_hash=excluded.text_hash,
                text_char_count=excluded.text_char_count,
                detected_language=excluded.detected_language,
                detected_language_confidence=excluded.detected_language_confidence,
                detected_language_reason=excluded.detected_language_reason,
                detected_language_token_count=excluded.detected_language_token_count,
                detector_version='stopword_v1',
                analyzed_at=datetime('now')
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert_email(self, email: Email, *, ingestion_run_id: int | None = None) -> bool:
        """Insert a single email and update contacts/edges.

        Returns False if uid already exists (duplicate).
        All writes happen in a single transaction - either the email and all
        its related rows (recipients, contacts, edges) are committed together,
        or nothing is written.
        """
        return insert_email_impl(self, email, ingestion_run_id=ingestion_run_id)

    def insert_emails_batch(
        self,
        emails: list[Email],
        ingestion_run_id: int | None = None,
        *,
        commit: bool = True,
    ) -> set[str]:
        """Insert a batch of emails in a single transaction.

        Returns the set of UIDs that were actually inserted (new emails).
        The set is truthy/has ``len()`` so callers that only need the count
        still work via ``len(result)`` or ``bool(result)``.

        Uses batched parameter collection for recipients, categories,
        attachments, contacts, and communication edges to reduce per-row
        execute() overhead.
        """
        if commit:
            return insert_emails_batch_impl(
                self,
                emails,
                ingestion_run_id=ingestion_run_id,
            )
        return insert_emails_batch_impl(
            self,
            emails,
            ingestion_run_id=ingestion_run_id,
            commit=commit,
        )

    def _upsert_contact(
        self,
        cur: sqlite3.Cursor,
        email_address: str,
        display_name: str,
        date: str,
        role: str,
    ) -> None:
        """Insert or update one normalized contact without erasing known display data."""
        _upsert_contact_impl(cur, email_address, display_name, date, role)

    def _upsert_communication_edge(
        self,
        cur: sqlite3.Cursor,
        sender: str,
        recipient: str,
        date: str,
    ) -> None:
        """Increment the directed sender-recipient communication edge."""
        _upsert_communication_edge_impl(cur, sender, recipient, date)

    # ------------------------------------------------------------------
    # Read operations - see QueryMixin (db_queries.py)
    # ------------------------------------------------------------------

    def update_body_text(
        self,
        uid: str,
        body_text: str,
        body_html: str,
        *,
        normalized_body_source: str | None = None,
        body_normalization_version: int | None = None,
        body_kind: str | None = None,
        body_empty_reason: str | None = None,
        recovery_strategy: str | None = None,
        recovery_confidence: float | None = None,
        commit: bool = True,
    ) -> bool:
        """Update body_text and body_html for an existing email.

        Only overwrites body_html if the new value is non-empty, to avoid
        losing good HTML content when the re-parsed email lacks an HTML body.
        Returns True if updated.  Pass ``commit=False`` to defer the commit
        (caller is responsible for calling ``self.conn.commit()``).
        """
        if normalized_body_source is None:
            normalized_body_source = "body_text"
        if body_normalization_version is None:
            body_normalization_version = BODY_NORMALIZATION_VERSION
        if body_kind is None:
            body_kind = "content"
        if body_empty_reason is None:
            body_empty_reason = ""
        if recovery_strategy is None:
            recovery_strategy = ""
        if recovery_confidence is None:
            recovery_confidence = 0.0

        if body_html:
            cur = self.conn.execute(
                """UPDATE emails
                   SET body_text = ?, body_html = ?, normalized_body_source = ?,
                       body_normalization_version = ?, body_kind = ?, body_empty_reason = ?,
                       recovery_strategy = ?, recovery_confidence = ?
                 WHERE uid = ?""",
                (
                    body_text,
                    body_html,
                    normalized_body_source,
                    body_normalization_version,
                    body_kind,
                    body_empty_reason,
                    recovery_strategy,
                    recovery_confidence,
                    uid,
                ),
            )
        else:
            cur = self.conn.execute(
                """UPDATE emails
                   SET body_text = ?, normalized_body_source = ?,
                       body_normalization_version = ?, body_kind = ?, body_empty_reason = ?,
                       recovery_strategy = ?, recovery_confidence = ?
                 WHERE uid = ?""",
                (
                    body_text,
                    normalized_body_source,
                    body_normalization_version,
                    body_kind,
                    body_empty_reason,
                    recovery_strategy,
                    recovery_confidence,
                    uid,
                ),
            )
        if commit:
            self.conn.commit()
        return cur.rowcount > 0

    def update_headers(
        self,
        uid: str,
        subject: str,
        sender_name: str,
        sender_email: str,
        base_subject: str,
        email_type: str,
        *,
        commit: bool = True,
    ) -> bool:
        """Update decoded header fields for an existing email.

        Fixes MIME encoded-word subjects and sender names that were stored
        without decoding during earlier ingestions.  Returns True if updated.
        Pass ``commit=False`` to defer the commit.
        """
        cur = self.conn.execute(
            """UPDATE emails
               SET subject = ?, sender_name = ?, sender_email = ?,
                   base_subject = ?, email_type = ?
             WHERE uid = ?""",
            (subject, sender_name, sender_email, base_subject, email_type, uid),
        )
        if commit:
            self.conn.commit()
        return cur.rowcount > 0

    def update_v7_metadata(self, email: Email, *, commit: bool = True) -> bool:
        """Update schema-v7 metadata fields for an existing email.

        Populates categories, thread_topic, inference_classification,
        is_calendar_message, references_json, and related tables
        (email_categories, attachments). Returns True if updated.
        Pass ``commit=False`` to defer the commit.
        """
        cur = self.conn.cursor()
        if not _update_v7_email_row(cur, email):
            return False
        _replace_v7_categories(cur, email)
        _replace_v7_attachments(self, cur, email)
        if commit:
            self.conn.commit()
        return True

    def mark_ingest_batch_pending(
        self,
        rows: list[dict[str, object]],
        *,
        commit: bool = True,
    ) -> None:
        """Mark one batch as pending vector completion in the ingest ledger."""
        if not rows:
            return
        self.conn.executemany(
            """INSERT INTO email_ingest_state(
                   email_uid, body_chunk_count, attachment_chunk_count, image_chunk_count,
                   vector_chunk_count, vector_status, attachment_status, image_status,
                   last_error, updated_at
               ) VALUES(?, ?, ?, ?, ?, 'pending', ?, ?, '', datetime('now'))
               ON CONFLICT(email_uid) DO UPDATE SET
                   body_chunk_count=excluded.body_chunk_count,
                   attachment_chunk_count=excluded.attachment_chunk_count,
                   image_chunk_count=excluded.image_chunk_count,
                   vector_chunk_count=excluded.vector_chunk_count,
                   vector_status='pending',
                   attachment_status=excluded.attachment_status,
                   image_status=excluded.image_status,
                   last_error='',
                   updated_at=datetime('now')""",
            _ingest_state_rows(rows, email_first=True),
        )
        if commit:
            self.conn.commit()

    def mark_ingest_batch_completed(
        self,
        rows: list[dict[str, object]],
        *,
        commit: bool = True,
    ) -> None:
        """Mark one batch as fully persisted to the vector store."""
        if not rows:
            return
        self.conn.executemany(
            """UPDATE email_ingest_state
               SET body_chunk_count = ?,
                   attachment_chunk_count = ?,
                   image_chunk_count = ?,
                   vector_chunk_count = ?,
                   vector_status = 'completed',
                   attachment_status = ?,
                   image_status = ?,
                   last_error = '',
                   updated_at = datetime('now')
               WHERE email_uid = ?""",
            _ingest_state_rows(rows, email_first=False),
        )
        if commit:
            self.conn.commit()

    def mark_ingest_batch_failed(
        self,
        email_uids: list[str],
        *,
        error_message: str,
        commit: bool = True,
    ) -> None:
        """Persist a failed vector-write state for one batch."""
        if not email_uids:
            return
        self.conn.executemany(
            """UPDATE email_ingest_state
               SET vector_status = 'failed',
                   last_error = ?,
                   updated_at = datetime('now')
               WHERE email_uid = ?""",
            [(error_message, uid) for uid in email_uids if uid],
        )
        if commit:
            self.conn.commit()

    def all_uids(self) -> set[str]:
        """Return all UIDs in the database."""
        rows = self.conn.execute("SELECT uid FROM emails").fetchall()
        return {r["uid"] for r in rows}

    def uids_missing_body(self) -> set[str]:
        """Return UIDs of emails where body_text is NULL, empty, or whitespace-only."""
        rows = self.conn.execute("SELECT uid FROM emails WHERE body_text IS NULL OR TRIM(body_text) = ''").fetchall()
        return {r["uid"] for r in rows}

    def delete_sparse_by_chunk_ids(self, chunk_ids: list[str], *, commit: bool = True) -> int:
        """Delete sparse vectors for an explicit chunk-id list. Returns count deleted."""
        filtered_ids = [chunk_id for chunk_id in chunk_ids if chunk_id]
        if not filtered_ids:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(
            "DELETE FROM sparse_vectors WHERE chunk_id = ?",
            [(chunk_id,) for chunk_id in filtered_ids],
        )
        if commit:
            self.conn.commit()
        return self.conn.total_changes - before

    def delete_sparse_by_uid(self, uid: str) -> int:
        """Delete sparse vectors for all chunks of an email. Returns count deleted."""
        cur = self.conn.execute(
            "DELETE FROM sparse_vectors WHERE chunk_id LIKE ? ESCAPE '\\'",
            (f"{_escape_like(uid)}\\_\\_%",),
        )
        self.conn.commit()
        return cur.rowcount

    def reset_vector_data(self) -> dict[str, int]:
        """Clear rebuildable vector/sparse rows while retaining email metadata."""
        vector_count_row = self.conn.execute("SELECT COUNT(*) AS count FROM vector_chunks").fetchone()
        sparse_count_row = self.conn.execute("SELECT COUNT(*) AS count FROM sparse_vectors").fetchone()
        vector_count = int(vector_count_row["count"]) if vector_count_row else 0
        sparse_count = int(sparse_count_row["count"]) if sparse_count_row else 0
        self.conn.execute("DELETE FROM vector_index_ops")
        self.conn.execute("DELETE FROM vector_index_state")
        self.conn.execute("DELETE FROM vector_chunks")
        self.conn.execute("DELETE FROM sparse_vectors")
        self.conn.execute(
            """UPDATE email_ingest_state
                  SET vector_status = 'pending',
                      vector_chunk_count = 0,
                      last_error = '',
                      updated_at = datetime('now')"""
        )
        self.conn.commit()
        return {"dense_vectors": vector_count, "sparse_vectors": sparse_count}

    # ------------------------------------------------------------------
    # Evidence management (see EvidenceMixin)
    # Ingestion tracking (see CustodyMixin)
    # Chain of custody (see CustodyMixin)
    # Re-embed, grouping, consistency - see QueryMixin (db_queries.py)
    # ------------------------------------------------------------------
