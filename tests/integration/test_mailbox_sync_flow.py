"""Synthetic EWS synchronization flows over the canonical SQLite mailbox state."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mailarium.archive import ArchiveDatabase
from mailarium.mailbox.ews.gateway import EWSItem, EWSItemRef, EWSSyncDelta
from mailarium.mailbox.mailbox_runtime import MailboxRuntimePolicy
from mailarium.mailbox.mailbox_service import MailboxService
from mailarium.mailbox.mailbox_store import MailboxStore


class _Gateway:
    def __init__(self, deltas: list[EWSSyncDelta], items: tuple[EWSItem, ...]) -> None:
        self.deltas = iter(deltas)
        self.items = items
        self.watermarks: list[str | None] = []

    def sync_folder_items(self, folder_id: str, *, watermark: str | None, max_changes: int) -> EWSSyncDelta:
        assert folder_id == "inbox"
        assert max_changes > 0
        self.watermarks.append(watermark)
        return next(self.deltas)

    def get_items(self, item_ids: tuple[EWSItemRef, ...]) -> tuple[EWSItem, ...]:
        assert item_ids
        return self.items


def _service(tmp_path, gateway: _Gateway, persist_record):
    database = ArchiveDatabase(str(tmp_path / "archive.db"))
    store = MailboxStore(database.conn, operation_context=database.operation)
    service = MailboxService(
        store,
        db=database,
        policy=MailboxRuntimePolicy(read_enabled=True),
        gateway_factory=lambda _account, _policy: gateway,
        persist_record=persist_record,
    )
    service.configure_account(
        account_id="synthetic",
        mailbox_address="archive@example.test",
        endpoint="https://ews.example.test/EWS/Exchange.asmx",
        auth_mode="basic",
        credential_ref="basic-env:SYNTHETIC_USER:SYNTHETIC_PASSWORD",
        folders=("inbox",),
        read_enabled=True,
    )
    return database, store, service


def _item() -> EWSItem:
    return EWSItem(
        item_id="remote-1",
        change_key="change-1",
        subject="Synthetic handoff",
        sender="sender@example.test",
        body_text="Synthetic evidence",
        received_at="2026-08-20T10:00:00Z",
        recipients=("recipient@example.test",),
    )


def _created_delta(*, watermark: str = "watermark-1") -> EWSSyncDelta:
    return EWSSyncDelta(
        created=(EWSItemRef("remote-1", "change-1"),),
        updated=(),
        deleted=(),
        watermark=watermark,
        has_more=False,
        raw_change_count=1,
    )


def test_sync_persists_synthetic_ews_records_and_commits_the_cursor(tmp_path) -> None:
    """A successful page persists one source record, reports totals, and closes the full refresh."""
    gateway = _Gateway([_created_delta()], (_item(),))
    holder = {}

    def persist(record, **_kwargs):
        holder["store"].upsert_message(record, stamp_current_generation=True)
        return SimpleNamespace(indexed_chunks=2)

    database, store, service = _service(tmp_path, gateway, persist)
    holder["store"] = store
    try:
        result = service.sync("synthetic", folders=("inbox",))

        assert result["created"] == 1
        assert result["indexed_chunks"] == 2
        assert result["folders"]["inbox"]["complete"] is True
        assert store.cursor("synthetic", "inbox") == (1, "watermark-1")
        assert store.list_sources("synthetic", "inbox")[0]["remote_item_id"] == "remote-1"
    finally:
        service.close()
        database.close()


def test_sync_failure_leaves_the_page_cursor_uncommitted_for_a_retry(tmp_path) -> None:
    """A failed persist step cannot advance the page watermark; the same synthetic page can later succeed."""
    gateway = _Gateway([_created_delta(), _created_delta(watermark="watermark-2")], (_item(),))
    holder = {"fail": True}

    def persist(record, **_kwargs):
        if holder["fail"]:
            raise RuntimeError("synthetic persistence failure")
        holder["store"].upsert_message(record, stamp_current_generation=True)
        return SimpleNamespace(indexed_chunks=1)

    database, store, service = _service(tmp_path, gateway, persist)
    holder["store"] = store
    try:
        with pytest.raises(RuntimeError, match="synthetic persistence failure"):
            service.sync("synthetic", folders=("inbox",))
        assert store.cursor("synthetic", "inbox") == (1, "")
        assert store.list_sources("synthetic", "inbox") == []

        holder["fail"] = False
        result = service.sync("synthetic", folders=("inbox",))

        assert result["created"] == 1
        assert store.cursor("synthetic", "inbox") == (1, "watermark-2")
        assert gateway.watermarks == [None, None]
    finally:
        service.close()
        database.close()
