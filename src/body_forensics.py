"""Source-preserving forensic body rendering helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from email.parser import HeaderParser

from .html_converter import clean_text as _clean_text
from .html_converter import html_to_text as _html_to_text
from .html_converter import looks_like_html as _looks_like_html
from .rfc2822 import _extract_body_from_source


@dataclass(frozen=True)
class ForensicBody:
    """Deterministic visible-text render built from preserved raw surfaces."""

    text: str
    source: str
    raw_headers: dict[str, str]
    content_hash: str


def extract_source_headers(raw_source: str) -> dict[str, str]:
    """Extract RFC 2822 headers without mutating or normalizing values."""
    if not raw_source.strip():
        return {}
    parser = HeaderParser()
    message = parser.parsestr(raw_source, headersonly=True)
    return dict(message.items())


def render_forensic_text(raw_body_text: str, raw_body_html: str, raw_source: str) -> ForensicBody:
    """Build a visible-text forensic body without retrieval-specific stripping."""
    headers = extract_source_headers(raw_source)

    if raw_body_text.strip():
        if _looks_like_html(raw_body_text):
            text = _html_to_text(raw_body_text)
            source = "raw_body_text_html"
        else:
            text = _clean_text(raw_body_text)
            source = "raw_body_text"
    elif raw_body_html.strip():
        text = _html_to_text(raw_body_html)
        source = "raw_body_html"
    elif raw_source.strip():
        source_body_text, source_body_html = _extract_body_from_source(raw_source)
        if source_body_text.strip():
            text = _clean_text(source_body_text)
            source = "raw_source_text"
        elif source_body_html.strip():
            text = _html_to_text(source_body_html)
            source = "raw_source_html"
        else:
            text = ""
            source = "raw_source"
    else:
        text = ""
        source = ""

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ForensicBody(text=text, source=source, raw_headers=headers, content_hash=content_hash)
