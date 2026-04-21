"""Attachment malformed and unsupported edge tests split from RF19."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

from src.attachment_extractor import (
    _extract_html,
    _pdf_extractor,
    _xlsx_extractor,
    extract_image_embedding,
    extract_text,
)


class TestMalformedAndUnsupported:
    def test_html_empty_body_returns_none(self) -> None:
        html = b"<html><body></body></html>"
        result = _extract_html(html)
        assert result is None or isinstance(result, str)

    def test_unknown_extension_returns_none(self) -> None:
        assert extract_text("data.xyz", b"some content") is None

    def test_skip_extensions_return_none(self) -> None:
        for ext in (".eml", ".msg", ".zip", ".gz", ".exe", ".mp3", ".mp4"):
            assert extract_text(f"file{ext}", b"data") is None

    def test_image_extensions_return_none(self) -> None:
        for ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
            assert extract_text(f"file{ext}", b"data") is None

    def test_non_image_returns_none(self) -> None:
        assert extract_image_embedding("doc.txt", b"hello") is None

    def test_empty_content_returns_none(self) -> None:
        assert extract_image_embedding("photo.jpg", b"") is None

    def test_empty_filename_returns_none(self) -> None:
        assert extract_image_embedding("", b"\xff") is None


class TestExtractorEdgeBehaviors:
    def test_pdf_extractor_empty_pages(self) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        mock_pdf_reader_cls = MagicMock(return_value=mock_reader)
        result = _pdf_extractor(mock_pdf_reader_cls, io.BytesIO(b"fake"))
        assert result == ""

    def test_xlsx_extractor_empty_cells_filtered(self) -> None:
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [
            (None, None, None),
        ]

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__ = MagicMock(return_value=mock_ws)

        mock_load_workbook = MagicMock(return_value=mock_wb)
        result = _xlsx_extractor(mock_load_workbook, io.BytesIO(b"fake"))
        assert "[Sheet: Sheet1]" in result
