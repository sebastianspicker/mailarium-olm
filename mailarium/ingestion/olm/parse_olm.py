"""
Parse .olm (Outlook for Mac) archive files.

OLM files are ZIP archives containing XML-formatted email messages.
Structure: Accounts/<email>/com.microsoft.__Messages/<folder>/<message>.xml

Supports two OLM variants:
- Namespaced XML (older Outlook for Mac, namespace: http://schemas.microsoft.com/outlook/mac/2011)
- Non-namespaced XML (newer Outlook for Mac, plain element names)

When structured XML elements are missing (e.g. Inbox emails with only
OPFMessageCopySource), fields are extracted from the raw RFC 2822 headers.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator

from mailarium.model.message import classify_message_type as _classify_email_type
from mailarium.model.rfc2822 import (
    extract_identity_addresses as _extract_identity_addresses,
)

from ..records import ParsedMessage
from .parse_olm_postprocess import (
    ParsedEmailEnrichments as _ParsedEmailEnrichments,
)
from .parse_olm_postprocess import (
    ParsedEmailParts as _ParsedEmailParts,
)
from .parse_olm_postprocess import (
    apply_source_header_fallbacks as _apply_source_header_fallbacks_impl,
)
from .parse_olm_postprocess import (
    derive_email_enrichments as _derive_email_enrichments_impl,
)
from .parse_olm_postprocess import (
    finalize_parsed_email_parts as _finalize_parsed_email_parts_impl,
)
from .parse_olm_xml_parser import (
    build_parsed_email_from_parts_impl as _build_parsed_email_from_parts_impl,
)
from .parse_olm_xml_parser import parse_email_xml_impl as _parse_email_xml_impl
from .parse_olm_xml_parser import parse_olm_archive_impl as _parse_olm_archive_impl

logger = logging.getLogger(__name__)
MAX_XML_BYTES = int(os.environ.get("OLM_MAX_XML_BYTES", 50_000_000))  # 50 MB default
MAX_XML_FILES = int(os.environ.get("OLM_MAX_XML_FILES", 500_000))
MAX_TOTAL_XML_BYTES = 20_000_000_000  # 20 GB - safe because parse_olm is a generator


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

    yield from _parse_olm_archive_impl(
        olm_path,
        extract_attachments=extract_attachments,
        max_xml_files=MAX_XML_FILES,
        max_total_xml_bytes=MAX_TOTAL_XML_BYTES,
        max_xml_bytes=MAX_XML_BYTES,
        logger=logger,
        parse_email_xml_fn=_parse_email_xml,
    )


# ── ParsedMessage XML Parsing ─────────────────────────────────────────


def _apply_source_header_fallbacks(parts: _ParsedEmailParts) -> None:
    """Backfill fields absent from XML using recoverable source-message headers."""
    _apply_source_header_fallbacks_impl(parts, extract_identity_addresses_fn=_extract_identity_addresses)


def _finalize_parsed_email_parts(parts: _ParsedEmailParts) -> None:
    """Normalize parsed parts after fallback recovery and before model construction."""
    _finalize_parsed_email_parts_impl(parts, extract_identity_addresses_fn=_extract_identity_addresses)


def _derive_email_enrichments(parts: _ParsedEmailParts, source_path: str) -> _ParsedEmailEnrichments:
    return _derive_email_enrichments_impl(parts, source_path, classify_email_type_fn=_classify_email_type)


def _build_parsed_email_from_parts(parts: _ParsedEmailParts, enrichments: _ParsedEmailEnrichments) -> ParsedMessage:
    return _build_parsed_email_from_parts_impl(
        parts,
        enrichments,
        email_cls=ParsedMessage,
    )


def _parse_email_xml(xml_bytes: bytes, source_path: str) -> ParsedMessage | None:
    return _parse_email_xml_impl(
        xml_bytes,
        source_path,
        logger=logger,
        extract_identity_addresses_fn=_extract_identity_addresses,
        apply_source_header_fallbacks_fn=_apply_source_header_fallbacks,
        finalize_parsed_email_parts_fn=_finalize_parsed_email_parts,
        derive_email_enrichments_fn=_derive_email_enrichments,
        build_parsed_email_from_parts_fn=_build_parsed_email_from_parts,
    )
