"""SQLite relational store for email metadata and relationships."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

from .db_analytics import AnalyticsMixin
from .db_attachments import AttachmentMixin
from .db_custody import CustodyMixin
from .db_entities import EntityMixin
from .db_evidence import EvidenceMixin
from .db_queries import QueryMixin
from .db_schema import _escape_like, init_schema
from .email_db_enrichment import parse_address
from .email_db_enrichment import (
    upsert_communication_edge as _upsert_communication_edge_impl,
)
from .email_db_enrichment import (
    upsert_contact as _upsert_contact_impl,
)
from .email_db_persistence import (
    insert_email_impl,
    insert_emails_batch_impl,
)
from .parse_olm import BODY_NORMALIZATION_VERSION, Email

logger = logging.getLogger(__name__)

# Backward-compatible re-export for tests and existing imports.
_parse_address = parse_address

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
_EMAIL_INSERT_SQL = f"""INSERT INTO emails ({", ".join(_EMAIL_INSERT_COLUMNS)})
VALUES ({",".join("?" for _ in _EMAIL_INSERT_COLUMNS)})"""
_EMAIL_INSERT_OR_IGNORE_SQL = _EMAIL_INSERT_SQL.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)


class EmailDatabase(CustodyMixin, EvidenceMixin, EntityMixin, AnalyticsMixin, AttachmentMixin, QueryMixin):
    """SQLite-backed relational store for email metadata.

    Method groups are organized into mixins for maintainability:
    - ``CustodyMixin`` — chain-of-custody audit trail and ingestion tracking
    - ``EvidenceMixin`` — evidence item CRUD, verification, search
    - ``EntityMixin`` — NLP entity insert, search, timeline
    - ``AnalyticsMixin`` — clusters, topics, keywords, contacts, relationships
    - ``QueryMixin`` — read queries, full-body retrieval, browsing, consistency
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()
        self._email_insert_sql = _EMAIL_INSERT_SQL
        self._email_insert_or_ignore_sql = _EMAIL_INSERT_OR_IGNORE_SQL
        self._sqlite_integrity_error = sqlite3.IntegrityError

    @property
    def conn(self) -> sqlite3.Connection:  # type: ignore[override]  # mixin stubs declare as attribute
        # Fast path: connection already initialized (no lock needed).
        if self._conn is not None:
            return self._conn
        # Slow path: first access — serialize with lock to prevent two
        # threads from racing to create the connection.  Only contends once.
        with self._conn_lock:
            if self._conn is None:
                if self._db_path != ":memory:":
                    Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA busy_timeout = 5000")
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._conn.row_factory = sqlite3.Row
                init_schema(self._conn)
        return self._conn

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Sparse vector storage

    def insert_sparse_batch(
        self,
        chunk_ids: list[str],
        sparse_vectors: list[dict[int, float]],
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

            rows.append((cid, token_blob, weight_blob, len(token_ids)))

        if rows:
            self.conn.executemany(
                "INSERT OR REPLACE INTO sparse_vectors(chunk_id, token_ids, weights, num_tokens) VALUES(?, ?, ?, ?)",
                rows,
            )
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

    def all_sparse_vectors(self) -> dict[str, dict[int, float]]:
        """Load all sparse vectors into memory (for building inverted index)."""
        import struct

        result = {}
        for row in self.conn.execute("SELECT chunk_id, token_ids, weights, num_tokens FROM sparse_vectors"):
            n = row["num_tokens"]
            token_ids = list(struct.unpack(f"<{n}i", row["token_ids"]))
            weights = list(struct.unpack(f"<{n}f", row["weights"]))
            result[row["chunk_id"]] = dict(zip(token_ids, weights, strict=True))
        return result

    def iter_sparse_vectors(self):
        """Yield sparse vectors row-by-row to avoid full corpus materialization."""
        import struct

        for row in self.conn.execute("SELECT chunk_id, token_ids, weights, num_tokens FROM sparse_vectors"):
            n = row["num_tokens"]
            token_ids = list(struct.unpack(f"<{n}i", row["token_ids"]))
            weights = list(struct.unpack(f"<{n}f", row["weights"]))
            yield row["chunk_id"], dict(zip(token_ids, weights, strict=True))

    # ------------------------------------------------------------------
    # Analytics batch update
    # ------------------------------------------------------------------

    def update_analytics_batch(
        self,
        rows: list[tuple[str | None, str | None, float | None, str]],
    ) -> int:
        """Batch-update detected_language, sentiment_label, sentiment_score by uid.

        Each tuple: (detected_language, sentiment_label, sentiment_score, uid).
        Returns number of rows submitted for update.
        """
        self.conn.executemany(
            "UPDATE emails SET detected_language=?, sentiment_label=?, sentiment_score=? WHERE uid=?",
            rows,
        )
        self.conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert_email(self, email: Email, *, ingestion_run_id: int | None = None) -> bool:
        """Insert a single email and update contacts/edges.

        Returns False if uid already exists (duplicate).
        All writes happen in a single transaction — either the email and all
        its related rows (recipients, contacts, edges) are committed together,
        or nothing is written.
        """
        return insert_email_impl(self, email, ingestion_run_id=ingestion_run_id)

    def insert_emails_batch(
        self,
        emails: list[Email],
        ingestion_run_id: int | None = None,
    ) -> set[str]:
        """Insert a batch of emails in a single transaction.

        Returns the set of UIDs that were actually inserted (new emails).
        The set is truthy/has ``len()`` so callers that only need the count
        still work via ``len(result)`` or ``bool(result)``.

        Uses batched parameter collection for recipients, categories,
        attachments, contacts, and communication edges to reduce per-row
        execute() overhead.
        """
        return insert_emails_batch_impl(self, emails, ingestion_run_id=ingestion_run_id)

    def _upsert_contact(
        self,
        cur: sqlite3.Cursor,
        email_address: str,
        display_name: str,
        date: str,
        role: str,
    ) -> None:
        _upsert_contact_impl(cur, email_address, display_name, date, role)

    def _upsert_communication_edge(
        self,
        cur: sqlite3.Cursor,
        sender: str,
        recipient: str,
        date: str,
    ) -> None:
        _upsert_communication_edge_impl(cur, sender, recipient, date)

    # ------------------------------------------------------------------
    # Read operations — see QueryMixin (db_queries.py)
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
        categories_json = json.dumps(getattr(email, "categories", []) or [])
        references_json = json.dumps(getattr(email, "references", []) or [])

        cur = self.conn.cursor()
        cur.execute(
            """UPDATE emails
               SET categories = ?, thread_topic = ?, inference_classification = ?,
                   is_calendar_message = ?, references_json = ?
             WHERE uid = ?""",
            (
                categories_json,
                getattr(email, "thread_topic", "") or "",
                getattr(email, "inference_classification", "") or "",
                int(getattr(email, "is_calendar_message", False)),
                references_json,
                email.uid,
            ),
        )
        if cur.rowcount == 0:
            return False

        # Upsert categories
        cats = getattr(email, "categories", []) or []
        if cats:
            cur.executemany(
                "INSERT OR IGNORE INTO email_categories(email_uid, category) VALUES(?,?)",
                [(email.uid, cat) for cat in cats],
            )

        # Upsert attachments
        cur.execute("DELETE FROM attachments WHERE email_uid = ?", (email.uid,))
        atts = getattr(email, "attachments", []) or []
        if atts:
            cur.executemany(
                "INSERT INTO attachments(email_uid, name, mime_type, size, content_id, is_inline, "
                "extraction_state, evidence_strength, ocr_used, failure_reason, text_preview) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        email.uid,
                        att.get("name", ""),
                        att.get("mime_type", ""),
                        att.get("size", 0),
                        att.get("content_id", ""),
                        int(att.get("is_inline", False)),
                        att.get("extraction_state", "") or "",
                        att.get("evidence_strength", "") or "",
                        int(bool(att.get("ocr_used", False))),
                        att.get("failure_reason", "") or "",
                        att.get("text_preview", "") or "",
                    )
                    for att in atts
                ],
            )

        if commit:
            self.conn.commit()
        return True

    def all_uids(self) -> set[str]:
        """Return all UIDs in the database."""
        rows = self.conn.execute("SELECT uid FROM emails").fetchall()
        return {r["uid"] for r in rows}

    def uids_missing_body(self) -> set[str]:
        """Return UIDs of emails where body_text is NULL."""
        rows = self.conn.execute("SELECT uid FROM emails WHERE body_text IS NULL").fetchall()
        return {r["uid"] for r in rows}

    def delete_sparse_by_uid(self, uid: str) -> int:
        """Delete sparse vectors for all chunks of an email. Returns count deleted."""
        cur = self.conn.execute(
            "DELETE FROM sparse_vectors WHERE chunk_id LIKE ? ESCAPE '\\'",
            (f"{_escape_like(uid)}\\_\\_%",),
        )
        self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Evidence management (see EvidenceMixin)
    # Ingestion tracking (see CustodyMixin)
    # Chain of custody (see CustodyMixin)
    # Re-embed, grouping, consistency — see QueryMixin (db_queries.py)
    # ------------------------------------------------------------------
