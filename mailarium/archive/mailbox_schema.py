"""Mailbox feature tables owned by the canonical archive schema boundary."""

from __future__ import annotations

import sqlite3

MAILBOX_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mailbox_accounts (
 account_id TEXT PRIMARY KEY,
 source TEXT NOT NULL,
 mailbox_address TEXT NOT NULL DEFAULT '',
 endpoint TEXT NOT NULL DEFAULT '',
 auth_mode TEXT NOT NULL DEFAULT '',
 credential_ref TEXT NOT NULL DEFAULT '',
 read_enabled INTEGER NOT NULL DEFAULT 0,
 write_enabled INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mailbox_folders (
 account_id TEXT NOT NULL,
 folder_id TEXT NOT NULL,
 source TEXT NOT NULL,
 display_name TEXT NOT NULL DEFAULT '',
 selected INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 PRIMARY KEY(account_id, folder_id),
 FOREIGN KEY(account_id) REFERENCES mailbox_accounts(account_id)
);
CREATE TABLE IF NOT EXISTS email_sources (
 account_id TEXT NOT NULL,
 folder_id TEXT NOT NULL,
 source TEXT NOT NULL,
 source_identity TEXT NOT NULL,
 canonical_email_uid TEXT NOT NULL DEFAULT '',
 remote_item_id TEXT NOT NULL,
 change_key TEXT NOT NULL DEFAULT '',
 is_tombstone INTEGER NOT NULL DEFAULT 0,
 canonical_preexisting INTEGER NOT NULL DEFAULT 0,
 metadata_json TEXT NOT NULL DEFAULT '{}',
 updated_at TEXT NOT NULL,
 PRIMARY KEY(account_id, source, remote_item_id),
 FOREIGN KEY(account_id, folder_id) REFERENCES mailbox_folders(account_id, folder_id)
);
CREATE TABLE IF NOT EXISTS email_source_identity_history (
 id INTEGER PRIMARY KEY,
 account_id TEXT NOT NULL,
 folder_id TEXT NOT NULL,
 source TEXT NOT NULL,
 source_identity TEXT NOT NULL,
 change_key TEXT NOT NULL DEFAULT '',
 is_tombstone INTEGER NOT NULL DEFAULT 0,
 observed_at TEXT NOT NULL,
 UNIQUE(account_id, folder_id, source, source_identity, change_key, is_tombstone, observed_at)
);
CREATE TABLE IF NOT EXISTS mailbox_sync_cursors (
 account_id TEXT NOT NULL,
 scope TEXT NOT NULL,
 folder_id TEXT NOT NULL,
 generation INTEGER NOT NULL DEFAULT 0,
 cursor_value TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'idle',
 completed_at TEXT,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(account_id, scope, folder_id),
 FOREIGN KEY(account_id, folder_id) REFERENCES mailbox_folders(account_id, folder_id)
);
CREATE TABLE IF NOT EXISTS mailbox_action_proposals (
 proposal_id TEXT PRIMARY KEY,
 account_id TEXT NOT NULL,
 folder_id TEXT NOT NULL,
 operation TEXT NOT NULL,
 target_identity TEXT NOT NULL,
 target_change_key TEXT NOT NULL,
 target_json TEXT NOT NULL DEFAULT '{}',
 parameters_json TEXT NOT NULL DEFAULT '{}',
 proposal_digest TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL,
 proposer_kind TEXT NOT NULL,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 approved_at TEXT,
 execution_deadline TEXT,
 FOREIGN KEY(account_id, folder_id) REFERENCES mailbox_folders(account_id, folder_id)
);
CREATE TABLE IF NOT EXISTS mailbox_action_events (
 id INTEGER PRIMARY KEY,
 proposal_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 actor_kind TEXT NOT NULL,
 detail_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 FOREIGN KEY(proposal_id) REFERENCES mailbox_action_proposals(proposal_id)
);
CREATE TABLE IF NOT EXISTS mailbox_action_attempts (
 id INTEGER PRIMARY KEY,
 proposal_id TEXT NOT NULL,
 state TEXT NOT NULL,
 started_at TEXT NOT NULL,
 completed_at TEXT,
 detail_json TEXT NOT NULL DEFAULT '{}',
 FOREIGN KEY(proposal_id) REFERENCES mailbox_action_proposals(proposal_id)
);
CREATE INDEX IF NOT EXISTS idx_mailbox_actions_state
 ON mailbox_action_proposals(state, expires_at);
CREATE INDEX IF NOT EXISTS idx_mailbox_source_history
 ON email_source_identity_history(account_id, folder_id, source_identity);
CREATE INDEX IF NOT EXISTS idx_email_sources_canonical_visibility
 ON email_sources(canonical_email_uid, is_tombstone);
"""

_IDENTITY_HISTORY_STATEMENT = (
    "INSERT OR IGNORE INTO email_source_identity_history("
    "account_id,folder_id,source,source_identity,change_key,is_tombstone,observed_at) "
    "VALUES(?,?,?,?,?,?,?)"
)


def ensure_mailbox_schema_compatibility(
    database: sqlite3.Connection | sqlite3.Cursor,
) -> None:
    """Add columns from early development copies without committing a transaction."""
    columns = {row[1] for row in database.execute("PRAGMA table_info(mailbox_action_proposals)")}
    for name in ("target_json", "parameters_json"):
        if name not in columns:
            database.execute(f"ALTER TABLE mailbox_action_proposals ADD COLUMN {name} TEXT NOT NULL DEFAULT '{{}}'")
    source_columns = {row[1] for row in database.execute("PRAGMA table_info(email_sources)")}
    if "canonical_preexisting" not in source_columns:
        database.execute("ALTER TABLE email_sources ADD COLUMN canonical_preexisting INTEGER NOT NULL DEFAULT 0")
    folder_columns = {row[1] for row in database.execute("PRAGMA table_info(mailbox_folders)")}
    if "selected" not in folder_columns:
        database.execute("ALTER TABLE mailbox_folders ADD COLUMN selected INTEGER NOT NULL DEFAULT 1")


def initialize_mailbox_schema(conn: sqlite3.Connection) -> None:
    """Install mailbox tables without owning or changing the root schema version."""
    conn.executescript(MAILBOX_SCHEMA_SQL)
    ensure_mailbox_schema_compatibility(conn)
    conn.commit()
