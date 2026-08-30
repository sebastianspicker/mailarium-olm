"""Mailbox source identities and synchronization-cursor repository."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mailarium.model.mailbox_models import MailboxMessageRecord

from .store_connection import MailboxStoreConnection
from .store_schema import (
    _complete_refresh_cursor,
    _copy_remote_identity,
    _ensure_identity_destination_folder,
    _move_remote_identity,
    _record_identity_history,
    _redacted,
    _remote_identity_metadata,
    _stale_refresh_rows,
    _stamp,
    _tombstone_refresh_rows,
    _validated_refresh_cursor,
)


class MailboxSourceRepository(MailboxStoreConnection):
    @staticmethod
    def _current_sync_generation(
        cur: sqlite3.Cursor,
        account_id: str,
        folder_id: str,
    ) -> int:
        row = cur.execute(
            "SELECT generation FROM mailbox_sync_cursors WHERE account_id=? AND scope='items' AND folder_id=?",
            (account_id, folder_id),
        ).fetchone()
        return 0 if row is None else int(row["generation"])

    def upsert_message(
        self,
        record: MailboxMessageRecord,
        *,
        display_name: str = "",
        stamp_current_generation: bool = False,
    ) -> None:
        """Persist one mailbox source record and its identity-history observation."""
        observed = _stamp()
        account_statement = "INSERT OR IGNORE INTO mailbox_accounts(account_id, source, created_at) VALUES(?,?,?)"
        folder_statement = (
            "INSERT OR IGNORE INTO mailbox_folders("
            "account_id,folder_id,source,display_name,selected,created_at) "
            "VALUES(?,?,?,?,0,?)"
        )
        source_statement = """
            INSERT INTO email_sources(
                account_id,folder_id,source,source_identity,canonical_email_uid,
                remote_item_id,change_key,is_tombstone,canonical_preexisting,
                metadata_json,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(account_id,source,remote_item_id) DO UPDATE SET
                folder_id=excluded.folder_id,
                source_identity=excluded.source_identity,
                canonical_email_uid=excluded.canonical_email_uid,
                change_key=excluded.change_key,
                is_tombstone=excluded.is_tombstone,
                canonical_preexisting=MAX(
                    email_sources.canonical_preexisting,
                    excluded.canonical_preexisting
                ),
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
        """
        history_statement = (
            "INSERT INTO email_source_identity_history("
            "account_id,folder_id,source,source_identity,change_key,is_tombstone,observed_at) "
            "VALUES(?,?,?,?,?,?,?)"
        )
        remote_item_id = record.remote_item_id or record.source_identity
        metadata = dict(record.metadata)
        with self._write() as cur:
            if stamp_current_generation:
                metadata["sync_generation"] = self._current_sync_generation(
                    cur,
                    record.account_id,
                    record.folder_id,
                )
            cur.execute(
                account_statement,
                (record.account_id, record.source, observed),
            )
            cur.execute(
                folder_statement,
                (
                    record.account_id,
                    record.folder_id,
                    record.source,
                    display_name,
                    observed,
                ),
            )
            cur.execute(
                source_statement,
                (
                    record.account_id,
                    record.folder_id,
                    record.source,
                    record.source_identity,
                    record.canonical_email_uid or remote_item_id,
                    remote_item_id,
                    record.change_key,
                    int(record.is_tombstone),
                    int(bool(metadata.get("canonical_preexisting", False))),
                    _redacted(metadata),
                    observed,
                ),
            )
            cur.execute(
                history_statement,
                (
                    record.account_id,
                    record.folder_id,
                    record.source,
                    record.source_identity,
                    record.change_key,
                    int(record.is_tombstone),
                    observed,
                ),
            )

    upsert_source = upsert_message

    def finalize_source_projection(self, record: MailboxMessageRecord) -> None:
        """Refresh a pending source row without recording a second observation."""
        remote_item_id = record.remote_item_id or record.source_identity
        metadata = dict(record.metadata)
        with self._write() as cur:
            row = cur.execute(
                "SELECT canonical_preexisting,metadata_json FROM email_sources "
                "WHERE account_id=? AND source=? AND remote_item_id=?",
                (record.account_id, record.source, remote_item_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("pending mailbox source disappeared before projection completion")
            previous_metadata = json.loads(row["metadata_json"])
            if not previous_metadata.get("projection_pending"):
                raise RuntimeError("mailbox source is not pending projection completion")
            cur.execute(
                """
                UPDATE email_sources SET
                    folder_id=?, source_identity=?, canonical_email_uid=?, change_key=?,
                    is_tombstone=?, canonical_preexisting=?, metadata_json=?, updated_at=?
                WHERE account_id=? AND source=? AND remote_item_id=?
                """,
                (
                    record.folder_id,
                    record.source_identity,
                    record.canonical_email_uid or remote_item_id,
                    record.change_key,
                    int(record.is_tombstone),
                    max(
                        int(row["canonical_preexisting"]),
                        int(bool(metadata.get("canonical_preexisting", False))),
                    ),
                    _redacted(metadata),
                    _stamp(),
                    record.account_id,
                    record.source,
                    remote_item_id,
                ),
            )

    def record_remote_identity_change(
        self,
        *,
        account_id: str,
        source: str,
        old_remote_item_id: str,
        new_remote_item_id: str,
        new_change_key: str,
        destination_folder_id: str,
        copy: bool = False,
    ) -> None:
        """Persist an EWS move/copy identity result while retaining the old identity."""
        with self._write() as cur:
            row = cur.execute(
                "SELECT * FROM email_sources WHERE account_id=? AND source=? AND remote_item_id=?",
                (account_id, source, old_remote_item_id),
            ).fetchone()
            if row is None:
                raise KeyError(old_remote_item_id)
            metadata_json = _remote_identity_metadata(
                row,
                self._current_sync_generation(cur, account_id, destination_folder_id),
            )
            _ensure_identity_destination_folder(cur, account_id, destination_folder_id, source)
            _record_identity_history(cur, account_id, source, old_remote_item_id, row)
            if copy:
                _copy_remote_identity(
                    cur, row, account_id, destination_folder_id, source, new_remote_item_id, new_change_key, metadata_json
                )
            else:
                _move_remote_identity(
                    cur,
                    account_id,
                    destination_folder_id,
                    source,
                    old_remote_item_id,
                    new_remote_item_id,
                    new_change_key,
                    metadata_json,
                )

    def tombstone_source(
        self,
        *,
        account_id: str,
        folder_id: str,
        source: str,
        source_identity: str,
        change_key: str = "",
    ) -> None:
        """Record a deleted source identity while retaining its canonical mail linkage."""
        existing = self.conn.execute(
            "SELECT * FROM email_sources WHERE account_id=? AND source=? "
            "AND (remote_item_id=? OR source_identity=?) ORDER BY "
            "CASE WHEN remote_item_id=? THEN 0 ELSE 1 END LIMIT 1",
            (account_id, source, source_identity, source_identity, source_identity),
        ).fetchone()
        metadata = json.loads(existing["metadata_json"]) if existing is not None else {}
        if existing is not None:
            metadata["canonical_preexisting"] = bool(existing["canonical_preexisting"])
        self.upsert_message(
            MailboxMessageRecord(
                account_id,
                folder_id,
                source,
                str(existing["source_identity"] if existing is not None else source_identity),
                canonical_email_uid=str(existing["canonical_email_uid"] if existing is not None else ""),
                remote_item_id=str(existing["remote_item_id"] if existing is not None else source_identity),
                change_key=change_key,
                is_tombstone=True,
                metadata=metadata,
            )
        )

    def list_sources(
        self,
        account_id: str,
        folder_id: str,
        *,
        include_tombstones: bool = False,
    ) -> list[dict[str, Any]]:
        """List account-folder source records, optionally including tombstones."""
        query = "SELECT * FROM email_sources WHERE account_id=? AND folder_id=?"
        args: tuple[Any, ...] = (account_id, folder_id)
        if not include_tombstones:
            query += " AND is_tombstone=0"
        rows = self.conn.execute(query + " ORDER BY source,source_identity", args)
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    def advance_cursor(
        self,
        account_id: str,
        folder_id: str,
        cursor_value: str,
        *,
        scope: str = "items",
        expected_generation: int | None = None,
        expected_cursor_value: str | None = None,
        completed: bool = False,
    ) -> int:
        """Advance a cursor by compare-and-set within its active synchronization generation."""
        select_statement = (
            "SELECT generation,cursor_value,state FROM mailbox_sync_cursors WHERE account_id=? AND scope=? AND folder_id=?"
        )
        update_statement = (
            "UPDATE mailbox_sync_cursors SET "
            "cursor_value=?,state=?,completed_at=?,updated_at=? "
            "WHERE account_id=? AND scope=? AND folder_id=? AND generation=?"
        )
        with self._write() as cur:
            row = cur.execute(
                select_statement,
                (account_id, scope, folder_id),
            ).fetchone()
            generation = int(row["generation"]) if row else 0
            if expected_generation is not None and expected_generation != generation:
                raise RuntimeError("cursor generation conflict")
            if row is None:
                raise RuntimeError("cursor generation not started")
            if expected_cursor_value is not None and str(row["cursor_value"]) != expected_cursor_value:
                raise RuntimeError("cursor watermark conflict")
            next_state = "completed" if completed else str(row["state"] or "active")
            cur.execute(
                update_statement,
                (
                    cursor_value,
                    next_state,
                    _stamp() if completed else None,
                    _stamp(),
                    account_id,
                    scope,
                    folder_id,
                    generation,
                ),
            )
            return generation

    def cursor(
        self,
        account_id: str,
        folder_id: str,
        *,
        scope: str = "items",
    ) -> tuple[int, str]:
        """Return the current generation and watermark for one synchronization scope."""
        row = self.conn.execute(
            "SELECT generation,cursor_value FROM mailbox_sync_cursors WHERE account_id=? AND scope=? AND folder_id=?",
            (account_id, scope, folder_id),
        ).fetchone()
        return (0, "") if row is None else (int(row["generation"]), str(row["cursor_value"]))

    get_cursor = cursor

    def cursor_state(
        self,
        account_id: str,
        folder_id: str,
        *,
        scope: str = "items",
    ) -> str:
        """Return the lifecycle state for one synchronization cursor."""
        row = self.conn.execute(
            "SELECT state FROM mailbox_sync_cursors WHERE account_id=? AND scope=? AND folder_id=?",
            (account_id, scope, folder_id),
        ).fetchone()
        return "idle" if row is None else str(row["state"])

    def start_cursor_generation(
        self,
        account_id: str,
        folder_id: str,
        *,
        scope: str = "items",
        expected_generation: int | None = None,
    ) -> int:
        """Start a new full-refresh generation after an optional generation check."""
        select_statement = "SELECT generation FROM mailbox_sync_cursors WHERE account_id=? AND scope=? AND folder_id=?"
        insert_statement = (
            "INSERT INTO mailbox_sync_cursors("
            "account_id,scope,folder_id,generation,cursor_value,state,completed_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(account_id,scope,folder_id) DO UPDATE SET "
            "generation=excluded.generation,cursor_value='',state='full_refresh',completed_at=NULL,"
            "updated_at=excluded.updated_at"
        )
        with self._write() as cur:
            row = cur.execute(
                select_statement,
                (account_id, scope, folder_id),
            ).fetchone()
            current_generation = int(row["generation"]) if row else 0
            if expected_generation is not None and current_generation != expected_generation:
                raise RuntimeError("cursor generation conflict")
            generation = current_generation + 1
            cur.execute(
                insert_statement,
                (
                    account_id,
                    scope,
                    folder_id,
                    generation,
                    "",
                    "full_refresh",
                    None,
                    _stamp(),
                ),
            )
            return generation

    def complete_full_refresh(
        self,
        account_id: str,
        folder_id: str,
        cursor_value: str,
        *,
        generation: int,
        expected_cursor_value: str,
        scope: str = "items",
    ) -> int:
        """Atomically tombstone stale rows and complete the current generation."""
        observed = _stamp()
        with self._write() as cur:
            _validated_refresh_cursor(cur, account_id, folder_id, scope, generation, expected_cursor_value)
            stale = _stale_refresh_rows(cur, account_id, folder_id, generation)
            _tombstone_refresh_rows(cur, stale, account_id, folder_id, observed)
            _complete_refresh_cursor(
                cur,
                account_id,
                folder_id,
                cursor_value,
                scope,
                generation,
                expected_cursor_value,
                observed,
            )
            return len(stale)

    commit_cursor = advance_cursor
