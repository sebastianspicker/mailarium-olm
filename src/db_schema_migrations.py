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
    if current < 19:
        _migrate_to_v19(cur)
    if current < 20:
        _migrate_to_v20(cur)
    if current < 21:
        _migrate_to_v21(cur)
    if current < 22:
        _migrate_to_v22(cur, table_columns=table_columns)
    if current < 23:
        _migrate_to_v23(cur, table_columns=table_columns)
    if current < 24:
        _migrate_to_v24(cur, table_columns=table_columns)
    if current < 25:
        _migrate_to_v25(cur)
    if current < 26:
        _migrate_to_v26(cur, table_columns=table_columns)
    if current < 27:
        _migrate_to_v27(cur, table_columns=table_columns)
    if current < 28:
        _migrate_to_v28(cur, table_columns=table_columns)
    if current < 29:
        _migrate_to_v29(cur)
    if current < 30:
        _migrate_to_v30(cur)
    if current < 31:
        _migrate_to_v31(cur)
    if current < 32:
        _migrate_to_v32(cur)
    if current < 33:
        _migrate_to_v33(cur)
    if current < 34:
        _migrate_to_v34(cur)
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


def _migrate_to_v19(cur: sqlite3.Cursor) -> None:
    """Add human review override persistence for matter products (schema v19)."""
    cur.execute(
        """CREATE TABLE IF NOT EXISTS matter_review_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            review_state TEXT NOT NULL DEFAULT 'machine_extracted',
            override_payload_json TEXT DEFAULT '{}',
            machine_payload_json TEXT DEFAULT '{}',
            source_evidence_json TEXT DEFAULT '[]',
            reviewer TEXT DEFAULT 'human',
            review_notes TEXT DEFAULT '',
            apply_on_refresh INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(workspace_id, target_type, target_id)
        )"""
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_review_workspace ON matter_review_overrides(workspace_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_review_target ON matter_review_overrides(target_type, target_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_review_state ON matter_review_overrides(review_state)")
    logger.info("Schema migration v19: added matter review override persistence")


def _migrate_to_v20(cur: sqlite3.Cursor) -> None:
    """Add persisted matter workspace and snapshot tables (schema v20)."""
    cur.executescript(
        """CREATE TABLE IF NOT EXISTS matters (
            matter_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL UNIQUE,
            case_label TEXT DEFAULT '',
            analysis_goal TEXT DEFAULT '',
            date_from TEXT DEFAULT '',
            date_to TEXT DEFAULT '',
            target_person_entity_id TEXT DEFAULT '',
            latest_snapshot_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_matters_workspace_id ON matters(workspace_id);

        CREATE TABLE IF NOT EXISTS matter_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            review_mode TEXT NOT NULL DEFAULT 'retrieval_only',
            source_scope TEXT NOT NULL DEFAULT '',
            review_state TEXT NOT NULL DEFAULT 'machine_extracted',
            payload_json TEXT NOT NULL,
            coverage_summary_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE,
            FOREIGN KEY (workspace_id) REFERENCES matters(workspace_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_snapshots_workspace_id ON matter_snapshots(workspace_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_matter_snapshots_matter_id ON matter_snapshots(matter_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS matter_sources (
            snapshot_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_type TEXT DEFAULT '',
            document_kind TEXT DEFAULT '',
            source_date TEXT DEFAULT '',
            actor_id TEXT DEFAULT '',
            title TEXT DEFAULT '',
            support_level TEXT DEFAULT '',
            quality_rank TEXT DEFAULT '',
            text_available INTEGER DEFAULT 0,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, source_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_sources_snapshot_id ON matter_sources(snapshot_id, source_type);

        CREATE TABLE IF NOT EXISTS matter_exhibits (
            snapshot_id TEXT NOT NULL,
            exhibit_id TEXT NOT NULL,
            source_id TEXT DEFAULT '',
            exhibit_date TEXT DEFAULT '',
            strength TEXT DEFAULT '',
            readiness TEXT DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, exhibit_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_exhibits_snapshot_id ON matter_exhibits(snapshot_id, source_id);

        CREATE TABLE IF NOT EXISTS matter_chronology_entries (
            snapshot_id TEXT NOT NULL,
            chronology_id TEXT NOT NULL,
            chronology_date TEXT DEFAULT '',
            entry_type TEXT DEFAULT '',
            title TEXT DEFAULT '',
            primary_read TEXT DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, chronology_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_chronology_snapshot_id ON matter_chronology_entries(snapshot_id, chronology_date);

        CREATE TABLE IF NOT EXISTS matter_actors (
            snapshot_id TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            role_hint TEXT DEFAULT '',
            classification TEXT DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, actor_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_actors_snapshot_id ON matter_actors(snapshot_id, email);

        CREATE TABLE IF NOT EXISTS matter_witnesses (
            snapshot_id TEXT NOT NULL,
            witness_id TEXT NOT NULL,
            actor_id TEXT DEFAULT '',
            witness_kind TEXT DEFAULT '',
            title TEXT DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, witness_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_witnesses_snapshot_id ON matter_witnesses(snapshot_id, actor_id);

        CREATE TABLE IF NOT EXISTS matter_comparator_points (
            snapshot_id TEXT NOT NULL,
            comparator_point_id TEXT NOT NULL,
            comparator_issue TEXT DEFAULT '',
            comparison_strength TEXT DEFAULT '',
            claimant_treatment TEXT DEFAULT '',
            comparator_treatment TEXT DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, comparator_point_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_comparator_points_snapshot_id
            ON matter_comparator_points(snapshot_id, comparator_issue);

        CREATE TABLE IF NOT EXISTS matter_issue_rows (
            snapshot_id TEXT NOT NULL,
            issue_id TEXT NOT NULL,
            title TEXT DEFAULT '',
            legal_relevance_status TEXT DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, issue_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_issue_rows_snapshot_id ON matter_issue_rows(snapshot_id, legal_relevance_status);

        CREATE TABLE IF NOT EXISTS matter_dashboard_cards (
            snapshot_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            card_group TEXT DEFAULT '',
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            payload_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, card_id),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_dashboard_cards_snapshot_id ON matter_dashboard_cards(snapshot_id, card_group);

        CREATE TABLE IF NOT EXISTS matter_exports (
            export_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            delivery_target TEXT DEFAULT '',
            delivery_format TEXT DEFAULT '',
            output_path TEXT DEFAULT '',
            review_state TEXT DEFAULT 'machine_extracted',
            details_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (snapshot_id) REFERENCES matter_snapshots(snapshot_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_exports_snapshot_id ON matter_exports(snapshot_id, created_at DESC);"""
    )
    logger.info("Schema migration v20: added persisted matter workspace tables")


def _migrate_to_v21(cur: sqlite3.Cursor) -> None:
    """Add ingest completion ledger and inferred-edge uniqueness (schema v21)."""
    cur.execute(
        """CREATE TABLE IF NOT EXISTS email_ingest_state (
            email_uid TEXT PRIMARY KEY REFERENCES emails(uid) ON DELETE CASCADE,
            body_chunk_count INTEGER DEFAULT 0,
            attachment_chunk_count INTEGER DEFAULT 0,
            image_chunk_count INTEGER DEFAULT 0,
            vector_chunk_count INTEGER DEFAULT 0,
            vector_status TEXT DEFAULT 'pending',
            attachment_status TEXT DEFAULT 'not_requested',
            image_status TEXT DEFAULT 'not_requested',
            last_error TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_ingest_state_vector_status ON email_ingest_state(vector_status)")
    cur.execute(
        """DELETE FROM conversation_edges
           WHERE id NOT IN (
               SELECT MIN(id)
               FROM conversation_edges
               GROUP BY child_uid, parent_uid, edge_type
           )"""
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_edges_unique ON conversation_edges(child_uid, parent_uid, edge_type)"
    )
    logger.info("Schema migration v21: added ingest completion ledger and inferred-edge uniqueness")


def _migrate_to_v22(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add durable attachment text and locator persistence columns (schema v22)."""
    existing = table_columns(cur, "attachments")
    new_cols = {
        "extracted_text": "TEXT DEFAULT ''",
        "text_source_path": "TEXT DEFAULT ''",
        "text_locator_json": "TEXT DEFAULT '{}'",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE attachments ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v22: added durable attachment text and locator persistence columns")


def _migrate_to_v23(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add entity extractor provenance columns (schema v23)."""
    existing = table_columns(cur, "entity_mentions")
    new_cols = {
        "extractor_key": "TEXT DEFAULT ''",
        "extraction_version": "TEXT DEFAULT ''",
        "extracted_at": "TEXT DEFAULT ''",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE entity_mentions ADD COLUMN {col} {col_type}")
    cur.execute(
        """UPDATE entity_mentions
           SET extracted_at = datetime('now')
         WHERE COALESCE(extracted_at, '') = ''"""
    )
    logger.info("Schema migration v23: added entity extractor provenance columns")


def _migrate_to_v24(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add language analytics provenance and confidence columns (schema v24)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "detected_language_confidence": "TEXT",
        "detected_language_reason": "TEXT",
        "detected_language_token_count": "INTEGER DEFAULT 0",
        "detected_language_source": "TEXT DEFAULT ''",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_emails_language_confidence ON emails(detected_language_confidence)")
    logger.info("Schema migration v24: added language analytics provenance and confidence columns")


def _migrate_to_v25(cur: sqlite3.Cursor) -> None:
    """Add evidence-candidate persistence for archive-harvest runs (schema v25)."""
    cur.executescript(
        """\
CREATE TABLE IF NOT EXISTS evidence_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    phase_id TEXT DEFAULT '',
    wave_id TEXT NOT NULL,
    wave_label TEXT DEFAULT '',
    question_ids_json TEXT DEFAULT '[]',
    email_uid TEXT REFERENCES emails(uid),
    candidate_kind TEXT NOT NULL DEFAULT 'body',
    quote_candidate TEXT NOT NULL,
    summary TEXT DEFAULT '',
    category_hint TEXT DEFAULT 'general',
    rank INTEGER DEFAULT 0,
    score REAL DEFAULT 0,
    verification_status TEXT DEFAULT '',
    verified_exact INTEGER DEFAULT 0,
    subject TEXT DEFAULT '',
    sender_name TEXT DEFAULT '',
    sender_email TEXT DEFAULT '',
    date TEXT DEFAULT '',
    conversation_id TEXT DEFAULT '',
    matched_query_lanes_json TEXT DEFAULT '[]',
    matched_query_queries_json TEXT DEFAULT '[]',
    provenance_json TEXT DEFAULT '{}',
    context_json TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'harvested',
    promoted_evidence_id INTEGER REFERENCES evidence_items(id),
    content_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(run_id, wave_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_evidence_candidates_run ON evidence_candidates(run_id, wave_id);
CREATE INDEX IF NOT EXISTS idx_evidence_candidates_email ON evidence_candidates(email_uid);
CREATE INDEX IF NOT EXISTS idx_evidence_candidates_status ON evidence_candidates(status);
CREATE INDEX IF NOT EXISTS idx_evidence_candidates_exact ON evidence_candidates(verified_exact);
"""
    )
    logger.info("Schema migration v25: added evidence_candidates harvest table")


def _migrate_to_v26(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add durable meeting and Exchange metadata JSON columns (schema v26)."""
    existing = table_columns(cur, "emails")
    new_cols = {
        "meeting_data_json": "TEXT DEFAULT '{}'",
        "exchange_extracted_links_json": "TEXT DEFAULT '[]'",
        "exchange_extracted_emails_json": "TEXT DEFAULT '[]'",
        "exchange_extracted_contacts_json": "TEXT DEFAULT '[]'",
        "exchange_extracted_meetings_json": "TEXT DEFAULT '[]'",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE emails ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v26: added durable meeting and Exchange metadata JSON columns")


def _migrate_to_v27(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add durable evidence provenance JSON columns (schema v27)."""
    existing = table_columns(cur, "evidence_items")
    new_cols = {
        "candidate_kind": "TEXT DEFAULT ''",
        "provenance_json": "TEXT DEFAULT '{}'",
        "document_locator_json": "TEXT DEFAULT '{}'",
        "context_json": "TEXT DEFAULT '{}'",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE evidence_items ADD COLUMN {col} {col_type}")
    logger.info("Schema migration v27: added durable evidence provenance columns")


def _migrate_to_v28(cur: sqlite3.Cursor, *, table_columns: Callable[[sqlite3.Cursor, str], set[str]]) -> None:
    """Add stable attachment identity and normalization columns (schema v28)."""
    existing = table_columns(cur, "attachments")
    new_cols = {
        "attachment_id": "TEXT DEFAULT ''",
        "content_sha256": "TEXT DEFAULT ''",
        "ocr_engine": "TEXT DEFAULT ''",
        "ocr_lang": "TEXT DEFAULT ''",
        "ocr_confidence": "REAL DEFAULT 0",
        "normalized_text": "TEXT DEFAULT ''",
        "text_normalization_version": "INTEGER DEFAULT 0",
        "locator_version": "INTEGER DEFAULT 1",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE attachments ADD COLUMN {col} {col_type}")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_attachment_id ON attachments(attachment_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_content_sha256 ON attachments(content_sha256)")
    logger.info("Schema migration v28: added attachment identity and normalization columns")


def _migrate_to_v29(cur: sqlite3.Cursor) -> None:
    """Add per-surface language analytics table (schema v29)."""
    cur.executescript(
        """\
CREATE TABLE IF NOT EXISTS language_surface_analytics (
    email_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
    surface_scope TEXT NOT NULL,
    source_surface TEXT DEFAULT '',
    segment_ordinal INTEGER,
    text_hash TEXT DEFAULT '',
    text_char_count INTEGER DEFAULT 0,
    detected_language TEXT DEFAULT 'unknown',
    detected_language_confidence TEXT DEFAULT '',
    detected_language_reason TEXT DEFAULT '',
    detected_language_token_count INTEGER DEFAULT 0,
    detector_version TEXT DEFAULT 'stopword_v1',
    analyzed_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (email_uid, surface_scope)
);
CREATE INDEX IF NOT EXISTS idx_language_surface_scope ON language_surface_analytics(surface_scope, detected_language);
CREATE INDEX IF NOT EXISTS idx_language_surface_email ON language_surface_analytics(email_uid);
"""
    )
    logger.info("Schema migration v29: added per-surface language analytics table")


def _migrate_to_v30(cur: sqlite3.Cursor) -> None:
    """Add source-aware event record persistence table (schema v30)."""
    cur.executescript(
        """\
CREATE TABLE IF NOT EXISTS event_records (
    event_key TEXT PRIMARY KEY,
    email_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
    event_kind TEXT NOT NULL,
    source_scope TEXT NOT NULL,
    surface_scope TEXT DEFAULT '',
    segment_ordinal INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    trigger_text TEXT DEFAULT '',
    event_date TEXT DEFAULT '',
    surface_hash TEXT DEFAULT '',
    detected_language TEXT DEFAULT 'unknown',
    confidence TEXT DEFAULT 'low',
    extractor_version TEXT DEFAULT 'de_event_rule_v1',
    provenance_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_event_records_uid ON event_records(email_uid, event_kind);
CREATE INDEX IF NOT EXISTS idx_event_records_scope ON event_records(source_scope, event_kind);
"""
    )
    logger.info("Schema migration v30: added event_records table")


def _migrate_to_v31(cur: sqlite3.Cursor) -> None:
    """Add entity occurrence-level provenance table (schema v31)."""
    cur.executescript(
        """\
CREATE TABLE IF NOT EXISTS entity_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    email_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
    source_scope TEXT NOT NULL DEFAULT 'email_text',
    surface_scope TEXT DEFAULT '',
    segment_ordinal INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    occurrence_text TEXT DEFAULT '',
    occurrence_hash TEXT NOT NULL,
    extractor_key TEXT DEFAULT '',
    extraction_version TEXT DEFAULT '',
    extracted_at TEXT DEFAULT (datetime('now')),
    UNIQUE(entity_id, email_uid, occurrence_hash)
);
CREATE INDEX IF NOT EXISTS idx_entity_occurrences_uid ON entity_occurrences(email_uid, source_scope);
CREATE INDEX IF NOT EXISTS idx_entity_occurrences_entity_id ON entity_occurrences(entity_id, extracted_at);
"""
    )
    logger.info("Schema migration v31: added entity_occurrences table")


def _migrate_to_v32(cur: sqlite3.Cursor) -> None:
    """Add resumable ingest checkpoint table (schema v32)."""
    cur.executescript(
        """\
CREATE TABLE IF NOT EXISTS ingest_checkpoints (
    run_id INTEGER PRIMARY KEY REFERENCES ingestion_runs(id) ON DELETE CASCADE,
    olm_path TEXT NOT NULL,
    last_batch_ordinal INTEGER DEFAULT 0,
    emails_parsed INTEGER DEFAULT 0,
    emails_inserted INTEGER DEFAULT 0,
    last_email_uid TEXT DEFAULT '',
    status TEXT DEFAULT 'running',
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ingest_checkpoints_olm_path ON ingest_checkpoints(olm_path, status, updated_at);
"""
    )
    logger.info("Schema migration v32: added ingest_checkpoints table")


def _migrate_to_v33(cur: sqlite3.Cursor) -> None:
    """Upgrade mailbox locator payload compatibility markers (schema v33)."""
    cur.execute(
        """
        UPDATE attachments
        SET locator_version = 2
        WHERE COALESCE(locator_version, 0) < 2
          AND COALESCE(text_locator_json, '{}') NOT IN ('', '{}')
        """
    )
    logger.info("Schema migration v33: normalized mailbox locator versions")


def _migrate_to_v34(cur: sqlite3.Cursor) -> None:
    """Add durable attachment surface child table (schema v34)."""
    cur.executescript(
        """\
CREATE TABLE IF NOT EXISTS attachment_surfaces (
    surface_id TEXT NOT NULL,
    attachment_id TEXT NOT NULL,
    email_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
    attachment_name TEXT DEFAULT '',
    surface_kind TEXT NOT NULL,
    origin_kind TEXT DEFAULT '',
    text TEXT DEFAULT '',
    normalized_text TEXT DEFAULT '',
    alignment_map_json TEXT DEFAULT '{}',
    language TEXT DEFAULT 'unknown',
    language_confidence TEXT DEFAULT '',
    ocr_confidence REAL DEFAULT 0,
    surface_hash TEXT DEFAULT '',
    locator_json TEXT DEFAULT '{}',
    quality_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (attachment_id, surface_id)
);
CREATE INDEX IF NOT EXISTS idx_attachment_surfaces_email_uid ON attachment_surfaces(email_uid);
CREATE INDEX IF NOT EXISTS idx_attachment_surfaces_attachment_id ON attachment_surfaces(attachment_id);
CREATE INDEX IF NOT EXISTS idx_attachment_surfaces_kind ON attachment_surfaces(surface_kind);
"""
    )
    logger.info("Schema migration v34: added attachment_surfaces table")
