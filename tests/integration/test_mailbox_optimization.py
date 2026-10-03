"""Synthetic session reuse and durable mailbox page recovery."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from mailarium.archive import open_archive_database
from mailarium.ingestion.mailbox_ingest import persist_mailbox_records
from mailarium.mailbox.ews.errors import EWSValidationError
from mailarium.mailbox.ews.gateway import EWSGateway, EWSItem, EWSItemRef, EWSSyncDelta
from mailarium.mailbox.ews.transport import EWSTransport
from mailarium.mailbox.policy import MailboxRuntimePolicy
from mailarium.mailbox.service import MailboxService
from mailarium.model.mailbox_models import MailboxMessageRecord


def _records(count: int = 4) -> list[MailboxMessageRecord]:
    return [
        MailboxMessageRecord(
            account_id="synthetic",
            folder_id="inbox",
            source="ews",
            source_identity=f"remote-{index}",
            remote_item_id=f"remote-{index}",
            change_key="change-1",
            internet_message_id=f"mail-{index}@example.test",
            subject="Synthetic projection",
            sender_email="sender@example.test",
            to=("recipient@example.test",),
            received_at="2026-09-01T12:00:00Z",
            body_text=f"Synthetic evidence for the delivery plan number {index}.",
        )
        for index in range(count)
    ]


class _Embedder:
    def __init__(self, db_path, *, fail_after: int | None = None):
        self.db_path = db_path
        self.fail_after = fail_after
        self.calls = 0
        self.chunks = {}
        self.collection = self.image_collection = self

    def _write(self, chunks):
        # An independent reader must see retry markers before any vector work.
        with sqlite3.connect(self.db_path) as observer:
            assert observer.execute(
                "SELECT COUNT(*) FROM email_sources WHERE metadata_json LIKE '%projection_pending%'"
            ).fetchone()[0]
        self.calls += 1
        if self.calls == self.fail_after:
            raise RuntimeError("synthetic indexing failure")
        self.chunks.update({chunk.chunk_id: chunk for chunk in chunks})
        return len(chunks)

    def add_chunks(self, chunks, **_kwargs):
        return self._write(chunks)

    def upsert_chunks(self, chunks):
        return self._write(chunks)

    def get_ids_for_uids(self, uids):
        return {key for key, chunk in self.chunks.items() if chunk.uid in uids}

    def delete(self, *, ids):
        for key in ids:
            self.chunks.pop(key, None)

    def forget_existing_ids(self, ids):
        pass

    def checkpoint(self):
        pass


def test_mailbox_page_commits_canonical_and_source_state_in_two_transactions(tmp_path) -> None:
    with open_archive_database(str(tmp_path / "archive.db")) as db:
        store = db.mailbox
        statements = []
        db.conn.set_trace_callback(statements.append)
        results = persist_mailbox_records(_records(12), db=db, store=store.sources)
        db.conn.set_trace_callback(None)
        assert len(results) == 12 and all(result.inserted for result in results)
        assert statements.count("BEGIN IMMEDIATE") == statements.count("COMMIT") == 2
        assert db.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 12
        assert db.conn.execute("SELECT COUNT(*) FROM email_source_identity_history").fetchone()[0] == 12
        assert all("projection_pending" not in row["metadata"] for row in store.sources.list_sources("synthetic", "inbox"))


def test_repeated_source_identities_keep_observation_order_and_finish_projection(tmp_path) -> None:
    with open_archive_database(str(tmp_path / "archive.db")) as db:
        store = db.mailbox
        record = _records(1)[0]
        updated = replace(record, body_text="Later content for this repeated source.", change_key="change-2")
        results = persist_mailbox_records([record, record, updated], db=db, store=store.sources)
        assert [result.inserted for result in results] == [True, False, False]
        assert [result.content_changed for result in results] == [False, False, True]
        assert results[1].metadata_changed is False
        source = store.sources.list_sources("synthetic", "inbox")[0]
        assert "projection_pending" not in source["metadata"]
        assert source["change_key"] == "change-2"
        assert db.queries.get_email_full(results[-1].canonical_email_uid)["body_text"] == updated.body_text


@pytest.mark.parametrize("failure_phase", ["canonical", "index", "finalize"])
def test_mailbox_page_failure_is_replayable_without_losing_retry_markers(tmp_path, monkeypatch, failure_phase) -> None:
    path = tmp_path / "archive.db"
    with open_archive_database(str(path)) as db:
        store = db.mailbox
        records = _records()
        embedder = _Embedder(path, fail_after=2 if failure_phase == "index" else None)
        method = "upsert_source" if failure_phase == "canonical" else "finalize_source_projection"
        original = getattr(store.sources, method)
        calls = 0

        def fail_second(record):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic source failure")
            return original(record)

        if failure_phase != "index":
            monkeypatch.setattr(store.sources, method, fail_second)
        with pytest.raises(RuntimeError, match="synthetic"):
            persist_mailbox_records(records, db=db, store=store.sources, embedder=embedder)
        assert not db.conn.in_transaction
        if failure_phase == "canonical":
            assert db.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 0
            assert not store.sources.list_sources("synthetic", "inbox")
        else:
            sources = store.sources.list_sources("synthetic", "inbox")
            assert len(sources) == 4 and all(row["metadata"]["projection_pending"] for row in sources)
            assert all("projection_hash" not in row["metadata"] for row in sources)
        monkeypatch.setattr(store.sources, method, original)
        embedder.fail_after = None
        results = persist_mailbox_records(records, db=db, store=store.sources, embedder=embedder)
        assert len({result.canonical_email_uid for result in results}) == 4
        assert db.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 4
        assert db.conn.execute("SELECT COUNT(*) FROM email_source_identity_history").fetchone()[0] == 4
        assert all(row["metadata"]["projection_hash"] for row in store.sources.list_sources("synthetic", "inbox"))
        updated = [
            replace(record, body_text="Changed synthetic evidence for a new delivery plan.", change_key="change-2")
            for record in records
        ]
        updates = persist_mailbox_records(updated, db=db, store=store.sources, embedder=embedder)
        assert all(result.content_changed for result in updates)
        assert all(
            db.queries.get_email_full(result.canonical_email_uid)["body_text"] == updated[0].body_text for result in updates
        )


def test_ews_reuses_one_session_only_within_the_bounded_scope() -> None:
    sessions = []

    class Session:
        def __init__(self):
            self.closed = 0

        def post(self, _endpoint, *, data, **_kwargs):
            return SimpleNamespace(status_code=302 if data == b"redirect" else 200, content=b"safe")

        def close(self):
            self.closed += 1

    def factory():
        session = Session()
        sessions.append(session)
        return session

    transport = EWSTransport("https://ews.example.test/EWS", factory)
    with pytest.raises(EWSValidationError, match="redirects"):
        with transport.session():
            assert transport.execute("GetItem", b"one") == b"safe"
            assert transport.execute("GetAttachment", b"two") == b"safe"
            assert len(sessions) == 1 and not sessions[0].closed
            transport.execute("GetItem", b"redirect")
    assert sessions[0].closed == 1
    assert transport.execute("GetItem", b"next operation") == b"safe"
    assert len(sessions) == 2 and sessions[1].closed == 1


def test_sync_reuses_transport_across_pages_and_closes_it_on_completion(tmp_path) -> None:
    sessions = []

    class Session:
        closed = False

        def post(self, *_args, **_kwargs):
            return SimpleNamespace(status_code=200, content=b"synthetic")

        def close(self):
            self.closed = True

    def factory():
        session = Session()
        sessions.append(session)
        return session

    class Gateway(EWSGateway):
        page = 0

        def sync_folder_items(self, folder_id, *, watermark, max_changes):
            self.transport.execute("SyncFolderItems", b"synthetic")
            self.page += 1
            return EWSSyncDelta(
                (EWSItemRef(f"remote-{self.page}", "change-1"),), (), (), f"watermark-{self.page}", self.page < 2, 1
            )

        def get_items(self, item_ids):
            self.transport.execute("GetItem", b"synthetic")
            return tuple(EWSItem(ref.item_id, ref.change_key, "Synthetic", body_text="Synthetic message") for ref in item_ids)

    gateway = Gateway(EWSTransport("https://ews.example.test/EWS", factory))
    with open_archive_database(str(tmp_path / "archive.db")) as db:
        store = db.mailbox
        service = MailboxService(
            store, db=db, policy=MailboxRuntimePolicy(read_enabled=True), gateway_factory=lambda *_args: gateway
        )
        service.configure_account(
            account_id="synthetic",
            mailbox_address="mail@example.test",
            endpoint="https://ews.example.test/EWS",
            auth_mode="basic",
            credential_ref="basic-env:SYNTHETIC_USER:SYNTHETIC_PASSWORD",
            folders=("inbox",),
            read_enabled=True,
        )
        result = service.sync("synthetic", defer_indexing=True)
        assert result["created"] == 2
        assert store.sources.cursor("synthetic", "inbox")[1] == "watermark-2"
        assert len(sessions) == 1 and sessions[0].closed
