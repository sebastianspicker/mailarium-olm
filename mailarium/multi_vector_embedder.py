"""Dense SentenceTransformer embeddings with optional learned sparse encoding."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_MODEL_REVISION,
    resolve_device,
    resolve_embedding_batch_size,
    resolve_embedding_load_mode,
)
from .sparse_encoder import SparseTextEncoder

_MPS_CLEAR_INTERVAL = int(os.environ.get("MPS_CACHE_CLEAR_INTERVAL", "1"))
_MPS_CACHE_CLEAR_ENABLED = os.environ.get("MPS_CACHE_CLEAR_ENABLED", "0") == "1"

logger = logging.getLogger(__name__)


@dataclass
class MultiVectorResult:
    """Dense vectors plus optional provider-independent sparse vectors."""

    dense: list[list[float]]
    sparse: list[dict[int, float]] | None = None


@dataclass(frozen=True)
class _BackendInfo:
    """Expose the active dense backend and sparse availability."""

    name: str = "sentence_transformer"
    has_sparse: bool = False


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when local-only model loading cannot satisfy a request."""


class MultiVectorEmbedder:
    """Primary dense encoder with an independently loaded sparse adapter."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        device: str = "auto",
        sparse_enabled: bool = False,
        sparse_model: str = "opensearch-project/opensearch-neural-sparse-encoding-multilingual-v1",
        sparse_model_revision: str = "",
        batch_size: int = 0,
        load_mode: str = "auto",
        model_revision: str | None = None,
    ) -> None:
        """Configure validated dense and optional sparse encoders without loading either model.

        Non-default dense models require an explicit revision; device, load mode, and batch size
        are resolved before inference. Sparse configuration is retained for its own lazy loader.
        """
        self.model_name = model_name
        self.model_revision = model_revision or (
            DEFAULT_EMBEDDING_MODEL_REVISION if model_name == DEFAULT_EMBEDDING_MODEL else ""
        )
        if not self.model_revision:
            raise ValueError("model_revision is required for a non-default dense embedding model")
        self.device = resolve_device(device)
        self._sparse_enabled = sparse_enabled
        self.load_mode = resolve_embedding_load_mode(load_mode)
        self.batch_size = batch_size or resolve_embedding_batch_size(self.device)
        self._model: Any | None = None
        self._encode_count = 0
        self._sparse_encoder = (
            SparseTextEncoder(
                model_name=sparse_model,
                model_revision=sparse_model_revision,
                device=self.device,
                batch_size=self.batch_size,
                load_mode=self.load_mode,
            )
            if sparse_enabled
            else None
        )

    @property
    def backend(self) -> _BackendInfo:
        """Report sparse availability after ensuring the primary encoder can load."""
        self._ensure_loaded()
        return _BackendInfo(has_sparse=self.has_sparse)

    @property
    def has_sparse(self) -> bool:
        """Indicate whether the optional sparse adapter is ready for use."""
        return bool(self._sparse_encoder and self._sparse_encoder.is_available)

    def encode_dense(self, texts: list[str]) -> list[list[float]]:
        """Encode dense text vectors."""
        if not texts:
            return []
        self._ensure_loaded()
        if self.device == "mps" and len(texts) > self.batch_size:
            chunks = [
                self._encode_dense_batch(texts[index : index + self.batch_size])
                for index in range(0, len(texts), self.batch_size)
            ]
            return _to_list_of_lists(np.concatenate(chunks, axis=0))
        return _to_list_of_lists(self._encode_dense_batch(texts))

    def encode_sparse(self, texts: list[str]) -> list[dict[int, float]] | None:
        """Encode documents for learned sparse indexing."""
        if not self._sparse_encoder:
            return None
        return self._sparse_encoder.encode_documents(texts)

    def encode_sparse_query(self, texts: list[str]) -> list[dict[int, float]] | None:
        """Encode queries using the sparse model's query prompt."""
        if not self._sparse_encoder:
            return None
        return self._sparse_encoder.encode_queries(texts)

    def encode_all(self, texts: list[str]) -> MultiVectorResult:
        """Encode dense vectors and the optional independent sparse lane."""
        if not texts:
            return MultiVectorResult(dense=[])
        return MultiVectorResult(
            dense=self.encode_dense(texts),
            sparse=self.encode_sparse(texts),
        )

    def warmup(self) -> None:
        """Load configured embedding backends early so failures are deterministic."""
        self._ensure_loaded()
        self.encode_dense(["warmup"])
        logger.info(
            "Model warmed up: %s (backend=sentence_transformer, device=%s, batch_size=%d, load_mode=%s)",
            self.model_name,
            self.device,
            self.batch_size,
            self.load_mode,
        )

    def runtime_summary(self) -> dict[str, Any]:
        """Describe configured encoders and their current load state for diagnostics."""
        summary: dict[str, Any] = {
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "device": self.device,
            "batch_size": self.batch_size,
            "load_mode": self.load_mode,
            "backend": "sentence_transformer" if self._model is not None else "unloaded",
            "has_sparse": bool(self._sparse_encoder and self._sparse_encoder.is_available),
        }
        if self._sparse_encoder is not None:
            summary["sparse"] = self._sparse_encoder.runtime_summary()
        return summary

    def _ensure_loaded(self) -> None:
        """Load the dense encoder once, honoring local-only model availability."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            kwargs: dict[str, Any] = {
                "device": self.device,
                "trust_remote_code": False,
                "revision": self.model_revision,
            }
            if self.load_mode == "local_only":
                kwargs["local_files_only"] = True
            with _offline_model_load(self.load_mode == "local_only"):
                self._model = SentenceTransformer(self.model_name, **kwargs)
        except Exception as exc:
            if self.load_mode == "local_only":
                raise EmbeddingModelUnavailableError(f"Embedding model {self.model_name!r} is not available locally") from exc
            raise

    def _encode_dense_batch(self, texts: list[str]) -> Any:
        """Encode one batch with normalized embeddings and release periodic MPS cache pressure."""
        assert self._model is not None
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        self._mps_cache_clear()
        return vectors

    def _mps_cache_clear(self) -> None:
        """Periodically free MPS allocator cache when the configured interval is reached."""
        if self.device != "mps" or not _MPS_CACHE_CLEAR_ENABLED:
            return
        self._encode_count += 1
        if self._encode_count % _MPS_CLEAR_INTERVAL:
            return
        try:
            import torch

            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
        except ImportError, RuntimeError:
            return


def _to_list_of_lists(vectors: Any) -> list[list[float]]:
    """Convert NumPy-style encoder outputs into the list contract used by callers."""
    if hasattr(vectors, "tolist"):
        return vectors.tolist()
    if isinstance(vectors, list) and vectors and hasattr(vectors[0], "tolist"):
        return [vector.tolist() for vector in vectors]
    return vectors


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
        _restore_environment("HF_HUB_OFFLINE", old_hf)
        _restore_environment("TRANSFORMERS_OFFLINE", old_tx)
        _restore_environment("DISABLE_SAFETENSORS_CONVERSION", old_st)


def _restore_environment(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
