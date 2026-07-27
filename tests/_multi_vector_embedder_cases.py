"""Shared deterministic fakes for SentenceTransformer-backed tests."""

from __future__ import annotations

import numpy as np


def make_dense_output(n: int = 2, dim: int = 4):
    return np.arange(n * dim, dtype=np.float32).reshape(n, dim)


class FakeSentenceTransformer:
    def __init__(self, model_name: str, device: str = "cpu", **kwargs):
        self.model_name = model_name
        self.device = device
        self.kwargs = kwargs

    def encode(self, texts, **_kwargs):
        return make_dense_output(len(texts))
