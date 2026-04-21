"""Embedding-generation path tests for the multi-vector embedder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from src.multi_vector_embedder import MultiVectorEmbedder, MultiVectorResult
from tests._multi_vector_embedder_cases import FakeFlagModel


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_embedder_loads_flag_model():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        sparse_enabled=True,
        colbert_enabled=True,
    )
    assert emb.backend.name == "flag"
    assert emb.has_sparse is True
    assert emb.has_colbert is True


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_dense_flag():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
    result = emb.encode_dense(["hello", "world"])
    assert len(result) == 2
    assert isinstance(result[0], list)


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_sparse_flag():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        sparse_enabled=True,
    )
    result = emb.encode_sparse(["hello", "world"])
    assert result is not None
    assert len(result) == 2
    assert isinstance(result[0], dict)


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_sparse_disabled():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        sparse_enabled=False,
    )
    assert emb.encode_sparse(["hello"]) is None


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_colbert_flag():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        colbert_enabled=True,
    )
    result = emb.encode_colbert(["hello", "world"])
    assert result is not None
    assert len(result) == 2
    assert isinstance(result[0], np.ndarray)


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_colbert_disabled():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        colbert_enabled=False,
    )
    assert emb.encode_colbert(["hello"]) is None


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_all_flag():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        sparse_enabled=True,
        colbert_enabled=True,
    )
    result = emb.encode_all(["hello", "world"])
    assert isinstance(result, MultiVectorResult)
    assert len(result.dense) == 2
    assert result.sparse is not None
    assert result.colbert is not None


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_all_flag_dense_only():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(
        model_name="BAAI/bge-m3",
        device="cpu",
        sparse_enabled=False,
        colbert_enabled=False,
    )
    result = emb.encode_all(["hello"])
    assert result.sparse is None
    assert result.colbert is None


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_warmup_loads_model_and_encodes():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
    assert emb._model is None
    emb.warmup()
    assert emb._model is not None
    assert emb._backend is not None
