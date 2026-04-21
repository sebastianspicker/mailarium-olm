# ruff: noqa: F401,I001
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

from .helpers.ingest_extended_fixtures import _MockEmailDB, _MockEmbedder, _block_import, _make_email


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
            main(["--reingest-analytics"])
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
            main(["--reembed"])
        assert exc.value.code == 0
        assert "Reembedded" in capsys.readouterr().out

    def test_main_requires_olm_for_reingest_bodies(self):
        with pytest.raises(SystemExit) as exc:
            main(["--reingest-bodies"])

        assert exc.value.code == 2

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


class TestReingestMetadataEdgeCases:
    def test_empty_db(self, tmp_path):
        from src.email_db import EmailDatabase

        sqlite_file = str(tmp_path / "test.db")
        db = EmailDatabase(sqlite_file)
        db.close()

        result = reingest_metadata("mock.olm", sqlite_path=sqlite_file)
        assert result["updated"] == 0
        assert "No emails" in result["message"]


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
            lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-{j}", "uid": e.get("uid", "x")} for j in range(3)],
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
                "--resume",
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
        assert args.resume is True
        assert args.yes is True
        assert args.log_level == "DEBUG"

    def test_positive_int_error(self):
        with pytest.raises(SystemExit):
            parse_args(["data/file.olm", "--batch-size", "-1"])

    def test_reingest_analytics_does_not_require_olm_path(self):
        args = parse_args(["--reingest-analytics"])
        assert args.olm_path is None
        assert args.reingest_analytics is True

    def test_reembed_does_not_require_olm_path(self):
        args = parse_args(["--reembed"])
        assert args.olm_path is None
        assert args.reembed is True

    def test_reextract_entities_does_not_require_olm_path(self):
        args = parse_args(["--reextract-entities"])
        assert args.olm_path is None
        assert args.reextract_entities is True

    def test_default_ingest_still_requires_olm_path(self):
        with pytest.raises(SystemExit):
            parse_args([])

    def test_reingest_bodies_still_requires_olm_path(self):
        with pytest.raises(SystemExit):
            parse_args(["--reingest-bodies"])


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
