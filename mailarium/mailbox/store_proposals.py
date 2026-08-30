"""Durable immutable mailbox proposal lifecycle repository."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from mailarium.model.mailbox_models import (
    ActorKind,
    MailboxActionClaim,
    MailboxActionOutcome,
    MailboxActionProposal,
    ProposalState,
)

from .store_connection import MailboxStoreConnection
from .store_schema import _now, _proposal_payload, _redacted, _stamp

_OUTCOME_STATES = {
    ProposalState.SUCCEEDED,
    ProposalState.RETRYABLE,
    ProposalState.CONFLICTED,
    ProposalState.FAILED,
    ProposalState.UNCERTAIN,
}
_ALLOWED_OPERATIONS = frozenset({"update_item", "move_item", "copy_item", "delete_item", "create_draft", "send_item"})


class MailboxProposalRepository(MailboxStoreConnection):
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
