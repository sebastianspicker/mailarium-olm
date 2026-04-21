"""Schema migration helpers for the email SQLite database."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable

logger = logging.getLogger(__name__)


def apply_pending_migrations_impl(
    conn: sqlite3.Connection,
    cur: sqlite3.Cursor,
    *,
    schema_version: int,
    table_columns: Callable[[sqlite3.Cursor, str], set[str]],
    sparse_schema_sql: str,
) -> None:
    """Apply any pending schema migrations and persist the current version."""
    row = cur.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    current = row[0] if row and row[0] else 0
    if current < 3:
        _migrate_to_v3(cur, table_columns=table_columns)
    if current < 4:
        _migrate_to_v4(cur, table_columns=table_columns)
    if current < 5:
        _migrate_to_v5(cur, sparse_schema_sql=sparse_schema_sql)
    if current < 6:
        _migrate_to_v6(cur)
    if current < 7:
        _migrate_to_v7(cur, table_columns=table_columns)
    if current < 8:
        _migrate_to_v8(cur, table_columns=table_columns)
    if current < 9:
        _migrate_to_v9(cur, table_columns=table_columns)
    if current < 10:
        _migrate_to_v10(cur, table_columns=table_columns)
    if current < 11:
        _migrate_to_v11(cur, table_columns=table_columns)
    if current < 12:
        _migrate_to_v12(cur, table_columns=table_columns)
    if current < 13:
        _migrate_to_v13(cur, table_columns=table_columns)
    if current < 14:
        _migrate_to_v14(cur, table_columns=table_columns)
    if current < 15:
        _migrate_to_v15(cur)
    if current < 16:
        _migrate_to_v16(cur, table_columns=table_columns)
    if current < 17:
        _migrate_to_v17(cur, table_columns=table_columns)
    if current < 18:
        _migrate_to_v18(cur, table_columns=table_columns)
    if current < schema_version:
        cur.execute(
            "INSERT OR REPLACE INTO schema_version(version) VALUES(?)",
            (schema_version,),
        )
    conn.commit()


def _migrate_to_v3(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add body_text and body_html columns (schema v3)."""
    existing = table_columns(cur, "emails")
    if "body_text" not in existing:
        cur.execute("ALTER TABLE emails ADD COLUMN body_text TEXT")
        logger.info("Schema migration v3: added body_text column")
    if "body_html" not in existing:
        cur.execute("ALTER TABLE emails ADD COLUMN body_html TEXT")
        logger.info("Schema migration v3: added body_html column")


def _migrate_to_v4(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add chain-of-custody columns and tables (schema v4)."""
    ir_cols = table_columns(cur, "ingestion_runs")
    if "olm_sha256" not in ir_cols:
        cur.execute("ALTER TABLE ingestion_runs ADD COLUMN olm_sha256 TEXT")
        cur.execute("ALTER TABLE ingestion_runs ADD COLUMN file_size_bytes INTEGER")
        cur.execute("ALTER TABLE ingestion_runs ADD COLUMN custodian TEXT DEFAULT 'system'")
        logger.info("Schema migration v4: added ingestion_runs custody columns")

    em_cols = table_columns(cur, "emails")
    if "content_sha256" not in em_cols:
        cur.execute("ALTER TABLE emails ADD COLUMN content_sha256 TEXT")
        logger.info("Schema migration v4: added emails.content_sha256")

    ev_cols = table_columns(cur, "evidence_items")
    if "content_hash" not in ev_cols:
        cur.execute("ALTER TABLE evidence_items ADD COLUMN content_hash TEXT")
        cur.execute("ALTER TABLE evidence_items ADD COLUMN ingestion_run_id INTEGER")
        logger.info("Schema migration v4: added evidence_items custody columns")


def _migrate_to_v5(cur: sqlite3.Cursor, *, sparse_schema_sql: str) -> None:
    """Add sparse_vectors table (schema v5)."""
    cur.executescript(sparse_schema_sql)
    logger.info("Schema migration v5: created sparse_vectors table")


def _migrate_to_v6(cur: sqlite3.Cursor) -> None:
    """Add composite indexes for common query patterns (schema v6)."""
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_sender_date ON emails(sender_email, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_folder_date ON emails(folder, date)")
    logger.info("Schema migration v6: added composite indexes (sender_date, folder_date)")


def _migrate_to_v7(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add categories, calendar, thread_topic, references_json columns + tables (schema v7)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "categories": "TEXT",
        "thread_topic": "TEXT",
        "inference_classification": "TEXT",
        "is_calendar_message": "INTEGER DEFAULT 0",
        "references_json": "TEXT",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_calendar ON emails(is_calendar_message, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_inference ON emails(inference_classification)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_thread_topic ON emails(thread_topic)")
    logger.info("Schema migration v7: added categories, calendar, thread_topic, references_json columns + tables")


def _migrate_to_v8(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add language detection and sentiment analysis columns (schema v8)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "detected_language": "TEXT",
        "sentiment_label": "TEXT",
        "sentiment_score": "REAL",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_language ON emails(detected_language)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_sentiment ON emails(sentiment_label)")
    logger.info("Schema migration v8: added detected_language, sentiment_label, sentiment_score columns")


def _migrate_to_v9(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add ingestion_run_id to emails for provenance tracking (schema v9)."""
    existing = table_columns(cur, "emails")
    if "ingestion_run_id" not in existing:
        cur.execute("ALTER TABLE emails ADD COLUMN ingestion_run_id INTEGER")
        logger.info("Schema migration v9: added emails.ingestion_run_id")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_ingestion_run ON emails(ingestion_run_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_evidence_category_relevance ON evidence_items(category, relevance)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_type_date ON emails(email_type, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recipients_uid_type ON recipients(email_uid, type)")


def _migrate_to_v10(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add normalized body provenance columns (schema v10)."""
    existing = table_columns(cur, "emails")
    if "normalized_body_source" not in existing:
        cur.execute("ALTER TABLE emails ADD COLUMN normalized_body_source TEXT DEFAULT 'body_text'")
    if "body_normalization_version" not in existing:
        cur.execute("ALTER TABLE emails ADD COLUMN body_normalization_version INTEGER DEFAULT 10")
    logger.info("Schema migration v10: added normalized body provenance columns")


def _migrate_to_v11(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add raw and forensic body preservation columns (schema v11)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "raw_body_text": "TEXT",
        "raw_body_html": "TEXT",
        "raw_source": "TEXT",
        "raw_source_headers_json": "TEXT DEFAULT '{}'",
        "forensic_body_text": "TEXT",
        "forensic_body_source": "TEXT DEFAULT ''",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v11: added raw and forensic body preservation columns")


def _migrate_to_v12(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add empty-body classification and recovery provenance columns (schema v12)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "body_kind": "TEXT DEFAULT 'content'",
        "body_empty_reason": "TEXT DEFAULT ''",
        "recovery_strategy": "TEXT DEFAULT ''",
        "recovery_confidence": "REAL DEFAULT 0",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v12: added empty-body classification and recovery provenance columns")


def _migrate_to_v13(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add durable recipient identity persistence columns (schema v13)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "to_identities_json": "TEXT DEFAULT '[]'",
        "cc_identities_json": "TEXT DEFAULT '[]'",
        "bcc_identities_json": "TEXT DEFAULT '[]'",
        "recipient_identity_source": "TEXT DEFAULT ''",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v13: added durable recipient identity persistence columns")


def _migrate_to_v14(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add inferred quoted reply-context persistence columns (schema v14)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "reply_context_from": "TEXT DEFAULT ''",
        "reply_context_to_json": "TEXT DEFAULT '[]'",
        "reply_context_subject": "TEXT DEFAULT ''",
        "reply_context_date": "TEXT DEFAULT ''",
        "reply_context_source": "TEXT DEFAULT ''",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v14: added inferred quoted reply-context persistence columns")


def _migrate_to_v15(cur: sqlite3.Cursor) -> None:
    """Add persisted conversation segments (schema v15)."""
    cur.execute(
        """CREATE TABLE IF NOT EXISTS message_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            segment_type TEXT NOT NULL,
            depth INTEGER DEFAULT 0,
            text TEXT NOT NULL,
            source_surface TEXT NOT NULL,
            provenance_json TEXT DEFAULT '{}'
        )"""
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_message_segments_email_uid ON message_segments(email_uid, ordinal)")
    logger.info("Schema migration v15: added conversation segment persistence table")


def _migrate_to_v16(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add inferred thread persistence columns and edges (schema v16)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "inferred_parent_uid": "TEXT DEFAULT ''",
        "inferred_thread_id": "TEXT DEFAULT ''",
        "inferred_match_reason": "TEXT DEFAULT ''",
        "inferred_match_confidence": "REAL DEFAULT 0",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    cur.execute(
        """CREATE TABLE IF NOT EXISTS conversation_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
            parent_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
            edge_type TEXT NOT NULL,
            reason TEXT DEFAULT '',
            confidence REAL DEFAULT 0
        )"""
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_inferred_parent_uid ON emails(inferred_parent_uid)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_inferred_thread_id ON emails(inferred_thread_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_conversation_edges_child ON conversation_edges(child_uid)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_conversation_edges_parent ON conversation_edges(parent_uid)")
    logger.info("Schema migration v16: added inferred thread persistence columns and edges table")


def _migrate_to_v17(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add attachment evidence metadata columns (schema v17)."""
    existing = table_columns(cur, "attachments")
    new_cols = {
        "extraction_state": "TEXT DEFAULT ''",
        "evidence_strength": "TEXT DEFAULT ''",
        "ocr_used": "INTEGER DEFAULT 0",
        "failure_reason": "TEXT DEFAULT ''",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE attachments ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v17: added attachment evidence metadata columns")


def _migrate_to_v18(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add attachment text preview persistence column (schema v18)."""
    existing = table_columns(cur, "attachments")
    if "text_preview" not in existing:
        cur.execute("ALTER TABLE attachments ADD COLUMN text_preview TEXT DEFAULT ''")
    logger.info("Schema migration v18: added attachments.text_preview")
