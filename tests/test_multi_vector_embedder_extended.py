"""Additional deterministic adapter contracts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mailarium.multi_vector_embedder import EmbeddingModelUnavailableError, MultiVectorEmbedder


def test_warmup_loads_dense_model_and_encodes_once():
    embedder = MultiVectorEmbedder(device="cpu")
    model = MagicMock()
    model.encode.return_value = [[1.0, 0.0]]
    with patch.object(embedder, "_ensure_loaded", side_effect=lambda: setattr(embedder, "_model", model)):
        embedder.warmup()
    model.encode.assert_called_once()


def test_empty_input_avoids_model_load():
    embedder = MultiVectorEmbedder(device="cpu")
    assert embedder.encode_dense([]) == []
    assert embedder.encode_all([]).dense == []


def test_local_only_error_retains_cause():
    embedder = MultiVectorEmbedder(device="cpu", load_mode="local_only")
    with patch.dict("sys.modules", {"sentence_transformers": None}):
        with pytest.raises(EmbeddingModelUnavailableError):
            embedder._ensure_loaded()


def test_dense_loader_passes_immutable_revision(monkeypatch):
    model = MagicMock()
    sentence_transformer = MagicMock(return_value=model)
    fake_module = MagicMock(SentenceTransformer=sentence_transformer)
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", fake_module)

    embedder = MultiVectorEmbedder(
        model_name="custom/model",
        model_revision="immutable-revision",
        device="cpu",
        load_mode="local_only",
    )
    embedder._ensure_loaded()

    sentence_transformer.assert_called_once_with(
        "custom/model",
        device="cpu",
        trust_remote_code=False,
        revision="immutable-revision",
        local_files_only=True,
    )
