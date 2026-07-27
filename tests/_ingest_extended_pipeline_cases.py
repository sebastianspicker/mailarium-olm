# ruff: noqa: I001
"""Ingest pipeline durability, analytics, attachments, checkpoints, and rollback behavior."""

import argparse
import types
from unittest.mock import MagicMock

import pytest

from mailarium.email_db import EmailDatabase
from mailarium.ingest import (
    _EmbedPipeline,
)

# ── Helpers ──────────────────────────────────────────────────────────

from .helpers.ingest_extended_fixtures import _MockEmailDB, _make_email
from .helpers.ingest_fixtures import _make_ingest_body_chunks, _make_ingest_pipeline, _make_pipeline_embedder


class TestCheckpointWal:
    def test_checkpoint_wal_success(self):
        mock_db = MagicMock()
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=None,
            batch_size=100,
        )
        pipeline._checkpoint_wal()
        mock_db.conn.execute.assert_called_with("PRAGMA wal_checkpoint(PASSIVE)")

    def test_checkpoint_wal_failure_is_non_critical(self):
        mock_db = MagicMock()
        mock_db.conn.execute.side_effect = Exception("WAL error")
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=None,
            batch_size=100,
        )
        # Should not raise
        pipeline._checkpoint_wal()

    def test_checkpoint_wal_no_db(self):
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=None,
            entity_extractor_fn=None,
            batch_size=100,
        )
        # Should not raise even when email_db is None
        pipeline._checkpoint_wal()


class TestComputeAnalytics:
    def test_skips_when_no_email_db(self):
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=None,
            entity_extractor_fn=None,
            batch_size=100,
        )
        # Should return immediately without error
        pipeline._compute_analytics([_make_email(1)])

    def test_short_body_is_recorded_with_low_confidence_metadata(self):
        mock_db = MagicMock()
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=None,
            batch_size=100,
        )
        email = _make_email(1, body_text="zur Prüfung")
        pipeline._compute_analytics([email])
        mock_db.update_analytics_batch.assert_called_once()
        rows = mock_db.update_analytics_batch.call_args.args[0]
        assert len(rows) == 1
        assert rows[0][0] == "de"
        assert rows[0][1] == "low"
        assert rows[0][2] == "short_text_stopword_vote"
        assert rows[0][3] == "body_text"

    def test_prefers_forensic_text_for_analytics(self):
        mock_db = MagicMock()
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=None,
            batch_size=100,
        )
        email = _make_email(1, body_text="ok")
        email.forensic_body_text = "zur Prüfung"
        email.forensic_body_source = "raw_body_text"
        pipeline._compute_analytics([email])
        rows = mock_db.update_analytics_batch.call_args.args[0]
        assert rows[0][0] == "de"
        assert rows[0][1] == "low"
        assert rows[0][3] == "raw_body_text"


class TestPipelineProcessBatch:
    def test_process_batch_with_entity_extraction(self):
        mock_db = _MockEmailDB()

        def _extract(body, sender):
            entity = MagicMock()
            entity.text = "ACME Corp"
            entity.entity_type = "organization"
            entity.normalized_form = "acme corp"
            return [entity]

        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=_extract,
            batch_size=100,
        )
        pipeline._wal_checkpoint_interval = 0  # disable WAL checkpoint

        emails = [_make_email(1)]
        pipeline._process_batch([], emails)
        assert len(mock_db._entities) > 0

    def test_process_batch_with_cooldown(self, monkeypatch):
        monkeypatch.setenv("INGEST_BATCH_COOLDOWN", "0.01")
        mock_embedder = MagicMock()
        mock_embedder.add_chunks.return_value = 1

        pipeline = _EmbedPipeline(
            embedder=mock_embedder,
            email_db=None,
            entity_extractor_fn=None,
            batch_size=100,
        )
        assert pipeline._cooldown == 0.01

        from mailarium.chunker import EmailChunk

        chunk = EmailChunk(uid="test", chunk_id="test::0", text="hello", metadata={})
        pipeline._process_batch([chunk], [])
        assert pipeline.chunks_added == 1

    def test_wal_checkpoint_triggers_on_interval(self):
        mock_db = MagicMock()
        mock_db.insert_emails_batch.return_value = set()
        mock_embedder = MagicMock()
        mock_embedder.add_chunks.return_value = 1

        pipeline = _EmbedPipeline(
            embedder=mock_embedder,
            email_db=mock_db,
            entity_extractor_fn=None,
            batch_size=100,
        )
        pipeline._wal_checkpoint_interval = 1
        pipeline.batches_written = 0

        from mailarium.chunker import EmailChunk

        chunk = EmailChunk(uid="test", chunk_id="test::0", text="hello", metadata={})
        pipeline._process_batch([chunk], [])
        # After batch, batches_written should be 1, and 1 % 1 == 0 triggers checkpoint
        mock_db.conn.execute.assert_called_with("PRAGMA wal_checkpoint(PASSIVE)")

    def test_entity_extraction_skips_empty_body(self):
        mock_db = _MockEmailDB()
        extract_called = []

        def _extract(body, sender):
            extract_called.append(body)
            return []

        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=_extract,
            batch_size=100,
        )
        pipeline._wal_checkpoint_interval = 0

        email = _make_email(1, body_text="")
        pipeline._process_batch([], [email])
        # Extractor should NOT have been called for empty body
        assert len(extract_called) == 0


class TestPipelineSubmitError:
    def test_submit_raises_when_error_set(self):
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=None,
            entity_extractor_fn=None,
            batch_size=100,
        )
        pipeline._error = RuntimeError("previous error")
        with pytest.raises(RuntimeError, match="previous error"):
            pipeline.submit(["chunk"], [])


class TestResetIndex:
    def test_reset_index_preserves_sqlite_and_deletes_derived_index(self, tmp_path, monkeypatch):
        from mailarium.ingest import _reset_index

        sqlite_file = tmp_path / "test.db"
        EmailDatabase(str(sqlite_file)).close()
        vector_index_dir = tmp_path / "vector-index"
        vector_index_dir.mkdir()
        (vector_index_dir / "data.bin").write_text("dummy", encoding="utf-8")

        args = argparse.Namespace(
            sqlite_path=str(sqlite_file),
            vector_index_path=str(vector_index_dir),
        )
        _reset_index(args)

        assert sqlite_file.exists()
        assert not vector_index_dir.exists()

    def test_reset_index_handles_missing_files(self, tmp_path):
        from mailarium.ingest import _reset_index

        args = argparse.Namespace(
            sqlite_path=str(tmp_path / "nonexistent.db"),
            vector_index_path=str(tmp_path / "nonexistent_dir"),
        )
        # Should not raise
        _reset_index(args)


class TestPipelineSkipAlreadyInserted:
    def test_skips_entity_extraction_for_existing(self):
        """When insert_emails_batch returns fewer UIDs, entities should be skipped for duplicates."""
        mock_db = MagicMock()
        email1 = _make_email(1)
        email2 = _make_email(2)
        # Only email2 is new
        mock_db.insert_emails_batch.return_value = {email2.uid}
        mock_db.update_analytics_batch.return_value = 0

        extract_calls = []

        def _extract(body, sender):
            extract_calls.append(body)
            return []

        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=_extract,
            batch_size=100,
        )
        pipeline._wal_checkpoint_interval = 0

        pipeline._process_batch([], [email1, email2])
        # Only email2 (new) should have entity extraction
        assert len(extract_calls) == 1

    def test_skips_vector_writes_and_ledger_rows_for_duplicate_emails(self):
        mock_db = _MockEmailDB()
        email1 = _make_email(1)
        email2 = _make_email(2)
        mock_db.insert_emails_batch = lambda emails, ingestion_run_id=None, commit=True: {email2.uid}

        seen_chunk_ids = []
        pipeline = _make_ingest_pipeline(
            _make_pipeline_embedder(
                existing_ids={f"{email1.uid}__0", f"{email2.uid}__0"},
                seen_chunk_ids=seen_chunk_ids,
            ),
            mock_db,
        )
        chunk1, chunk2 = _make_ingest_body_chunks(email1, email2)

        pipeline._process_batch([chunk1, chunk2], [email1, email2])

        assert seen_chunk_ids == [f"{email2.uid}__0"]
        assert [row["email_uid"] for row in mock_db._pending] == [email2.uid]
        assert [row["email_uid"] for row in mock_db._completed] == [email2.uid]

    def test_marks_ingest_failed_when_embedding_raises(self):
        mock_db = _MockEmailDB()

        email = _make_email(1)
        pipeline = _make_ingest_pipeline(
            _make_pipeline_embedder(existing_ids={"uid__0"}, error=RuntimeError("vector store unavailable")),
            mock_db,
        )
        (chunk,) = _make_ingest_body_chunks(email)

        with pytest.raises(RuntimeError, match="vector store unavailable"):
            pipeline._process_batch([chunk], [email])

        mock_db.conn.rollback.assert_called_once()
        assert mock_db._failed == {"email_uids": [email.uid], "error_message": "vector store unavailable"}

    def test_cleans_up_vectors_when_relational_completion_fails(self):
        mock_db = _MockEmailDB()
        mock_db.mark_ingest_batch_completed = MagicMock(side_effect=RuntimeError("sqlite finalize failed"))

        email = _make_email(1)
        pipeline = _make_ingest_pipeline(_make_pipeline_embedder(existing_ids={"uid__0"}), mock_db)
        (chunk,) = _make_ingest_body_chunks(email)

        with pytest.raises(RuntimeError, match="sqlite finalize failed"):
            pipeline._process_batch([chunk], [email])

        pipeline._embedder.collection.delete.assert_called_once_with(ids=[f"{email.uid}__0"])
        assert mock_db._failed == {"email_uids": [email.uid], "error_message": "sqlite finalize failed"}

    def test_cleanup_deletes_only_new_vectors_when_batch_contains_duplicates(self):
        mock_db = _MockEmailDB()
        email1 = _make_email(1)
        email2 = _make_email(2)
        mock_db.insert_emails_batch = lambda emails, ingestion_run_id=None, commit=True: {email2.uid}
        mock_db.mark_ingest_batch_completed = MagicMock(side_effect=RuntimeError("sqlite finalize failed"))

        pipeline = _make_ingest_pipeline(
            _make_pipeline_embedder(existing_ids={f"{email1.uid}__0", f"{email2.uid}__0"}),
            mock_db,
        )
        chunk1, chunk2 = _make_ingest_body_chunks(email1, email2)

        with pytest.raises(RuntimeError, match="sqlite finalize failed"):
            pipeline._process_batch([chunk1, chunk2], [email1, email2])

        pipeline._embedder.collection.delete.assert_called_once_with(ids=[f"{email2.uid}__0"])
        assert mock_db._failed == {"email_uids": [email2.uid], "error_message": "sqlite finalize failed"}

    def test_ingest_marks_run_failed_when_pipeline_raises(self, monkeypatch, tmp_path):
        import mailarium.ingest as ingest_mod

        emails = [_make_email(1)]
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}__0"}],
        )

        class _BoomEmbedder:
            def __init__(self, **_kw):
                self.collection = MagicMock()

            def count(self):
                return 0

            def set_sparse_db(self, db):
                pass

            def warmup(self):
                pass

            def add_chunks(self, chunks, **_kw):
                raise RuntimeError("vector store unavailable")

            def get_existing_ids(self, refresh=False):
                return {f"{emails[0].uid}__0"}

        monkeypatch.setattr("mailarium.embedder.EmailEmbedder", _BoomEmbedder)

        sqlite_file = str(tmp_path / "test.db")
        with pytest.raises(RuntimeError, match="vector store unavailable"):
            ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

        db = EmailDatabase(sqlite_file)
        row = db.conn.execute("SELECT status FROM ingestion_runs ORDER BY id DESC LIMIT 1").fetchone()
        assert row is not None
        assert row["status"] == "failed"
        db.close()

    def test_rolls_back_relational_rows_when_embedding_raises(self, tmp_path):
        db = EmailDatabase(str(tmp_path / "emails.db"))

        email = _make_email(1, body_text="")
        pipeline = _make_ingest_pipeline(
            _make_pipeline_embedder(existing_ids=set(), error=RuntimeError("vector store unavailable")),
            db,
        )
        (chunk,) = _make_ingest_body_chunks(email)

        with pytest.raises(RuntimeError, match="vector store unavailable"):
            pipeline._process_batch([chunk], [email])

        email_count = db.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        ingest_state_count = db.conn.execute("SELECT COUNT(*) FROM email_ingest_state").fetchone()[0]
        assert email_count == 0
        assert ingest_state_count == 0


class TestAttachmentProcessing:
    def test_attachment_text_extraction(self, monkeypatch, tmp_path):
        """When extract_attachments=True, attachment text should be chunked."""
        import mailarium.ingest as ingest_mod

        class _EmailWithAtt:
            def __init__(self):
                self.uid = "uid-att"
                self.attachment_contents = [("doc.txt", b"Hello attachment text")]
                self.message_id = "<att@example.test>"

            def to_dict(self):
                return {
                    "uid": self.uid,
                    "subject": "Test",
                    "sender_name": "S",
                    "sender_email": "s@example.test",
                    "date": "2024-01-01",
                    "folder": "Inbox",
                }

        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_EmailWithAtt()])
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
        )
        monkeypatch.setattr(
            ingest_mod,
            "chunk_attachment",
            lambda **kw: [MagicMock()],
        )

        # Mock the attachment_extractor
        original_import = __import__

        def _mock_import(name, *args, **kwargs):
            if name == "mailarium.attachment_extractor" or (args and "attachment_extractor" in str(args)):
                mod = types.ModuleType("mailarium.attachment_extractor")
                mod.extract_text = lambda name, data: "extracted text" if data else None
                return mod
            return original_import(name, *args, **kwargs)

        stats = ingest_mod.ingest(
            "mock.olm",
            dry_run=True,
            extract_attachments=True,
        )
        # Attachment chunking should have happened
        assert stats["emails_parsed"] == 1
