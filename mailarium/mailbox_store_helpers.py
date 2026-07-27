"""Internal SQLite primitives for :mod:`mailarium.mailbox_store`.

Keeping schema and serialisation details here lets ``MailboxStore`` remain the
public transactional facade while keeping the facade module below the static
analysis file-size threshold.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

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


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _stamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _redacted(value: Mapping[str, Any] | None) -> str:
    """Persist structured audit metadata while dropping secret-shaped values."""
    sensitive = {"token", "secret", "password", "credential", "authorization", "api_key"}

    def clean(current: Any, *, key: str = "") -> Any:
        if any(word in key.casefold() for word in sensitive):
            return "[REDACTED]"
        if isinstance(current, Mapping):
            return {str(nested_key): clean(nested, key=str(nested_key)) for nested_key, nested in current.items()}
        if isinstance(current, (list, tuple)):
            return [clean(nested, key=key) for nested in current]
        return current

    return json.dumps(clean(value or {}), sort_keys=True, separators=(",", ":"), default=str)


def _proposal_payload(
    account_id: str,
    folder_id: str,
    operation: str,
    target_identity: str,
    target_change_key: str,
    target: Mapping[str, Any] | None,
    parameters: Mapping[str, Any] | None,
) -> tuple[str, str, str]:
    exact_target = json.dumps(target or {}, sort_keys=True, separators=(",", ":"), default=str)
    exact_parameters = json.dumps(parameters or {}, sort_keys=True, separators=(",", ":"), default=str)
    digest_payload = {
        "account_id": account_id,
        "folder_id": folder_id,
        "operation": operation,
        "target_identity": target_identity,
        "target_change_key": target_change_key,
        "target": json.loads(exact_target),
        "parameters": json.loads(exact_parameters),
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return exact_target, exact_parameters, digest


def _remote_identity_metadata(row: sqlite3.Row, generation: int) -> str:
    try:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["sync_generation"] = generation
    return _redacted(metadata)


def _record_identity_history(
    cur: sqlite3.Cursor,
    account_id: str,
    source: str,
    old_remote_item_id: str,
    row: sqlite3.Row,
) -> None:
    cur.execute(
        _IDENTITY_HISTORY_STATEMENT,
        (account_id, str(row["folder_id"]), source, old_remote_item_id, str(row["change_key"]), 0, _stamp()),
    )


def _ensure_identity_destination_folder(cur: sqlite3.Cursor, account_id: str, destination_folder_id: str, source: str) -> None:
    cur.execute(
        "INSERT OR IGNORE INTO mailbox_folders(account_id,folder_id,source,display_name,selected,created_at) VALUES(?,?,?,?,0,?)",
        (account_id, destination_folder_id, source, destination_folder_id, _stamp()),
    )


def _copy_remote_identity(
    cur: sqlite3.Cursor,
    row: sqlite3.Row,
    account_id: str,
    destination_folder_id: str,
    source: str,
    new_remote_item_id: str,
    new_change_key: str,
    metadata_json: str,
) -> None:
    cur.execute(
        "INSERT INTO email_sources(account_id,folder_id,source,source_identity,canonical_email_uid,"
        "remote_item_id,change_key,is_tombstone,canonical_preexisting,metadata_json,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            account_id,
            destination_folder_id,
            source,
            new_remote_item_id,
            str(row["canonical_email_uid"]),
            new_remote_item_id,
            new_change_key,
            0,
            int(row["canonical_preexisting"]),
            metadata_json,
            _stamp(),
        ),
    )


def _move_remote_identity(
    cur: sqlite3.Cursor,
    account_id: str,
    destination_folder_id: str,
    source: str,
    old_remote_item_id: str,
    new_remote_item_id: str,
    new_change_key: str,
    metadata_json: str,
) -> None:
    cur.execute(
        "UPDATE email_sources SET folder_id=?,source_identity=?,remote_item_id=?,change_key=?,"
        "metadata_json=?,updated_at=? WHERE account_id=? AND source=? AND remote_item_id=?",
        (
            destination_folder_id,
            new_remote_item_id,
            new_remote_item_id,
            new_change_key,
            metadata_json,
            _stamp(),
            account_id,
            source,
            old_remote_item_id,
        ),
    )


def _validated_refresh_cursor(
    cur: sqlite3.Cursor,
    account_id: str,
    folder_id: str,
    scope: str,
    generation: int,
    expected_cursor_value: str,
) -> None:
    cursor = cur.execute(
        "SELECT generation,cursor_value FROM mailbox_sync_cursors WHERE account_id=? AND scope=? AND folder_id=?",
        (account_id, scope, folder_id),
    ).fetchone()
    if cursor is None or int(cursor["generation"]) != generation:
        raise RuntimeError("cursor generation conflict")
    if str(cursor["cursor_value"]) != expected_cursor_value:
        raise RuntimeError("cursor watermark conflict")


def _stale_refresh_rows(
    cur: sqlite3.Cursor,
    account_id: str,
    folder_id: str,
    generation: int,
) -> list[sqlite3.Row]:
    rows = cur.execute(
        "SELECT * FROM email_sources WHERE account_id=? AND folder_id=? AND is_tombstone=0",
        (account_id, folder_id),
    ).fetchall()
    return [row for row in rows if _row_generation(row) != generation]


def _row_generation(row: sqlite3.Row) -> int:
    try:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    return int(metadata.get("sync_generation") or 0)


def _tombstone_refresh_rows(
    cur: sqlite3.Cursor,
    rows: list[sqlite3.Row],
    account_id: str,
    folder_id: str,
    observed: str,
) -> None:
    for row in rows:
        cur.execute(
            "UPDATE email_sources SET is_tombstone=1,updated_at=? "
            "WHERE account_id=? AND source=? AND remote_item_id=? "
            "AND is_tombstone=0",
            (observed, account_id, str(row["source"]), str(row["remote_item_id"])),
        )
        if cur.rowcount == 1:
            cur.execute(
                "INSERT INTO email_source_identity_history("
                "account_id,folder_id,source,source_identity,change_key,"
                "is_tombstone,observed_at) VALUES(?,?,?,?,?,?,?)",
                (
                    account_id,
                    folder_id,
                    str(row["source"]),
                    str(row["source_identity"]),
                    str(row["change_key"] or ""),
                    1,
                    observed,
                ),
            )


def _complete_refresh_cursor(
    cur: sqlite3.Cursor,
    account_id: str,
    folder_id: str,
    cursor_value: str,
    scope: str,
    generation: int,
    expected_cursor_value: str,
    observed: str,
) -> None:
    cur.execute(
        "UPDATE mailbox_sync_cursors SET cursor_value=?,state='completed',"
        "completed_at=?,updated_at=? WHERE account_id=? AND scope=? "
        "AND folder_id=? AND generation=? AND cursor_value=?",
        (
            cursor_value,
            observed,
            observed,
            account_id,
            scope,
            folder_id,
            generation,
            expected_cursor_value,
        ),
    )
    if cur.rowcount != 1:
        raise RuntimeError("cursor completion conflict")
