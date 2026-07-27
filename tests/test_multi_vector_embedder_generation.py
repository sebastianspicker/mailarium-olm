"""Deterministic contracts for the dense and sparse embedding adapters."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np

from mailarium.multi_vector_embedder import MultiVectorEmbedder, MultiVectorResult


class _DenseModel:
    def encode(self, texts, **_kwargs):
        return np.asarray([[float(index), 1.0] for index, _ in enumerate(texts)], dtype=np.float32)


class _SparseEncoder:
    is_available = True

    def encode_documents(self, texts):
        return [{index: 1.0} for index, _ in enumerate(texts)]

    def encode_queries(self, texts):
        return [{index + 10: 0.5} for index, _ in enumerate(texts)]

    def runtime_summary(self):
        return {"model_name": "sparse-test", "loaded": True}


def test_dense_encoding_uses_sentence_transformer_shape():
    embedder = MultiVectorEmbedder(device="cpu")
    embedder._model = _DenseModel()
    assert embedder.encode_dense(["one", "two"]) == [[0.0, 1.0], [1.0, 1.0]]


def test_sparse_document_and_query_encoders_are_asymmetric():
    with patch("mailarium.multi_vector_embedder.SparseTextEncoder", return_value=_SparseEncoder()):
        embedder = MultiVectorEmbedder(device="cpu", sparse_enabled=True)
    assert embedder.has_sparse is True
    assert embedder.encode_sparse(["document"]) == [{0: 1.0}]
    assert embedder.encode_sparse_query(["query"]) == [{10: 0.5}]


def test_sparse_disabled_returns_none_without_loading_an_optional_model():
    embedder = MultiVectorEmbedder(device="cpu", sparse_enabled=False)
    assert embedder.encode_sparse(["document"]) is None
    assert embedder.encode_sparse_query(["query"]) is None


def test_encode_all_keeps_dense_and_optional_sparse_contract():
    with patch("mailarium.multi_vector_embedder.SparseTextEncoder", return_value=_SparseEncoder()):
        embedder = MultiVectorEmbedder(device="cpu", sparse_enabled=True)
    embedder._model = _DenseModel()
    result = embedder.encode_all(["one", "two"])
    assert isinstance(result, MultiVectorResult)
    assert result.dense == [[0.0, 1.0], [1.0, 1.0]]
    assert result.sparse == [{0: 1.0}, {1: 1.0}]
