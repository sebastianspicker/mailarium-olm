from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np


def make_dense_output(n: int = 2, dim: int = 4):
    """Fake dense vectors as numpy array."""
    return np.random.rand(n, dim).astype(np.float32)


def make_sparse_output(n: int = 2):
    """Fake lexical_weights as list of dicts (FlagEmbedding format)."""
    return [{1: 0.5, 42: 0.9}, {7: 0.3, 100: 0.0}][:n]


def make_colbert_output(n: int = 2, tokens: int = 8, dim: int = 4):
    """Fake ColBERT token vectors."""
    return [np.random.rand(tokens, dim).astype(np.float32) for _ in range(n)]


class FakeFlagModel:
    """Mock BGEM3FlagModel that returns predictable outputs."""

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
            result["dense_vecs"] = make_dense_output(n)
        if return_sparse:
            result["lexical_weights"] = make_sparse_output(n)
        if return_colbert_vecs:
            result["colbert_vecs"] = make_colbert_output(n)
        return result


class FakeSentenceTransformer:
    """Mock SentenceTransformer."""

    def __init__(self, model_name: str, device: str = "cpu", **kwargs):
        self.model_name = model_name
        self.device = device
        self.kwargs = kwargs

    def encode(self, texts, batch_size=16, show_progress_bar=False):
        return make_dense_output(len(texts))


def make_flag_module():
    flag_module = MagicMock()
    flag_module.BGEM3FlagModel = FakeFlagModel
    return flag_module
