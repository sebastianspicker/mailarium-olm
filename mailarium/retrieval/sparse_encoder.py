"""Optional SentenceTransformers learned-sparse encoder."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


class SparseEncoderUnavailableError(RuntimeError):
    """Raised when an explicitly requested sparse encoder cannot be loaded."""


class SparseTextEncoder:
    """Asymmetric document/query adapter around ``SparseEncoder``."""

    def __init__(
        self,
        *,
        model_name: str,
        model_revision: str = "",
        device: str = "cpu",
        batch_size: int = 16,
        load_mode: str = "auto",
    ) -> None:
        self.model_name = model_name
        self.model_revision = model_revision
        self.device = device
        self.batch_size = batch_size
        self.load_mode = load_mode
        self._model: Any | None = None
        self._load_error: str = ""

    @property
    def is_available(self) -> bool:
        """Load the learned sparse model on demand and retain a diagnostic on failure."""
        if self._model is not None:
            return True
        try:
            self._load()
        except (ImportError, OSError, SparseEncoderUnavailableError) as exc:
            self._load_error = str(exc)
            logger.warning("Learned sparse retrieval is unavailable: %s", exc)
            return False
        return self._model is not None

    def encode_documents(self, texts: list[str]) -> list[dict[int, float]] | None:
        """Encode corpus documents with the model's document prompt."""
        return self._encode(texts, query=False)

    def encode_queries(self, texts: list[str]) -> list[dict[int, float]] | None:
        """Encode search queries with the model's query prompt."""
        return self._encode(texts, query=True)

    def runtime_summary(self) -> dict[str, Any]:
        """Describe the configured model and any retained load failure for diagnostics."""
        return {
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "loaded": self._model is not None,
            "load_error": self._load_error,
        }

    def _load(self) -> None:
        """Instantiate the configured SparseEncoder without remote code and honor local-only mode."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SparseEncoder
        except ImportError as exc:
            raise SparseEncoderUnavailableError("sentence-transformers with SparseEncoder support is not installed") from exc
        kwargs: dict[str, Any] = {
            "device": self.device,
            "trust_remote_code": False,
        }
        if self.model_revision:
            kwargs["revision"] = self.model_revision
        if self.load_mode == "local_only":
            kwargs["local_files_only"] = True
        try:
            with _offline_model_load(self.load_mode == "local_only"):
                self._model = SparseEncoder(self.model_name, **kwargs)
        except Exception as exc:
            if self.load_mode == "local_only":
                raise SparseEncoderUnavailableError(f"Sparse model {self.model_name!r} is not available locally") from exc
            raise

    def _encode(self, texts: list[str], *, query: bool) -> list[dict[int, float]] | None:
        """Encode query or document batches and normalize backend-specific sparse outputs."""
        if not texts:
            return []
        if not self.is_available:
            return None
        assert self._model is not None
        method = self._model.encode_query if query else self._model.encode_document
        embeddings = method(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        return sparse_embeddings_to_dicts(embeddings, expected_rows=len(texts))


def sparse_embeddings_to_dicts(embeddings: Any, *, expected_rows: int) -> list[dict[int, float]]:
    """Convert list, SciPy, Torch, or dense sparse outputs into positive token-weight mappings."""
    if isinstance(embeddings, list) and all(isinstance(row, dict) for row in embeddings):
        return [_positive_weights(row) for row in embeddings]
    if hasattr(embeddings, "tocsr"):
        return _scipy_sparse_to_dicts(embeddings)
    if hasattr(embeddings, "to_sparse"):
        return _torch_sparse_to_dicts(embeddings, expected_rows)
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    if isinstance(embeddings, list):
        return [_sparse_row_to_dict(row) for row in embeddings]
    raise TypeError(f"Unsupported sparse embedding output: {type(embeddings)!r}")


def _scipy_sparse_to_dicts(embeddings: Any) -> list[dict[int, float]]:
    """Convert every CSR matrix row into a token-weight mapping."""
    matrix = embeddings.tocsr()
    return [_scipy_sparse_row_to_dict(matrix, row) for row in range(matrix.shape[0])]


def _scipy_sparse_row_to_dict(matrix: Any, row: int) -> dict[int, float]:
    """Read positive column weights from one CSR row."""
    start, end = matrix.indptr[row : row + 2]
    return {
        int(index): float(value)
        for index, value in zip(matrix.indices[start:end], matrix.data[start:end], strict=True)
        if float(value) > 0
    }


def _torch_sparse_to_dicts(embeddings: Any, expected_rows: int) -> list[dict[int, float]]:
    """Coalesce a Torch sparse tensor and distribute positive values by output row."""
    sparse = embeddings if bool(getattr(embeddings, "is_sparse", False)) else embeddings.to_sparse()
    sparse = sparse.coalesce()
    indices = sparse.indices().detach().cpu().tolist()
    values = sparse.values().detach().cpu().tolist()
    rows: list[dict[int, float]] = [{} for _ in range(expected_rows)]
    if len(indices) == 2:
        for row, column, value in zip(indices[0], indices[1], values, strict=True):
            if 0 <= int(row) < expected_rows and float(value) > 0:
                rows[int(row)][int(column)] = float(value)
    return rows


def _sparse_row_to_dict(row: Any) -> dict[int, float]:
    """Convert a dense row or existing mapping to positive token weights."""
    if isinstance(row, dict):
        return _positive_weights(row)
    return {index: float(value) for index, value in enumerate(row) if float(value) > 0}


def _positive_weights(weights: dict[Any, Any]) -> dict[int, float]:
    """Coerce token IDs and retain only strictly positive weights."""
    return {int(token_id): float(weight) for token_id, weight in weights.items() if float(weight) > 0}


@contextmanager
def _offline_model_load(enabled: bool):
    """Temporarily force Hugging Face and Transformers offline mode, then restore the environment."""
    if not enabled:
        yield
        return
    old_hf = os.environ.get("HF_HUB_OFFLINE")
    old_tx = os.environ.get("TRANSFORMERS_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
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
