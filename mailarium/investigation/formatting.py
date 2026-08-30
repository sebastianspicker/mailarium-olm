"""Investigation-specific presentation and report-formatting helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from html import unescape
from typing import Any

from mailarium.platform.repo_paths import validate_new_output_path


def resolve_body_for_render(email_dict: Mapping[str, Any], render_mode: str = "retrieval") -> tuple[str, str]:
    """Resolve the body text and provenance for a requested render mode."""
    mode = "forensic" if render_mode == "forensic" else "retrieval"
    if mode == "forensic":
        forensic_text = (email_dict.get("forensic_body_text") or "").strip()
        if forensic_text:
            return forensic_text, str(email_dict.get("forensic_body_source") or "forensic_body_text")
    return (email_dict.get("body_text") or ""), str(email_dict.get("normalized_body_source") or "body_text")


def weak_message_semantics(email_dict: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a consistent answer-facing explanation for weak message bodies."""
    body_kind = str(email_dict.get("body_kind") or "")
    body_empty_reason = str(email_dict.get("body_empty_reason") or "")
    recovery_strategy = str(email_dict.get("recovery_strategy") or "")
    recovery_confidence = float(email_dict.get("recovery_confidence") or 0.0)

    definitions = {
        "image_only": (
            "Image-only message",
            "The message matched, but no recoverable body text was found beyond image-backed content.",
            "content",
        ),
        "source_shell_only": (
            "Source-shell message",
            "The message matched, but only source-shell structure or metadata was recoverable, not visible authored text.",
            "content",
        ),
        "metadata_only_reply": (
            "Metadata-only reply",
            "The reply matched, but only reply metadata was recoverable; no authored reply body text was found.",
            "content",
        ),
        "true_blank": (
            "Blank message",
            "The message matched, but no recoverable body text was present in the export surfaces.",
            "empty",
        ),
    }
    definition = definitions.get(body_empty_reason)
    if definition is None:
        return None
    label, explanation, default_kind = definition
    return {
        "is_weak": True,
        "code": body_empty_reason,
        "label": label,
        "explanation": explanation,
        "body_kind": body_kind or default_kind,
        "body_empty_reason": body_empty_reason,
        "recovery_strategy": recovery_strategy,
        "recovery_confidence": recovery_confidence,
    }


def format_date(iso_date: str | None) -> str:
    """Convert ISO date string to human-readable format.

    '2024-01-15T10:30:00' → 'January 15, 2024, 10:30 AM'
    '2024-01-15' → 'January 15, 2024'
    Falls back to the original string on parse failure.
    """
    if not iso_date:
        return ""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(iso_date.strip(), fmt)
            if dt.hour or dt.minute:
                return dt.strftime("%B %d, %Y, %I:%M %p").replace(" 0", " ")
            return dt.strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            continue
    return iso_date


def format_file_size(size_bytes: int | None) -> str:
    """Format file size in human-readable units."""
    if size_bytes is None or size_bytes < 0:
        return ""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


# Regex to strip HTML tags (handles multi-line tags)
_HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
# Collapse runs of whitespace (but preserve paragraph breaks)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def strip_html_tags(text: str | None) -> str:
    """Strip HTML tags from text, returning clean plain text.

    Handles common HTML email patterns: converts <br> and block elements
    to newlines, strips all remaining tags, and decodes HTML entities.
    """
    if not text:
        return ""
    # Quick check: if there are no HTML tags or entities, return as-is
    if "<" not in text and "&" not in text:
        return text
    # Text with entities but no tags - just decode entities
    if "<" not in text:
        return unescape(text)
    # Remove <style>...</style> and <script>...</script> blocks including their text content
    result = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip HTML comment fragments (<!--[if gte mso 9]-->, <!-- ... -->)
    result = re.sub(r"<!--[\s\S]*?-->", "", result)
    # Replace <br>, <br/>, <br /> with newlines
    result = re.sub(r"<br\s*/?>", "\n", result, flags=re.IGNORECASE)
    # Replace block-level closing tags with newlines for readability
    result = re.sub(
        r"</(?:p|div|tr|li|h[1-6]|blockquote|pre|table|thead|tbody|tfoot)>",
        "\n",
        result,
        flags=re.IGNORECASE,
    )
    # Strip all remaining HTML tags
    result = _HTML_TAG_RE.sub("", result)
    # Decode HTML entities (&amp; → &, &lt; → <, &#8230; → …, etc.)
    result = unescape(result)
    # Collapse excessive blank lines
    result = _MULTI_BLANK_RE.sub("\n\n", result)
    return result.strip()


def write_html_or_pdf(html: str, output_path: str, fmt: str) -> dict[str, Any]:
    """Write HTML content to disk as HTML or PDF.

    If ``fmt`` is ``"pdf"`` but WeasyPrint is not installed, falls back to
    HTML and includes a ``note`` key in the result.

    Returns:
        ``{"output_path": str, "format": str}`` (plus optional ``"note"``).
    """
    output = validate_new_output_path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if fmt.lower() == "pdf":
        try:
            from weasyprint import HTML as WeasyprintHTML

            WeasyprintHTML(string=html).write_pdf(str(output))
            return {"output_path": output_path, "format": "pdf"}
        except ImportError:
            fallback_output_path = str(output.with_suffix(".html"))
            output = validate_new_output_path(str(output.with_suffix(".html")))
            output.write_text(html, encoding="utf-8")
            return {
                "output_path": fallback_output_path,
                "format": "html",
                "note": "weasyprint not installed; saved as HTML. Install with: pip install weasyprint",
            }

    output.write_text(html, encoding="utf-8")
    return {"output_path": output_path, "format": fmt}
