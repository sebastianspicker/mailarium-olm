"""Mailbox proposal creation, validation, approval, and rejection policy."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict
from typing import Any

from mailarium.model.mailbox_models import ActorKind, ProposalState

from .account_service import _account_config_fingerprint
from .mailbox_store import MailboxStore
from .service_context import MailboxServiceContext

_OPERATIONS = frozenset({"update_item", "move_item", "copy_item", "delete_item", "create_draft", "send_item"})
_UPDATE_FIELDS = frozenset({"is_read", "categories", "importance", "follow_up", "subject", "body_text", "recipients"})
_MAX_DRAFT_BODY_CHARS = 1_000_000
_MAX_RECIPIENTS = 500
_MAX_CATEGORIES = 100


class MailboxProposalPolicy(MailboxServiceContext):
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


def _proposal_dict(proposal: Any) -> dict[str, Any]:
    value = asdict(proposal)
    value["state"] = proposal.state.value
    value["proposer_kind"] = proposal.proposer_kind.value
    return value
