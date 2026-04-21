"""MPS, batching, and runtime-limit tests for the multi-vector embedder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.multi_vector_embedder import MultiVectorEmbedder
from tests._multi_vector_embedder_cases import FakeFlagModel


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_flag_model_no_fp16_on_mps():
    import sys

    calls = []

    class SpyFlagModel(FakeFlagModel):
        def __init__(self, model_name, device="cpu", use_fp16=False):
            super().__init__(model_name, device, use_fp16)
            calls.append({"device": device, "use_fp16": use_fp16})

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = SpyFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
    emb.device = "mps"
    emb._load_model()
    assert calls[0]["use_fp16"] is False


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_flag_model_fp16_on_cuda():
    import sys

    calls = []

    class SpyFlagModel(FakeFlagModel):
        def __init__(self, model_name, device="cpu", use_fp16=False):
            super().__init__(model_name, device, use_fp16)
            calls.append({"device": device, "use_fp16": use_fp16})

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = SpyFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
    emb.device = "cuda"
    emb._load_model()
    assert calls[0]["use_fp16"] is True


def test_mps_cache_clear_no_torch(monkeypatch):
    import sys

    import src.multi_vector_embedder as mve_mod

    monkeypatch.setattr(mve_mod, "_MPS_CACHE_CLEAR_ENABLED", True)
    emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    emb.device = "mps"
    emb._encode_count = 9
    monkeypatch.setitem(sys.modules, "torch", None)
    emb._mps_cache_clear()


def test_mps_cache_clear_skipped_on_cpu():
    emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    emb.device = "cpu"
    emb._encode_count = 0
    emb._mps_cache_clear()


def test_mps_cache_clear_throttled(monkeypatch):
    import src.multi_vector_embedder as mve_mod

    monkeypatch.setattr(mve_mod, "_MPS_CLEAR_INTERVAL", 3)
    monkeypatch.setattr(mve_mod, "_MPS_CACHE_CLEAR_ENABLED", True)

    emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    emb.device = "mps"
    emb._encode_count = 0

    clear_calls = []
    mock_torch = MagicMock()
    mock_torch.mps.empty_cache = lambda: clear_calls.append(1)

    with patch.dict("sys.modules", {"torch": mock_torch}):
        for _ in range(9):
            emb._mps_cache_clear()

    assert len(clear_calls) == 3
    assert emb._encode_count == 9


def test_mps_cache_clear_every_call_with_interval_1(monkeypatch):
    import src.multi_vector_embedder as mve_mod

    monkeypatch.setattr(mve_mod, "_MPS_CLEAR_INTERVAL", 1)
    monkeypatch.setattr(mve_mod, "_MPS_CACHE_CLEAR_ENABLED", True)

    emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    emb.device = "mps"
    emb._encode_count = 0

    clear_calls = []
    mock_torch = MagicMock()
    mock_torch.mps.empty_cache = lambda: clear_calls.append(1)

    with patch.dict("sys.modules", {"torch": mock_torch}):
        for _ in range(5):
            emb._mps_cache_clear()

    assert len(clear_calls) == 5


def test_mps_cache_clear_disabled_by_default(monkeypatch):
    import src.multi_vector_embedder as mve_mod

    monkeypatch.setattr(mve_mod, "_MPS_CACHE_CLEAR_ENABLED", False)

    emb = MultiVectorEmbedder.__new__(MultiVectorEmbedder)
    emb.device = "mps"
    emb._encode_count = 0

    mock_torch = MagicMock()
    mock_torch.mps.empty_cache = MagicMock()

    with patch.dict("sys.modules", {"torch": mock_torch}):
        emb._mps_cache_clear()

    mock_torch.mps.empty_cache.assert_not_called()


def test_mps_float16_setting_from_env(monkeypatch):
    monkeypatch.setenv("MPS_FLOAT16", "true")
    from src.config import Settings

    settings = Settings.from_env()
    assert settings.mps_float16 is True


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_mps_fp16_used_when_opted_in():
    import sys

    calls = []

    class SpyFlagModel(FakeFlagModel):
        def __init__(self, model_name, device="cpu", use_fp16=False):
            super().__init__(model_name, device, use_fp16)
            calls.append({"device": device, "use_fp16": use_fp16})

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = SpyFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu", mps_float16=True)
    emb.device = "mps"
    emb._load_model()
    assert calls[0]["use_fp16"] is True


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_mps_fp32_by_default():
    import sys

    calls = []

    class SpyFlagModel(FakeFlagModel):
        def __init__(self, model_name, device="cpu", use_fp16=False):
            super().__init__(model_name, device, use_fp16)
            calls.append({"device": device, "use_fp16": use_fp16})

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = SpyFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu", mps_float16=False)
    emb.device = "mps"
    emb._load_model()
    assert calls[0]["use_fp16"] is False


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_all_mps_sub_batching():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
    emb._load_model()
    emb.device = "mps"
    emb.batch_size = 2

    texts = ["text1", "text2", "text3", "text4", "text5"]
    result = emb.encode_all(texts)

    assert len(result.dense) == 5
    dims = {len(vector) for vector in result.dense}
    assert len(dims) == 1


@patch.dict("sys.modules", {"FlagEmbedding": MagicMock()})
def test_encode_all_no_sub_batching_when_small():
    import sys

    flag_mod = sys.modules["FlagEmbedding"]
    flag_mod.BGEM3FlagModel = FakeFlagModel

    emb = MultiVectorEmbedder(model_name="BAAI/bge-m3", device="cpu")
    emb._load_model()
    emb.device = "mps"
    emb.batch_size = 32

    texts = ["short text"]
    result = emb.encode_all(texts)
    assert len(result.dense) == 1
