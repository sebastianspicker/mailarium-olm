"""Loading and offline-mode tests for the SentenceTransformer adapter."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from mailarium.config import DEFAULT_EMBEDDING_MODEL_REVISION
from mailarium.multi_vector_embedder import EmbeddingModelUnavailableError, MultiVectorEmbedder, _offline_model_load
from tests._multi_vector_embedder_cases import FakeSentenceTransformer


def test_local_only_cache_miss_raises_adapter_error():
    embedder = MultiVectorEmbedder(device="cpu", load_mode="local_only")
    st = MagicMock()
    st.SentenceTransformer.side_effect = OSError("not cached")
    with patch.dict("sys.modules", {"sentence_transformers": st}):
        with pytest.raises(EmbeddingModelUnavailableError):
            embedder._ensure_loaded()


def test_download_mode_constructs_sentence_transformer_without_local_only():
    embedder = MultiVectorEmbedder(device="cpu", load_mode="download")
    st = MagicMock()
    st.SentenceTransformer.return_value = FakeSentenceTransformer("dense")
    with patch.dict("sys.modules", {"sentence_transformers": st}):
        embedder._ensure_loaded()
    assert st.SentenceTransformer.call_args.kwargs == {
        "device": "cpu",
        "revision": DEFAULT_EMBEDDING_MODEL_REVISION,
        "trust_remote_code": False,
    }


def test_runtime_summary_does_not_claim_late_interaction_from_dense_adapter():
    embedder = MultiVectorEmbedder(device="cpu")
    summary = embedder.runtime_summary()
    assert summary["backend"] == "unloaded"


def test_offline_model_load_restores_environment(monkeypatch):
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DISABLE_SAFETENSORS_CONVERSION"):
        monkeypatch.delenv(name, raising=False)
    with _offline_model_load(True):
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert "HF_HUB_OFFLINE" not in os.environ
    assert "TRANSFORMERS_OFFLINE" not in os.environ
    assert "DISABLE_SAFETENSORS_CONVERSION" not in os.environ


def test_mps_sub_batches_dense_work_without_network():
    embedder = MultiVectorEmbedder(device="cpu", batch_size=2)
    embedder.device = "mps"
    embedder._model = FakeSentenceTransformer("dense")
    assert len(embedder.encode_dense(["a", "b", "c"])) == 3
