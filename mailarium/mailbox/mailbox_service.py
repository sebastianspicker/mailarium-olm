"""Public application boundary for proposal-gated EWS mailbox operations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .account_service import MailboxAccountService, build_ews_gateway
from .mailbox_runtime import MailboxRuntimePolicy
from .mailbox_store import MailboxStore
from .proposal_service import MailboxProposalService
from .sync_service import MailboxSynchronizationService

GatewayFactory = Callable[[Mapping[str, Any], MailboxRuntimePolicy], Any]
PersistRecord = Callable[..., Any]


class MailboxService(MailboxAccountService, MailboxSynchronizationService, MailboxProposalService):
    """Compose account, synchronization, and proposal responsibilities at the UI boundary."""

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
        self._owns_store = db is None

    def close(self) -> None:
        """Close a standalone store without closing an injected archive database."""
        if self._owns_store:
            self.store.close()


def _persist_record_default(record: Any, **kwargs: Any) -> Any:
    from mailarium.ingestion.mailbox_ingest import persist_mailbox_record

    return persist_mailbox_record(record, **kwargs)
