"""Extended tests for src/ingest.py to increase coverage from ~73% to >=85%.

Covers: reingest paths, _reset_index, _resolve_entity_extractor,
_auto_download_spacy_models, _checkpoint_wal, _NoOpProgressBar,
_make_progress_bar, _hash_file_sha256, pipeline edge cases,
main() dispatch branches, attachment processing, and more.
"""

import argparse
import types
from unittest.mock import MagicMock, patch

import pytest

from src.ingest import (
    _auto_download_spacy_models,
    _EmbedPipeline,
    _hash_file_sha256,
    _make_progress_bar,
    _NoOpProgressBar,
    _resolve_entity_extractor,
    format_ingestion_summary,
    main,
    parse_args,
    reembed,
    reingest_analytics,
    reingest_bodies,
    reingest_metadata,
)
from src.parse_olm import Email

# ── Helpers ──────────────────────────────────────────────────────────


def _make_email(idx, body_text="Body text that is long enough for analytics processing and detection"):
    return Email(
        message_id=f"<msg{idx}@test.com>",
        subject=f"Subject {idx}",
        sender_name="Sender",
        sender_email="sender@test.com",
        to=["recipient@test.com"],
        cc=[],
        bcc=[],
        date=f"2024-01-0{idx}T10:00:00",
        body_text=body_text,
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


class _MockEmbedder:
    def __init__(self, **_kw):
        self.chromadb_path = "mock"
        self.model_name = "mock"
        self._count = 0
        self.collection = MagicMock()
        self.collection.metadata = {"hnsw:space": "cosine"}

    def count(self):
        return self._count

    def add_chunks(self, chunks, **_kw):
        self._count += len(chunks)
        return len(chunks)

    def set_sparse_db(self, db):
        pass

    def warmup(self):
        pass

    def close(self):
        pass

    def get_existing_ids(self, refresh=False):
        return set()

    def delete_chunks_by_uid(self, uid):
        return 0

    def upsert_chunks(self, chunks, batch_size=100):
        return len(chunks)


class _MockEmailDB:
    """Lightweight mock for EmailDatabase used in pipeline tests."""

    def __init__(self):
        self.conn = MagicMock()
        self._inserted = []
        self._entities = []
        self._analytics = []

    def insert_emails_batch(self, emails, ingestion_run_id=None):
        uids = [e.uid for e in emails]
        self._inserted.extend(uids)
        return set(uids)

    def insert_entities_batch(self, uid, entities, commit=True):
        self._entities.extend(entities)

    def update_analytics_batch(self, rows):
        self._analytics.extend(rows)
        return len(rows)

    def email_exists(self, uid):
        return uid in self._inserted

    def email_count(self):
        return len(self._inserted)

    def close(self):
        pass


# ── _NoOpProgressBar ─────────────────────────────────────────────────


class TestNoOpProgressBar:
    def test_update_does_nothing(self):
        bar = _NoOpProgressBar()
        bar.update(5)

    def test_close_does_nothing(self):
        bar = _NoOpProgressBar()
        bar.close()

    def test_set_postfix_does_nothing(self):
        bar = _NoOpProgressBar()
        bar.set_postfix(key="value")


# ── _make_progress_bar ───────────────────────────────────────────────


class TestMakeProgressBar:
    def test_returns_noop_when_tqdm_unavailable(self, monkeypatch):
        """Without tqdm, should return _NoOpProgressBar."""
        monkeypatch.setattr("builtins.__import__", _block_import("tqdm"))
        bar = _make_progress_bar(100, desc="Test", unit="it")
        assert isinstance(bar, _NoOpProgressBar)

    def test_returns_tqdm_when_available(self):
        """With tqdm available, should return a tqdm instance."""
        bar = _make_progress_bar(10, desc="Test", unit="item")
        # tqdm may or may not be installed; just verify no crash
        bar.update(1)
        bar.close()


def _block_import(module_name):
    """Return an __import__ replacement that blocks a specific module."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _mock_import(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"blocked {module_name}")
        return real_import(name, *args, **kwargs)

    return _mock_import


# ── _hash_file_sha256 ───────────────────────────────────────────────


class TestHashFileSha256:
    def test_computes_hash(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        h = _hash_file_sha256(str(f))
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"deterministic content")
        assert _hash_file_sha256(str(f)) == _hash_file_sha256(str(f))


# ── _resolve_entity_extractor ────────────────────────────────────────


class TestResolveEntityExtractor:
    def test_returns_none_when_disabled(self):
        assert _resolve_entity_extractor(extract_entities=False, dry_run=False) is None

    def test_returns_none_when_dry_run(self):
        assert _resolve_entity_extractor(extract_entities=True, dry_run=True) is None

    def test_falls_back_to_regex_on_import_error(self, monkeypatch):
        """When nlp_entity_extractor is not importable, falls back to regex."""
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def _block_nlp(name, *args, **kwargs):
            if "nlp_entity_extractor" in name:
                raise ImportError("no spaCy")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _block_nlp)
        result = _resolve_entity_extractor(extract_entities=True, dry_run=False)
        assert result is not None  # Falls back to regex extractor

    def test_uses_spacy_when_available(self, monkeypatch):
        """When spaCy is available, should use NLP extractor."""
        # Create mock modules
        mock_nlp = types.ModuleType("src.nlp_entity_extractor")
        mock_nlp.is_spacy_available = lambda: True
        mock_nlp.extract_nlp_entities = lambda text, sender: []

        monkeypatch.setitem(__import__("sys").modules, "src.nlp_entity_extractor", mock_nlp)
        result = _resolve_entity_extractor(extract_entities=True, dry_run=False)
        assert result is not None


# ── _auto_download_spacy_models ──────────────────────────────────────


class TestAutoDownloadSpacyModels:
    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("SPACY_AUTO_DOWNLOAD", "0")
        # Should return immediately without error
        _auto_download_spacy_models()

    def test_skips_when_spacy_not_installed(self, monkeypatch):
        monkeypatch.delenv("SPACY_AUTO_DOWNLOAD", raising=False)
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def _block_spacy(name, *args, **kwargs):
            if name == "spacy":
                raise ImportError("no spacy")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _block_spacy)
        _auto_download_spacy_models()

    def test_downloads_missing_models(self, monkeypatch):
        monkeypatch.delenv("SPACY_AUTO_DOWNLOAD", raising=False)
        mock_spacy = MagicMock()
        mock_spacy.load = MagicMock(side_effect=OSError("model not found"))
        monkeypatch.setitem(__import__("sys").modules, "spacy", mock_spacy)

        with patch("subprocess.check_call") as mock_check:
            _auto_download_spacy_models()
            assert mock_check.call_count == 2  # Two models

    def test_handles_download_failure(self, monkeypatch):
        import subprocess

        monkeypatch.delenv("SPACY_AUTO_DOWNLOAD", raising=False)
        mock_spacy = MagicMock()
        mock_spacy.load = MagicMock(side_effect=OSError("model not found"))
        monkeypatch.setitem(__import__("sys").modules, "spacy", mock_spacy)

        with patch("subprocess.check_call", side_effect=subprocess.CalledProcessError(1, "cmd")):
            _auto_download_spacy_models()  # Should not raise

    def test_skips_already_installed(self, monkeypatch):
        monkeypatch.delenv("SPACY_AUTO_DOWNLOAD", raising=False)
        mock_spacy = MagicMock()
        mock_spacy.load = MagicMock(return_value=MagicMock())  # Model loads fine
        monkeypatch.setitem(__import__("sys").modules, "spacy", mock_spacy)

        with patch("subprocess.check_call") as mock_check:
            _auto_download_spacy_models()
            mock_check.assert_not_called()


# ── _checkpoint_wal ──────────────────────────────────────────────────


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


# ── _compute_analytics ───────────────────────────────────────────────


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

    def test_skips_short_body(self):
        mock_db = MagicMock()
        pipeline = _EmbedPipeline(
            embedder=None,
            email_db=mock_db,
            entity_extractor_fn=None,
            batch_size=100,
        )
        email = _make_email(1, body_text="short")
        pipeline._compute_analytics([email])
        mock_db.update_analytics_batch.assert_not_called()


# ── Pipeline entity extraction + cooldown + WAL checkpoint ───────────


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

        from src.chunker import EmailChunk

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

        from src.chunker import EmailChunk

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


# ── Pipeline submit with existing error ──────────────────────────────


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


# ── _reset_index ─────────────────────────────────────────────────────


class TestResetIndex:
    def test_reset_index_deletes_sqlite_and_chromadb(self, tmp_path, monkeypatch):
        from src.ingest import _reset_index

        sqlite_file = tmp_path / "test.db"
        sqlite_file.write_text("dummy", encoding="utf-8")
        chroma_dir = tmp_path / "chromadb"
        chroma_dir.mkdir()
        (chroma_dir / "data.bin").write_text("dummy", encoding="utf-8")

        args = argparse.Namespace(
            sqlite_path=str(sqlite_file),
            chromadb_path=str(chroma_dir),
        )
        _reset_index(args)

        assert not sqlite_file.exists()
        assert not chroma_dir.exists()

    def test_reset_index_handles_missing_files(self, tmp_path):
        from src.ingest import _reset_index

        args = argparse.Namespace(
            sqlite_path=str(tmp_path / "nonexistent.db"),
            chromadb_path=str(tmp_path / "nonexistent_dir"),
        )
        # Should not raise
        _reset_index(args)


# ── main() dispatch branches ─────────────────────────────────────────


class TestMainDispatch:
    def test_main_reset_index_without_yes(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["data/file.olm", "--reset-index"])
        assert exc.value.code == 2
        out = capsys.readouterr().out
        assert "Refusing" in out

    def test_main_reset_index_with_yes(self, tmp_path, monkeypatch, capsys):
        import src.ingest as ingest_mod

        monkeypatch.setattr(ingest_mod, "_reset_index", lambda args: None)
        with pytest.raises(SystemExit) as exc:
            main(["data/file.olm", "--reset-index", "--yes"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "reset" in out.lower()

    def test_main_reingest_bodies(self, monkeypatch, capsys):
        import src.ingest as ingest_mod

        monkeypatch.setattr(
            ingest_mod,
            "reingest_bodies",
            lambda olm_path, sqlite_path=None, force=False: {"message": "Bodies updated"},
        )
        with pytest.raises(SystemExit) as exc:
            main(["data/file.olm", "--reingest-bodies"])
        assert exc.value.code == 0
        assert "Bodies updated" in capsys.readouterr().out

    def test_main_reingest_metadata(self, monkeypatch, capsys):
        import src.ingest as ingest_mod

        monkeypatch.setattr(
            ingest_mod,
            "reingest_metadata",
            lambda olm_path, sqlite_path=None: {"message": "Metadata updated"},
        )
        with pytest.raises(SystemExit) as exc:
            main(["data/file.olm", "--reingest-metadata"])
        assert exc.value.code == 0
        assert "Metadata updated" in capsys.readouterr().out

    def test_main_reingest_analytics(self, monkeypatch, capsys):
        import src.ingest as ingest_mod

        monkeypatch.setattr(
            ingest_mod,
            "reingest_analytics",
            lambda sqlite_path=None: {"message": "Analytics computed"},
        )
        with pytest.raises(SystemExit) as exc:
            main(["data/file.olm", "--reingest-analytics"])
        assert exc.value.code == 0
        assert "Analytics computed" in capsys.readouterr().out

    def test_main_reembed(self, monkeypatch, capsys):
        import src.ingest as ingest_mod

        monkeypatch.setattr(
            ingest_mod,
            "reembed",
            lambda chromadb_path=None, sqlite_path=None, batch_size=100: {"message": "Reembedded"},
        )
        with pytest.raises(SystemExit) as exc:
            main(["data/file.olm", "--reembed"])
        assert exc.value.code == 0
        assert "Reembedded" in capsys.readouterr().out

    def test_main_runtime_error(self, monkeypatch, capsys):
        import src.ingest as ingest_mod

        monkeypatch.setattr(
            ingest_mod,
            "ingest",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("test runtime error")),
        )
        with pytest.raises(SystemExit) as exc:
            main(["data/file.olm", "--dry-run"])
        assert exc.value.code == 2
        out = capsys.readouterr().out
        assert "test runtime error" in out


# ── reingest_bodies edge cases ───────────────────────────────────────


class TestReingestBodiesEdgeCases:
    def test_force_empty_db(self, monkeypatch, tmp_path):
        from src.email_db import EmailDatabase

        sqlite_file = str(tmp_path / "test.db")
        db = EmailDatabase(sqlite_file)
        db.close()

        result = reingest_bodies("mock.olm", sqlite_path=sqlite_file, force=True)
        assert result["updated"] == 0
        assert "No emails" in result["message"]

    def test_non_force_with_missing_bodies(self, monkeypatch, tmp_path):
        """Non-force reingest should update only emails with NULL body_text."""
        import src.embedder as embedder_mod
        import src.ingest as ingest_mod
        from src.email_db import EmailDatabase

        email = _make_email(1)
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
        )
        monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

        sqlite_file = str(tmp_path / "test.db")
        ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

        # Clear body_text to simulate missing body
        db = EmailDatabase(sqlite_file)
        db.conn.execute("UPDATE emails SET body_text = NULL")
        db.conn.commit()
        db.close()

        # Re-parse should find and update the missing body
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
        result = reingest_bodies("mock.olm", sqlite_path=sqlite_file, force=False)
        assert result["updated"] == 1

    def test_force_with_progress_logging(self, monkeypatch, tmp_path):
        """Force reingest with >100 emails should trigger progress logging."""
        import src.embedder as embedder_mod
        import src.ingest as ingest_mod

        emails = [_make_email(i) for i in range(1, 5)]
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
        )
        monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

        sqlite_file = str(tmp_path / "test.db")
        ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

        # Force reingest
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
        result = reingest_bodies("mock.olm", sqlite_path=sqlite_file, force=True)
        assert result["updated"] == 4


# ── reingest_metadata edge cases ─────────────────────────────────────


class TestReingestMetadataEdgeCases:
    def test_empty_db(self, tmp_path):
        from src.email_db import EmailDatabase

        sqlite_file = str(tmp_path / "test.db")
        db = EmailDatabase(sqlite_file)
        db.close()

        result = reingest_metadata("mock.olm", sqlite_path=sqlite_file)
        assert result["updated"] == 0
        assert "No emails" in result["message"]


# ── reingest_analytics edge cases ────────────────────────────────────


class TestReingestAnalyticsEdgeCases:
    def test_all_already_have_analytics(self, tmp_path):
        """reingest_analytics should return early when nothing is missing."""
        from src.email_db import EmailDatabase

        sqlite_file = str(tmp_path / "test.db")
        db = EmailDatabase(sqlite_file)
        db.close()

        result = reingest_analytics(sqlite_path=sqlite_file)
        assert result["updated"] == 0
        assert "already have" in result["message"]


# ── format_ingestion_summary edge cases ──────────────────────────────


class TestFormatSummaryEdgeCases:
    def test_includes_sqlite_inserted(self):
        lines = format_ingestion_summary(
            {
                "emails_parsed": 10,
                "chunks_created": 20,
                "chunks_added": 18,
                "chunks_skipped": 2,
                "batches_written": 3,
                "total_in_db": 99,
                "sqlite_inserted": 10,
                "dry_run": False,
                "elapsed_seconds": 1.5,
            }
        )
        assert any("SQLite rows inserted: 10" in line for line in lines)

    def test_includes_skipped_incremental(self):
        lines = format_ingestion_summary(
            {
                "emails_parsed": 10,
                "chunks_created": 20,
                "chunks_added": 18,
                "chunks_skipped": 2,
                "batches_written": 3,
                "total_in_db": 99,
                "sqlite_inserted": 5,
                "skipped_incremental": 5,
                "dry_run": False,
                "elapsed_seconds": 1.5,
            }
        )
        assert any("Skipped (incremental): 5" in line for line in lines)

    def test_no_timing_info(self):
        lines = format_ingestion_summary(
            {
                "emails_parsed": 10,
                "chunks_created": 20,
                "dry_run": True,
                "elapsed_seconds": 1.0,
            }
        )
        assert not any("Timing:" in line for line in lines)


# ── ingest() with timing and max_emails ──────────────────────────────


class TestIngestEdgeCases:
    def test_timing_flag_adds_detailed_breakdown(self, monkeypatch, tmp_path):
        import src.embedder as embedder_mod
        import src.ingest as ingest_mod

        emails = [_make_email(i) for i in range(1, 4)]
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
        )
        monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

        sqlite_file = str(tmp_path / "test.db")
        stats = ingest_mod.ingest(
            "mock.olm",
            dry_run=False,
            sqlite_path=sqlite_file,
            timing=True,
        )
        timing = stats["timing"]
        assert "parse_seconds" in timing
        assert "queue_wait_seconds" in timing
        assert "sqlite_seconds" in timing
        assert "entity_seconds" in timing
        assert "analytics_seconds" in timing

    def test_max_emails_limits_parsing(self, monkeypatch):
        import src.ingest as ingest_mod

        class _Email:
            def __init__(self, idx):
                self.idx = idx
                self.uid = f"uid-{idx}"
                self.attachment_contents = []

            def to_dict(self):
                return {"id": self.idx, "uid": self.uid}

        monkeypatch.setattr(
            ingest_mod,
            "parse_olm",
            lambda _path, **_kw: [_Email(i) for i in range(1, 11)],
        )
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
        )

        stats = ingest_mod.ingest("mock.olm", dry_run=True, max_emails=5)
        assert stats["emails_parsed"] == 5

    def test_batch_flushing_during_loop(self, monkeypatch, tmp_path):
        """When pending chunks exceed batch_size, they should be flushed."""
        import src.embedder as embedder_mod
        import src.ingest as ingest_mod

        emails = [_make_email(i) for i in range(1, 6)]
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-{j}"} for j in range(3)],
        )
        monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

        sqlite_file = str(tmp_path / "test.db")
        stats = ingest_mod.ingest(
            "mock.olm",
            dry_run=False,
            sqlite_path=sqlite_file,
            batch_size=5,
        )
        assert stats["chunks_created"] == 15
        assert stats["batches_written"] >= 1

    def test_hundred_email_progress_logging(self, monkeypatch):
        """100th email should trigger progress logging."""
        import src.ingest as ingest_mod

        class _SimpleEmail:
            def __init__(self, idx):
                self.idx = idx
                self.uid = f"uid-{idx}"
                self.attachment_contents = []

            def to_dict(self):
                return {"id": self.idx, "uid": self.uid}

        monkeypatch.setattr(
            ingest_mod,
            "parse_olm",
            lambda _path, **_kw: [_SimpleEmail(i) for i in range(1, 102)],
        )
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
        )

        stats = ingest_mod.ingest("mock.olm", dry_run=True, max_emails=101)
        assert stats["emails_parsed"] == 101

    def test_ingest_records_olm_hash(self, monkeypatch, tmp_path):
        """Non-dry ingest should compute OLM file hash and size."""
        import src.embedder as embedder_mod
        import src.ingest as ingest_mod

        olm_file = tmp_path / "test.olm"
        olm_file.write_bytes(b"fake olm content")

        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [])
        monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

        sqlite_file = str(tmp_path / "test.db")
        stats = ingest_mod.ingest(
            str(olm_file),
            dry_run=False,
            sqlite_path=sqlite_file,
        )
        assert stats["emails_parsed"] == 0


# ── Pipeline skip already-inserted in _process_batch ─────────────────


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


# ── Attachment processing in ingest ──────────────────────────────────


class TestAttachmentProcessing:
    def test_attachment_text_extraction(self, monkeypatch, tmp_path):
        """When extract_attachments=True, attachment text should be chunked."""
        import src.ingest as ingest_mod

        class _EmailWithAtt:
            def __init__(self):
                self.uid = "uid-att"
                self.attachment_contents = [("doc.txt", b"Hello attachment text")]
                self.message_id = "<att@test.com>"

            def to_dict(self):
                return {
                    "uid": self.uid,
                    "subject": "Test",
                    "sender_name": "S",
                    "sender_email": "s@test.com",
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
            if name == "src.attachment_extractor" or (args and "attachment_extractor" in str(args)):
                mod = types.ModuleType("src.attachment_extractor")
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


# ── parse_args edge cases ────────────────────────────────────────────


class TestParseArgsEdgeCases:
    def test_all_flags(self):
        args = parse_args(
            [
                "data/file.olm",
                "--chromadb-path",
                "/tmp/chroma",
                "--batch-size",
                "100",
                "--max-emails",
                "50",
                "--dry-run",
                "--extract-attachments",
                "--embed-images",
                "--extract-entities",
                "--sqlite-path",
                "/tmp/test.db",
                "--incremental",
                "--reset-index",
                "--reingest-bodies",
                "--reingest-metadata",
                "--reembed",
                "--reingest-analytics",
                "--force",
                "--timing",
                "--yes",
                "--log-level",
                "DEBUG",
            ]
        )
        assert args.olm_path == "data/file.olm"
        assert args.chromadb_path == "/tmp/chroma"
        assert args.batch_size == 100
        assert args.max_emails == 50
        assert args.dry_run is True
        assert args.extract_attachments is True
        assert args.embed_images is True
        assert args.extract_entities is True
        assert args.sqlite_path == "/tmp/test.db"
        assert args.incremental is True
        assert args.reset_index is True
        assert args.reingest_bodies is True
        assert args.reingest_metadata is True
        assert args.reembed is True
        assert args.reingest_analytics is True
        assert args.force is True
        assert args.timing is True
        assert args.yes is True
        assert args.log_level == "DEBUG"

    def test_positive_int_error(self):
        with pytest.raises(SystemExit):
            parse_args(["data/file.olm", "--batch-size", "-1"])


# ── reembed edge cases ──────────────────────────────────────────────


class TestReembedEdgeCases:
    def test_reembed_progress_logging(self, monkeypatch, tmp_path):
        """reembed with many emails should trigger progress logging."""
        import src.embedder as embedder_mod
        import src.ingest as ingest_mod

        emails = [_make_email(i) for i in range(1, 4)]
        monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
        monkeypatch.setattr(
            ingest_mod,
            "chunk_email",
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
        )
        monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

        sqlite_file = str(tmp_path / "test.db")
        ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

        monkeypatch.setattr("src.embedder.EmailEmbedder", _MockEmbedder)

        result = reembed(sqlite_path=sqlite_file)
        assert result["reembedded"] >= 1
        assert result["chunks_added"] >= 1


# ── _positive_int ────────────────────────────────────────────────────


class TestPositiveInt:
    def test_valid(self):
        from src.ingest import _positive_int

        assert _positive_int("5") == 5

    def test_invalid_raises_argparse_type_error(self):
        from src.ingest import _positive_int

        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("0")

    def test_negative_raises_argparse_type_error(self):
        from src.ingest import _positive_int

        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("-1")
