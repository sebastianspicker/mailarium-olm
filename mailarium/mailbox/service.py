"""Public application boundary for proposal-gated EWS mailbox operations."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any

from .accounts import GatewayFactory, MailboxAccounts
from .execution import ProposalExecutor
from .policy import MailboxRuntimePolicy
from .proposals import ProposalPolicy
from .sync import MailboxSynchronizer

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase, MailboxRepository

PersistRecord = Callable[..., Any]


class MailboxService:
    """Compose accounts, synchronization, proposal policy, and proposal execution at the UI boundary."""

    def __init__(
        self,
        store: MailboxRepository,
        *,
        db: ArchiveDatabase | None = None,
        policy: MailboxRuntimePolicy | None = None,
        gateway_factory: GatewayFactory | None = None,
        embedder_factory: Callable[[], Any] | None = None,
        persist_record: PersistRecord | None = None,
    ) -> None:
        self.store = store
        self.db = db
        self.policy = policy or MailboxRuntimePolicy.from_env()
        self.embedder_factory = embedder_factory
        self._owns_store = db is None
        self._persist_record = persist_record
        self._accounts = MailboxAccounts(store, self.policy, gateway_factory)
        self._synchronizer = MailboxSynchronizer(
            self._accounts,
            store,
            db=db,
            policy=self.policy,
            embedder_factory=embedder_factory,
            persist_records=_persist_records_default if persist_record is None else self._persist_records_individually,
        )
        self._proposal_policy = ProposalPolicy(self._accounts, store)
        self._executor = ProposalExecutor(self._accounts, store)

    def close(self) -> None:
        """Close a standalone store without closing an injected archive database."""
        if self._owns_store:
            self.store.close()

    def _persist_records_individually(self, records: Any, **kwargs: Any) -> list[Any]:
        """Retain the per-record contract for explicitly injected persistence adapters."""
        persist = self._persist_record or _persist_record_default
        return [persist(record, **kwargs) for record in records]

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
        return self._accounts.configure_account(
            account_id=account_id,
            mailbox_address=mailbox_address,
            endpoint=endpoint,
            auth_mode=auth_mode,
            credential_ref=credential_ref,
            folders=folders,
            read_enabled=read_enabled,
            write_enabled=write_enabled,
        )

    def accounts(self) -> list[dict[str, Any]]:
        """Return configured accounts without resolving external credentials."""
        return self._accounts.accounts()

    def account(self, account_id: str) -> dict[str, Any]:
        """Return one account and its selected folders without secret values."""
        return self._accounts.account(account_id)

    def readiness(self, account_id: str) -> dict[str, Any]:
        """Evaluate local readiness without performing network I/O."""
        return self._accounts.readiness(account_id)

    def discover_folders(self, account_id: str, *, select: bool = False) -> dict[str, Any]:
        """Discover physical mail folders and optionally replace the sync allowlist."""
        return self._accounts.discover_folders(account_id, select=select)

    def sync(
        self,
        account_id: str,
        *,
        folders: Iterable[str] = (),
        include_attachment_content: bool = False,
        until_complete: bool = False,
        defer_indexing: bool = False,
    ) -> dict[str, Any]:
        """Synchronize selected folders in one bounded pass or until complete when explicitly requested."""
        return self._synchronizer.sync(
            account_id,
            folders=folders,
            include_attachment_content=include_attachment_content,
            until_complete=until_complete,
            defer_indexing=defer_indexing,
        )

    def triage(self, account_id: str, *, folders: Iterable[str] = (), create_proposals: bool = False) -> list[dict[str, Any]]:
        """Generate deterministic unread-message suggestions from synchronized state."""
        return self._proposal_policy.triage(account_id, folders=folders, create_proposals=create_proposals)

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
        return self._proposal_policy.propose_action(
            account_id=account_id,
            folder_id=folder_id,
            operation=operation,
            target_identity=target_identity,
            target_change_key=target_change_key,
            parameters=parameters,
        )

    def proposals(self, *, state: str | None = None) -> list[dict[str, Any]]:
        """List proposals with decoded immutable payloads."""
        return self._proposal_policy.proposals(state=state)

    def proposal(self, proposal_id: str) -> dict[str, Any]:
        """Return one proposal with decoded immutable target and parameter payloads."""
        return self._proposal_policy.proposal(proposal_id)

    def approve(self, proposal_id: str) -> dict[str, Any]:
        """Approve as the trusted local human surface; no actor input is accepted."""
        return self._proposal_policy.approve(proposal_id)

    def reject(self, proposal_id: str, *, reason: str) -> dict[str, Any]:
        """Reject as the trusted local human surface; no actor input is accepted."""
        return self._proposal_policy.reject(proposal_id, reason=reason)

    def execute(self, proposal_id: str) -> dict[str, Any]:
        """Claim and execute one previously approved immutable proposal."""
        return self._executor.execute(proposal_id)

    def reconcile(self, proposal_id: str) -> dict[str, Any]:
        """Reconcile an uncertain create/send through the durable correlation property."""
        return self._executor.reconcile(proposal_id)


def _persist_record_default(record: Any, **kwargs: Any) -> Any:
    from mailarium.ingestion.mailbox_ingest import persist_mailbox_record

    return persist_mailbox_record(record, **kwargs)


def _persist_records_default(records: Any, **kwargs: Any) -> Any:
    from mailarium.ingestion.mailbox_ingest import persist_mailbox_records

    return persist_mailbox_records(records, **kwargs)
