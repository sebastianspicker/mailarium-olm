"""Attachment text extraction tests split from RF19."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from src.attachment_extractor import (
    MAX_EXTRACTED_CHARS,
    _docx_extractor,
    _extract_docx,
    _extract_html,
    _extract_pdf,
    _extract_plain_text,
    _extract_xlsx,
    _get_extension,
    _pdf_extractor,
    _pptx_extractor,
    _truncate,
    _xlsx_extractor,
    extract_text,
)


class TestGetExtension:
    def test_no_dot_returns_empty(self) -> None:
        assert _get_extension("noextension") == ""

    def test_dot_file(self) -> None:
        assert _get_extension(".gitignore") == ".gitignore"

    def test_multiple_dots(self) -> None:
        assert _get_extension("archive.tar.gz") == ".gz"

    def test_uppercase_normalized(self) -> None:
        assert _get_extension("FILE.PDF") == ".pdf"


class TestTruncate:
    def test_short_text_unchanged(self) -> None:
        assert _truncate("hello") == "hello"

    def test_exact_limit_unchanged(self) -> None:
        text = "x" * MAX_EXTRACTED_CHARS
        assert _truncate(text) == text

    def test_over_limit_truncated(self) -> None:
        text = "x" * (MAX_EXTRACTED_CHARS + 100)
        result = _truncate(text)
        assert result.endswith("[... content truncated ...]")
        assert len(result) < len(text)


class TestExtractPlainText:
    def test_utf8_text(self) -> None:
        result = _extract_plain_text(b"Hello world")
        assert result == "Hello world"

    def test_latin1_fallback(self) -> None:
        content = "Ärger mit Ümlauten".encode("latin-1")
        result = _extract_plain_text(content)
        assert result is not None
        assert "rger" in result

    def test_empty_text_returns_none(self) -> None:
        assert _extract_plain_text(b"   \n  ") is None

    def test_latin1_fallback_always_succeeds(self) -> None:
        result = _extract_plain_text(b"\xff\xfeHello")
        assert result is not None


class TestExtractHtml:
    def test_basic_html(self) -> None:
        html = b"<html><body><p>Test paragraph</p></body></html>"
        result = _extract_html(html)
        assert result is not None
        assert "Test paragraph" in result

    def test_html_latin1_fallback(self) -> None:
        html = "<html><body><p>Ärger</p></body></html>".encode("latin-1")
        result = _extract_html(html)
        assert result is not None

    def test_html_latin1_fallback_always_succeeds(self) -> None:
        result = _extract_html(b"\xff\xfe<p>Hello</p>")
        assert result is not None


class TestExtractTextRouting:
    def test_pdf_route(self) -> None:
        with patch("src.attachment_extractor._extract_pdf", return_value="PDF text") as mock_extract:
            result = extract_text("doc.pdf", b"fake")
            assert result == "PDF text"
            mock_extract.assert_called_once()

    def test_docx_route(self) -> None:
        with patch("src.attachment_extractor._extract_docx", return_value="DOCX text") as mock_extract:
            result = extract_text("doc.docx", b"fake")
            assert result == "DOCX text"
            mock_extract.assert_called_once()

    def test_xlsx_route(self) -> None:
        with patch("src.attachment_extractor._extract_xlsx", return_value="XLSX text") as mock_extract:
            result = extract_text("data.xlsx", b"fake")
            assert result == "XLSX text"
            mock_extract.assert_called_once()

    def test_pptx_route(self) -> None:
        with patch("src.attachment_extractor._extract_pptx", return_value="PPTX text") as mock_extract:
            result = extract_text("slides.pptx", b"fake")
            assert result == "PPTX text"
            mock_extract.assert_called_once()

    def test_htm_route(self) -> None:
        with patch("src.attachment_extractor._extract_html", return_value="HTML text") as mock_extract:
            result = extract_text("page.htm", b"fake")
            assert result == "HTML text"
            mock_extract.assert_called_once()

    def test_text_extensions_all_work(self) -> None:
        for ext in (
            ".txt",
            ".csv",
            ".log",
            ".md",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
            ".ini",
            ".cfg",
            ".conf",
            ".tsv",
            ".rst",
        ):
            result = extract_text(f"file{ext}", b"content")
            assert result == "content", f"Failed for {ext}"


class TestPdfExtractor:
    def test_pdf_extractor_function(self) -> None:
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 content"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page1, mock_page2]

        mock_pdf_reader_cls = MagicMock(return_value=mock_reader)
        stream = io.BytesIO(b"fake pdf")

        result = _pdf_extractor(mock_pdf_reader_cls, stream)
        assert "Page 1 content" in result
        assert "Page 2 content" in result

    def test_extract_pdf_via_optional(self) -> None:
        with patch("src.attachment_extractor._optional_extract", return_value="PDF out") as mock_extract:
            result = _extract_pdf(b"content")
            assert result == "PDF out"
            mock_extract.assert_called_once()


class TestDocxExtractor:
    def test_docx_extractor_function(self) -> None:
        mock_para1 = MagicMock()
        mock_para1.text = "Paragraph one"
        mock_para2 = MagicMock()
        mock_para2.text = "Paragraph two"
        mock_para3 = MagicMock()
        mock_para3.text = "   "

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]

        mock_document_cls = MagicMock(return_value=mock_doc)
        result = _docx_extractor(mock_document_cls, io.BytesIO(b"fake"))
        assert "Paragraph one" in result
        assert "Paragraph two" in result

    def test_extract_docx_via_optional(self) -> None:
        with patch("src.attachment_extractor._optional_extract", return_value="DOCX out") as mock_extract:
            result = _extract_docx(b"content")
            assert result == "DOCX out"
            mock_extract.assert_called_once()


class TestXlsxExtractor:
    def test_xlsx_extractor_function(self) -> None:
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [
            ("Name", "Value"),
            ("Alice", 100),
            (None, None),
        ]

        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__ = MagicMock(return_value=mock_ws)

        mock_load_workbook = MagicMock(return_value=mock_wb)
        result = _xlsx_extractor(mock_load_workbook, io.BytesIO(b"fake"))
        assert "[Sheet: Sheet1]" in result
        assert "Alice" in result

    def test_extract_xlsx_via_optional(self) -> None:
        with patch("src.attachment_extractor._optional_extract", return_value="XLSX out") as mock_extract:
            result = _extract_xlsx(b"content")
            assert result == "XLSX out"
            mock_extract.assert_called_once()


class TestPptxExtractor:
    def test_pptx_extractor_function(self) -> None:
        mock_para = MagicMock()
        mock_para.text = "Slide text"

        mock_text_frame = MagicMock()
        mock_text_frame.paragraphs = [mock_para]

        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text_frame = mock_text_frame

        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]

        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        mock_presentation_cls = MagicMock(return_value=mock_prs)
        result = _pptx_extractor(mock_presentation_cls, io.BytesIO(b"fake"))
        assert "[Slide 1]" in result
        assert "Slide text" in result
