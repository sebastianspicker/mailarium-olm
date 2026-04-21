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


_SCHEMA_VERSION = 34

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
    meeting_data_json TEXT DEFAULT '{}',
    exchange_extracted_links_json TEXT DEFAULT '[]',
    exchange_extracted_emails_json TEXT DEFAULT '[]',
    exchange_extracted_contacts_json TEXT DEFAULT '[]',
    exchange_extracted_meetings_json TEXT DEFAULT '[]',
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_edges_unique
    ON conversation_edges(child_uid, parent_uid, edge_type);

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
    extractor_key TEXT DEFAULT '',
    extraction_version TEXT DEFAULT '',
    extracted_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (entity_id, email_uid)
);

CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_normalized ON entities(normalized_form);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_uid ON entity_mentions(email_uid);

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

CREATE TABLE IF NOT EXISTS email_ingest_state (
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
);
CREATE INDEX IF NOT EXISTS idx_email_ingest_state_vector_status ON email_ingest_state(vector_status);
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
    content_hash    TEXT,
    ingestion_run_id INTEGER,
    candidate_kind  TEXT DEFAULT '',
    provenance_json TEXT DEFAULT '{}',
    document_locator_json TEXT DEFAULT '{}',
    context_json    TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    verified        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_evidence_email ON evidence_items(email_uid);
CREATE INDEX IF NOT EXISTS idx_evidence_category ON evidence_items(category);
CREATE INDEX IF NOT EXISTS idx_evidence_relevance ON evidence_items(relevance);
CREATE INDEX IF NOT EXISTS idx_evidence_date ON evidence_items(date);
CREATE INDEX IF NOT EXISTS idx_evidence_verified ON evidence_items(verified);

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

_REVIEW_GOVERNANCE_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS matter_review_overrides (
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
);
CREATE INDEX IF NOT EXISTS idx_review_workspace ON matter_review_overrides(workspace_id);
CREATE INDEX IF NOT EXISTS idx_review_target ON matter_review_overrides(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_review_state ON matter_review_overrides(review_state);
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
    attachment_id TEXT DEFAULT '',
    mime_type TEXT,
    size INTEGER DEFAULT 0,
    content_sha256 TEXT DEFAULT '',
    content_id TEXT,
    is_inline INTEGER DEFAULT 0,
    extraction_state TEXT DEFAULT '',
    evidence_strength TEXT DEFAULT '',
    ocr_used INTEGER DEFAULT 0,
    ocr_engine TEXT DEFAULT '',
    ocr_lang TEXT DEFAULT '',
    ocr_confidence REAL DEFAULT 0,
    failure_reason TEXT DEFAULT '',
    text_preview TEXT DEFAULT '',
    extracted_text TEXT DEFAULT '',
    normalized_text TEXT DEFAULT '',
    text_normalization_version INTEGER DEFAULT 0,
    locator_version INTEGER DEFAULT 1,
    text_source_path TEXT DEFAULT '',
    text_locator_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_attachments_uid ON attachments(email_uid);
CREATE INDEX IF NOT EXISTS idx_attachments_inline ON attachments(is_inline);
CREATE INDEX IF NOT EXISTS idx_attachments_name ON attachments(name);

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

_EVENT_SCHEMA_SQL = """\
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

_INGEST_CHECKPOINT_SCHEMA_SQL = """\
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

_LANGUAGE_SURFACE_SCHEMA_SQL = """\
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

_CATEGORIES_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS email_categories (
    email_uid TEXT NOT NULL REFERENCES emails(uid),
    category TEXT NOT NULL,
    PRIMARY KEY (email_uid, category)
);
CREATE INDEX IF NOT EXISTS idx_categories_name ON email_categories(category);
"""

_MATTER_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS matters (
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
CREATE INDEX IF NOT EXISTS idx_matter_comparator_points_snapshot_id ON matter_comparator_points(snapshot_id, comparator_issue);

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
CREATE INDEX IF NOT EXISTS idx_matter_exports_snapshot_id ON matter_exports(snapshot_id, created_at DESC);
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
    cur.executescript(_REVIEW_GOVERNANCE_SCHEMA_SQL)
    cur.executescript(_CUSTODY_SCHEMA_SQL)
    cur.executescript(_SPARSE_SCHEMA_SQL)
    cur.executescript(_ATTACHMENTS_SCHEMA_SQL)
    cur.executescript(_EVENT_SCHEMA_SQL)
    cur.executescript(_LANGUAGE_SURFACE_SCHEMA_SQL)
    cur.executescript(_INGEST_CHECKPOINT_SCHEMA_SQL)
    cur.executescript(_CATEGORIES_SCHEMA_SQL)
    cur.executescript(_MATTER_SCHEMA_SQL)
    migration_family.apply_pending_migrations_impl(
        conn,
        cur,
        schema_version=_SCHEMA_VERSION,
        table_columns=_table_columns,
        sparse_schema_sql=_SPARSE_SCHEMA_SQL,
    )
    attachment_columns = _table_columns(cur, "attachments")
    if "attachment_id" in attachment_columns:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_attachment_id ON attachments(attachment_id)")
    if "content_sha256" in attachment_columns:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_content_sha256 ON attachments(content_sha256)")
    conn.commit()
