"""Tests for image embedding and attachment routing."""

from __future__ import annotations

from src.attachment_extractor import (
    _IMAGE_EXTENSIONS,
    extract_image_embedding,
    extract_text,
    is_image_attachment,
)
from src.image_embedder import _WEIGHT_SEARCH_PATHS, ImageEmbedder, is_image_file

# ── is_image_file / is_image_attachment ───────────────────────────


def test_is_image_file_jpg():
    assert is_image_file("photo.jpg")


def test_is_image_file_png():
    assert is_image_file("screenshot.PNG")


def test_is_image_file_webp():
    assert is_image_file("image.webp")


def test_is_image_file_gif_not_supported():
    # GIF is not supported for embedding
    assert not is_image_file("animation.gif")


def test_is_image_file_pdf():
    assert not is_image_file("document.pdf")


def test_is_image_file_empty():
    assert not is_image_file("")


def test_is_image_file_no_extension():
    assert not is_image_file("noextension")


def test_is_image_attachment_jpg():
    assert is_image_attachment("photo.jpeg")


def test_is_image_attachment_not_image():
    assert not is_image_attachment("doc.txt")


def test_is_image_attachment_empty():
    assert not is_image_attachment("")


# ── ImageEmbedder initialization ────────────────────────────────


def test_image_embedder_no_weights():
    """Without weight file, embedder reports unavailable."""
    embedder = ImageEmbedder(weight_path="/nonexistent/path/weights.pth")
    assert not embedder.is_available


def test_image_embedder_no_weight_path():
    """Without any weight path (default), embedder is unavailable if no file exists."""
    # The default search paths are unlikely to exist in CI
    embedder = ImageEmbedder()
    # Should gracefully handle missing weights
    assert isinstance(embedder.is_available, bool)


def test_image_embedder_encode_when_unavailable():
    """Encoding returns None when embedder is not available."""
    embedder = ImageEmbedder(weight_path="/nonexistent/weights.pth")
    result = embedder.encode_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    assert result is None


def test_image_embedder_encode_empty_bytes():
    embedder = ImageEmbedder(weight_path="/nonexistent/weights.pth")
    assert embedder.encode_image(b"") is None


def test_image_embedder_batch_when_unavailable():
    embedder = ImageEmbedder(weight_path="/nonexistent/weights.pth")
    results = embedder.encode_image_batch([b"img1", b"img2"])
    assert results == [None, None]


# ── attachment_extractor routing ────────────────────────────────


def test_extract_text_skips_images():
    """Images should return None from extract_text (not extracted as text)."""
    assert extract_text("photo.jpg", b"\xff\xd8\xff\xe0") is None
    assert extract_text("screenshot.png", b"\x89PNG") is None
    assert extract_text("scan.tiff", b"II*\x00") is None


def test_extract_image_embedding_without_model():
    """Without Visualized-BGE, returns None gracefully."""
    result = extract_image_embedding("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    assert result is None


def test_extract_image_embedding_not_image():
    """Non-image files should return None."""
    assert extract_image_embedding("doc.txt", b"hello") is None


def test_extract_image_embedding_empty():
    assert extract_image_embedding("photo.jpg", b"") is None
    assert extract_image_embedding("", b"\xff\xd8") is None


def test_image_extensions_set():
    """Verify expected extensions are in the set."""
    assert ".jpg" in _IMAGE_EXTENSIONS
    assert ".jpeg" in _IMAGE_EXTENSIONS
    assert ".png" in _IMAGE_EXTENSIONS
    assert ".webp" in _IMAGE_EXTENSIONS
    assert ".tiff" in _IMAGE_EXTENSIONS
    assert ".bmp" in _IMAGE_EXTENSIONS


def test_weight_search_paths():
    """Verify default weight search paths are defined."""
    assert len(_WEIGHT_SEARCH_PATHS) >= 1
    for p in _WEIGHT_SEARCH_PATHS:
        assert "Visualized_m3.pth" in str(p)


# ── ImageEmbedder singleton ──────────────────────────────────────


def test_image_embedder_singleton():
    """_get_image_embedder() should return the same instance on repeated calls."""
    import src.attachment_extractor as mod

    # Reset singleton for clean test
    mod._image_embedder = None

    first = mod._get_image_embedder()
    second = mod._get_image_embedder()
    assert first is second

    # Cleanup
    mod._image_embedder = None
