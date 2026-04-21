"""Multi-vector embedding abstraction for BGE-M3.

Provides a unified interface over SentenceTransformer (dense-only fallback)
and FlagEmbedding's BGEM3FlagModel (dense + sparse + ColBERT).  All three
retrieval modes are extracted from a single forward pass when FlagEmbedding
is available, maximizing throughput on Apple Silicon MPS.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import resolve_device, resolve_embedding_batch_size, resolve_embedding_load_mode
from .transformers_compat import ensure_flagembedding_transformers_compat

_MPS_CLEAR_INTERVAL = int(os.environ.get("MPS_CACHE_CLEAR_INTERVAL", "1"))
_MPS_CACHE_CLEAR_ENABLED = os.environ.get("MPS_CACHE_CLEAR_ENABLED", "0") == "1"

logger = logging.getLogger(__name__)


@dataclass
class MultiVectorResult:
    """Output from a multi-vector encode pass."""

    dense: list[list[float]]
    sparse: list[dict[int, float]] | None = None
    colbert: list[np.ndarray] | None = None


@dataclass
class _BackendInfo:
    """Tracks which backend is active and its capabilities."""

    name: str  # "flag" or "sentence_transformer"
    has_sparse: bool = False
    has_colbert: bool = False


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when the configured load mode forbids downloading a missing model."""


class MultiVectorEmbedder:
    """Unified interface: BGEM3FlagModel (preferred) or SentenceTransformer fallback.

    Capabilities:
        - ``encode_dense()``: always available (both backends)
        - ``encode_sparse()``: only with FlagEmbedding + ``sparse_enabled``
        - ``encode_colbert()``: only with FlagEmbedding + ``colbert_enabled``
        - ``encode_all()``: single forward pass returning all enabled modes
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "auto",
        sparse_enabled: bool = False,
        colbert_enabled: bool = False,
        batch_size: int = 0,
        mps_float16: bool = False,
        load_mode: str = "auto",
    ) -> None:
        self.model_name = model_name
        self._device_spec = device
        self.device = resolve_device(device)
        self._sparse_enabled = sparse_enabled
        self._colbert_enabled = colbert_enabled
        self._mps_float16 = mps_float16
        self.load_mode = resolve_embedding_load_mode(load_mode)
        self.batch_size = batch_size or resolve_embedding_batch_size(self.device)

        self._model: Any = None
        self._backend: _BackendInfo | None = None
        self._encode_count: int = 0

    @property
    def backend(self) -> _BackendInfo:
        """Return backend info, loading model if needed."""
        if self._backend is None:
            self._load_model()
        if self._backend is None:
            raise RuntimeError("model not loaded")
        return self._backend

    @property
    def has_sparse(self) -> bool:
        return self.backend.has_sparse

    @property
    def has_colbert(self) -> bool:
        return self.backend.has_colbert

    def _load_model(self) -> None:
        """Load the best available model backend."""
        if self._model is not None:
            return

        # FlagEmbedding's M3 loader does not reliably honor offline cache-only
        # semantics. For dense-only local_only runs, use SentenceTransformer's
        # explicit local_files_only path instead of probing FlagEmbedding first.
        if self.load_mode == "local_only" and not self._sparse_enabled and not self._colbert_enabled:
            self._load_sentence_transformer()
            return

        # Try FlagEmbedding first (unlocks sparse + ColBERT)
        if self._try_load_flag_model():
            return

        # Fall back to SentenceTransformer (dense only)
        self._load_sentence_transformer()

    def _try_load_flag_model(self) -> bool:
        """Attempt to load BGEM3FlagModel from FlagEmbedding.

        Returns True on success, False if FlagEmbedding is not installed.
        """
        try:
            ensure_flagembedding_transformers_compat()
            from FlagEmbedding import BGEM3FlagModel
        except ImportError:
            logger.warning(
                "FlagEmbedding not installed — falling back to SentenceTransformer (dense only). "
                "Sparse retrieval and ColBERT reranking will be unavailable. "
                "Install with: pip install 'FlagEmbedding>=1.3.0'"
            )
            return False

        if self.device == "mps":
            # MPS backend defaults to float32 because Apple Silicon's GPU
            # produces silent numerical drift with fp16 on many transformer
            # ops, causing degraded retrieval quality.  Opt-in via mps_float16.
            use_fp16 = self._mps_float16
        else:
            use_fp16 = self.device not in ("cpu",)
        logger.info(
            "Loading BGEM3FlagModel: %s (device=%s, fp16=%s, sparse=%s, colbert=%s, load_mode=%s)",
            self.model_name,
            self.device,
            use_fp16,
            self._sparse_enabled,
            self._colbert_enabled,
            self.load_mode,
        )
        try:
            with _offline_model_load(self.load_mode == "local_only"):
                self._model = BGEM3FlagModel(
                    self.model_name,
                    device=self.device,
                    use_fp16=use_fp16,
                )
        except Exception as exc:
            if self.load_mode == "local_only":
                raise EmbeddingModelUnavailableError(
                    f"FlagEmbedding model '{self.model_name}' is not available locally and "
                    "EMBEDDING_LOAD_MODE=local_only forbids downloading it."
                ) from exc
            raise
        self._backend = _BackendInfo(
            name="flag",
            has_sparse=self._sparse_enabled,
            has_colbert=self._colbert_enabled,
        )
        return True

    def _load_sentence_transformer(self) -> None:
        """Load SentenceTransformer as dense-only fallback."""
        from sentence_transformers import SentenceTransformer

        if self.load_mode == "download":
            logger.info(
                "Loading SentenceTransformer with downloads enabled: %s (device=%s)",
                self.model_name,
                self.device,
            )
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._backend = _BackendInfo(name="sentence_transformer")
            return

        # Try local cache first to skip unnecessary HF Hub requests.
        try:
            with _offline_model_load(self.load_mode == "local_only"):
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    local_files_only=True,
                )
            logger.info(
                "Loaded SentenceTransformer from cache: %s (device=%s, load_mode=%s)",
                self.model_name,
                self.device,
                self.load_mode,
            )
        except (OSError, TypeError) as exc:
            # OSError → model not in local cache, need to download
            # TypeError → older sentence-transformers without local_files_only
            if self.load_mode == "local_only":
                raise EmbeddingModelUnavailableError(
                    f"Embedding model '{self.model_name}' is not available locally and "
                    "EMBEDDING_LOAD_MODE=local_only forbids downloading it."
                ) from exc
            logger.info(
                "Downloading SentenceTransformer: %s (device=%s)",
                self.model_name,
                self.device,
            )
            self._model = SentenceTransformer(self.model_name, device=self.device)

        self._backend = _BackendInfo(name="sentence_transformer")

    def _ensure_loaded(self) -> None:
        if self._model is None:
            self._load_model()

    def encode_dense(self, texts: list[str]) -> list[list[float]]:
        """Encode texts to dense embeddings (always available)."""
        if not texts:
            return []
        self._ensure_loaded()

        if self.backend.name == "flag":
            output = self._model.encode(
                texts,
                batch_size=self.batch_size,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            vecs = output["dense_vecs"]
            self._mps_cache_clear()
            return _to_list_of_lists(vecs)

        # SentenceTransformer path
        vecs = self._model.encode(texts, batch_size=self.batch_size, show_progress_bar=False)
        return _to_list_of_lists(vecs)

    def encode_sparse(self, texts: list[str]) -> list[dict[int, float]] | None:
        """Encode texts to learned sparse vectors.

        Returns None if FlagEmbedding is not available or sparse is disabled.
        """
        if not self.has_sparse:
            return None
        if not texts:
            return []

        self._ensure_loaded()
        output = self._model.encode(
            texts,
            batch_size=self.batch_size,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        self._mps_cache_clear()
        return _convert_sparse(output["lexical_weights"])

    def encode_colbert(self, texts: list[str]) -> list[np.ndarray] | None:
        """Encode texts to ColBERT token-level vectors.

        Returns None if FlagEmbedding is not available or ColBERT is disabled.
        """
        if not self.has_colbert:
            return None
        if not texts:
            return []

        self._ensure_loaded()
        output = self._model.encode(
            texts,
            batch_size=self.batch_size,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
        )
        self._mps_cache_clear()
        return _normalize_colbert(output["colbert_vecs"])

    def encode_all(self, texts: list[str]) -> MultiVectorResult:
        """Single forward pass returning all enabled modes.

        On MPS, texts are processed in explicit sub-batches with GPU cache
        clearing between them to prevent memory accumulation that tanks
        throughput on sustained workloads.
        """
        if not texts:
            return MultiVectorResult(dense=[])
        self._ensure_loaded()
        use_sub_batching = self.device == "mps" and len(texts) > self.batch_size

        if self.backend.name == "flag":
            return self._encode_all_flag(texts, use_sub_batching)

        # SentenceTransformer: dense only
        if use_sub_batching:
            all_vecs = []
            for i in range(0, len(texts), self.batch_size):
                sub = texts[i : i + self.batch_size]
                vecs = self._model.encode(sub, batch_size=self.batch_size, show_progress_bar=False)
                all_vecs.append(vecs)
                self._mps_cache_clear()
            combined = np.concatenate(all_vecs, axis=0)
            return MultiVectorResult(dense=_to_list_of_lists(combined))

        vecs = self._model.encode(texts, batch_size=self.batch_size, show_progress_bar=False)
        return MultiVectorResult(dense=_to_list_of_lists(vecs))

    def _encode_all_flag(self, texts: list[str], use_sub_batching: bool) -> MultiVectorResult:
        """FlagEmbedding path for encode_all — single call or MPS sub-batched."""
        return_sparse = self._sparse_enabled
        return_colbert = self._colbert_enabled

        if not use_sub_batching:
            output = self._model.encode(
                texts,
                batch_size=self.batch_size,
                return_dense=True,
                return_sparse=return_sparse,
                return_colbert_vecs=return_colbert,
            )
            self._mps_cache_clear()
            return MultiVectorResult(
                dense=_to_list_of_lists(output["dense_vecs"]),
                sparse=_convert_sparse(output["lexical_weights"]) if return_sparse else None,
                colbert=_normalize_colbert(output["colbert_vecs"]) if return_colbert else None,
            )

        # MPS sub-batched: clear GPU cache between sub-batches
        all_dense: list = []
        all_sparse: list[dict] = []
        all_colbert: list = []

        for i in range(0, len(texts), self.batch_size):
            sub = texts[i : i + self.batch_size]
            output = self._model.encode(
                sub,
                batch_size=self.batch_size,
                return_dense=True,
                return_sparse=return_sparse,
                return_colbert_vecs=return_colbert,
            )
            all_dense.append(output["dense_vecs"])
            if return_sparse:
                all_sparse.extend(output["lexical_weights"])
            if return_colbert:
                all_colbert.extend(output["colbert_vecs"])
            self._mps_cache_clear()

        dense = _to_list_of_lists(np.concatenate(all_dense, axis=0))
        sparse = _convert_sparse(all_sparse) if return_sparse else None
        colbert = _normalize_colbert(all_colbert) if return_colbert else None
        return MultiVectorResult(dense=dense, sparse=sparse, colbert=colbert)

    def warmup(self) -> None:
        """Force model load and run a tiny encode to prime GPU memory."""
        self._ensure_loaded()
        self.encode_dense(["warmup"])
        logger.info(
            "Model warmed up: %s (backend=%s, device=%s, batch_size=%d, load_mode=%s)",
            self.model_name,
            self.backend.name,
            self.device,
            self.batch_size,
            self.load_mode,
        )

    def runtime_summary(self) -> dict[str, Any]:
        """Return a compact backend summary for diagnostics and startup logs."""
        summary: dict[str, Any] = {
            "model_name": self.model_name,
            "device": self.device,
            "batch_size": self.batch_size,
            "load_mode": self.load_mode,
        }
        if self._backend is None:
            summary["backend"] = "unloaded"
            summary["has_sparse"] = self._sparse_enabled
            summary["has_colbert"] = self._colbert_enabled
            return summary
        summary["backend"] = self.backend.name
        summary["has_sparse"] = self.backend.has_sparse
        summary["has_colbert"] = self.backend.has_colbert
        return summary

    def _mps_cache_clear(self) -> None:
        """Free MPS GPU cache periodically (every _MPS_CLEAR_INTERVAL encodes)."""
        if self.device != "mps" or not _MPS_CACHE_CLEAR_ENABLED:
            return

        self._encode_count += 1
        if self._encode_count % _MPS_CLEAR_INTERVAL != 0:
            return

        try:
            import torch

            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
        except (ImportError, RuntimeError):
            pass  # torch/MPS not available — cache clear is optional


def _to_list_of_lists(vecs: Any) -> list[list[float]]:
    """Convert numpy/tensor array to list of lists."""
    if hasattr(vecs, "tolist"):
        return vecs.tolist()
    if isinstance(vecs, list) and len(vecs) > 0 and hasattr(vecs[0], "tolist"):
        return [v.tolist() for v in vecs]
    return vecs


def _convert_sparse(lexical_weights: list[dict]) -> list[dict[int, float]]:
    """Normalize FlagEmbedding lexical_weights to {token_id: weight} dicts."""
    result = []
    for weights in lexical_weights:
        converted: dict[int, float] = {}
        for token_id, weight in weights.items():
            tid = int(token_id)
            w = float(weight)
            if w > 0:
                converted[tid] = w
        result.append(converted)
    return result


def _normalize_colbert(colbert_vecs: list[Any]) -> list[np.ndarray]:
    """Ensure ColBERT vectors are numpy arrays."""
    result = []
    for vecs in colbert_vecs:
        if isinstance(vecs, np.ndarray):
            result.append(vecs)
        elif hasattr(vecs, "numpy"):
            # Handle GPU/MPS tensors that can't call .numpy() directly
            if hasattr(vecs, "detach"):
                vecs = vecs.detach().cpu()
            result.append(vecs.numpy())
        else:
            result.append(np.array(vecs))
    return result


@contextmanager
def _offline_model_load(enabled: bool):
    """Temporarily force Hugging Face libraries into offline mode."""
    if not enabled:
        yield
        return
    old_hf = os.environ.get("HF_HUB_OFFLINE")
    old_tx = os.environ.get("TRANSFORMERS_OFFLINE")
    old_st = os.environ.get("DISABLE_SAFETENSORS_CONVERSION")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["DISABLE_SAFETENSORS_CONVERSION"] = "1"
    try:
        yield
    finally:
        if old_hf is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = old_hf
        if old_tx is None:
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
        else:
            os.environ["TRANSFORMERS_OFFLINE"] = old_tx
        if old_st is None:
            os.environ.pop("DISABLE_SAFETENSORS_CONVERSION", None)
        else:
            os.environ["DISABLE_SAFETENSORS_CONVERSION"] = old_st
