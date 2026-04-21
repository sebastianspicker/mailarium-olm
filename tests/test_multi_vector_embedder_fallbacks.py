"""Fallback and error-handling tests for the multi-vector embedder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.multi_vector_embedder import MultiVectorEmbedder, MultiVectorResult
from tests._multi_vector_embedder_cases import FakeSentenceTransformer


def test_embedder_falls_back_to_sentence_transformer():
    with patch.dict("sys.modules", {"FlagEmbedding": None}):
        with patch("src.multi_vector_embedder.MultiVectorEmbedder._load_sentence_transformer") as mock_load:

            def side_effect():
                emb._model = FakeSentenceTransformer("BAAI/bge-m3")
                emb._backend = _BackendInfo(name="sentence_transformer")

            from src.multi_vector_embedder import _BackendInfo

            emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
            mock_load.side_effect = side_effect
            assert emb.backend.name == "sentence_transformer"
            assert emb.has_sparse is False
            assert emb.has_colbert is False


def test_encode_dense_sentence_transformer():
    with patch.dict("sys.modules", {"FlagEmbedding": None}):
        emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
        from src.multi_vector_embedder import _BackendInfo

        emb._model = FakeSentenceTransformer("BAAI/bge-m3")
        emb._backend = _BackendInfo(name="sentence_transformer")

        result = emb.encode_dense(["hello", "world"])
        assert len(result) == 2


def test_encode_all_sentence_transformer():
    with patch.dict("sys.modules", {"FlagEmbedding": None}):
        emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
        from src.multi_vector_embedder import _BackendInfo

        emb._model = FakeSentenceTransformer("BAAI/bge-m3")
        emb._backend = _BackendInfo(name="sentence_transformer")

        result = emb.encode_all(["hello"])
        assert isinstance(result, MultiVectorResult)
        assert len(result.dense) == 1
        assert result.sparse is None
        assert result.colbert is None


def test_load_sentence_transformer_local_only_raises_on_cache_miss():
    import src.multi_vector_embedder as mve_mod

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu", load_mode="local_only")
    mock_st_module = MagicMock()

    def fake_constructor(*args, **kwargs):
        raise OSError("not in cache")

    mock_st_module.SentenceTransformer = fake_constructor

    with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
        with pytest.raises(mve_mod.EmbeddingModelUnavailableError):
            emb._load_sentence_transformer()


def test_load_sentence_transformer_download_mode_skips_local_probe():
    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu", load_mode="download")
    mock_st_module = MagicMock()
    calls = []

    def fake_constructor(*args, **kwargs):
        calls.append(kwargs)
        return FakeSentenceTransformer("test", **kwargs)

    mock_st_module.SentenceTransformer = fake_constructor

    with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
        emb._load_sentence_transformer()

    assert calls == [{"device": "cpu"}]
    assert emb.backend.name == "sentence_transformer"


def test_batch_size_default_auto():
    emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    emb._device_spec = "auto"
    emb.device = "cpu"
    emb.batch_size = 16
    assert emb.batch_size == 16


def test_batch_size_explicit():
    emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    emb.batch_size = 42
    assert emb.batch_size == 42
