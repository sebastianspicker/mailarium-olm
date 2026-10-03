"""
Parse .olm (Outlook for Mac) archive files.

OLM files are ZIP archives containing XML-formatted email messages.
Structure: Accounts/<email>/com.microsoft.__Messages/<folder>/<message>.xml

Supports two OLM variants:
- Namespaced XML (older Outlook for Mac, namespace: http://schemas.microsoft.com/outlook/mac/2011)
- Non-namespaced XML (newer Outlook for Mac, plain element names)

When structured XML elements are missing (e.g. Inbox emails with only
OPFMessageCopySource), fields are extracted from the raw RFC 2822 headers.
This module owns archive traversal and resource limits; ``xml_parser`` turns
one message XML member into a ``ParsedMessage``.
"""

from __future__ import annotations

import logging
import os
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

from lxml import etree

from mailarium.platform.sanitization import sanitize_untrusted_text

from ..records import ParsedMessage
from .xml_helpers import (
    _apply_attachment_payload_metadata,
    _extract_attachment_contents,
    _extract_attachment_payloads,
    _read_limited_bytes,
)
from .xml_parser import parse_email_xml

logger = logging.getLogger(__name__)
MAX_XML_BYTES = int(os.environ.get("OLM_MAX_XML_BYTES", 50_000_000))  # 50 MB default
MAX_XML_FILES = int(os.environ.get("OLM_MAX_XML_FILES", 500_000))
MAX_TOTAL_XML_BYTES = 20_000_000_000  # 20 GB - safe because parse_olm is a generator
_SAFE_ZIP_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})


def parse_olm(olm_path: str, extract_attachments: bool = False) -> Iterator[ParsedMessage]:
    """Yield parseable messages from a resource-bounded OLM archive scan.

    Args:
        olm_path: Path to the .olm file.
        extract_attachments: If True, extract binary attachment content
            and populate ``ParsedMessage.attachment_contents``. Default False
            to avoid memory bloat.

    Yields:
        ParsedMessage objects for valid message XML entries encountered before archive
        file and byte limits are reached. Oversized or malformed members are
        logged and skipped, so a damaged or over-limit archive can yield a
        partial result.

    Raises:
        FileNotFoundError: If *olm_path* does not exist.
    """
    if not os.path.exists(olm_path):
        raise FileNotFoundError(f"OLM file not found: {olm_path}")

    with zipfile.ZipFile(olm_path, "r") as zf:
        limits = _ArchiveLimits(MAX_XML_FILES, MAX_TOTAL_XML_BYTES, MAX_XML_BYTES)
        processed = _ArchiveProgress()
        for info in zf.infolist():
            if not _is_message_xml(info.filename):
                continue
            if _should_stop_archive_parse(info, processed, limits):
                break
            # Charge attempted work before opening the member so malformed or
            # checksum-failing entries cannot evade the archive-wide budgets.
            processed.files += 1
            processed.bytes += info.file_size
            email, size, xml_bytes = _parse_archive_member(zf, info, limits)
            if size is None:
                continue
            if email:
                if extract_attachments:
                    _populate_attachment_contents(email, zf, info.filename, xml_bytes)
                _clear_transient_xml(email)
                yield email


@dataclass
class _ArchiveProgress:
    """Track archive members and uncompressed bytes accepted during parsing."""

    files: int = 0
    bytes: int = 0


@dataclass(frozen=True)
class _ArchiveLimits:
    """Define per-archive and per-member limits that protect OLM extraction."""

    max_files: int
    max_total_bytes: int
    max_bytes: int


def _is_message_xml(path: str) -> bool:
    normalized = path.lower()
    return normalized.endswith(".xml") and "com.microsoft.__messages" in normalized


def _should_stop_archive_parse(info: zipfile.ZipInfo, progress: _ArchiveProgress, limits: _ArchiveLimits) -> bool:
    if progress.files >= limits.max_files:
        logger.warning("Stopping parse due to MAX_XML_FILES limit (%s).", limits.max_files)
        return True
    if progress.bytes + info.file_size > limits.max_total_bytes:
        logger.warning("Stopping parse due to MAX_TOTAL_XML_BYTES limit (%s).", limits.max_total_bytes)
        return True
    return False


def _parse_archive_member(
    zf: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    limits: _ArchiveLimits,
) -> tuple[ParsedMessage | None, int | None, bytes]:
    safe_name = sanitize_untrusted_text(info.filename)
    if info.file_size > limits.max_bytes:
        logger.warning("Skipping oversized XML payload (%s bytes): %s", info.file_size, safe_name)
        return None, None, b""
    if info.compress_type not in _SAFE_ZIP_COMPRESSION:
        logger.warning("Skipping XML payload with unsupported ZIP compression: %s", safe_name)
        return None, None, b""
    try:
        with zf.open(info) as file_obj:
            xml_bytes = _read_limited_bytes(file_obj, byte_limit=limits.max_bytes)
        if len(xml_bytes) > limits.max_total_bytes:
            logger.warning("Skipping XML payload exceeding MAX_TOTAL_XML_BYTES limit: %s", safe_name)
            return None, None, b""
        return parse_email_xml(xml_bytes, info.filename), len(xml_bytes), xml_bytes
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("Failed to parse %s: %s", safe_name, sanitize_untrusted_text(str(exc)))
        return None, None, b""


def _populate_attachment_contents(
    email: ParsedMessage,
    zf: zipfile.ZipFile,
    xml_path: str,
    xml_bytes: bytes,
) -> None:
    """Attach bounded archive payloads to parsed attachment metadata in matching order."""
    transient = cast(Any, email)
    transient._attachment_payload_extraction_failed = False
    transient._attachment_payload_extraction_error = ""
    try:
        root = getattr(email, "_olm_root", None)
        ns = getattr(email, "_olm_ns", None)
        if isinstance(root, etree._Element) and isinstance(ns, dict):
            payloads = _extract_attachment_payloads(root, ns, xml_path, zf)
            email.attachment_contents = [
                (str(item.get("name") or ""), cast(bytes, item.get("content") or b""))
                for item in payloads
                if item.get("content") is not None and str(item.get("name") or "")
            ]
            _apply_attachment_payload_metadata(getattr(email, "attachments", []) or [], payloads)
        else:
            email.attachment_contents = _extract_attachment_contents(xml_bytes, xml_path, zf)
    except Exception as exc:
        logger.warning(
            "Attachment extraction failed for %s: %s",
            sanitize_untrusted_text(xml_path),
            sanitize_untrusted_text(str(exc)),
        )
        email.attachment_contents = []
        transient._attachment_payload_extraction_failed = True
        transient._attachment_payload_extraction_error = str(exc)


def _clear_transient_xml(email: ParsedMessage) -> None:
    """Release XML-only references once durable parsed fields are extracted."""
    for attr_name in ("_olm_root", "_olm_ns"):
        if hasattr(email, attr_name):
            delattr(email, attr_name)
