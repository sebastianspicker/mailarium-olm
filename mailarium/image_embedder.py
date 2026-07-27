"""Optional SigLIP2 image/text embeddings in a dedicated vector space."""

from __future__ import annotations

import io
import logging
from typing import Any, Literal

import numpy as np

from .config import (
    DEFAULT_IMAGE_EMBEDDING_MODEL,
    DEFAULT_IMAGE_EMBEDDING_MODEL_REVISION,
    _require_model_revision,
    resolve_device,
    resolve_embedding_load_mode,
)

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"})
_DEFAULT_MODEL = DEFAULT_IMAGE_EMBEDDING_MODEL
_DEFAULT_MAX_BYTES = 25 * 1024 * 1024
_DEFAULT_MAX_PIXELS = 40_000_000


def is_image_file(filename: str) -> bool:
    """Check if a filename has a supported image extension."""
    dot_pos = filename.rfind(".")
    return dot_pos >= 0 and filename[dot_pos:].lower() in _IMAGE_EXTENSIONS


class ImageEmbedder:
    """Encode images and text queries with standard Transformers SigLIP2."""

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        *,
        model_revision: str | None = None,
        device: str = "auto",
        load_mode: str = "auto",
        max_bytes: int = _DEFAULT_MAX_BYTES,
        max_pixels: int = _DEFAULT_MAX_PIXELS,
    ) -> None:
        """Configure deferred SigLIP2 loading from explicit model and device settings."""
        self.model_name = model_name
        self.model_revision = (
            model_revision
            if model_revision is not None
            else DEFAULT_IMAGE_EMBEDDING_MODEL_REVISION
            if model_name == DEFAULT_IMAGE_EMBEDDING_MODEL
            else ""
        )
        self.model_revision = _require_model_revision(self.model_revision, variable_name="model_revision")
        self.device = resolve_device(device)
        self.load_mode = resolve_embedding_load_mode(load_mode)
        self.max_bytes = max(int(max_bytes), 1)
        self.max_pixels = max(int(max_pixels), 1)
        self._model: Any | None = None
        self._processor: Any | None = None
        self._load_error: str = ""

    @property
    def is_available(self) -> bool:
        """Whether the optional model can be loaded without remote code."""
        try:
            self._ensure_loaded()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self._load_error = str(exc)
            logger.info("SigLIP2 image embedding unavailable: %s", exc)
            return False
        return self._model is not None and self._processor is not None

    def encode_image(self, image_bytes: bytes, filename: str = "") -> list[float] | None:
        """Validate and encode one image without writing it to disk."""
        if not image_bytes or len(image_bytes) > self.max_bytes:
            return None
        if filename and not is_image_file(filename):
            return None
        try:
            image = _validated_image(image_bytes, max_pixels=self.max_pixels)
            self._ensure_loaded()
            assert self._model is not None and self._processor is not None
            inputs = self._processor(images=image, return_tensors="pt")
            inputs = {name: value.to(self.device) for name, value in inputs.items()}
            with _torch_inference():
                features = self._model.get_image_features(**inputs)
            return _normalized_vector(features)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Failed to encode image %s", filename, exc_info=True)
            return None

    def encode_text(self, text: str) -> list[float] | None:
        """Encode a text query into the aligned image-search space."""
        if not text.strip():
            return None
        try:
            self._ensure_loaded()
            assert self._model is not None and self._processor is not None
            inputs = self._processor(text=[text], padding="max_length", return_tensors="pt")
            inputs = {name: value.to(self.device) for name, value in inputs.items()}
            with _torch_inference():
                features = self._model.get_text_features(**inputs)
            return _normalized_vector(features)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Failed to encode image-search text", exc_info=True)
            return None

    def encode_image_batch(self, images: list[bytes]) -> list[list[float] | None]:
        """Encode a bounded list while preserving row alignment."""
        return [self.encode_image(image) for image in images]

    def runtime_summary(self) -> dict[str, Any]:
        """Report model, device, and load state without forcing initialization."""
        return {
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "device": self.device,
            "load_mode": self.load_mode,
            "loaded": self._model is not None,
            "load_error": self._load_error,
        }

    def _ensure_loaded(self) -> None:
        """Load the image model and processor once before inference."""
        if self._model is not None and self._processor is not None:
            return
        from transformers import AutoModel, AutoProcessor

        load_options: dict[str, Any] = {
            "trust_remote_code": False,
        }
        if self.load_mode == "local_only":
            load_options["local_files_only"] = True
        self._processor = AutoProcessor.from_pretrained(
            self.model_name,
            revision=self.model_revision,
            **load_options,
        )
        self._model = AutoModel.from_pretrained(
            self.model_name,
            revision=self.model_revision,
            use_safetensors=True,
            **load_options,
        ).to(self.device)
        self._model.eval()


def _validated_image(image_bytes: bytes, *, max_pixels: int) -> Any:
    """Decode bytes into a valid RGB image or raise a clear input error."""
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > max_pixels:
            raise ValueError("image dimensions exceed the configured safety limit")
        return image.convert("RGB")


def _normalized_vector(features: Any) -> list[float]:
    """Convert model output to a unit vector and reject degenerate embeddings."""
    if hasattr(features, "detach"):
        features = features.detach().cpu().float().numpy()
    array = np.asarray(features, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(array))
    if norm <= 1e-12:
        raise ValueError("image embedding has zero norm")
    return (array / norm).tolist()


class _torch_inference:
    """Enter inference mode and disable gradient tracking for image encoding."""

    def __enter__(self) -> None:
        """Enter the scoped runtime configuration."""
        import torch

        self._context = torch.inference_mode()
        self._context.__enter__()

    def __exit__(self, exc_type, exc, traceback) -> Literal[False]:
        """Restore runtime state after the scoped operation."""
        self._context.__exit__(exc_type, exc, traceback)
        return False
