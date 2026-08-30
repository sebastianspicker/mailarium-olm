"""Typed shared state required by focused mailbox application services."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .mailbox_runtime import MailboxRuntimePolicy
from .mailbox_store import MailboxStore


class MailboxServiceContext:
    """Declare the composed boundary supplied by :class:`MailboxService`."""

    store: MailboxStore
    db: Any | None
    policy: MailboxRuntimePolicy
    gateway_factory: Callable[[Mapping[str, Any], MailboxRuntimePolicy], Any]
    embedder_factory: Callable[[], Any] | None
    _persist_record: Callable[..., Any]

    def _remote_account(self, account_id: str, *, require_write: bool) -> dict[str, Any]:
        raise NotImplementedError

    def _selected_folders(self, account_id: str, requested: Iterable[str]) -> tuple[str, ...]:
        raise NotImplementedError

    def _tombstone_remote(self, account_id: str, folder_id: str, remote_item_id: str, change_key: str) -> None:
        raise NotImplementedError
