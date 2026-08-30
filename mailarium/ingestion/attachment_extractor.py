"""Extract text content from common attachment file types."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path

from mailarium.model.attachment_identity import DEFAULT_ATTACHMENT_OCR_LANG
from mailarium.model.attachment_profiles import (
    IMAGE_EXTENSIONS as _IMAGE_EXTENSIONS,
)
from mailarium.model.attachment_profiles import (
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

logger = logging.getLogger(__name__)

_image_embedder = None


def _run_ocr_process(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    """Run an OCR subprocess command with safety checks."""
    executable = Path(command[0]).name if command else ""
    if executable not in {"tesseract", "pdftoppm"}:
        raise ValueError(f"Unsupported OCR executable: {executable!r}")
    return subprocess.run(  # nosemgrep
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _get_image_embedder():
    """Get or create the singleton image embedder instance."""
    global _image_embedder
    if _image_embedder is None:
        from mailarium.config import get_settings
        from mailarium.retrieval.image_embedder import ImageEmbedder

        settings = get_settings()
        _image_embedder = ImageEmbedder(
            model_name=settings.image_embedding_model,
            model_revision=settings.image_embedding_model_revision,
            device=settings.device,
            load_mode=settings.embedding_load_mode,
        )
    return _image_embedder


def extract_image_embedding(filename: str, content: bytes) -> list[float] | None:
    """Extract an embedding vector from an image attachment.

    Args:
        filename: The name of the attachment file.
        content: The raw bytes of the attachment.

    Returns:
        A list of float values representing the image embedding, or None if
        extraction fails or the file is not an image.
    """
    if not is_image_attachment(filename) or not content:
        return None
    try:
        embedder = _get_image_embedder()
        if not embedder.is_available:
            return None
        return embedder.encode_image(content, filename=filename)
    except RuntimeError, ValueError, OSError:
        return None


def _extract_pdf(content: bytes, failure_recorder=None) -> str | None:
    """Extract text from a PDF attachment.

    Args:
        content: The raw bytes of the PDF file.
        failure_recorder: Optional callable to record extraction failures.

    Returns:
        The extracted text as a string, or None if extraction fails.
    """
    return _optional_extract(content, "PyPDF2", "PdfReader", _pdf_extractor, "PDF", failure_recorder=failure_recorder)


def _extract_docx(content: bytes, failure_recorder=None) -> str | None:
    """Extract text from a DOCX attachment.

    Args:
        content: The raw bytes of the DOCX file.
        failure_recorder: Optional callable to record extraction failures.

    Returns:
        The extracted text as a string, or None if extraction fails.
    """
    return _optional_extract(content, "docx", "Document", _docx_extractor, "DOCX", failure_recorder=failure_recorder)


def _extract_xlsx(content: bytes, failure_recorder=None) -> str | None:
    """Extract text from an XLSX attachment.

    Args:
        content: The raw bytes of the XLSX file.
        failure_recorder: Optional callable to record extraction failures.

    Returns:
        The extracted text as a string, or None if extraction fails.
    """
    return _optional_extract(content, "openpyxl", "load_workbook", _xlsx_extractor, "XLSX", failure_recorder=failure_recorder)


def _extract_pptx(content: bytes, failure_recorder=None) -> str | None:
    """Extract text from a PPTX attachment.

    Args:
        content: The raw bytes of the PPTX file.
        failure_recorder: Optional callable to record extraction failures.

    Returns:
        The extracted text as a string, or None if extraction fails.
    """
    return _optional_extract(content, "pptx", "Presentation", _pptx_extractor, "PPTX", failure_recorder=failure_recorder)


def extract_text(filename: str, content: bytes, *, mime_type: str | None = None) -> str | None:
    """Extract text from an attachment file.

    Args:
        filename: The name of the attachment file.
        content: The raw bytes of the attachment.
        mime_type: Optional MIME type of the attachment.

    Returns:
        The extracted text as a string, or None if extraction fails.
    """
    text, _failure_reason = extract_text_with_reason(filename, content, mime_type=mime_type)
    return text


def extract_text_with_reason(filename: str, content: bytes, *, mime_type: str | None = None) -> tuple[str | None, str | None]:
    """Extract text from an attachment file with failure reason.

    Args:
        filename: The name of the attachment file.
        content: The raw bytes of the attachment.
        mime_type: Optional MIME type of the attachment.

    Returns:
        A tuple of (extracted_text, failure_reason) where extracted_text is the
        text content or None, and failure_reason is a string describing the
        failure or None if successful.
    """
    failure_reason: str | None = None

    def record_failure(reason: str) -> None:
        nonlocal failure_reason
        if not failure_reason:
            failure_reason = reason

    text = _extract_text_with_dispatch(
        filename,
        content,
        mime_type=mime_type,
        extractors={
            "plain": _extract_plain_text,
            "html": _extract_html,
            "pdf": lambda data: _extract_pdf(data, failure_recorder=record_failure),
            "docx": lambda data: _extract_docx(data, failure_recorder=record_failure),
            "xlsx": lambda data: _extract_xlsx(data, failure_recorder=record_failure),
            "ods": _extract_ods,
            "legacy_office": lambda data, label: _extract_legacy_binary_office(data, format_label=label),
            "pptx": lambda data: _extract_pptx(data, failure_recorder=record_failure),
        },
    )
    return text, failure_reason


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
    """Check if an attachment format supports OCR extraction.

    Args:
        filename: The name of the attachment file.
        mime_type: Optional MIME type of the attachment.

    Returns:
        True if the attachment format supports OCR (PDF or image formats),
        False otherwise.
    """
    ext = _dispatch_extension(filename, mime_type)
    return bool(ext == ".pdf" or is_image_attachment(filename))


def _write_temporary_attachment(content: bytes, *, suffix: str) -> str:
    """Materialize attachment bytes so external extractors can consume a path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        return temp_file.name


def _safe_unlink(path: str, *, message: str) -> None:
    """Delete a temporary path without masking the primary extraction result."""
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        logger.debug(message, exc_info=True)


def _ocr_psm() -> str:
    """Read and bound the configured Tesseract page-segmentation mode."""
    value = str(os.environ.get("ATTACHMENT_OCR_PSM", "6")).strip()
    return "6" if not value or not value.isdigit() else str(max(0, min(13, int(value))))


def _ocr_language() -> str:
    """Read a safe Tesseract language value or use the package default."""
    language = str(os.environ.get("ATTACHMENT_OCR_LANG", DEFAULT_ATTACHMENT_OCR_LANG) or "").strip()
    return DEFAULT_ATTACHMENT_OCR_LANG if not language or " " in language else language


def _pdf_ocr_max_pages() -> int:
    """Read and bound the number of PDF pages eligible for OCR."""
    try:
        return max(1, min(50, int(str(os.environ.get("ATTACHMENT_PDF_OCR_MAX_PAGES", "5")).strip())))
    except ValueError, TypeError:
        return 5


def _ocr_image_file(tesseract_path: str, image_path: str, *, timeout_seconds: int) -> str | None:
    """Run Tesseract for one image and return text when it succeeds."""
    command = [tesseract_path, image_path, "stdout", "--psm", _ocr_psm()]
    if language := _ocr_language():
        command.extend(["-l", language])
    result = _run_ocr_process(command, timeout_seconds=timeout_seconds)
    if result.returncode != 0:
        return None
    return _truncate(str(result.stdout or "").strip()) or None


def extract_image_text_ocr(filename: str, content: bytes, *, timeout_seconds: int = 30) -> str | None:
    """Best-effort OCR for image attachments using the local Tesseract binary."""
    if not is_image_attachment(filename) or not content or not image_ocr_available():
        return None
    tesseract_path = shutil.which("tesseract")
    if not tesseract_path:
        return None
    temp_path = ""
    try:
        temp_path = _write_temporary_attachment(content, suffix=Path(filename).suffix or ".img")
        return _ocr_image_file(tesseract_path, temp_path, timeout_seconds=timeout_seconds)
    except OSError, subprocess.SubprocessError:
        return None
    finally:
        _safe_unlink(temp_path, message="Failed to unlink temp file")


def _extract_rendered_pdf_page_text(temp_dir: str, *, timeout_seconds: int) -> str | None:
    """OCR rendered PDF pages in their existing lexicographic filename order."""
    page_texts: list[str] = []
    for page_path in sorted(Path(temp_dir).glob("page-*.png")):
        page_text = extract_image_text_ocr(page_path.name, page_path.read_bytes(), timeout_seconds=timeout_seconds)
        if page_text:
            page_texts.append(page_text)
    joined = "\n\n".join(page_texts).strip()
    return _truncate(joined) if joined else None


def extract_pdf_text_ocr(filename: str, content: bytes, *, timeout_seconds: int = 90) -> str | None:
    """Best-effort OCR for scanned PDFs using pdftoppm plus Tesseract."""
    if _dispatch_extension(filename) != ".pdf" or not content or not pdf_ocr_available():
        return None
    temp_pdf = ""
    temp_dir = ""
    try:
        temp_dir = tempfile.mkdtemp(prefix="pdf-ocr-")
        temp_pdf = _write_temporary_attachment(content, suffix=".pdf")
        output_prefix = str(Path(temp_dir) / "page")
        pdftoppm_path = shutil.which("pdftoppm")
        if not pdftoppm_path:
            return None
        render = _run_ocr_process(
            [pdftoppm_path, "-f", "1", "-l", str(_pdf_ocr_max_pages()), "-png", temp_pdf, output_prefix],
            timeout_seconds=timeout_seconds,
        )
        if render.returncode != 0:
            return None
        return _extract_rendered_pdf_page_text(temp_dir, timeout_seconds=timeout_seconds)
    except OSError, subprocess.SubprocessError, ValueError:
        return None
    finally:
        _safe_unlink(temp_pdf, message="Failed to unlink temp PDF")
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
    "extract_text_with_reason",
    "extraction_quality_profile",
    "image_ocr_available",
    "is_image_attachment",
    "pdf_ocr_available",
]
