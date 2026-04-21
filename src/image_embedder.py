"""Embed images into the same 1024-d vector space as text using Visualized-BGE-M3.

bge-visualized-m3 extends BGE-M3 with a vision encoder that maps images
into the same embedding space as text. This enables cross-modal retrieval:
text queries can find relevant image attachments and vice versa.

Requirements:
- FlagEmbedding >= 1.3.0 with visual support
- Weight file: Visualized_m3.pth (~2.3 GB, auto-downloaded on first use)

When Visualized-BGE is not available, falls back gracefully to None.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .transformers_compat import ensure_flagembedding_transformers_compat

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
    }
)

# Default search paths for the weight file
_WEIGHT_SEARCH_PATHS = [
    Path("models/Visualized_m3.pth"),
    Path.home() / ".cache" / "bge-visualized" / "Visualized_m3.pth",
]

# HuggingFace Hub repo and filename for auto-download
_HF_REPO_ID = "BAAI/bge-visualized"
_HF_FILENAME = "Visualized_m3.pth"


def is_image_file(filename: str) -> bool:
    """Check if a filename has a supported image extension."""
    dot_pos = filename.rfind(".")
    if dot_pos == -1:
        return False
    return filename[dot_pos:].lower() in _IMAGE_EXTENSIONS


class ImageEmbedder:
    """Embed images into the BGE-M3 1024-d vector space.

    Uses Visualized-BGE-M3 when available, otherwise reports unavailability.
    """

    def __init__(
        self,
        weight_path: str | None = None,
        model_name: str = "BAAI/bge-m3",
    ) -> None:
        self._model = None
        self._available = False
        self._weight_path = self._resolve_weight_path(weight_path)

        if self._weight_path:
            self._try_load(model_name)

    @property
    def is_available(self) -> bool:
        """Whether the image embedder is ready to encode images."""
        return self._available

    def encode_image(self, image_bytes: bytes, filename: str = "") -> list[float] | None:
        """Encode an image into a 1024-d embedding vector.

        Args:
            image_bytes: Raw image file bytes (PNG, JPG, etc.).
            filename: Original filename, used to infer the correct image
                format extension for the temp file.

        Returns:
            1024-d embedding list, or None if unavailable or encoding fails.
        """
        if not self._available or not image_bytes:
            return None

        try:
            import tempfile

            # Visualized-BGE requires a file path, not bytes.
            # Preserve the original extension so the image decoder uses the
            # correct format (JPG, BMP, TIFF, etc.) instead of always assuming PNG.
            ext = Path(filename).suffix.lower() if filename else ".png"
            if ext not in _IMAGE_EXTENSIONS:
                ext = ".png"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                tmp_path = f.name
                os.chmod(f.name, 0o600)  # restrict permissions before writing content
                f.write(image_bytes)

            try:
                embedding = self._model.encode(image=tmp_path)
                # Normalize to list of floats
                if hasattr(embedding, "tolist"):
                    return embedding.tolist()
                return list(embedding)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except Exception:
            logger.debug("Failed to encode image", exc_info=True)
            return None

    def encode_image_batch(
        self,
        images: list[bytes],
    ) -> list[list[float] | None]:
        """Encode multiple images.

        Args:
            images: List of raw image bytes.

        Returns:
            List of 1024-d embeddings (None for failures).
        """
        return [self.encode_image(img) for img in images]

    def _resolve_weight_path(self, explicit_path: str | None) -> str | None:
        """Find or auto-download the Visualized-BGE weight file."""
        if explicit_path:
            p = Path(explicit_path)
            if p.exists():
                return str(p)
            logger.warning("Weight file not found: %s", explicit_path)
            return None

        for candidate in _WEIGHT_SEARCH_PATHS:
            if candidate.exists():
                logger.info("Found Visualized-BGE weights: %s", candidate)
                return str(candidate)

        # Auto-download if not disabled
        if os.environ.get("IMAGE_EMBED_AUTO_DOWNLOAD", "1") == "0":
            logger.info(
                "Visualized-BGE weight file not found and auto-download disabled. "
                "Set IMAGE_EMBED_AUTO_DOWNLOAD=1 or download manually to: %s",
                _WEIGHT_SEARCH_PATHS[0],
            )
            return None

        return self._auto_download()

    # NOTE: _auto_download, _try_load, and encode_image each have exception
    # handling blocks that look similar at first glance but differ in log levels
    # (info vs warning vs debug), recovery semantics, and return types.
    # Kept as separate blocks intentionally — a shared helper would obscure the
    # per-method error context without meaningful deduplication.

    def _auto_download(self) -> str | None:
        """Download Visualized_m3.pth from HuggingFace Hub."""
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            logger.info(
                "huggingface_hub not installed — cannot auto-download Visualized-BGE weights. "
                "Install it or download manually to: %s",
                _WEIGHT_SEARCH_PATHS[0],
            )
            return None

        target_dir = _WEIGHT_SEARCH_PATHS[1].parent  # ~/.cache/bge-visualized/
        logger.info(
            "Auto-downloading Visualized-BGE weights (~2.3 GB) from %s/%s ...",
            _HF_REPO_ID,
            _HF_FILENAME,
        )
        try:
            downloaded = hf_hub_download(
                repo_id=_HF_REPO_ID,
                filename=_HF_FILENAME,
                revision="a53c18db9fd0015b8f8d6a8d778a20a20d4cc21b",
                local_dir=str(target_dir),
            )
            logger.info("Visualized-BGE weights downloaded to: %s", downloaded)
            return downloaded
        except Exception:
            logger.warning(
                "Failed to download Visualized-BGE weights. Download manually from https://huggingface.co/%s and place at: %s",
                _HF_REPO_ID,
                _WEIGHT_SEARCH_PATHS[0],
                exc_info=True,
            )
            return None

    def _try_load(self, model_name: str) -> None:
        """Attempt to load the Visualized-BGE model."""
        try:
            ensure_flagembedding_transformers_compat()
            from FlagEmbedding.visual.modeling import Visualized_BGE

            self._model = Visualized_BGE(
                model_name_bge=model_name,
                model_weight=self._weight_path,
            )
            self._available = True
            logger.info("Visualized-BGE loaded from %s", self._weight_path)
        except ImportError:
            logger.info("FlagEmbedding visual module not available. Install FlagEmbedding >= 1.3.0 for image embedding.")
        except Exception:
            logger.warning("Failed to load Visualized-BGE model", exc_info=True)
