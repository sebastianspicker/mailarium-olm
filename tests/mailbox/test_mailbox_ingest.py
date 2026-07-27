"""Focused source-neutral ingestion tests that need no model runtime."""

from __future__ import annotations

import hashlib
import unittest

from mailarium.email_db import EmailDatabase
from mailarium.mailbox_ingest import _mailbox_chunks, mailbox_record_to_email, persist_mailbox_record
from mailarium.mailbox_models import MailboxMessageRecord
from mailarium.mailbox_store import MailboxStore
from mailarium.mailbox_visibility import active_mailbox_uids
from mailarium.parse_olm import Email


class _DeleteRecorder:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, *, ids) -> None:
        self.deleted.extend(ids)


class _RecordingEmbedder:
    def __init__(self, *, existing_ids=(), fail_add: bool = False) -> None:
        self.existing_ids = set(existing_ids)
        self.fail_add = fail_add
        self.add_calls = 0
        self.upserted_ids: list[str] = []
        self.upserted_metadata: list[dict] = []
        self.collection = _DeleteRecorder()
        self.image_collection = _DeleteRecorder()

    def add_chunks(self, chunks, *, show_progress: bool) -> int:
        self.add_calls += 1
        if self.fail_add:
            self.fail_add = False
            raise RuntimeError("transient vector failure")
        return len(chunks)

    def upsert_chunks(self, chunks) -> int:
        self.upserted_ids = [chunk.chunk_id for chunk in chunks]
        self.upserted_metadata = [dict(chunk.metadata) for chunk in chunks]
        return len(chunks)

    def get_existing_ids(self, *, refresh: bool):
        return self.existing_ids

    def checkpoint(self) -> None:
        return None


class MailboxIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = EmailDatabase(":memory:")
        self.store = MailboxStore(self.db.conn)
        self.store.configure_account("account", "ews")
        self.store.set_folders("account", {"inbox": "Inbox"}, source="ews")

    def tearDown(self) -> None:
        self.db.close()

    def record(self, **changes) -> MailboxMessageRecord:
        values = {
            "account_id": "account",
            "folder_id": "inbox",
            "source": "ews",
            "source_identity": "item-1",
            "remote_item_id": "item-1",
            "change_key": "ck-1",
            "internet_message_id": "<message@example.test>",
            "subject": "Subject",
            "received_at": "2026-07-17T10:00:00+00:00",
            "sender_email": "sender@example.test",
            "to": ("recipient@example.test",),
            "body_text": "Original body",
        }
        values.update(changes)
        return MailboxMessageRecord(**values)

    def local_email(self, **changes) -> Email:
        values = {
            "message_id": "<message@example.test>",
            "subject": "Subject",
            "sender_name": "",
            "sender_email": "sender@example.test",
            "to": ["recipient@example.test"],
            "cc": [],
            "bcc": [],
            "date": "2026-07-17T10:00:00+00:00",
            "body_text": "Original body",
            "body_html": "",
            "folder": "local",
            "has_attachments": False,
            "raw_source": "olm",
        }
        values.update(changes)
        return Email(**values)

    def test_insert_then_content_update_reuses_canonical_uid(self) -> None:
        first = persist_mailbox_record(self.record(), db=self.db, store=self.store)
        second = persist_mailbox_record(
            self.record(body_text="Updated body", change_key="ck-2"),
            db=self.db,
            store=self.store,
        )

        self.assertTrue(first.inserted)
        self.assertTrue(second.content_changed)
        self.assertEqual(first.canonical_email_uid, second.canonical_email_uid)
        row = self.db.conn.execute("SELECT body_text FROM emails WHERE uid=?", (first.canonical_email_uid,)).fetchone()
        self.assertEqual("Updated body", row[0])
        source = self.store.conn.execute(
            "SELECT canonical_preexisting FROM email_sources WHERE remote_item_id='item-1'"
        ).fetchone()
        self.assertEqual(0, source[0])

    def test_conflicting_message_id_uses_source_specific_uid(self) -> None:
        first = persist_mailbox_record(self.record(), db=self.db, store=self.store)
        self.store.set_folders("other", {"inbox": "Inbox"}, source="ews")
        conflicting = self.record(
            account_id="other",
            source_identity="other-item",
            remote_item_id="other-item",
            sender_email="different@example.test",
        )
        second = persist_mailbox_record(conflicting, db=self.db, store=self.store)

        self.assertNotEqual(first.canonical_email_uid, second.canonical_email_uid)
        self.assertTrue(second.possible_duplicate)

    def test_preexisting_archive_email_remains_visible_after_ews_tombstone(self) -> None:
        local = self.local_email()
        self.assertTrue(self.db.insert_email(local))
        linked = persist_mailbox_record(self.record(), db=self.db, store=self.store)
        self.assertEqual(local.uid, linked.canonical_email_uid)
        source = self.store.conn.execute(
            "SELECT canonical_preexisting FROM email_sources WHERE remote_item_id='item-1'"
        ).fetchone()
        self.assertEqual(1, source[0])

        self.store.tombstone_source(
            account_id="account",
            folder_id="inbox",
            source="ews",
            source_identity="item-1",
            change_key="ck-2",
        )

        self.assertEqual({local.uid}, active_mailbox_uids(self.db.conn, (local.uid,)))

    def test_opted_in_attachment_content_uses_stable_identity_and_text_chunks(self) -> None:
        attachment = {
            "remote_attachment_id": "ews-att-1",
            "name": "notes.txt",
            "mime_type": "text/plain",
            "size": 11,
        }
        metadata_only = mailbox_record_to_email(
            self.record(attachments=(attachment,)),
            "canonical",
        )
        with_content = mailbox_record_to_email(
            self.record(
                attachments=(attachment,),
                attachment_contents=(("notes.txt", b"hello world"),),
            ),
            "canonical",
        )

        self.assertEqual(
            metadata_only.attachments[0]["attachment_id"],
            with_content.attachments[0]["attachment_id"],
        )
        self.assertEqual("hello world", with_content.attachments[0]["extracted_text"])
        chunks, _preserved = _mailbox_chunks(with_content)
        self.assertTrue(any("__att_" in chunk.chunk_id for chunk in chunks))

    def test_vector_failure_leaves_projection_retryable(self) -> None:
        embedder = _RecordingEmbedder(fail_add=True)

        with self.assertRaisesRegex(RuntimeError, "transient vector failure"):
            persist_mailbox_record(
                self.record(),
                db=self.db,
                store=self.store,
                embedder=embedder,
            )

        self.assertIsNone(self.store.conn.execute("SELECT 1 FROM email_sources WHERE remote_item_id='item-1'").fetchone())
        replay = persist_mailbox_record(
            self.record(),
            db=self.db,
            store=self.store,
            embedder=embedder,
        )
        self.assertTrue(replay.metadata_changed)
        self.assertTrue(embedder.upserted_ids)
        self.assertIsNotNone(self.store.conn.execute("SELECT 1 FROM email_sources WHERE remote_item_id='item-1'").fetchone())

    def test_metadata_only_ews_refresh_preserves_richer_canonical_attachment(self) -> None:
        content = b"canonical attachment evidence"
        content_sha256 = hashlib.sha256(content).hexdigest()
        attachment = {
            "name": "notes.txt",
            "mime_type": "text/plain",
            "size": len(content),
            "attachment_id": f"sha256:{content_sha256}",
            "content_sha256": content_sha256,
            "extracted_text": content.decode(),
            "normalized_text": content.decode(),
            "text_normalization_version": 1,
            "extraction_state": "text_extracted",
            "evidence_strength": "strong_text",
        }
        local = self.local_email(
            has_attachments=True,
            attachment_names=["notes.txt"],
            attachments=[attachment],
        )
        old_attachment_chunks = {chunk.chunk_id for chunk in _mailbox_chunks(local)[0] if "__att_" in chunk.chunk_id}
        self.assertTrue(self.db.insert_email(local))
        embedder = _RecordingEmbedder(existing_ids=old_attachment_chunks)

        result = persist_mailbox_record(
            self.record(
                attachments=(
                    {
                        "remote_attachment_id": "ews-att-1",
                        "name": "notes.txt",
                        "mime_type": "text/plain",
                        "size": len(content),
                    },
                )
            ),
            db=self.db,
            store=self.store,
            embedder=embedder,
        )

        self.assertTrue(result.metadata_changed)
        stored = self.db.attachments_for_email(local.uid)[0]
        self.assertEqual(f"sha256:{content_sha256}", stored["attachment_id"])
        self.assertEqual(content.decode(), stored["extracted_text"])
        self.assertLessEqual(old_attachment_chunks, set(embedder.upserted_ids))
        self.assertEqual([], embedder.collection.deleted)

    def test_copied_message_projects_both_active_source_folders(self) -> None:
        original = persist_mailbox_record(self.record(), db=self.db, store=self.store)
        self.store.set_folders("account", {"archive": "Archive"}, source="ews")
        self.store.record_remote_identity_change(
            account_id="account",
            source="ews",
            old_remote_item_id="item-1",
            new_remote_item_id="item-copy",
            new_change_key="copy-ck",
            destination_folder_id="archive",
            copy=True,
        )
        embedder = _RecordingEmbedder()

        copied = persist_mailbox_record(
            self.record(
                folder_id="archive",
                source_identity="item-copy",
                remote_item_id="item-copy",
                change_key="copy-ck",
            ),
            db=self.db,
            store=self.store,
            embedder=embedder,
        )

        self.assertEqual(original.canonical_email_uid, copied.canonical_email_uid)
        self.assertTrue(embedder.upserted_metadata)
        self.assertTrue(all(metadata["source_folders"] == ["archive", "inbox"] for metadata in embedder.upserted_metadata))
        folder = self.db.conn.execute(
            "SELECT folder FROM emails WHERE uid=?",
            (original.canonical_email_uid,),
        ).fetchone()[0]
        self.assertEqual("archive", folder)


if __name__ == "__main__":
    unittest.main()
