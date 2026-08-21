"""SQLite-backed canonical mailbox state and action ledger.

This module intentionally has no transport dependency. Source adapters own EWS,
Graph, or local-file calls and supply only stable source identities/change keys.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .mailbox_models import (
    ActorKind,
    MailboxActionClaim,
    MailboxActionOutcome,
    MailboxActionProposal,
    MailboxMessageRecord,
    ProposalState,
)
from .mailbox_store_helpers import (
    MAILBOX_SCHEMA_SQL,
    _complete_refresh_cursor,
    _copy_remote_identity,
    _ensure_identity_destination_folder,
    _move_remote_identity,
    _now,
    _proposal_payload,
    _record_identity_history,
    _redacted,
    _remote_identity_metadata,
    _stale_refresh_rows,
    _stamp,
    _tombstone_refresh_rows,
    _validated_refresh_cursor,
    ensure_mailbox_schema_compatibility,
    initialize_mailbox_schema,
)

__all__ = [
    "MAILBOX_SCHEMA_SQL",
    "MailboxStore",
    "ensure_mailbox_schema_compatibility",
    "initialize_mailbox_schema",
]

_OUTCOME_STATES = {
    ProposalState.SUCCEEDED,
    ProposalState.RETRYABLE,
    ProposalState.CONFLICTED,
    ProposalState.FAILED,
    ProposalState.UNCERTAIN,
}
_ALLOWED_OPERATIONS = frozenset({"update_item", "move_item", "copy_item", "delete_item", "create_draft", "send_item"})


class MailboxStore:
    """Small transactional state layer for source adapters and action executors."""

    def __init__(
        self,
        database: str | Path | sqlite3.Connection,
        *,
        operation_context: Callable[[], Any] | None = None,
    ) -> None:
        self._owns_connection = not isinstance(database, sqlite3.Connection)
        self.conn = (
            database
            if isinstance(database, sqlite3.Connection)
            else sqlite3.connect(str(database), timeout=5.0, check_same_thread=False)
        )
        self._operation_context = operation_context
        self._operation_lock = threading.RLock()
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.initialize()

    def close(self) -> None:
        """Close the SQLite connection when this store created and owns it."""
        if self._owns_connection:
            self.conn.close()

    def initialize(self) -> None:
        """Install the mailbox schema within the store's serialized operation context."""
        with self._operation():
            initialize_mailbox_schema(self.conn)

    def configure_account(
        self,
        account_id: str,
        source: str,
        *,
        mailbox_address: str = "",
        endpoint: str = "",
        auth_mode: str = "",
        credential_ref: str = "",
        read_enabled: bool = False,
        write_enabled: bool = False,
    ) -> None:
        """Create or update one mailbox account's connection and capability settings."""
        statement = (
            "INSERT INTO mailbox_accounts("
            "account_id,source,mailbox_address,endpoint,auth_mode,credential_ref,"
            "read_enabled,write_enabled,created_at) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(account_id) DO UPDATE SET "
            "source=excluded.source,mailbox_address=excluded.mailbox_address,"
            "endpoint=excluded.endpoint,auth_mode=excluded.auth_mode,"
            "credential_ref=excluded.credential_ref,read_enabled=excluded.read_enabled,"
            "write_enabled=excluded.write_enabled"
        )
        with self._write() as cur:
            cur.execute(
                statement,
                (
                    account_id,
                    source,
                    mailbox_address,
                    endpoint,
                    auth_mode,
                    credential_ref,
                    int(read_enabled),
                    int(write_enabled),
                    _stamp(),
                ),
            )

    def get_account(self, account_id: str) -> dict[str, str] | None:
        """Return the stored account configuration, if the account exists."""
        row = self.conn.execute("SELECT * FROM mailbox_accounts WHERE account_id=?", (account_id,)).fetchone()
        return None if row is None else dict(row)

    def list_accounts(self) -> list[dict[str, str]]:
        """List stored mailbox account configurations in stable identifier order."""
        return [dict(row) for row in self.conn.execute("SELECT * FROM mailbox_accounts ORDER BY account_id")]

    def set_folders(
        self,
        account_id: str,
        folders: Mapping[str, str],
        *,
        source: str,
        selected: bool = True,
    ) -> None:
        """Add or update folders while preserving their previous selection state."""
        account_statement = "INSERT OR IGNORE INTO mailbox_accounts(account_id,source,created_at) VALUES(?,?,?)"
        folder_statement = (
            "INSERT INTO mailbox_folders("
            "account_id,folder_id,source,display_name,selected,created_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(account_id,folder_id) DO UPDATE SET "
            "source=excluded.source,display_name=excluded.display_name,"
            "selected=MAX(mailbox_folders.selected,excluded.selected)"
        )
        with self._write() as cur:
            cur.execute(account_statement, (account_id, source, _stamp()))
            for folder_id, display_name in folders.items():
                cur.execute(
                    folder_statement,
                    (
                        account_id,
                        str(folder_id),
                        source,
                        str(display_name),
                        int(selected),
                        _stamp(),
                    ),
                )

    def replace_selected_folders(
        self,
        account_id: str,
        folders: Mapping[str, str],
        *,
        source: str,
    ) -> None:
        """Replace the account's sync allowlist while retaining source history."""
        if not folders:
            raise ValueError("at least one selected folder is required")
        account_statement = "INSERT OR IGNORE INTO mailbox_accounts(account_id,source,created_at) VALUES(?,?,?)"
        folder_statement = (
            "INSERT INTO mailbox_folders("
            "account_id,folder_id,source,display_name,selected,created_at) "
            "VALUES(?,?,?,?,1,?) ON CONFLICT(account_id,folder_id) DO UPDATE SET "
            "source=excluded.source,display_name=excluded.display_name,selected=1"
        )
        with self._write() as cur:
            cur.execute(account_statement, (account_id, source, _stamp()))
            cur.execute(
                "UPDATE mailbox_folders SET selected=0 WHERE account_id=?",
                (account_id,),
            )
            for folder_id, display_name in folders.items():
                cur.execute(
                    folder_statement,
                    (
                        account_id,
                        str(folder_id),
                        source,
                        str(display_name),
                        _stamp(),
                    ),
                )

    def list_folders(self, account_id: str) -> list[dict[str, str]]:
        """List the selected synchronization folders for an account."""
        statement = (
            "SELECT account_id,folder_id,source,display_name FROM mailbox_folders "
            "WHERE account_id=? AND selected=1 ORDER BY folder_id"
        )
        return [dict(row) for row in self.conn.execute(statement, (account_id,))]

    @contextmanager
    def _operation(self) -> Iterator[None]:
        context = self._operation_context() if self._operation_context is not None else self._operation_lock
        with context:
            yield

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Cursor]:
        with self._operation():
            cur = self.conn.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                yield cur
            except BaseException:
                self.conn.rollback()
                raise
            else:
                self.conn.commit()

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

    def create_proposal(
        self,
        *,
        account_id: str,
        folder_id: str,
        operation: str,
        target_identity: str,
        target_change_key: str,
        proposer_kind: ActorKind = ActorKind.SERVER,
        target: Mapping[str, Any] | None = None,
        parameters: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> MailboxActionProposal:
        """Create or reuse the durable proposal for an identical mailbox action request."""
        if operation not in _ALLOWED_OPERATIONS:
            raise ValueError(f"unsupported mailbox operation: {operation}")
        if not all((account_id, folder_id, operation, target_identity, target_change_key)):
            raise ValueError("account, folder, operation, target identity, and change key are required")
        created = now or _now()
        exact_target, exact_parameters, digest = _proposal_payload(
            account_id, folder_id, operation, target_identity, target_change_key, target, parameters
        )
        with self._write() as cur:
            existing = cur.execute(
                "SELECT * FROM mailbox_action_proposals WHERE proposal_digest=?",
                (digest,),
            ).fetchone()
            if existing is not None:
                current = self._proposal(existing)
                if current.state in {
                    ProposalState.EXPIRED,
                    ProposalState.FAILED,
                    ProposalState.CONFLICTED,
                }:
                    self._reopen_proposal(cur, current, proposer_kind, created)
                    return self.get_proposal(current.proposal_id, cur=cur)
                return current
            proposal_id = str(uuid4())
            self._insert_proposal(
                cur,
                proposal_id,
                account_id,
                folder_id,
                operation,
                target_identity,
                target_change_key,
                exact_target,
                exact_parameters,
                digest,
                proposer_kind,
                created,
            )
            self._event(
                cur,
                proposal_id,
                "proposed",
                proposer_kind,
                {"operation": operation, "parameter_keys": sorted((parameters or {}).keys())},
                created,
            )
            return self.get_proposal(proposal_id, cur=cur)

    def _reopen_proposal(
        self, cur: sqlite3.Cursor, proposal: MailboxActionProposal, proposer_kind: ActorKind, created: datetime
    ) -> None:
        expires = created + timedelta(hours=24)
        cur.execute(
            "UPDATE mailbox_action_proposals SET state=?,proposer_kind=?,created_at=?,expires_at=?,"
            "approved_at=NULL,execution_deadline=NULL WHERE proposal_id=?",
            (ProposalState.PENDING, proposer_kind, _stamp(created), _stamp(expires), proposal.proposal_id),
        )
        self._event(
            cur,
            proposal.proposal_id,
            "reproposed",
            proposer_kind,
            {"previous_state": proposal.state.value},
            created,
        )

    @staticmethod
    def _insert_proposal(
        cur: sqlite3.Cursor,
        proposal_id: str,
        account_id: str,
        folder_id: str,
        operation: str,
        target_identity: str,
        target_change_key: str,
        exact_target: str,
        exact_parameters: str,
        digest: str,
        proposer_kind: ActorKind,
        created: datetime,
    ) -> None:
        cur.execute(
            "INSERT INTO mailbox_action_proposals(proposal_id,account_id,folder_id,operation,target_identity,"
            "target_change_key,target_json,parameters_json,proposal_digest,state,proposer_kind,created_at,"
            "expires_at,approved_at,execution_deadline) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal_id,
                account_id,
                folder_id,
                operation,
                target_identity,
                target_change_key,
                exact_target,
                exact_parameters,
                digest,
                ProposalState.PENDING,
                proposer_kind,
                _stamp(created),
                _stamp(created + timedelta(hours=24)),
                None,
                None,
            ),
        )

    def approve(
        self,
        proposal_id: str,
        *,
        approver_kind: ActorKind,
        now: datetime | None = None,
    ) -> MailboxActionProposal:
        """Approve a pending proposal only when a different trusted actor confirms it."""
        when = now or _now()
        with self._write() as cur:
            proposal = self.get_proposal(proposal_id, cur=cur)
            if proposal.proposer_kind == approver_kind:
                raise PermissionError("approver kind must differ from proposer kind")
            if proposal.state == ProposalState.PENDING and when >= datetime.fromisoformat(proposal.expires_at):
                return self._transition(
                    cur,
                    proposal,
                    ProposalState.EXPIRED,
                    approver_kind,
                    {},
                    when,
                )
            if proposal.state != ProposalState.PENDING:
                raise RuntimeError("proposal is not pending")
            return self._transition(
                cur,
                proposal,
                ProposalState.APPROVED,
                approver_kind,
                {},
                when,
                approved_at=_stamp(when),
                deadline=_stamp(when + timedelta(minutes=15)),
            )

    approve_proposal = approve

    def reject(
        self,
        proposal_id: str,
        *,
        actor_kind: ActorKind,
        detail: Mapping[str, Any] | None = None,
    ) -> MailboxActionProposal:
        """Reject a pending or approved proposal and record the acting trusted actor."""
        with self._write() as cur:
            proposal = self.get_proposal(proposal_id, cur=cur)
            if proposal.state not in {ProposalState.PENDING, ProposalState.APPROVED}:
                raise RuntimeError("proposal cannot be rejected")
            return self._transition(
                cur,
                proposal,
                ProposalState.REJECTED,
                actor_kind,
                detail or {},
            )

    reject_proposal = reject

    def conflict_unexecuted_proposal(
        self,
        proposal_id: str,
        *,
        detail: Mapping[str, Any],
    ) -> MailboxActionProposal:
        """Conflict an approved intent before any remote execution claim."""
        with self._write() as cur:
            proposal = self.get_proposal(proposal_id, cur=cur)
            if proposal.state not in {ProposalState.APPROVED, ProposalState.RETRYABLE}:
                return proposal
            return self._transition(
                cur,
                proposal,
                ProposalState.CONFLICTED,
                ActorKind.SYSTEM,
                detail,
            )

    def list_proposals(
        self,
        *,
        state: ProposalState | None = None,
    ) -> list[MailboxActionProposal]:
        """List mailbox proposals, optionally restricted to one lifecycle state."""
        query = "SELECT * FROM mailbox_action_proposals"
        args: tuple[Any, ...] = ()
        if state is not None:
            query += " WHERE state=?"
            args = (state,)
        rows = self.conn.execute(query + " ORDER BY created_at,proposal_id", args)
        return [self._proposal(row) for row in rows]

    def claim_execution(
        self,
        proposal_id: str,
        *,
        actor_kind: ActorKind = ActorKind.SYSTEM,
        now: datetime | None = None,
    ) -> MailboxActionClaim | None:
        """Acquire the exclusive lease for an executable proposal, or return no claim."""
        when = now or _now()
        with self._write() as cur:
            proposal = self.get_proposal(proposal_id, cur=cur)
            if proposal.state == ProposalState.PENDING and when >= datetime.fromisoformat(proposal.expires_at):
                self._transition(cur, proposal, ProposalState.EXPIRED, actor_kind, {}, when)
                return None
            deadline_expired = proposal.execution_deadline is not None and when >= datetime.fromisoformat(
                proposal.execution_deadline
            )
            if proposal.state == ProposalState.EXECUTING and deadline_expired:
                self._transition(
                    cur,
                    proposal,
                    ProposalState.UNCERTAIN,
                    actor_kind,
                    {"reason": "execution_claim_expired"},
                    when,
                )
                cur.execute(
                    "UPDATE mailbox_action_attempts SET state=?,completed_at=?,"
                    "detail_json=? WHERE id=(SELECT id FROM mailbox_action_attempts "
                    "WHERE proposal_id=? AND state=? ORDER BY id DESC LIMIT 1)",
                    (
                        ProposalState.UNCERTAIN,
                        _stamp(when),
                        _redacted({"reason": "execution_claim_expired"}),
                        proposal_id,
                        ProposalState.EXECUTING,
                    ),
                )
                return None
            executable_states = {ProposalState.APPROVED, ProposalState.RETRYABLE}
            if proposal.state not in executable_states or deadline_expired:
                if proposal.state in executable_states and deadline_expired:
                    self._transition(
                        cur,
                        proposal,
                        ProposalState.EXPIRED,
                        actor_kind,
                        {},
                        when,
                    )
                return None
            cur.execute(
                "UPDATE mailbox_action_proposals SET state=? WHERE proposal_id=? AND state IN (?,?)",
                (
                    ProposalState.EXECUTING,
                    proposal_id,
                    ProposalState.APPROVED,
                    ProposalState.RETRYABLE,
                ),
            )
            if cur.rowcount != 1:
                return None
            cur.execute(
                "INSERT INTO mailbox_action_attempts(proposal_id,state,started_at,detail_json) VALUES(?,?,?,?)",
                (proposal_id, ProposalState.EXECUTING, _stamp(when), "{}"),
            )
            if cur.lastrowid is None:
                raise RuntimeError("mailbox action attempt insert did not return an ID")
            attempt_id = int(cur.lastrowid)
            execution_deadline = proposal.execution_deadline
            if execution_deadline is None:
                raise RuntimeError("executable mailbox action has no execution deadline")
            self._event(cur, proposal_id, "claimed", actor_kind, {"attempt_id": attempt_id}, when)
            return MailboxActionClaim(
                self.get_proposal(proposal_id, cur=cur),
                attempt_id,
                _stamp(when),
                execution_deadline,
            )

    def complete_execution(
        self,
        claim: MailboxActionClaim,
        outcome: ProposalState,
        *,
        detail: Mapping[str, Any] | None = None,
        actor_kind: ActorKind = ActorKind.SYSTEM,
    ) -> MailboxActionOutcome:
        """Persist a terminal execution outcome for the currently held proposal lease."""
        if outcome not in _OUTCOME_STATES:
            raise ValueError("invalid execution outcome")
        with self._write() as cur:
            proposal = self.get_proposal(claim.proposal.proposal_id, cur=cur)
            if proposal.state != ProposalState.EXECUTING:
                raise RuntimeError("proposal is not executing")
            payload = detail or {}
            self._transition(cur, proposal, outcome, actor_kind, payload)
            cur.execute(
                "UPDATE mailbox_action_attempts SET state=?,completed_at=?,detail_json=? WHERE id=? AND proposal_id=?",
                (
                    outcome,
                    _stamp(),
                    _redacted(payload),
                    claim.attempt_id,
                    proposal.proposal_id,
                ),
            )
            return MailboxActionOutcome(proposal.proposal_id, outcome, dict(payload))

    def append_attempt(
        self,
        proposal_id: str,
        *,
        state: ProposalState,
        detail: Mapping[str, Any] | None = None,
    ) -> int:
        """Record an externally observed attempt without changing proposal state."""
        with self._write() as cur:
            cur.execute(
                "INSERT INTO mailbox_action_attempts(proposal_id,state,started_at,completed_at,detail_json) VALUES(?,?,?,?,?)",
                (proposal_id, state, _stamp(), _stamp(), _redacted(detail)),
            )
            if cur.lastrowid is None:
                raise RuntimeError("mailbox action attempt insert did not return an ID")
            return int(cur.lastrowid)

    def reconcile_uncertain(
        self,
        proposal_id: str,
        *,
        detail: Mapping[str, Any] | None = None,
    ) -> MailboxActionProposal:
        """Mark a correlated uncertain create/send as succeeded without replay."""
        with self._write() as cur:
            proposal = self.get_proposal(proposal_id, cur=cur)
            if proposal.state != ProposalState.UNCERTAIN:
                return proposal
            return self._transition(
                cur,
                proposal,
                ProposalState.SUCCEEDED,
                ActorKind.SYSTEM,
                detail or {},
            )

    def conflict_uncertain_proposal(
        self,
        proposal_id: str,
        *,
        detail: Mapping[str, Any],
    ) -> MailboxActionProposal:
        """Atomically conflict an uncertain proposal with ambiguous remote evidence."""
        with self._write() as cur:
            proposal = self.get_proposal(proposal_id, cur=cur)
            if proposal.state != ProposalState.UNCERTAIN:
                return proposal
            return self._transition(
                cur,
                proposal,
                ProposalState.CONFLICTED,
                ActorKind.SYSTEM,
                detail,
            )

    def get_proposal(
        self,
        proposal_id: str,
        *,
        cur: sqlite3.Cursor | None = None,
    ) -> MailboxActionProposal:
        """Return one stored proposal or raise when its identifier is unknown."""
        row = (
            (cur or self.conn)
            .execute(
                "SELECT * FROM mailbox_action_proposals WHERE proposal_id=?",
                (proposal_id,),
            )
            .fetchone()
        )
        if row is None:
            raise KeyError(proposal_id)
        return self._proposal(row)

    def _transition(
        self,
        cur: sqlite3.Cursor,
        proposal: MailboxActionProposal,
        state: ProposalState,
        actor_kind: ActorKind,
        detail: Mapping[str, Any],
        when: datetime | None = None,
        approved_at: str | None = None,
        deadline: str | None = None,
    ) -> MailboxActionProposal:
        cur.execute(
            "UPDATE mailbox_action_proposals SET "
            "state=?,approved_at=COALESCE(?,approved_at),"
            "execution_deadline=COALESCE(?,execution_deadline) WHERE proposal_id=?",
            (state, approved_at, deadline, proposal.proposal_id),
        )
        self._event(cur, proposal.proposal_id, state, actor_kind, detail, when)
        return self.get_proposal(proposal.proposal_id, cur=cur)

    @staticmethod
    def _proposal(row: sqlite3.Row) -> MailboxActionProposal:
        return MailboxActionProposal(
            row["proposal_id"],
            row["account_id"],
            row["folder_id"],
            row["operation"],
            row["target_identity"],
            row["target_change_key"],
            row["proposal_digest"],
            ProposalState(row["state"]),
            ActorKind(row["proposer_kind"]),
            row["created_at"],
            row["expires_at"],
            row["approved_at"],
            row["execution_deadline"],
            json.loads(row["target_json"]),
            json.loads(row["parameters_json"]),
        )

    @staticmethod
    def _event(
        cur: sqlite3.Cursor,
        proposal_id: str,
        event_type: str | ProposalState,
        actor_kind: ActorKind,
        detail: Mapping[str, Any],
        when: datetime | None = None,
    ) -> None:
        cur.execute(
            "INSERT INTO mailbox_action_events(proposal_id,event_type,actor_kind,detail_json,created_at) VALUES(?,?,?,?,?)",
            (proposal_id, str(event_type), actor_kind, _redacted(detail), _stamp(when)),
        )
