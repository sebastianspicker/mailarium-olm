"""Internal SQLite primitives for :mod:`mailarium.mailbox.mailbox_store`.

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

_IDENTITY_HISTORY_STATEMENT = (
    "INSERT OR IGNORE INTO email_source_identity_history("
    "account_id,folder_id,source,source_identity,change_key,is_tombstone,observed_at) "
    "VALUES(?,?,?,?,?,?,?)"
)


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
