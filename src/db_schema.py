"""Schema DDL and migration logic for the email SQLite database."""

from __future__ import annotations

import logging
import sqlite3

from . import db_schema_migrations as migration_family

logger = logging.getLogger(__name__)


def _escape_like(text: str) -> str:
    """Escape SQL LIKE wildcards (``%``, ``_``, ``\\``) for use with ESCAPE '\\'."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _table_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    """Return the set of column names for *table* using PRAGMA table_info.

    Safety: *table* is always a hardcoded string from migration functions
    (e.g. ``"emails"``, ``"ingestion_runs"``), never user input.
    """
    return {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}


_SCHEMA_VERSION = 18

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version   INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS emails (
    uid              TEXT PRIMARY KEY,
    message_id       TEXT,
    subject          TEXT,
    sender_name      TEXT,
    sender_email     TEXT,
    date             TEXT,
    folder           TEXT,
    email_type       TEXT,
    has_attachments  INTEGER,
    attachment_count INTEGER,
    priority         INTEGER,
    is_read          INTEGER,
    conversation_id  TEXT,
    in_reply_to      TEXT,
    base_subject     TEXT,
    body_length      INTEGER,
    body_text        TEXT,
    body_html        TEXT,
    raw_body_text    TEXT,
    raw_body_html    TEXT,
    raw_source       TEXT,
    raw_source_headers_json TEXT DEFAULT '{}',
    forensic_body_text TEXT,
    forensic_body_source TEXT DEFAULT '',
    normalized_body_source TEXT DEFAULT 'body_text',
    body_normalization_version INTEGER DEFAULT 11,
    body_kind TEXT DEFAULT 'content',
    body_empty_reason TEXT DEFAULT '',
    recovery_strategy TEXT DEFAULT '',
    recovery_confidence REAL DEFAULT 0,
    to_identities_json TEXT DEFAULT '[]',
    cc_identities_json TEXT DEFAULT '[]',
    bcc_identities_json TEXT DEFAULT '[]',
    recipient_identity_source TEXT DEFAULT '',
    reply_context_from TEXT DEFAULT '',
    reply_context_to_json TEXT DEFAULT '[]',
    reply_context_subject TEXT DEFAULT '',
    reply_context_date TEXT DEFAULT '',
    reply_context_source TEXT DEFAULT '',
    inferred_parent_uid TEXT DEFAULT '',
    inferred_thread_id TEXT DEFAULT '',
    inferred_match_reason TEXT DEFAULT '',
    inferred_match_confidence REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS message_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    segment_type TEXT NOT NULL,
    depth INTEGER DEFAULT 0,
    text TEXT NOT NULL,
    source_surface TEXT NOT NULL,
    provenance_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS conversation_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
    parent_uid TEXT NOT NULL REFERENCES emails(uid) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    reason TEXT DEFAULT '',
    confidence REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(sender_email);
CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date);
CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder);
CREATE INDEX IF NOT EXISTS idx_emails_conversation ON emails(conversation_id);
CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);
CREATE INDEX IF NOT EXISTS idx_emails_in_reply_to ON emails(in_reply_to);
CREATE INDEX IF NOT EXISTS idx_emails_base_subject ON emails(base_subject);
CREATE INDEX IF NOT EXISTS idx_message_segments_email_uid ON message_segments(email_uid, ordinal);
CREATE INDEX IF NOT EXISTS idx_conversation_edges_child ON conversation_edges(child_uid);
CREATE INDEX IF NOT EXISTS idx_conversation_edges_parent ON conversation_edges(parent_uid);

CREATE TABLE IF NOT EXISTS recipients (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    email_uid TEXT NOT NULL REFERENCES emails(uid),
    address   TEXT NOT NULL,
    display_name TEXT,
    type      TEXT CHECK(type IN ('to', 'cc', 'bcc'))
);

CREATE INDEX IF NOT EXISTS idx_recipients_address ON recipients(address);
CREATE INDEX IF NOT EXISTS idx_recipients_uid ON recipients(email_uid);

CREATE TABLE IF NOT EXISTS contacts (
    email_address  TEXT PRIMARY KEY,
    display_name   TEXT,
    first_seen     TEXT,
    last_seen      TEXT,
    sent_count     INTEGER DEFAULT 0,
    received_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS communication_edges (
    sender_email    TEXT NOT NULL,
    recipient_email TEXT NOT NULL,
    email_count     INTEGER DEFAULT 1,
    first_date      TEXT,
    last_date       TEXT,
    PRIMARY KEY (sender_email, recipient_email)
);

CREATE INDEX IF NOT EXISTS idx_edges_sender ON communication_edges(sender_email);
CREATE INDEX IF NOT EXISTS idx_edges_recipient ON communication_edges(recipient_email);
"""

# Entity tables added in Phase 6 but created upfront for schema simplicity
_ENTITY_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_text     TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    normalized_form TEXT NOT NULL,
    UNIQUE(normalized_form, entity_type)
);

CREATE TABLE IF NOT EXISTS entity_mentions (
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    email_uid TEXT NOT NULL REFERENCES emails(uid),
    mention_count INTEGER DEFAULT 1,
    PRIMARY KEY (entity_id, email_uid)
);

CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_normalized ON entities(normalized_form);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_uid ON entity_mentions(email_uid);
"""

_KEYWORDS_TOPICS_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS email_keywords (
    email_uid TEXT NOT NULL REFERENCES emails(uid),
    keyword   TEXT NOT NULL,
    score     REAL NOT NULL,
    PRIMARY KEY (email_uid, keyword)
);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON email_keywords(keyword);

CREATE TABLE IF NOT EXISTS topics (
    id        INTEGER PRIMARY KEY,
    label     TEXT NOT NULL,
    top_words TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_topics (
    email_uid TEXT NOT NULL REFERENCES emails(uid),
    topic_id  INTEGER NOT NULL REFERENCES topics(id),
    weight    REAL NOT NULL,
    PRIMARY KEY (email_uid, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_email_topics_topic ON email_topics(topic_id);
"""

_CLUSTER_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS email_clusters (
    email_uid    TEXT PRIMARY KEY REFERENCES emails(uid),
    cluster_id   INTEGER NOT NULL,
    distance     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clusters_id ON email_clusters(cluster_id);

CREATE TABLE IF NOT EXISTS cluster_info (
    cluster_id        INTEGER PRIMARY KEY,
    size              INTEGER NOT NULL,
    representative_uid TEXT,
    label             TEXT
);
"""

_INGESTION_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    olm_path        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    emails_parsed   INTEGER,
    emails_inserted INTEGER,
    status          TEXT DEFAULT 'running'
);
CREATE INDEX IF NOT EXISTS idx_ingestion_status ON ingestion_runs(status);
"""

_EVIDENCE_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS evidence_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email_uid       TEXT NOT NULL REFERENCES emails(uid),
    category        TEXT NOT NULL,
    key_quote       TEXT NOT NULL,
    summary         TEXT NOT NULL,
    relevance       INTEGER NOT NULL CHECK(relevance BETWEEN 1 AND 5),
    sender_name     TEXT,
    sender_email    TEXT,
    date            TEXT,
    recipients      TEXT,
    subject         TEXT,
    notes           TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    verified        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_evidence_email ON evidence_items(email_uid);
CREATE INDEX IF NOT EXISTS idx_evidence_category ON evidence_items(category);
CREATE INDEX IF NOT EXISTS idx_evidence_relevance ON evidence_items(relevance);
CREATE INDEX IF NOT EXISTS idx_evidence_date ON evidence_items(date);
CREATE INDEX IF NOT EXISTS idx_evidence_verified ON evidence_items(verified);
"""

_CUSTODY_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS custody_chain (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    action       TEXT NOT NULL,
    timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
    actor        TEXT DEFAULT 'system',
    target_type  TEXT,
    target_id    TEXT,
    details      TEXT,
    content_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_custody_action ON custody_chain(action);
CREATE INDEX IF NOT EXISTS idx_custody_target ON custody_chain(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_custody_timestamp ON custody_chain(timestamp);
"""

_SPARSE_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS sparse_vectors (
    chunk_id   TEXT PRIMARY KEY,
    token_ids  BLOB NOT NULL,
    weights    BLOB NOT NULL,
    num_tokens INTEGER NOT NULL
);
"""

_ATTACHMENTS_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_uid TEXT NOT NULL REFERENCES emails(uid),
    name TEXT NOT NULL,
    mime_type TEXT,
    size INTEGER DEFAULT 0,
    content_id TEXT,
    is_inline INTEGER DEFAULT 0,
    extraction_state TEXT DEFAULT '',
    evidence_strength TEXT DEFAULT '',
    ocr_used INTEGER DEFAULT 0,
    failure_reason TEXT DEFAULT '',
    text_preview TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_attachments_uid ON attachments(email_uid);
CREATE INDEX IF NOT EXISTS idx_attachments_inline ON attachments(is_inline);
CREATE INDEX IF NOT EXISTS idx_attachments_name ON attachments(name);
"""

_CATEGORIES_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS email_categories (
    email_uid TEXT NOT NULL REFERENCES emails(uid),
    category TEXT NOT NULL,
    PRIMARY KEY (email_uid, category)
);
CREATE INDEX IF NOT EXISTS idx_categories_name ON email_categories(category);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and run pending migrations."""
    cur = conn.cursor()
    cur.executescript(_SCHEMA_SQL)
    cur.executescript(_ENTITY_SCHEMA_SQL)
    cur.executescript(_KEYWORDS_TOPICS_SCHEMA_SQL)
    cur.executescript(_CLUSTER_SCHEMA_SQL)
    cur.executescript(_INGESTION_SCHEMA_SQL)
    cur.executescript(_EVIDENCE_SCHEMA_SQL)
    cur.executescript(_CUSTODY_SCHEMA_SQL)
    cur.executescript(_SPARSE_SCHEMA_SQL)
    cur.executescript(_ATTACHMENTS_SCHEMA_SQL)
    cur.executescript(_CATEGORIES_SCHEMA_SQL)
    migration_family.apply_pending_migrations_impl(
        conn,
        cur,
        schema_version=_SCHEMA_VERSION,
        table_columns=_table_columns,
        sparse_schema_sql=_SPARSE_SCHEMA_SQL,
    )
