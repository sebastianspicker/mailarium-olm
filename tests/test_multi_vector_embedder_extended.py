"""Extended tests for src/multi_vector_embedder.py — targeting uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.multi_vector_embedder import (
    MultiVectorEmbedder,
    MultiVectorResult,
    _BackendInfo,
    _normalize_colbert,
)


def _make_dense_output(n: int = 2, dim: int = 4):
    return np.random.rand(n, dim).astype(np.float32)


def _make_sparse_output(n: int = 2):
    return [{1: 0.5, 42: 0.9}, {7: 0.3, 100: 0.0}][:n]


def _make_colbert_output(n: int = 2, tokens: int = 8, dim: int = 4):
    return [np.random.rand(tokens, dim).astype(np.float32) for _ in range(n)]


class FakeFlagModel:
    def __init__(self, model_name: str, device: str = "cpu", use_fp16: bool = False):
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16

    def encode(
        self,
        texts,
        batch_size=16,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    ):
        n = len(texts)
        result = {}
        if return_dense:
            result["dense_vecs"] = _make_dense_output(n)
        if return_sparse:
            result["lexical_weights"] = _make_sparse_output(n)
        if return_colbert_vecs:
            result["colbert_vecs"] = _make_colbert_output(n)
        return result


class FakeSentenceTransformer:
    def __init__(self, model_name: str, device: str = "cpu", **kwargs):
        self.model_name = model_name
        self.device = device

    def encode(self, texts, batch_size=16, show_progress_bar=False):
        return _make_dense_output(len(texts))


# ── backend RuntimeError (line 80) ──────────────────────────


class TestBackendRuntimeError:
    def test_backend_raises_when_model_not_loaded(self):
        """Accessing backend when _load_model completes but _backend is None raises RuntimeError."""
        emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
        emb._model = None
        emb._backend = None
        emb.model_name = "BAAI/bge-m3"
        emb._device_spec = "cpu"
        emb.device = "cpu"
        emb._sparse_enabled = False
        emb._colbert_enabled = False
        emb._mps_float16 = False
        emb.load_mode = "auto"
        emb.batch_size = 16
        emb._encode_count = 0

        # Make _load_model complete without setting _backend
        def noop_load():
            emb._model = MagicMock()  # model is set, but backend is not

        with patch.object(emb, "_load_model", side_effect=noop_load):
            with pytest.raises(RuntimeError, match="model not loaded"):
                _ = emb.backend


# ── _load_model early return (line 94) ──────────────────────


class TestLoadModelEarlyReturn:
    def test_load_model_skips_when_already_loaded(self):
        """_load_model does nothing when model is already loaded."""
        emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
        emb._model = FakeSentenceTransformer("test")
        emb._backend = _BackendInfo(name="sentence_transformer")
        emb._sparse_enabled = False
        emb._colbert_enabled = False
        emb._mps_float16 = False
        emb.load_mode = "auto"

        # Should not attempt to load again
        emb._load_model()
        assert emb._model is not None


# ── SentenceTransformer fallback paths (line 150) ────────────


class TestSentenceTransformerFallback:
    def test_load_sentence_transformer_cache_miss(self):
        """When local cache misses (OSError), downloads model."""
        emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
        emb.model_name = "BAAI/bge-m3"
        emb.device = "cpu"
        emb._model = None
        emb._backend = None
        emb.load_mode = "auto"

        mock_st_module = MagicMock()
        call_count = [0]

        def fake_constructor(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("not in cache")
            return FakeSentenceTransformer("test")

        mock_st_module.SentenceTransformer = fake_constructor

        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            emb._load_sentence_transformer()

        assert emb._model is not None
        assert emb._backend.name == "sentence_transformer"
        assert call_count[0] == 2

    def test_load_sentence_transformer_type_error_fallback(self):
        """Older sentence-transformers without local_files_only raise TypeError."""
        emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
        emb.model_name = "BAAI/bge-m3"
        emb.device = "cpu"
        emb._model = None
        emb._backend = None
        emb.load_mode = "auto"

        mock_st_module = MagicMock()
        call_count = [0]

        def fake_constructor(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise TypeError("unexpected keyword")
            return FakeSentenceTransformer("test")

        mock_st_module.SentenceTransformer = fake_constructor

        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            emb._load_sentence_transformer()

        assert emb._model is not None
        assert emb._backend.name == "sentence_transformer"
        assert call_count[0] == 2


# ── _encode_all_flag MPS sub-batched (lines 277-300) ─────────


class TestEncodeAllFlagMpsSubBatched:
    @patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
    def test_encode_all_flag_mps_sub_batched(self):
        """MPS sub-batching path for FlagEmbedding encode_all."""
        import sys

        flag_mod = sys.modules["FlagEmbedding"]
        flag_mod.BGEM3FlagModel = FakeFlagModel

        emb = MultiVectorEmbedder(
            model_name="BAAI/bge-m3",
            device="cpu",
            sparse_enabled=True,
            colbert_enabled=True,
            batch_size=2,
        )
        emb._load_model()
        # Simulate MPS device to trigger sub-batching
        emb.device = "mps"

        texts = ["text1", "text2", "text3", "text4", "text5"]
        result = emb.encode_all(texts)

        assert isinstance(result, MultiVectorResult)
        assert len(result.dense) == 5
        assert result.sparse is not None
        assert result.colbert is not None

    @patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
    def test_encode_all_flag_mps_no_sub_batching(self):
        """FlagEmbedding encode_all without sub-batching (texts fit in one batch)."""
        import sys

        flag_mod = sys.modules["FlagEmbedding"]
        flag_mod.BGEM3FlagModel = FakeFlagModel

        emb = MultiVectorEmbedder(
            model_name="BAAI/bge-m3",
            device="cpu",
            sparse_enabled=True,
            colbert_enabled=True,
            batch_size=32,
        )
        emb._load_model()
        emb.device = "mps"

        texts = ["short"]
        result = emb.encode_all(texts)
        assert len(result.dense) == 1
        assert result.sparse is not None
        assert result.colbert is not None

    @patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
    def test_encode_all_flag_sparse_only_sub_batched(self):
        """MPS sub-batching with sparse only (no ColBERT)."""
        import sys

        flag_mod = sys.modules["FlagEmbedding"]
        flag_mod.BGEM3FlagModel = FakeFlagModel

        emb = MultiVectorEmbedder(
            model_name="BAAI/bge-m3",
            device="cpu",
            sparse_enabled=True,
            colbert_enabled=False,
            batch_size=2,
        )
        emb._load_model()
        emb.device = "mps"

        texts = ["a", "b", "c"]
        result = emb.encode_all(texts)
        assert len(result.dense) == 3
        assert result.sparse is not None
        assert result.colbert is None


# ── _normalize_colbert GPU tensor (lines 360-362) ────────────


class TestNormalizeColbertGpuTensor:
    def test_normalize_colbert_gpu_tensor_with_detach(self):
        """ColBERT vecs from GPU tensors are detached and converted."""

        class FakeGpuTensor:
            """Simulates a GPU tensor with detach/cpu/numpy chain."""

            def numpy(self):
                return np.ones((3, 4))

            def detach(self):
                return self

            def cpu(self):
                return self

        result = _normalize_colbert([FakeGpuTensor()])
        assert len(result) == 1
        assert isinstance(result[0], np.ndarray)
        assert result[0].shape == (3, 4)

    def test_normalize_colbert_plain_list_input(self):
        """Plain list input is converted to numpy array."""
        data = [[[1.0, 2.0], [3.0, 4.0]]]
        result = _normalize_colbert(data)
        assert isinstance(result[0], np.ndarray)
        assert result[0].shape == (2, 2)


# ── SentenceTransformer encode_all MPS sub-batching ──────────


class TestSTEncodeAllMpsSubBatching:
    def test_encode_all_st_mps_sub_batching(self):
        """SentenceTransformer path with MPS sub-batching."""
        emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
        emb._model = FakeSentenceTransformer("test")
        emb._backend = _BackendInfo(name="sentence_transformer")
        emb.device = "mps"
        emb.batch_size = 2
        emb._encode_count = 0
        emb._sparse_enabled = False
        emb._colbert_enabled = False
        emb.load_mode = "auto"

        texts = ["a", "b", "c", "d", "e"]
        result = emb.encode_all(texts)
        assert len(result.dense) == 5
        assert result.sparse is None
        assert result.colbert is None
