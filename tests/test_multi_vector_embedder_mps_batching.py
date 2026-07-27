"""MPS cache and batching behavior for the dense adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mailarium.multi_vector_embedder import MultiVectorEmbedder
from tests._multi_vector_embedder_cases import FakeSentenceTransformer


def test_mps_cache_clear_throttles(monkeypatch):
    import mailarium.multi_vector_embedder as module

    monkeypatch.setattr(module, "_MPS_CLEAR_INTERVAL", 3)
    monkeypatch.setattr(module, "_MPS_CACHE_CLEAR_ENABLED", True)
    embedder = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    embedder.device, embedder._encode_count = "mps", 0
    torch = MagicMock()
    with patch.dict("sys.modules", {"torch": torch}):
        for _ in range(6):
            embedder._mps_cache_clear()
    assert torch.mps.empty_cache.call_count == 2


def test_mps_cache_clear_is_noop_on_cpu():
    embedder = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    embedder.device, embedder._encode_count = "cpu", 0
    embedder._mps_cache_clear()


def test_mps_sub_batching_preserves_all_rows():
    embedder = MultiVectorEmbedder(device="cpu", batch_size=2)
    embedder.device = "mps"
    embedder._model = FakeSentenceTransformer("dense")
    assert len(embedder.encode_all(["a", "b", "c", "d", "e"]).dense) == 5
