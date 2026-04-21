"""Extract text content from common attachment file types."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .attachment_extractor_profiles import (
    SOURCE_FORMAT_INGESTION_MATRIX_VERSION,
    attachment_format_profile,
    extraction_quality_profile,
)
from .attachment_extractor_text import (
    _ARCHIVE_INVENTORY_HEADER,
    _ARCHIVE_TEXT_HEADER,
    MAX_EXTRACTED_CHARS,
    _decode_text_bytes,
    _dispatch_extension,
    _docx_extractor,
    _extract_html,
    _extract_legacy_binary_office,
    _extract_ods,
    _extract_plain_text,
    _extract_text_with_dispatch,
    _get_extension,
    _optional_extract,
    _pdf_extractor,
    _pptx_extractor,
    _truncate,
    _xlsx_extractor,
    is_image_attachment,
)
from .attachment_identity import DEFAULT_ATTACHMENT_OCR_LANG
from .image_embedder import _IMAGE_EXTENSIONS

_image_embedder = None


def _get_image_embedder():
    global _image_embedder
    if _image_embedder is None:
        from .image_embedder import ImageEmbedder

        _image_embedder = ImageEmbedder()
    return _image_embedder


def extract_image_embedding(filename: str, content: bytes) -> list[float] | None:
    if not is_image_attachment(filename) or not content:
        return None
    try:
        embedder = _get_image_embedder()
        if not embedder.is_available:
            return None
        return embedder.encode_image(content, filename=filename)
    except Exception:
        return None


def _extract_pdf(content: bytes) -> str | None:
    return _optional_extract(content, "PyPDF2", "PdfReader", _pdf_extractor, "PDF")


def _extract_docx(content: bytes) -> str | None:
    return _optional_extract(content, "docx", "Document", _docx_extractor, "DOCX")


def _extract_xlsx(content: bytes) -> str | None:
    return _optional_extract(content, "openpyxl", "load_workbook", _xlsx_extractor, "XLSX")


def _extract_pptx(content: bytes) -> str | None:
    return _optional_extract(content, "pptx", "Presentation", _pptx_extractor, "PPTX")


def extract_text(filename: str, content: bytes, *, mime_type: str | None = None) -> str | None:
    return _extract_text_with_dispatch(
        filename,
        content,
        mime_type=mime_type,
        plain_text_extractor=_extract_plain_text,
        html_extractor=_extract_html,
        pdf_extractor=_extract_pdf,
        docx_extractor=_extract_docx,
        xlsx_extractor=_extract_xlsx,
        ods_extractor=_extract_ods,
        legacy_office_extractor=lambda data, label: _extract_legacy_binary_office(data, format_label=label),
        pptx_extractor=_extract_pptx,
    )


def image_ocr_available() -> bool:
    """Return whether the local Tesseract OCR binary is available."""
    return bool(shutil.which("tesseract"))


def pdf_ocr_available() -> bool:
    """Return whether local PDF OCR tooling is available."""
    return image_ocr_available() and bool(shutil.which("pdftoppm"))


def attachment_ocr_available() -> bool:
    """Return whether any supported attachment OCR path is available."""
    return image_ocr_available() or pdf_ocr_available()


def attachment_ocr_available_for(filename: str, *, mime_type: str | None = None) -> bool:
    """Return whether OCR is available for this specific attachment format."""
    ext = _dispatch_extension(filename, mime_type)
    if ext == ".pdf":
        return pdf_ocr_available()
    if is_image_attachment(filename):
        return image_ocr_available()
    return False


def attachment_supports_ocr(filename: str, *, mime_type: str | None = None) -> bool:
    ext = _dispatch_extension(filename, mime_type)
    return bool(ext == ".pdf" or is_image_attachment(filename))


def extract_image_text_ocr(filename: str, content: bytes, *, timeout_seconds: int = 30) -> str | None:
    """Best-effort OCR for image attachments using the local Tesseract binary."""
    if not is_image_attachment(filename) or not content or not image_ocr_available():
        return None
    suffix = Path(filename).suffix or ".img"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        command = ["tesseract", temp_path, "stdout", "--psm", os.environ.get("ATTACHMENT_OCR_PSM", "6")]
        language_hint = str(os.environ.get("ATTACHMENT_OCR_LANG", DEFAULT_ATTACHMENT_OCR_LANG) or "").strip()
        if not language_hint:
            language_hint = DEFAULT_ATTACHMENT_OCR_LANG
        if language_hint:
            command.extend(["-l", language_hint])
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            return None
        text = _truncate(str(result.stdout or "").strip())
        return text or None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def extract_pdf_text_ocr(filename: str, content: bytes, *, timeout_seconds: int = 90) -> str | None:
    """Best-effort OCR for scanned PDFs using pdftoppm plus Tesseract."""
    if _dispatch_extension(filename) != ".pdf" or not content or not pdf_ocr_available():
        return None
    temp_pdf = ""
    temp_dir = ""
    try:
        temp_dir = tempfile.mkdtemp(prefix="pdf-ocr-")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(content)
            temp_pdf = temp_file.name
        output_prefix = str(Path(temp_dir) / "page")
        max_pages = max(1, int(os.environ.get("ATTACHMENT_PDF_OCR_MAX_PAGES", "5")))
        render = subprocess.run(
            ["pdftoppm", "-f", "1", "-l", str(max_pages), "-png", temp_pdf, output_prefix],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if render.returncode != 0:
            return None
        page_paths = sorted(Path(temp_dir).glob("page-*.png"))
        page_texts: list[str] = []
        for page_path in page_paths:
            page_bytes = page_path.read_bytes()
            page_text = extract_image_text_ocr(page_path.name, page_bytes, timeout_seconds=timeout_seconds)
            if page_text:
                page_texts.append(page_text)
        joined = "\n\n".join(page_texts).strip()
        return _truncate(joined) if joined else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        if temp_pdf:
            try:
                os.unlink(temp_pdf)
            except OSError:
                pass
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def extract_attachment_text_ocr(filename: str, content: bytes, *, timeout_seconds: int = 90) -> str | None:
    """Best-effort OCR for supported attachment types."""
    ext = _dispatch_extension(filename)
    if ext == ".pdf":
        return extract_pdf_text_ocr(filename, content, timeout_seconds=timeout_seconds)
    return extract_image_text_ocr(filename, content, timeout_seconds=min(timeout_seconds, 30))


def classify_text_extraction_state(filename: str, text: str, *, ocr_used: bool = False) -> str:
    """Return a normalized extraction-state label for extracted attachment text."""
    if ocr_used:
        return "ocr_text_extracted"
    compact = str(text or "").strip()
    ext = _dispatch_extension(filename)
    if ext == ".zip":
        if compact.startswith(_ARCHIVE_TEXT_HEADER):
            return "archive_contents_extracted"
        if compact.startswith(_ARCHIVE_INVENTORY_HEADER):
            return "archive_inventory_extracted"
    return "text_extracted"


__all__ = [
    "MAX_EXTRACTED_CHARS",
    "SOURCE_FORMAT_INGESTION_MATRIX_VERSION",
    "_ARCHIVE_INVENTORY_HEADER",
    "_ARCHIVE_TEXT_HEADER",
    "_IMAGE_EXTENSIONS",
    "_decode_text_bytes",
    "_dispatch_extension",
    "_docx_extractor",
    "_extract_docx",
    "_extract_html",
    "_extract_legacy_binary_office",
    "_extract_ods",
    "_extract_pdf",
    "_extract_plain_text",
    "_extract_pptx",
    "_extract_text_with_dispatch",
    "_extract_xlsx",
    "_get_extension",
    "_get_image_embedder",
    "_image_embedder",
    "_optional_extract",
    "_pdf_extractor",
    "_pptx_extractor",
    "_truncate",
    "_xlsx_extractor",
    "attachment_format_profile",
    "attachment_ocr_available",
    "attachment_ocr_available_for",
    "attachment_supports_ocr",
    "classify_text_extraction_state",
    "extract_attachment_text_ocr",
    "extract_image_embedding",
    "extract_image_text_ocr",
    "extract_pdf_text_ocr",
    "extract_text",
    "extraction_quality_profile",
    "image_ocr_available",
    "is_image_attachment",
    "pdf_ocr_available",
]
