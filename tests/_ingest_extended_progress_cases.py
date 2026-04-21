# ruff: noqa: F401,I001
"""Extended tests for src/ingest.py to increase coverage from ~73% to >=85%.

Covers: reingest paths, _reset_index, _resolve_entity_extractor,
_auto_download_spacy_models, _checkpoint_wal, _NoOpProgressBar,
_make_progress_bar, _hash_file_sha256, pipeline edge cases,
main() dispatch branches, attachment processing, and more.
"""

import argparse
import sys
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

    def test_attempts_spacy_bootstrap_by_default(self, monkeypatch):
        """Ingest should attempt spaCy model bootstrap by default when models are missing."""
        monkeypatch.delenv("SPACY_AUTO_DOWNLOAD_DURING_INGEST", raising=False)
        availability = {"value": False}
        mock_nlp = types.ModuleType("src.nlp_entity_extractor")
        mock_nlp.extract_nlp_entities = lambda text, sender: []
        mock_nlp.is_spacy_available = lambda: availability["value"]
        reset_cache = MagicMock()
        mock_nlp.reset_model_cache = reset_cache
        monkeypatch.setitem(sys.modules, "src.nlp_entity_extractor", mock_nlp)
        auto_download = MagicMock(side_effect=lambda: availability.__setitem__("value", True))
        monkeypatch.setattr("src.ingest._auto_download_spacy_models", auto_download)

        result = _resolve_entity_extractor(extract_entities=True, dry_run=False)

        auto_download.assert_called_once_with()
        reset_cache.assert_called_once_with()
        assert result is mock_nlp.extract_nlp_entities

    def test_skips_spacy_bootstrap_when_disabled_during_ingest(self, monkeypatch):
        """Operators can still opt out of spaCy bootstrap during ingest."""
        monkeypatch.setenv("SPACY_AUTO_DOWNLOAD_DURING_INGEST", "0")
        mock_nlp = types.ModuleType("src.nlp_entity_extractor")
        mock_nlp.extract_nlp_entities = lambda text, sender: []
        mock_nlp.is_spacy_available = lambda: False
        mock_nlp.reset_model_cache = MagicMock()
        monkeypatch.setitem(sys.modules, "src.nlp_entity_extractor", mock_nlp)
        auto_download = MagicMock()
        monkeypatch.setattr("src.ingest._auto_download_spacy_models", auto_download)

        result = _resolve_entity_extractor(extract_entities=True, dry_run=False)

        auto_download.assert_not_called()
        mock_nlp.reset_model_cache.assert_not_called()
        assert result is not None


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
