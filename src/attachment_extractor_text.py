"""Attachment text and image embedding extraction helpers."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-positional-arguments,too-many-return-statements

from __future__ import annotations

import email
import email.policy
import io
import logging
import re
import zipfile
from collections.abc import Callable
from typing import Any, cast

from .image_embedder import _IMAGE_EXTENSIONS
from .rfc2822 import _extract_body_from_source, _extract_header

logger = logging.getLogger(__name__)

MAX_EXTRACTED_CHARS = 50_000

_TEXT_EXTENSIONS = frozenset(
    {
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
        ".ics",
        ".ical",
        ".vcs",
        ".rtf",
        ".odt",
        ".doc",
    }
)

_SKIP_EXTENSIONS = frozenset(
    {
        ".msg",
        ".gz",
        ".tar",
        ".rar",
        ".7z",
        ".exe",
        ".dll",
        ".bin",
        ".dat",
        ".iso",
        ".gif",
        ".ico",
        ".svg",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".mkv",
        ".flac",
        ".ppt",
    }
)

_MIME_EXTENSION_MAP = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/tab-separated-values": ".tsv",
    "application/json": ".json",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "text/calendar": ".ics",
    "application/ics": ".ics",
    "application/rtf": ".rtf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
}

_MIME_OVERRIDE_EXTENSIONS = frozenset({"", ".bin", ".dat"})

_image_embedder: object | None = None
_ARCHIVE_TEXT_HEADER = "[Archive extracted member text]"
_ARCHIVE_INVENTORY_HEADER = "[Archive member inventory]"
_MAX_ARCHIVE_MEMBERS = 20
_MAX_ARCHIVE_MEMBER_BYTES = 2_000_000


def _get_extension(filename: str) -> str:
    """Extract the file extension from a filename.

    Args:
        filename: The filename to extract the extension from.

    Returns:
        The lowercase file extension including the dot, or empty string if no extension.
    """
    dot_pos = filename.rfind(".")
    if dot_pos == -1:
        return ""
    return filename[dot_pos:].lower()


def is_image_attachment(filename: str) -> bool:
    """Check if a filename is a supported image format for embedding."""
    if not filename:
        return False
    return _get_extension(filename) in _IMAGE_EXTENSIONS


def _dispatch_extension(filename: str, mime_type: str | None = None) -> str:
    """Determine the effective extension for a file, considering MIME type overrides.

    Args:
        filename: The filename to check.
        mime_type: Optional MIME type to use for override mapping.

    Returns:
        The determined extension string.
    """
    ext = _get_extension(filename)
    normalized_mime = str(mime_type or "").split(";", 1)[0].strip().lower()
    mime_ext = _MIME_EXTENSION_MAP.get(normalized_mime, "")
    if mime_ext and ext in _MIME_OVERRIDE_EXTENSIONS:
        return mime_ext
    return ext or mime_ext


def _get_image_embedder():
    """Return the module-level ImageEmbedder singleton (lazy-init).

    Returns:
        The ImageEmbedder instance, initializing it if necessary.
    """
    global _image_embedder  # pylint: disable=global-statement
    if _image_embedder is None:
        from .image_embedder import ImageEmbedder

        _image_embedder = ImageEmbedder()
    return _image_embedder


def extract_image_embedding(filename: str, content: bytes) -> list[float] | None:
    """Encode an image attachment into a 1024-d embedding vector."""
    if not is_image_attachment(filename) or not content:
        return None

    try:
        embedder = _get_image_embedder()
        if not embedder.is_available:
            return None
        return embedder.encode_image(content, filename=filename)
    except (RuntimeError, ValueError, OSError):
        logger.debug("Failed to encode image attachment: %s", filename, exc_info=True)
        return None


def _extract_text_with_dispatch(
    filename: str,
    content: bytes,
    *,
    mime_type: str | None = None,
    extractors: dict[str, Callable[..., str | None]],
) -> str | None:
    """Shared routing matrix for attachment text extraction.

    Args:
        filename: The filename to extract text from.
        content: The raw bytes to extract text from.
        mime_type: Optional MIME type for extension dispatch override.
        extractors: Named extractors for the supported attachment formats.

    Returns:
        The extracted text, or None if no matching extractor found.
    """
    if not filename or not content:
        return None

    ext = _dispatch_extension(filename, mime_type)
    if ext == ".eml":
        return _extract_eml(content)
    if ext == ".zip":
        return _extract_zip_archive(content, extractors=extractors)
    return _extract_standard_attachment(ext, content, extractors=extractors)


def _extract_standard_attachment(
    ext: str,
    content: bytes,
    *,
    extractors: dict[str, Callable[..., str | None]],
) -> str | None:
    if ext in _SKIP_EXTENSIONS or ext in _IMAGE_EXTENSIONS:
        return None
    if ext in _TEXT_EXTENSIONS:
        return extractors["plain"](content)
    if ext in {".html", ".htm"}:
        return extractors["html"](content)
    if ext in {".pdf", ".docx", ".ods", ".pptx"}:
        return extractors[ext[1:]](content)
    if ext in {".xlsx", ".xlsm"}:
        return extractors["xlsx"](content)
    if ext in {".xls", ".doc"}:
        return extractors["legacy_office"](content, ext[1:].upper())
    return None


def extract_text(filename: str, content: bytes, *, mime_type: str | None = None) -> str | None:
    """Extract readable text from an attachment."""
    return _extract_text_with_dispatch(
        filename,
        content,
        mime_type=mime_type,
        extractors=_default_extractors(),
    )


def _default_extractors() -> dict[str, Callable[..., str | None]]:
    return {
        "plain": _extract_plain_text,
        "html": _extract_html,
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "xlsx": _extract_xlsx,
        "ods": _extract_ods,
        "legacy_office": lambda data, label: _extract_legacy_binary_office(data, format_label=label),
        "pptx": _extract_pptx,
    }


def _truncate(text: str) -> str:
    """Truncate text to the maximum allowed length.

    Args:
        text: The text to truncate.

    Returns:
        The text truncated to MAX_EXTRACTED_CHARS with a truncation marker if needed.
    """
    if len(text) <= MAX_EXTRACTED_CHARS:
        return text
    return text[:MAX_EXTRACTED_CHARS] + "\n[... content truncated ...]"


def _extract_plain_text(content: bytes) -> str | None:
    """Extract text from plain text content.

    Args:
        content: The raw bytes to decode and extract.

    Returns:
        The decoded and stripped text, truncated if necessary, or None if empty.
    """
    text = _decode_text_bytes(content)
    text = text.strip()
    return _truncate(text) if text else None


def _extract_html(content: bytes) -> str | None:
    """Extract text from HTML content.

    Args:
        content: The HTML bytes to convert.

    Returns:
        The converted and stripped text, truncated if necessary, or None if empty.
    """
    html = _decode_text_bytes(content)

    from .html_converter import html_to_text as _html_to_text

    text = _html_to_text(html).strip()
    return _truncate(text) if text else None


def _extract_eml(content: bytes) -> str | None:
    """Extract text from an EML (email) file.

    Args:
        content: The EML file bytes.

    Returns:
        The extracted email metadata and body text, or None if extraction fails.
    """
    raw_source = _decode_text_bytes(content)
    headers = _eml_headers(raw_source)
    if not any(headers.values()) and "\n" not in raw_source and "\r" not in raw_source:
        return None
    text = "\n".join(_eml_parts(headers, _eml_message(content), _eml_body(raw_source))).strip()
    return _truncate(text) if text else None


def _eml_headers(raw_source: str) -> dict[str, str]:
    return {name: _extract_header(raw_source, name) for name in ("Subject", "From", "Date")}


def _eml_message(content: bytes):
    try:
        return email.message_from_bytes(content, policy=cast(Any, email.policy.default))
    except (ValueError, TypeError, AttributeError):
        logger.debug("Failed to parse .eml attachment.", exc_info=True)
        return None


def _eml_body(raw_source: str) -> str:
    body_text, body_html = _extract_body_from_source(raw_source)
    if not body_text and body_html:
        return _extract_html(body_html.encode("utf-8", errors="ignore")) or ""
    return body_text


def _eml_parts(headers: dict[str, str], message: Any, body_text: str) -> list[str]:
    parts = [f"{name}: {value}" for name, value in headers.items() if value]
    if message and message.get_content_type():
        parts.append(f"Content-Type: {message.get_content_type()}")
    if body_text:
        parts.extend(["", body_text.strip()])
    return parts


def _looks_like_utf16(content: bytes) -> bool:
    """Check if byte content appears to be UTF-16 encoded.

    Args:
        content: The bytes to check.

    Returns:
        True if the content looks like UTF-16 (has BOM or high null byte density).
    """
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True
    if len(content) < 4:
        return False
    sample = content[:32]
    null_count = sum(1 for byte in sample if byte == 0)
    return null_count >= max(2, len(sample) // 4)


def _decode_text_bytes(content: bytes) -> str:
    """Decode bytes to a string using appropriate encoding detection.

    Args:
        content: The bytes to decode.

    Returns:
        The decoded string, trying UTF-8-sig, UTF-16 variants, cp1252, and latin-1.
    """
    encodings = ["utf-8-sig"]
    if _looks_like_utf16(content):
        encodings.extend(["utf-16", "utf-16le", "utf-16be"])
    encodings.extend(["cp1252", "latin-1"])
    for encoding in encodings:
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if decoded.replace("\x00", "").strip():
            return decoded
    return content.decode("latin-1", errors="ignore")


def _optional_extract(
    content: bytes,
    import_name: str,
    import_from: str,
    extractor: Callable[[Any, io.BytesIO], str | None],
    fmt_label: str,
    failure_recorder: Callable[[str], None] | None = None,
) -> str | None:
    """Optionally extract text using an external library.

    Args:
        content: The bytes to extract text from.
        import_name: The module name to import.
        import_from: The symbol to import from the module.
        extractor: The extraction function to call with the imported symbol and stream.
        fmt_label: The format label for logging.
        failure_recorder: Optional function to record failures.

    Returns:
        The extracted text, truncated if necessary, or None if extraction fails.
    """
    try:
        mod = __import__(import_name)
        imported = getattr(mod, import_from)
    except (ImportError, AttributeError):
        logger.debug("%s not installed; skipping %s extraction.", import_name, fmt_label)
        if failure_recorder:
            failure_recorder(f"dependency_missing:{import_name}")
        return None
    try:
        text = extractor(imported, io.BytesIO(content))
        if text:
            return _truncate(text)
        return None
    except (RuntimeError, ValueError, OSError, TypeError) as exc:
        logger.debug("Failed to extract %s text from attachment.", fmt_label, exc_info=True)
        if failure_recorder:
            failure_recorder(f"text_extraction_failed:{fmt_label}:{type(exc).__name__}")
        return None


def _extract_zip_archive(
    content: bytes,
    *,
    extractors: dict[str, Callable[..., str | None]],
) -> str | None:
    """Extract text from a ZIP archive by extracting text from its members.

    Args:
        content: The ZIP archive bytes.
        extractors: Named extractors for supported archive members.

    Returns:
        The extracted text from archive members, or None if extraction fails.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        logger.debug("Failed to parse ZIP attachment.", exc_info=True)
        return None

    inventory_lines: list[str] = []
    extracted_sections: list[str] = []
    with archive:
        for member in archive.infolist()[:_MAX_ARCHIVE_MEMBERS]:
            if member.is_dir():
                continue
            inventory_lines.append(member.filename)
            member_text = _archive_member_text(archive, member, extractors=extractors)
            if member_text:
                extracted_sections.append(f"[Member: {member.filename}]\n{member_text}")

    if extracted_sections:
        lines = [_ARCHIVE_TEXT_HEADER]
        lines.extend(f"- {name}" for name in inventory_lines[:_MAX_ARCHIVE_MEMBERS])
        lines.append("")
        lines.extend(extracted_sections)
        return _truncate("\n".join(lines).strip())
    if inventory_lines:
        lines = [_ARCHIVE_INVENTORY_HEADER]
        lines.extend(f"- {name}" for name in inventory_lines[:_MAX_ARCHIVE_MEMBERS])
        return _truncate("\n".join(lines).strip())
    return None


def _archive_member_text(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    *,
    extractors: dict[str, Callable[..., str | None]],
) -> str | None:
    if member.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
        return None
    ext = _dispatch_extension(member.filename)
    if ext in _SKIP_EXTENSIONS or ext in _IMAGE_EXTENSIONS or ext in {".zip", ".gz", ".tar", ".rar", ".7z"}:
        return None
    try:
        member_bytes = archive.read(member)
    except OSError:
        logger.debug("Failed to read ZIP member %s.", member.filename, exc_info=True)
        return None
    return _extract_text_with_dispatch(member.filename, member_bytes, extractors=extractors)


def _pdf_extractor(pdf_reader_cls, stream):
    """Extract text from a PDF file using PyPDF2.

    Args:
        pdf_reader_cls: The PdfReader class from PyPDF2.
        stream: A file-like object containing PDF data.

    Returns:
        The extracted text with page markers, or empty string.
    """
    reader = pdf_reader_cls(stream)
    pages: list[str] = []
    for page_index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text()
        if page_text:
            pages.append(f"[Page {page_index}]\n{page_text}")
    return "\n\n".join(pages).strip()


def _docx_extractor(document_cls, stream):
    """Extract text from a DOCX file using python-docx.

    Args:
        document_cls: The Document class from python-docx.
        stream: A file-like object containing DOCX data.

    Returns:
        The extracted text joined from all non-empty paragraphs.
    """
    doc = document_cls(stream)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def _xlsx_extractor(load_workbook, stream):
    """Extract text from an XLSX file using openpyxl.

    Args:
        load_workbook: The load_workbook function from openpyxl.
        stream: A file-like object containing XLSX data.

    Returns:
        The extracted text with sheet and row markers.
    """
    wb = load_workbook(stream, read_only=True, data_only=True)
    lines = []
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        lines.append(f"[Sheet: {sheet}]")
        for row in ws.iter_rows(values_only=True):
            cells = [str(cell) if cell is not None else "" for cell in row]
            if any(c.strip() for c in cells):
                lines.append("\t".join(cells))
    wb.close()
    return "\n".join(lines).strip()


def _extract_ods(content: bytes) -> str | None:
    """Extract text from an ODS (OpenDocument Spreadsheet) file.

    Args:
        content: The ODS file bytes.

    Returns:
        The extracted text from content.xml, or None if extraction fails.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_text = archive.read("content.xml")
    except (KeyError, OSError, zipfile.BadZipFile):
        logger.debug("Failed to extract ODS content.xml.", exc_info=True)
        return None

    try:
        decoded = _decode_text_bytes(xml_text)
    except (UnicodeDecodeError, ValueError):
        logger.debug("Failed to decode ODS content.xml.", exc_info=True)
        return None

    # ODS stores readable strings in XML. Strip tags conservatively.
    flattened = re.sub(r"<[^>]+>", " ", decoded)
    text = " ".join(flattened.split()).strip()
    return _truncate(text) if text else None


def _extract_legacy_binary_office(content: bytes, *, format_label: str) -> str | None:
    """Return a conservative printable-text fallback for legacy binary Office files.

    Args:
        content: The binary Office file bytes.
        format_label: The format label for logging (e.g., 'XLS', 'DOC').

    Returns:
        The extracted printable text, or None if no printable text found.
    """
    decoded_variants = [
        _decode_text_bytes(content),
        content.decode("utf-16le", errors="ignore"),
        content.decode("utf-16be", errors="ignore"),
    ]
    candidates: list[str] = []
    for decoded in decoded_variants:
        normalized = " ".join(decoded.replace("\x00", " ").split())
        if normalized:
            candidates.append(normalized)
    printable_pattern = r"[A-Za-z0-9ÄÖÜäöüß@:/._%+\-(),]{4,}(?:\s+[A-Za-z0-9ÄÖÜäöüß@:/._%+\-(),]{2,})*"
    printable_runs = re.findall(printable_pattern, " ".join(candidates))
    text = " ".join(dict.fromkeys(run.strip() for run in printable_runs if run.strip()))
    if not text:
        logger.debug("No printable fallback text recovered from %s attachment.", format_label)
        return None
    return _truncate(text)


def _pptx_extractor(presentation_cls, stream):
    """Extract text from a PPTX file using python-pptx.

    Args:
        presentation_cls: The Presentation class from python-pptx.
        stream: A file-like object containing PPTX data.

    Returns:
        The extracted text with slide and shape markers.
    """
    prs = presentation_cls(stream)
    lines: list[str] = []
    for slide_num, slide in enumerate(prs.slides, 1):
        lines.append(f"[Slide {slide_num}]")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        lines.append(text)
    return "\n".join(lines).strip()


def _extract_pdf(content: bytes) -> str | None:
    """Extract text from a PDF file.

    Args:
        content: The PDF file bytes.

    Returns:
        The extracted text, or None if extraction fails.
    """
    return _optional_extract(content, "PyPDF2", "PdfReader", _pdf_extractor, "PDF")


def _extract_docx(content: bytes) -> str | None:
    """Extract text from a DOCX file.

    Args:
        content: The DOCX file bytes.

    Returns:
        The extracted text, or None if extraction fails.
    """
    return _optional_extract(content, "docx", "Document", _docx_extractor, "DOCX")


def _extract_xlsx(content: bytes) -> str | None:
    """Extract text from an XLSX file.

    Args:
        content: The XLSX file bytes.

    Returns:
        The extracted text, or None if extraction fails.
    """
    return _optional_extract(content, "openpyxl", "load_workbook", _xlsx_extractor, "XLSX")


def _extract_pptx(content: bytes) -> str | None:
    """Extract text from a PPTX file.

    Args:
        content: The PPTX file bytes.

    Returns:
        The extracted text, or None if extraction fails.
    """
    return _optional_extract(content, "pptx", "Presentation", _pptx_extractor, "PPTX")
