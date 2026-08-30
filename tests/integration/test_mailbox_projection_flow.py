"""Mailbox record projection persists durable source-to-archive mappings."""

from __future__ import annotations

from mailarium.archive import open_archive_database
from mailarium.ingestion.mailbox_ingest import persist_mailbox_record
from mailarium.mailbox.mailbox_store import MailboxStore
from mailarium.model.mailbox_models import MailboxMessageRecord


def _record(*, body: str = "Projected local mailbox evidence.", change_key: str = "change-1") -> MailboxMessageRecord:
    return MailboxMessageRecord(
        account_id="synthetic",
        folder_id="inbox",
        source="ews",
        source_identity="remote-1",
        remote_item_id="remote-1",
        change_key=change_key,
        subject="Mailbox projection",
        received_at="2026-08-28T10:00:00Z",
        internet_message_id="<mailbox-projection@example.test>",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=("recipient@example.test",),
        body_text=body,
    )


def test_mailbox_projection_persists_source_completion_and_update_metadata(tmp_path) -> None:
    """The same EWS identity maps to one canonical SQLite message across an update."""
    database = open_archive_database(str(tmp_path / "archive.db"))
    store = MailboxStore(database.conn, operation_context=database.operation)
    try:
        first = persist_mailbox_record(_record(), db=database, store=store)
        source = store.list_sources("synthetic", "inbox")[0]
        assert first.inserted is True
        assert source["canonical_email_uid"] == first.canonical_email_uid
        assert source["metadata"]["projection_hash"]
        assert "projection_pending" not in source["metadata"]

        updated = persist_mailbox_record(
            _record(body="Updated local mailbox evidence.", change_key="change-2"), db=database, store=store
        )
        assert updated.content_changed is True
        assert updated.canonical_email_uid == first.canonical_email_uid
        assert database.get_email_full(first.canonical_email_uid)["body_text"] == "Updated local mailbox evidence."
    finally:
        database.close()
