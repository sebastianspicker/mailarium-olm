"""Mailbox proposal execution, result projection, and reconciliation."""

from __future__ import annotations

from typing import Any

from mailarium.model.mailbox_models import MailboxMessageRecord, ProposalState

from .account_service import _account_config_fingerprint
from .service_context import MailboxServiceContext

_CONFLICT_CODES = frozenset({"ErrorChangeKeyRequired", "ErrorInvalidChangeKey", "ErrorIrresolvableConflict", "ErrorItemNotFound"})
_RETRYABLE_CODES = frozenset({"ErrorServerBusy", "ErrorTimeoutExpired", "ErrorMailboxStoreUnavailable"})


class MailboxProposalExecution(MailboxServiceContext):
    def execute(self, proposal_id: str) -> dict[str, Any]:
        """Claim and execute one previously approved immutable proposal."""
        proposal = self.store.get_proposal(proposal_id)
        if proposal.state not in {ProposalState.APPROVED, ProposalState.RETRYABLE}:
            self.store.claim_execution(proposal_id)
            current = self.store.get_proposal(proposal_id)
            return {
                "proposal_id": proposal_id,
                "state": current.state.value,
                "executed": False,
            }
        account = self._remote_account(proposal.account_id, require_write=True)
        expected_fingerprint = str(proposal.target.get("account_config_fingerprint") or "")
        if not expected_fingerprint or expected_fingerprint != _account_config_fingerprint(account):
            conflicted = self.store.conflict_unexecuted_proposal(
                proposal_id,
                detail={"reason": "account_configuration_changed"},
            )
            return {
                "proposal_id": proposal_id,
                "state": conflicted.state.value,
                "executed": False,
                "detail": {"reason": "account_configuration_changed"},
            }
        # The default factory validates local credentials and constructs a
        # transport without network I/O. Complete this preflight before the
        # durable execution claim so local setup failures remain retryable.
        gateway = self.gateway_factory(account, self.policy)
        claim = self.store.claim_execution(proposal_id)
        if claim is None:
            current = self.store.get_proposal(proposal_id)
            return {"proposal_id": proposal_id, "state": current.state.value, "executed": False}
        try:
            source = self._current_source(claim.proposal)
            if source is None and claim.proposal.operation != "create_draft":
                outcome = self.store.complete_execution(
                    claim,
                    ProposalState.CONFLICTED,
                    detail={"reason": "source_item_missing"},
                )
                return _outcome_dict(outcome)
            if source is not None and str(source["change_key"] or "") != claim.proposal.target_change_key:
                outcome = self.store.complete_execution(
                    claim,
                    ProposalState.CONFLICTED,
                    detail={"reason": "stale_change_key"},
                )
                return _outcome_dict(outcome)
            result = _execute_gateway_operation(gateway, claim.proposal)
            self._record_successful_mutation(claim.proposal, source, result)
            outcome = self.store.complete_execution(
                claim,
                ProposalState.SUCCEEDED,
                detail={"operation": result.operation, "item_count": len(result.items)},
            )
        except Exception as exc:
            state, detail = _classify_execution_error(exc, operation=claim.proposal.operation)
            outcome = self.store.complete_execution(claim, state, detail=detail)
        return _outcome_dict(outcome)

    def reconcile(self, proposal_id: str) -> dict[str, Any]:
        """Reconcile an uncertain create/send through the durable correlation property."""
        proposal = self.store.get_proposal(proposal_id)
        if proposal.state != ProposalState.UNCERTAIN:
            return {"proposal_id": proposal_id, "state": proposal.state.value, "reconciled": False}
        if proposal.operation not in {"create_draft", "send_item"}:
            return _unreconciled_result(proposal)
        account = self._remote_account(proposal.account_id, require_write=True)
        gateway = self.gateway_factory(account, self.policy)
        folders = ("sentitems",) if proposal.operation == "send_item" else ("drafts",)
        matches = _correlated_items(gateway, folders, proposal_id)
        unresolved = self._unresolved_reconciliation(proposal, matches, folders)
        if unresolved is not None:
            return unresolved
        self._record_reconciled_match(proposal, matches[0])
        reconciled = self.store.reconcile_uncertain(
            proposal_id,
            detail={"matched": len(matches), "folder_count": len(folders)},
        )
        return {
            "proposal_id": proposal_id,
            "state": reconciled.state.value,
            "reconciled": reconciled.state == ProposalState.SUCCEEDED,
        }

    def _current_source(self, proposal: Any) -> Any | None:
        return self.store.conn.execute(
            "SELECT * FROM email_sources WHERE account_id=? AND folder_id=? "
            "AND source='ews' AND remote_item_id=? AND is_tombstone=0",
            (proposal.account_id, proposal.folder_id, proposal.target_identity),
        ).fetchone()

    def _record_successful_mutation(self, proposal: Any, source: Any | None, result: Any) -> None:
        _require_result_identity(proposal, result)
        if proposal.operation == "create_draft":
            self._record_draft_source(proposal, result.items[0])
            return
        if source is None:
            return
        self._record_existing_mutation(proposal, source, result)

    def _record_draft_source(self, proposal: Any, item: Any) -> None:
        self.store.set_folders(
            proposal.account_id,
            {"drafts": "drafts"},
            source="ews",
            selected=False,
        )
        self.store.upsert_source(
            MailboxMessageRecord(
                account_id=proposal.account_id,
                folder_id="drafts",
                source="ews",
                source_identity=item.item_id,
                remote_item_id=item.item_id,
                change_key=item.change_key or "",
                metadata={"proposal_id": proposal.proposal_id},
            ),
            stamp_current_generation=True,
        )

    def _record_existing_mutation(self, proposal: Any, source: Any, result: Any) -> None:
        if proposal.operation == "delete_item":
            self._tombstone_remote(
                proposal.account_id,
                str(source["folder_id"]),
                str(source["remote_item_id"]),
                str(source["change_key"]),
            )
            return
        if proposal.operation == "send_item" and not result.items:
            self._tombstone_remote(
                proposal.account_id,
                str(source["folder_id"]),
                str(source["remote_item_id"]),
                str(source["change_key"]),
            )
            return
        if not result.items:
            return
        returned = result.items[0]
        default_destination = "sentitems" if proposal.operation == "send_item" else source["folder_id"]
        destination = str(proposal.parameters.get("destination_folder_id") or default_destination)
        self.store.record_remote_identity_change(
            account_id=proposal.account_id,
            source="ews",
            old_remote_item_id=str(source["remote_item_id"]),
            new_remote_item_id=returned.item_id,
            new_change_key=returned.change_key or str(source["change_key"]),
            destination_folder_id=destination,
            copy=proposal.operation == "copy_item",
        )

    def _unresolved_reconciliation(
        self,
        proposal: Any,
        matches: tuple[Any, ...],
        folders: tuple[str, ...],
    ) -> dict[str, Any] | None:
        if not matches:
            return _unreconciled_result(proposal)
        if len(matches) == 1:
            return None
        detail = {
            "reason": "duplicate_correlation_matches",
            "matched": len(matches),
            "folder_count": len(folders),
        }
        conflicted = self.store.conflict_uncertain_proposal(proposal.proposal_id, detail=detail)
        return {
            "proposal_id": proposal.proposal_id,
            "state": conflicted.state.value,
            "reconciled": conflicted.state == ProposalState.SUCCEEDED,
            "detail": detail,
        }

    def _record_reconciled_match(self, proposal: Any, matched: Any) -> None:
        if proposal.operation == "create_draft":
            existing = self.store.conn.execute(
                "SELECT 1 FROM email_sources WHERE account_id=? AND source='ews' AND remote_item_id=?",
                (proposal.account_id, matched.item_id),
            ).fetchone()
            if existing is None:
                self._record_draft_source(proposal, matched)
            return
        source = self._current_source(proposal)
        if source is not None:
            self._tombstone_remote(
                proposal.account_id,
                str(source["folder_id"]),
                str(source["remote_item_id"]),
                str(source["change_key"] or ""),
            )


def _correlated_items(gateway: Any, folders: tuple[str, ...], proposal_id: str) -> tuple[Any, ...]:
    matches_by_id = {
        item.item_id: item
        for folder in folders
        for item in gateway.find_items_by_proposal_id(folder, proposal_id)
        if item.item_id
    }
    return tuple(matches_by_id.values())


def _unreconciled_result(proposal: Any) -> dict[str, Any]:
    return {"proposal_id": proposal.proposal_id, "state": proposal.state.value, "reconciled": False}


def _require_result_identity(proposal: Any, result: Any) -> None:
    result_required = proposal.operation in {
        "update_item",
        "move_item",
        "copy_item",
        "create_draft",
    }
    if result_required and not result.items:
        raise RuntimeError("EWS mutation response omitted the resulting item identity.")


def _execute_gateway_operation(gateway: Any, proposal: Any) -> Any:
    parameters = dict(proposal.parameters)
    if proposal.operation == "update_item":
        return gateway.update_item(proposal.target_identity, proposal.target_change_key, **parameters)
    if proposal.operation == "move_item":
        return gateway.move_item(
            proposal.target_identity,
            proposal.target_change_key,
            parameters["destination_folder_id"],
        )
    if proposal.operation == "copy_item":
        return gateway.copy_item(
            proposal.target_identity,
            proposal.target_change_key,
            parameters["destination_folder_id"],
        )
    if proposal.operation == "delete_item":
        return gateway.delete_to_deleted_items(proposal.target_identity, proposal.target_change_key)
    if proposal.operation == "create_draft":
        return gateway.create_text_draft(
            parameters["subject"],
            parameters["body_text"],
            parameters["recipients"],
            proposal_id=proposal.proposal_id,
        )
    if proposal.operation == "send_item":
        return gateway.send_existing_draft(
            proposal.target_identity,
            proposal.target_change_key,
            proposal_id=proposal.proposal_id,
        )
    raise AssertionError("validated operation is not executable")


def _classify_execution_error(exc: Exception, *, operation: str) -> tuple[ProposalState, dict[str, Any]]:
    try:
        from mailarium.mailbox.ews.errors import (
            EWSAuthenticationError,
            EWSConfigurationError,
            EWSFaultError,
            EWSValidationError,
        )
    except ImportError:
        return ProposalState.FAILED, {"reason": "ews_extra_unavailable"}
    if isinstance(exc, EWSFaultError):
        if exc.code in _CONFLICT_CODES:
            return ProposalState.CONFLICTED, {"reason": "ews_conflict", "code": exc.code}
        if exc.code in _RETRYABLE_CODES:
            return ProposalState.RETRYABLE, {"reason": "ews_transient", "code": exc.code}
        http_status = getattr(exc, "http_status", None)
        if (
            exc.code in {"MalformedResponse", "SOAPFault"}
            or http_status == 429
            or (isinstance(http_status, int) and http_status >= 500)
        ):
            detail: dict[str, Any] = {
                "reason": "transport_outcome_unknown",
                "operation": operation,
                "code": exc.code,
            }
            if http_status is not None:
                detail["http_status"] = http_status
            return ProposalState.UNCERTAIN, detail
        return ProposalState.FAILED, {"reason": "ews_fault", "code": exc.code}
    if isinstance(exc, (EWSAuthenticationError, EWSConfigurationError)):
        return ProposalState.RETRYABLE, {"reason": type(exc).__name__}
    if isinstance(exc, EWSValidationError):
        return ProposalState.FAILED, {"reason": type(exc).__name__}
    return ProposalState.UNCERTAIN, {
        "reason": "transport_outcome_unknown",
        "operation": operation,
    }


def _outcome_dict(outcome: Any) -> dict[str, Any]:
    return {"proposal_id": outcome.proposal_id, "state": outcome.state.value, "detail": dict(outcome.detail)}
