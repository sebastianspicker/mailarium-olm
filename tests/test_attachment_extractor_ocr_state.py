"""Attachment OCR and extraction-state tests split from RF19."""

from __future__ import annotations

import builtins
import io
from unittest.mock import MagicMock, patch

from src.attachment_extractor import (
    MAX_EXTRACTED_CHARS,
    _optional_extract,
    _pptx_extractor,
    attachment_ocr_available_for,
    extract_image_embedding,
    is_image_attachment,
)


class TestOptionalExtract:
    def test_import_error_returns_none(self) -> None:
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "nonexistent_module":
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", mock_import):
            result = _optional_extract(
                b"content",
                "nonexistent_module",
                "SomeClass",
                lambda obj, stream: "text",
                "TEST",
            )
            assert result is None

    def test_attribute_error_returns_none(self) -> None:
        result = _optional_extract(
            b"content",
            "os",
            "nonexistent_attribute_xyz",
            lambda obj, stream: "text",
            "TEST",
        )
        assert result is None

    def test_extractor_success(self) -> None:
        def fake_extractor(obj, stream):
            return f"extracted with {obj.__name__}"

        result = _optional_extract(
            b"content",
            "os",
            "path",
            fake_extractor,
            "TEST",
        )
        assert result is not None
        assert "extracted with" in result

    def test_extractor_returns_empty_string(self) -> None:
        result = _optional_extract(
            b"content",
            "os",
            "path",
            lambda obj, stream: "",
            "TEST",
        )
        assert result is None

    def test_extractor_returns_none(self) -> None:
        result = _optional_extract(
            b"content",
            "os",
            "path",
            lambda obj, stream: None,
            "TEST",
        )
        assert result is None

    def test_extractor_exception_returns_none(self) -> None:
        def failing_extractor(obj, stream):
            raise RuntimeError("extraction failed")

        result = _optional_extract(
            b"content",
            "os",
            "path",
            failing_extractor,
            "TEST",
        )
        assert result is None

    def test_extractor_truncates_long_text(self) -> None:
        long_text = "x" * (MAX_EXTRACTED_CHARS + 500)

        result = _optional_extract(
            b"content",
            "os",
            "path",
            lambda obj, stream: long_text,
            "TEST",
        )
        assert result is not None
        assert "[... content truncated ...]" in result


class TestExtractImageEmbedding:
    def test_embedder_unavailable_returns_none(self) -> None:
        import src.attachment_extractor as mod

        mock_embedder = MagicMock()
        mock_embedder.is_available = False

        old = mod._image_embedder
        mod._image_embedder = mock_embedder
        try:
            result = extract_image_embedding("photo.jpg", b"\xff\xd8\xff\xe0")
            assert result is None
        finally:
            mod._image_embedder = old

    def test_embedder_available_returns_embedding(self) -> None:
        import src.attachment_extractor as mod

        mock_embedder = MagicMock()
        mock_embedder.is_available = True
        mock_embedder.encode_image.return_value = [0.1, 0.2, 0.3]

        old = mod._image_embedder
        mod._image_embedder = mock_embedder
        try:
            result = extract_image_embedding("photo.jpg", b"\xff\xd8\xff\xe0")
            assert result == [0.1, 0.2, 0.3]
            mock_embedder.encode_image.assert_called_once_with(b"\xff\xd8\xff\xe0", filename="photo.jpg")
        finally:
            mod._image_embedder = old

    def test_embedder_exception_returns_none(self) -> None:
        import src.attachment_extractor as mod

        mock_embedder = MagicMock()
        mock_embedder.is_available = True
        mock_embedder.encode_image.side_effect = RuntimeError("boom")

        old = mod._image_embedder
        mod._image_embedder = mock_embedder
        try:
            result = extract_image_embedding("photo.jpg", b"\xff\xd8\xff\xe0")
            assert result is None
        finally:
            mod._image_embedder = old


class TestIsImageAttachment:
    def test_supported_images(self) -> None:
        assert is_image_attachment("photo.jpg")
        assert is_image_attachment("photo.jpeg")
        assert is_image_attachment("photo.png")
        assert is_image_attachment("photo.bmp")
        assert is_image_attachment("photo.tiff")
        assert is_image_attachment("photo.tif")
        assert is_image_attachment("photo.webp")

    def test_unsupported_image(self) -> None:
        assert not is_image_attachment("anim.gif")
        assert not is_image_attachment("icon.svg")

    def test_non_image(self) -> None:
        assert not is_image_attachment("doc.pdf")

    def test_empty(self) -> None:
        assert not is_image_attachment("")


class TestExtractorStateEdges:
    def test_pptx_extractor_no_text_frame(self) -> None:
        mock_shape = MagicMock()
        mock_shape.has_text_frame = False

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        mock_presentation_cls = MagicMock(return_value=mock_prs)
        result = _pptx_extractor(mock_presentation_cls, io.BytesIO(b"fake"))
        assert "[Slide 1]" in result


class TestAttachmentOcrAvailability:
    def test_pdf_requires_pdftoppm_even_when_tesseract_exists(self, monkeypatch) -> None:
        monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
        monkeypatch.setattr("src.attachment_extractor.pdf_ocr_available", lambda: False)
        assert attachment_ocr_available_for("scan.pdf", mime_type="application/pdf") is False

    def test_pdf_available_when_both_tools_exist(self, monkeypatch) -> None:
        monkeypatch.setattr("src.attachment_extractor.pdf_ocr_available", lambda: True)
        assert attachment_ocr_available_for("scan.pdf", mime_type="application/pdf") is True

    def test_image_ocr_depends_on_tesseract_only(self, monkeypatch) -> None:
        monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
        assert attachment_ocr_available_for("photo.png", mime_type="image/png") is True
        monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
        assert attachment_ocr_available_for("photo.png", mime_type="image/png") is False
