"""Shared mailbox application service for CLI, MCP, and Streamlit surfaces."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .mailbox_models import ActorKind, MailboxMessageRecord, ProposalState
from .mailbox_runtime import MailboxRuntimePolicy, resolve_external_credentials, validate_account_configuration
from .mailbox_store import MailboxStore

_OPERATIONS = frozenset({"update_item", "move_item", "copy_item", "delete_item", "create_draft", "send_item"})
_UPDATE_FIELDS = frozenset({"is_read", "categories", "importance", "follow_up", "subject", "body_text", "recipients"})
_MAX_DRAFT_BODY_CHARS = 1_000_000
_MAX_RECIPIENTS = 500
_MAX_CATEGORIES = 100
_GET_ITEM_BATCH_SIZE = 20
_CONFLICT_CODES = frozenset({"ErrorChangeKeyRequired", "ErrorInvalidChangeKey", "ErrorIrresolvableConflict", "ErrorItemNotFound"})
_RETRYABLE_CODES = frozenset({"ErrorServerBusy", "ErrorTimeoutExpired", "ErrorMailboxStoreUnavailable"})

GatewayFactory = Callable[[Mapping[str, Any], MailboxRuntimePolicy], Any]
PersistRecord = Callable[..., Any]


@dataclass
class _AttachmentContentBudget:
    remaining_bytes: int

    def consume(self, size: int) -> None:
        if size < 0 or size > self.remaining_bytes:
            raise ValueError("EWS attachment content exceeds the per-sync byte limit.")
        self.remaining_bytes -= size


class MailboxService:
    """Coordinate local state and an injected EWS gateway under fail-closed gates."""

    def __init__(
        self,
        store: MailboxStore,
        *,
        db: Any | None = None,
        policy: MailboxRuntimePolicy | None = None,
        gateway_factory: GatewayFactory | None = None,
        embedder_factory: Callable[[], Any] | None = None,
        persist_record: PersistRecord | None = None,
    ) -> None:
        self.store = store
        self.db = db
        self.policy = policy or MailboxRuntimePolicy.from_env()
        self.gateway_factory = gateway_factory or build_ews_gateway
        self.embedder_factory = embedder_factory
        self._persist_record = persist_record or _persist_record_default
        self._owned_db: Any | None = None

    def close(self) -> None:
        """Close resources created by ``mailbox_service_for_path``."""
        if self._owned_db is not None:
            self._owned_db.close()
            self._owned_db = None
        else:
            self.store.close()

    def configure_account(
        self,
        *,
        account_id: str,
        mailbox_address: str,
        endpoint: str,
        auth_mode: str,
        credential_ref: str,
        folders: Iterable[str],
        read_enabled: bool = False,
        write_enabled: bool = False,
    ) -> dict[str, Any]:
        """Persist validated non-secret account configuration."""
        account = account_id.strip()
        mailbox = mailbox_address.strip()
        if not account or not mailbox:
            raise ValueError("Account ID and mailbox address are required.")
        endpoint, auth_mode, credential_ref, selected = validate_account_configuration(
            endpoint=endpoint,
            auth_mode=auth_mode,
            credential_ref=credential_ref,
            folders=tuple(folders),
        )
        self.store.configure_account(
            account,
            "ews",
            mailbox_address=mailbox,
            endpoint=endpoint,
            auth_mode=auth_mode,
            credential_ref=credential_ref,
            read_enabled=read_enabled,
            write_enabled=write_enabled,
        )
        self.store.replace_selected_folders(
            account,
            {folder: folder for folder in selected},
            source="ews",
        )
        return self.account(account)

    def accounts(self) -> list[dict[str, Any]]:
        """Return configured accounts without resolving external credentials."""
        return [self._public_account(value) for value in self.store.list_accounts()]

    def account(self, account_id: str) -> dict[str, Any]:
        """Return one account and its selected folders without secret values."""
        value = self.store.get_account(account_id)
        if value is None:
            raise KeyError(account_id)
        public = self._public_account(value)
        public["folders"] = self.store.list_folders(account_id)
        return public

    @staticmethod
    def _public_account(value: Mapping[str, Any]) -> dict[str, Any]:
        public = dict(value)
        public["read_enabled"] = bool(public.get("read_enabled"))
        public["write_enabled"] = bool(public.get("write_enabled"))
        return public

    def readiness(self, account_id: str) -> dict[str, Any]:
        """Evaluate local readiness without performing network I/O."""
        account = self.store.get_account(account_id)
        if account is None:
            raise KeyError(account_id)
        configuration_problem = _readiness_configuration_problem(
            account,
            self.store.list_folders(account_id),
        )
        credentials_available = _credential_environment_available(str(account.get("credential_ref") or ""))
        problems = _readiness_problems(
            configuration_problem,
            credentials_available,
            bool(account.get("read_enabled")),
            self.policy.read_enabled,
        )
        return _readiness_result(
            account_id,
            configuration_problem is None,
            credentials_available,
            bool(account.get("read_enabled")),
            bool(account.get("write_enabled")),
            self.policy,
            problems,
        )

    def sync(
        self,
        account_id: str,
        *,
        folders: Iterable[str] = (),
        include_attachment_content: bool = False,
    ) -> dict[str, Any]:
        """Synchronize selected folders and then advance each durable watermark."""
        account = self._remote_account(account_id, require_write=False)
        selected = self._selected_folders(account_id, folders)
        if include_attachment_content and not self.policy.attachment_content_enabled:
            raise PermissionError("Attachment content is disabled; set EWS_ATTACHMENT_CONTENT_ENABLED=true to opt in.")
        if self.db is None:
            raise RuntimeError("Mailbox synchronization requires the canonical EmailDatabase.")

        gateway = self.gateway_factory(account, self.policy)
        embedder = self.embedder_factory() if self.embedder_factory is not None else None
        attachment_budget = (
            _AttachmentContentBudget(self.policy.max_attachment_total_bytes_per_sync) if include_attachment_content else None
        )
        totals = {"created": 0, "updated": 0, "deleted": 0, "indexed_chunks": 0}
        folder_totals: dict[str, dict[str, Any]] = {}
        try:
            for folder_id in selected:
                folder_totals[folder_id] = self._sync_folder(
                    account_id,
                    folder_id,
                    gateway,
                    embedder,
                    include_attachment_content=include_attachment_content,
                    attachment_budget=attachment_budget,
                )
                for name in ("created", "updated", "deleted", "indexed_chunks"):
                    totals[name] += int(folder_totals[folder_id][name])
        finally:
            close = getattr(embedder, "close", None)
            if callable(close):
                close()
        return {"account_id": account_id, **totals, "folders": folder_totals}

    def _sync_folder(
        self,
        account_id: str,
        folder_id: str,
        gateway: Any,
        embedder: Any | None,
        *,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> dict[str, Any]:
        generation, watermark, full_refresh = self._sync_cursor_state(account_id, folder_id)
        result = {"created": 0, "updated": 0, "deleted": 0, "indexed_chunks": 0, "complete": False}
        reset_attempted = False
        while True:
            remaining = self.policy.max_sync_items - _sync_processed_count(result)
            if remaining <= 0:
                return result
            request_watermark = watermark
            delta, generation, watermark, full_refresh, reset_attempted = self._request_sync_delta(
                account_id, folder_id, gateway, generation, watermark, full_refresh, reset_attempted, remaining
            )
            if delta is None:
                continue
            next_watermark = _validate_sync_delta(delta, watermark, remaining)
            items = _synchronized_items(gateway, delta)
            self._persist_sync_items(
                result,
                account_id,
                folder_id,
                items,
                delta,
                gateway,
                embedder,
                generation,
                include_attachment_content,
                attachment_budget,
            )
            self._tombstone_sync_items(result, account_id, folder_id, delta.deleted)
            watermark = next_watermark
            self._commit_sync_page(result, account_id, folder_id, delta, watermark, generation, request_watermark, full_refresh)
            if not delta.has_more:
                result["complete"] = True
                return result
            if _sync_processed_count(result) >= self.policy.max_sync_items:
                return result

    def _sync_cursor_state(self, account_id: str, folder_id: str) -> tuple[int, str, bool]:
        generation, watermark = self.store.get_cursor(account_id, folder_id, scope="items")
        full_refresh = generation == 0 or self.store.cursor_state(account_id, folder_id) == "full_refresh"
        if full_refresh and generation == 0:
            generation = self.store.start_cursor_generation(account_id, folder_id, scope="items", expected_generation=generation)
        return generation, watermark, full_refresh

    def _request_sync_delta(
        self,
        account_id: str,
        folder_id: str,
        gateway: Any,
        generation: int,
        watermark: str,
        full_refresh: bool,
        reset_attempted: bool,
        remaining: int,
    ) -> tuple[Any | None, int, str, bool, bool]:
        try:
            delta = gateway.sync_folder_items(folder_id, watermark=watermark or None, max_changes=min(100, remaining))
        except Exception as exc:
            if reset_attempted or not _is_expired_watermark(exc):
                raise
            generation = self.store.start_cursor_generation(account_id, folder_id, scope="items", expected_generation=generation)
            return None, generation, "", True, True
        return delta, generation, watermark, full_refresh, reset_attempted

    def _persist_sync_items(
        self,
        result: dict[str, Any],
        account_id: str,
        folder_id: str,
        items: tuple[Any, ...],
        delta: Any,
        gateway: Any,
        embedder: Any | None,
        generation: int,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> None:
        created_ids = {value.item_id for value in delta.created}
        for item in items:
            record = self._record_from_ews_item(
                account_id,
                folder_id,
                item,
                gateway,
                generation=generation,
                include_attachment_content=include_attachment_content,
                attachment_budget=attachment_budget,
            )
            persisted = self._persist_record(record, db=self.db, store=self.store, embedder=embedder)
            result["created" if item.item_id in created_ids else "updated"] += 1
            result["indexed_chunks"] += int(getattr(persisted, "indexed_chunks", 0))

    def _tombstone_sync_items(self, result: dict[str, Any], account_id: str, folder_id: str, deleted: Any) -> None:
        for item in deleted:
            self._tombstone_remote(account_id, folder_id, item.item_id, item.change_key or "")
            result["deleted"] += 1

    def _commit_sync_page(
        self,
        result: dict[str, Any],
        account_id: str,
        folder_id: str,
        delta: Any,
        watermark: str,
        generation: int,
        request_watermark: str,
        full_refresh: bool,
    ) -> None:
        if not delta.has_more and full_refresh:
            result["deleted"] += self.store.complete_full_refresh(
                account_id,
                folder_id,
                watermark,
                generation=generation,
                expected_cursor_value=request_watermark,
                scope="items",
            )
            return
        self.store.commit_cursor(
            account_id,
            folder_id,
            watermark,
            scope="items",
            expected_generation=generation,
            expected_cursor_value=request_watermark,
            completed=not delta.has_more,
        )

    def _record_from_ews_item(
        self,
        account_id: str,
        folder_id: str,
        item: Any,
        gateway: Any,
        *,
        generation: int,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> MailboxMessageRecord:
        attachments, contents = self._item_attachments(item, gateway, include_attachment_content, attachment_budget)
        return MailboxMessageRecord(
            account_id=account_id,
            folder_id=folder_id,
            source="ews",
            source_identity=item.item_id,
            remote_item_id=item.item_id,
            change_key=item.change_key or "",
            subject=item.subject,
            received_at=item.received_at or "",
            internet_message_id=item.internet_message_id or "",
            sender_email=item.sender or "",
            to=tuple(item.recipients),
            cc=tuple(item.cc_recipients),
            bcc=tuple(item.bcc_recipients),
            body_text=item.body_text or "",
            is_read=bool(item.is_read),
            importance=item.importance or "Normal",
            categories=tuple(item.categories),
            conversation_id=item.conversation_id or "",
            attachments=tuple(attachments),
            attachment_contents=tuple(contents),
            metadata={
                "sync_generation": generation,
                "is_read": bool(item.is_read),
                "importance": item.importance or "Normal",
                "subject": item.subject,
            },
        )

    def _item_attachments(
        self,
        item: Any,
        gateway: Any,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> tuple[list[dict[str, Any]], list[tuple[str, bytes]]]:
        attachments = [_attachment_metadata(attachment) for attachment in item.attachments]
        file_attachments = tuple(attachment for attachment in item.attachments if attachment.attachment_type == "file")
        if include_attachment_content and len(file_attachments) > self.policy.max_attachments_per_item:
            raise ValueError("EWS item exceeds the configured attachment-count limit.")
        if not include_attachment_content:
            return attachments, []
        return attachments, self._load_attachment_contents(file_attachments, gateway, attachment_budget)

    def _load_attachment_contents(
        self,
        attachments: tuple[Any, ...],
        gateway: Any,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> list[tuple[str, bytes]]:
        if attachment_budget is None:
            raise RuntimeError("Attachment content budget is unavailable.")
        contents: list[tuple[str, bytes]] = []
        item_remaining_bytes = self.policy.max_attachment_total_bytes_per_item
        for attachment in attachments:
            allowed_bytes = _allowed_attachment_bytes(self.policy, attachment, item_remaining_bytes, attachment_budget)
            loaded = gateway.get_attachment(attachment.attachment_id, max_content_bytes=allowed_bytes)
            if loaded.content is not None:
                loaded_size = len(loaded.content)
                if loaded_size > allowed_bytes:
                    raise ValueError("EWS attachment content exceeds an aggregate byte limit.")
                item_remaining_bytes -= loaded_size
                attachment_budget.consume(loaded_size)
                contents.append((loaded.name or attachment.name or "attachment", loaded.content))
        return contents

    def _tombstone_remote(self, account_id: str, folder_id: str, remote_item_id: str, change_key: str) -> None:
        self.store.tombstone_source(
            account_id=account_id,
            folder_id=folder_id,
            source="ews",
            source_identity=remote_item_id,
            change_key=change_key,
        )

    def triage(self, account_id: str, *, folders: Iterable[str] = (), create_proposals: bool = False) -> list[dict[str, Any]]:
        """Generate deterministic unread-message suggestions from synchronized state."""
        selected = self._selected_folders(account_id, folders)
        suggestions: list[dict[str, Any]] = []
        for folder_id in selected:
            for row in self.store.list_sources(account_id, folder_id):
                metadata = row.get("metadata") or {}
                if bool(metadata.get("is_read", True)):
                    continue
                suggestion = {
                    "account_id": account_id,
                    "folder_id": folder_id,
                    "operation": "update_item",
                    "target_identity": row["remote_item_id"],
                    "target_change_key": row["change_key"],
                    "parameters": {"is_read": True},
                    "reason": "message is unread",
                }
                if create_proposals:
                    proposal = self.propose_action(
                        **{
                            key: suggestion[key]
                            for key in (
                                "account_id",
                                "folder_id",
                                "operation",
                                "target_identity",
                                "target_change_key",
                                "parameters",
                            )
                        }
                    )
                    suggestion["proposal_id"] = proposal["proposal_id"]
                suggestions.append(suggestion)
        return suggestions

    def propose_action(
        self,
        *,
        account_id: str,
        folder_id: str,
        operation: str,
        target_identity: str,
        target_change_key: str,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create an idempotent, immutable assistant proposal from allowlisted input."""
        account = self.store.get_account(account_id)
        if account is None:
            raise KeyError(account_id)
        normalized = _validate_operation(operation, parameters)
        folder_id = _validated_proposal_folder(
            self.store,
            account_id,
            folder_id,
            operation,
            target_identity,
            normalized,
        )
        proposal = self.store.create_proposal(
            account_id=account_id,
            folder_id=folder_id,
            operation=operation,
            target_identity=target_identity or ("drafts" if operation == "create_draft" else ""),
            target_change_key=target_change_key or ("new" if operation == "create_draft" else ""),
            proposer_kind=ActorKind.ASSISTANT,
            target={
                "item_id": target_identity,
                "change_key": target_change_key,
                "account_config_fingerprint": _account_config_fingerprint(account),
            },
            parameters=normalized,
        )
        return _proposal_dict(proposal)

    def proposals(self, *, state: str | None = None) -> list[dict[str, Any]]:
        """List proposals with decoded immutable payloads."""
        proposal_state = ProposalState(state) if state else None
        return [_proposal_dict(value) for value in self.store.list_proposals(state=proposal_state)]

    def proposal(self, proposal_id: str) -> dict[str, Any]:
        """Return one proposal with decoded immutable target and parameter payloads."""
        return _proposal_dict(self.store.get_proposal(proposal_id))

    def approve(self, proposal_id: str) -> dict[str, Any]:
        """Approve as the trusted local human surface; no actor input is accepted."""
        return _proposal_dict(self.store.approve_proposal(proposal_id, approver_kind=ActorKind.HUMAN))

    def reject(self, proposal_id: str, *, reason: str) -> dict[str, Any]:
        """Reject as the trusted local human surface; no actor input is accepted."""
        return _proposal_dict(self.store.reject_proposal(proposal_id, actor_kind=ActorKind.HUMAN, detail={"reason": reason}))

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

    def _remote_account(self, account_id: str, *, require_write: bool) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise KeyError(account_id)
        if not self.policy.read_enabled or not bool(account.get("read_enabled")):
            raise PermissionError("EWS reads are disabled by process or account policy.")
        if require_write and (not self.policy.write_enabled or not bool(account.get("write_enabled"))):
            raise PermissionError("EWS writes are disabled by process or account policy.")
        return account

    def _selected_folders(self, account_id: str, requested: Iterable[str]) -> tuple[str, ...]:
        allowed = tuple(str(row["folder_id"]) for row in self.store.list_folders(account_id))
        selected = tuple(dict.fromkeys(value.strip() for value in requested if value.strip())) or allowed
        unknown = sorted(set(selected) - set(allowed))
        if unknown:
            raise ValueError(f"Folders are outside the configured allowlist: {', '.join(unknown)}")
        if not selected:
            raise ValueError("No mailbox folders are configured.")
        return selected

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


def _readiness_configuration_problem(
    account: Mapping[str, Any],
    folders: list[dict[str, str]],
) -> str | None:
    try:
        validate_account_configuration(
            endpoint=str(account.get("endpoint") or ""),
            auth_mode=str(account.get("auth_mode") or ""),
            credential_ref=str(account.get("credential_ref") or ""),
            folders=tuple(folder["folder_id"] for folder in folders),
        )
    except ValueError as exc:
        return str(exc)
    return None


def _readiness_problems(
    configuration_problem: str | None,
    credentials_available: bool,
    account_read_enabled: bool,
    process_read_enabled: bool,
) -> list[str]:
    problems = [configuration_problem] if configuration_problem else []
    if not credentials_available:
        problems.append("Referenced credential environment variables are unavailable.")
    if not account_read_enabled:
        problems.append("Account reads are disabled.")
    if not process_read_enabled:
        problems.append("Process reads are disabled; set EWS_READ_ENABLED=true to opt in.")
    return problems


def _readiness_result(
    account_id: str,
    configuration_valid: bool,
    credentials_available: bool,
    account_read_enabled: bool,
    account_write_enabled: bool,
    policy: MailboxRuntimePolicy,
    problems: list[str],
) -> dict[str, Any]:
    offline_ready = configuration_valid and credentials_available
    read_ready = offline_ready and account_read_enabled and policy.read_enabled
    return {
        "account_id": account_id,
        "offline_ready": offline_ready,
        "read_ready": read_ready,
        "write_ready": read_ready and account_write_enabled and policy.write_enabled,
        "live_verified": False,
        "status": "Offline verified; live EWS writes unverified.",
        "problems": problems,
    }


def _validated_proposal_folder(
    store: MailboxStore,
    account_id: str,
    folder_id: str,
    operation: str,
    target_identity: str,
    parameters: Mapping[str, Any],
) -> str:
    if operation == "create_draft":
        store.set_folders(account_id, {"drafts": "drafts"}, source="ews", selected=False)
        return "drafts"
    _validate_existing_proposal_folder(store, account_id, folder_id, operation, target_identity, parameters)
    return folder_id


def _validate_existing_proposal_folder(
    store: MailboxStore,
    account_id: str,
    folder_id: str,
    operation: str,
    target_identity: str,
    parameters: Mapping[str, Any],
) -> None:
    configured = {str(row["folder_id"]) for row in store.list_folders(account_id)}
    tracked_draft = _tracked_draft_source(store, account_id, folder_id, operation, target_identity)
    if folder_id not in configured and tracked_draft is None:
        raise ValueError("The proposal folder is outside the configured allowlist.")
    destination = str(parameters.get("destination_folder_id") or "")
    if destination and destination not in configured:
        raise ValueError("The destination folder is outside the configured allowlist.")


def _tracked_draft_source(
    store: MailboxStore,
    account_id: str,
    folder_id: str,
    operation: str,
    target_identity: str,
) -> Any | None:
    if operation != "send_item" or folder_id != "drafts":
        return None
    return store.conn.execute(
        "SELECT 1 FROM email_sources WHERE account_id=? AND source='ews' AND folder_id=? AND remote_item_id=? AND is_tombstone=0",
        (account_id, folder_id, target_identity),
    ).fetchone()


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


def _persist_record_default(record: MailboxMessageRecord, **kwargs: Any) -> Any:
    from .mailbox_ingest import persist_mailbox_record

    return persist_mailbox_record(record, **kwargs)


def _account_config_fingerprint(account: Mapping[str, Any]) -> str:
    """Bind an action intent to the non-secret remote account configuration."""
    payload = {
        "source": str(account.get("source") or "").strip().casefold(),
        "mailbox_address": str(account.get("mailbox_address") or "").strip().casefold(),
        "endpoint": str(account.get("endpoint") or "").strip(),
        "auth_mode": str(account.get("auth_mode") or "").strip().casefold(),
        "credential_ref": str(account.get("credential_ref") or "").strip(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_ews_gateway(account: Mapping[str, Any], policy: MailboxRuntimePolicy) -> Any:
    """Build the on-premises HTTPS EWS gateway from external credentials."""
    from mailarium.ews import EWSGateway, EWSHTTPSSession, EWSTransport
    from mailarium.ews.transport import basic_authorization

    username, password = resolve_external_credentials(str(account.get("credential_ref") or ""))
    if account.get("auth_mode") == "ntlm":
        session = EWSHTTPSSession(ntlm_username=username, ntlm_password=password)
    else:
        session = EWSHTTPSSession(authorization=basic_authorization(username, password))
    session.preflight()
    return EWSGateway(
        EWSTransport(
            str(account.get("endpoint") or ""),
            session,
            timeout_seconds=policy.request_timeout_seconds,
            max_response_bytes=max(policy.max_attachment_bytes * 2, 10_000_000),
        ),
        mailbox_address=str(account.get("mailbox_address") or ""),
    )


def mailbox_service_for_path(
    sqlite_path: str,
    *,
    vector_index_path: str | None = None,
    policy: MailboxRuntimePolicy | None = None,
) -> MailboxService:
    """Create the shared service on the root archive database."""
    from .email_db import EmailDatabase
    from .embedder import EmailEmbedder

    db = EmailDatabase(sqlite_path)
    service = MailboxService(
        MailboxStore(db.conn, operation_context=db.operation),
        db=db,
        policy=policy,
        embedder_factory=lambda: EmailEmbedder(vector_index_path=vector_index_path, sqlite_path=sqlite_path),
    )
    service._owned_db = db
    return service


def _credential_environment_available(credential_ref: str) -> bool:
    parts = credential_ref.split(":")
    return len(parts) == 3 and parts[0] == "basic-env" and all(os.getenv(name) for name in parts[1:])


def _sync_processed_count(result: Mapping[str, Any]) -> int:
    return sum(int(result[name]) for name in ("created", "updated", "deleted"))


def _validate_sync_delta(delta: Any, watermark: str, remaining: int) -> str:
    returned_changes = len(delta.created) + len(delta.updated) + len(delta.deleted)
    raw_change_count = getattr(delta, "raw_change_count", None)
    if raw_change_count is not None and returned_changes != int(raw_change_count):
        raise RuntimeError("EWS sync response contained unsupported or unparsed changes.")
    if returned_changes > min(100, remaining):
        raise RuntimeError("EWS sync response exceeded the requested change limit.")
    next_watermark = delta.watermark or watermark
    if delta.has_more and next_watermark == watermark:
        raise RuntimeError("EWS sync watermark did not advance for a partial page.")
    return next_watermark


def _synchronized_items(gateway: Any, delta: Any) -> tuple[Any, ...]:
    changed_refs = (*delta.created, *delta.updated)
    items = tuple(
        item
        for start in range(0, len(changed_refs), _GET_ITEM_BATCH_SIZE)
        for item in gateway.get_items(changed_refs[start : start + _GET_ITEM_BATCH_SIZE])
    )
    if len(items) != len(changed_refs):
        raise RuntimeError("EWS GetItem did not return every synchronized item.")
    return items


def _attachment_metadata(attachment: Any) -> dict[str, Any]:
    return {
        "remote_attachment_id": attachment.attachment_id,
        "name": attachment.name or "",
        "mime_type": attachment.content_type or "",
        "size": int(attachment.size or 0),
        "is_inline": bool(attachment.is_inline),
        "attachment_type": attachment.attachment_type,
    }


def _allowed_attachment_bytes(
    policy: MailboxRuntimePolicy,
    attachment: Any,
    item_remaining_bytes: int,
    attachment_budget: _AttachmentContentBudget,
) -> int:
    declared_size = max(0, int(attachment.size or 0))
    if declared_size > policy.max_attachment_bytes:
        raise ValueError("EWS attachment exceeds the configured content limit.")
    allowed_bytes = min(policy.max_attachment_bytes, item_remaining_bytes, attachment_budget.remaining_bytes)
    if allowed_bytes < 1 or declared_size > allowed_bytes:
        raise ValueError("EWS attachment content exceeds an aggregate byte limit.")
    return allowed_bytes


def _validate_operation(operation: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if operation not in _OPERATIONS:
        raise ValueError(f"Unsupported mailbox operation: {operation}")
    values = dict(parameters)
    if operation == "update_item":
        return _validated_update_parameters(values)
    elif operation in {"move_item", "copy_item"}:
        if set(values) != {"destination_folder_id"} or not str(values["destination_folder_id"]).strip():
            raise ValueError(f"{operation} requires destination_folder_id only.")
    elif operation == "delete_item" and values:
        raise ValueError("delete_item accepts no parameters and always moves to Deleted Items.")
    elif operation == "create_draft":
        if set(values) != {"subject", "body_text", "recipients"}:
            raise ValueError("create_draft requires subject, body_text, and recipients.")
        values["subject"] = _validated_text(values["subject"], name="subject")
        values["body_text"] = _validated_text(values["body_text"], name="body_text")
        values["recipients"] = _validated_string_list(
            values["recipients"],
            name="recipients",
            maximum=_MAX_RECIPIENTS,
        )
    elif operation == "send_item" and values:
        raise ValueError("send_item accepts no parameters.")
    return values


def _validated_update_parameters(values: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(values) - _UPDATE_FIELDS)
    if unknown or not values:
        raise ValueError("update_item requires only supported update fields.")
    for name in ("is_read", "follow_up"):
        if name in values and not isinstance(values[name], bool):
            raise ValueError(f"{name} must be a boolean.")
    if "importance" in values and values["importance"] not in {"Low", "Normal", "High"}:
        raise ValueError("importance must be Low, Normal, or High.")
    for name, maximum, allow_empty in (("categories", _MAX_CATEGORIES, True), ("recipients", _MAX_RECIPIENTS, False)):
        if name in values:
            values[name] = _validated_string_list(values[name], name=name, maximum=maximum, allow_empty=allow_empty)
    for name in ("subject", "body_text"):
        if name in values:
            values[name] = _validated_text(values[name], name=name)
    return values


def _validated_text(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    maximum = 998 if name == "subject" else _MAX_DRAFT_BODY_CHARS
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds the supported size limit.")
    return value


def _validated_string_list(
    value: Any,
    *,
    name: str,
    maximum: int,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        raise ValueError(f"{name} must be a list of strings.")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds the supported item limit.")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must contain only non-empty strings.")
    return list(value)


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
        from mailarium.ews.errors import (
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


def _is_expired_watermark(exc: Exception) -> bool:
    return getattr(exc, "code", "") in {"ErrorInvalidSyncStateData", "ErrorSyncStateNotFound"}


def _proposal_dict(proposal: Any) -> dict[str, Any]:
    value = asdict(proposal)
    value["state"] = proposal.state.value
    value["proposer_kind"] = proposal.proposer_kind.value
    return value


def _outcome_dict(outcome: Any) -> dict[str, Any]:
    return {"proposal_id": outcome.proposal_id, "state": outcome.state.value, "detail": dict(outcome.detail)}
