"""Formatting helpers shared across chunking and retrieval output."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from html import unescape
from typing import TYPE_CHECKING, Any

from .repo_paths import validate_new_output_path

if TYPE_CHECKING:
    from .retriever import SearchResult


def format_sender(name: str | None, email: str | None) -> str:
    """Format sender consistently for headers and output."""
    clean_name = (name or "").strip()
    clean_email = (email or "").strip()
    if clean_name and clean_email:
        return f"{clean_name} <{clean_email}>"
    if clean_name:
        return clean_name
    return clean_email


def build_email_header(email_dict: Mapping[str, Any]) -> str:
    """Build a concise metadata header for embedding context."""
    parts: list[str] = []

    date_value = email_dict.get("date")
    if date_value:
        parts.append(f"Date: {date_value}")

    sender = format_sender(email_dict.get("sender_name"), email_dict.get("sender_email"))
    if sender:
        parts.append(f"From: {sender}")

    to_values = _as_list(email_dict.get("to"))
    if to_values:
        parts.append(f"To: {', '.join(to_values[:3])}")

    cc_values = _as_list(email_dict.get("cc"))
    if cc_values:
        parts.append(f"CC: {', '.join(cc_values[:3])}")

    subject = email_dict.get("subject")
    if subject:
        parts.append(f"Subject: {subject}")

    folder = email_dict.get("folder")
    if folder:
        parts.append(f"Folder: {folder}")

    categories = email_dict.get("categories")
    if categories and isinstance(categories, list) and categories:
        parts.append(f"Categories: {', '.join(str(c) for c in categories[:5])}")

    if email_dict.get("is_calendar_message"):
        parts.append("[Calendar/Meeting]")

    if email_dict.get("has_attachments"):
        attachment_names = _as_list(email_dict.get("attachment_names"))
        if attachment_names:
            parts.append(f"Attachments: {', '.join(attachment_names[:5])}")
        else:
            parts.append("Has attachments")

    return "\n".join(parts)


def build_result_header(metadata: Mapping[str, Any]) -> str:
    """Build result header used in LLM context formatting.

    Compact format: date truncated to date-only, ``Folder: Inbox`` omitted
    (most common folder, low information value).
    """
    parts: list[str] = []

    date_value = metadata.get("date")
    if date_value:
        # Truncate to date-only (drop time) for compactness
        parts.append(f"Date: {str(date_value)[:10]}")

    sender = format_sender(metadata.get("sender_name"), metadata.get("sender_email"))
    if sender:
        parts.append(f"From: {sender}")

    to_value = metadata.get("to")
    if to_value:
        if isinstance(to_value, list):
            to_value = ", ".join(str(v) for v in to_value)
        parts.append(f"To: {to_value}")

    subject = metadata.get("subject")
    if subject:
        parts.append(f"Subject: {subject}")

    email_type = metadata.get("email_type")
    if email_type and email_type != "original":
        parts.append(f"Type: {email_type}")

    folder = metadata.get("folder")
    if folder and folder != "Inbox":
        parts.append(f"Folder: {folder}")

    priority = metadata.get("priority")
    if priority and str(priority) not in ("0", ""):
        parts.append(f"Priority: {priority}")

    categories = metadata.get("categories")
    if categories and str(categories).strip():
        parts.append(f"Categories: {categories}")

    if str(metadata.get("is_calendar_message", "")).lower() in ("true", "1"):
        parts.append("[Calendar/Meeting]")

    attachment_names = metadata.get("attachment_names")
    if attachment_names and str(attachment_names).strip():
        parts.append(f"Attachments: {attachment_names}")

    return "\n".join(parts)


def truncate_body(text: str | None, max_chars: int) -> str:
    """Truncate email body text to *max_chars* characters.

    Normalizes non-breaking spaces (``\\xa0``) to regular spaces before
    truncation.  Returns the text unchanged when *max_chars* is ``<= 0``
    (unlimited) or the text already fits.  Otherwise appends a hint to
    use ``email_get_full``.

    Accepts ``None`` gracefully (returns ``""``), because SQLite returns
    ``None`` for NULL ``body_text`` columns and ``dict.get("body_text", "")``
    does **not** substitute the default when the key exists with a ``None``
    value.
    """
    if text is None:
        return ""
    text = text.replace("\xa0", " ")
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    total_chars = len(text)
    return (
        text[:max_chars] + f"\n[...truncated at {max_chars:,}/{total_chars:,} chars. "
        f"Use email_deep_context with the UID to read the full {total_chars:,}-character body.]"
    )


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

    if body_empty_reason == "image_only":
        return {
            "is_weak": True,
            "code": "image_only",
            "label": "Image-only message",
            "explanation": "The message matched, but no recoverable body text was found beyond image-backed content.",
            "body_kind": body_kind or "content",
            "body_empty_reason": body_empty_reason,
            "recovery_strategy": recovery_strategy,
            "recovery_confidence": recovery_confidence,
        }
    if body_empty_reason == "source_shell_only":
        return {
            "is_weak": True,
            "code": "source_shell_only",
            "label": "Source-shell message",
            "explanation": (
                "The message matched, but only source-shell structure or metadata was recoverable, not visible authored text."
            ),
            "body_kind": body_kind or "content",
            "body_empty_reason": body_empty_reason,
            "recovery_strategy": recovery_strategy,
            "recovery_confidence": recovery_confidence,
        }
    if body_empty_reason == "metadata_only_reply":
        return {
            "is_weak": True,
            "code": "metadata_only_reply",
            "label": "Metadata-only reply",
            "explanation": "The reply matched, but only reply metadata was recoverable; no authored reply body text was found.",
            "body_kind": body_kind or "content",
            "body_empty_reason": body_empty_reason,
            "recovery_strategy": recovery_strategy,
            "recovery_confidence": recovery_confidence,
        }
    if body_empty_reason == "true_blank":
        return {
            "is_weak": True,
            "code": "true_blank",
            "label": "Blank message",
            "explanation": "The message matched, but no recoverable body text was present in the export surfaces.",
            "body_kind": body_kind or "empty",
            "body_empty_reason": body_empty_reason,
            "recovery_strategy": recovery_strategy,
            "recovery_confidence": recovery_confidence,
        }
    return None


def format_context_block(
    text: str,
    metadata: Mapping[str, Any],
    score: float,
    *,
    max_body_chars: int = 0,
) -> str:
    """Format a single result block for LLM context."""
    header = build_result_header(metadata)
    body = truncate_body(text, max_body_chars)
    return f"---\n{header}\nRelevance: {score:.2f}\n---\n{body}\n"


def estimate_tokens(text: str | None) -> int:
    """Rough token estimate for LLM context budgeting (~4 chars per token)."""
    if not text:
        return 1
    return max(1, len(text) // 4)


def format_triage_results(
    results: list[SearchResult],
    preview_chars: int = 200,
) -> list[dict[str, Any]]:
    """Format search results as ultra-compact triage entries.

    Returns minimal dicts with uid, sender, date, subject, score, and an
    optional body preview.  Designed for high-volume scanning where token
    economy matters (~80 tokens per result at preview_chars=200).
    """
    compact = []
    for r in results:
        meta = r.metadata
        entry: dict[str, Any] = {
            "uid": meta.get("uid", ""),
            "sender": meta.get("sender_email", ""),
            "date": str(meta.get("date", ""))[:10],
            "subject": meta.get("subject", ""),
            "score": round(r.score, 3),
        }
        if preview_chars > 0:
            body = _strip_metadata_header(r.text or "")
            if len(body) > preview_chars:
                entry["preview"] = body[:preview_chars] + "..."
            else:
                entry["preview"] = body
        compact.append(entry)
    return compact


# Regex to detect metadata header lines at the start of chunk text
# (e.g. "Date: ...\nFrom: ...\nSubject: ...\n\nActual body")
_META_HEADER_RE = re.compile(
    r"^(?:(?:Date|From|To|CC|Subject|Folder|Categories|Attachments|Type|Priority"
    r"|Relevance|\[Calendar/Meeting\]|\[Part \d+/\d+\]|Has attachments)"
    r"[:\s].*\n)*\n*",
    re.MULTILINE,
)


def _strip_metadata_header(text: str) -> str:
    """Strip the metadata header block from chunk text for cleaner previews."""
    if not text:
        return text
    m = _META_HEADER_RE.match(text)
    if m and m.end() > 0:
        return text[m.end() :].strip()
    return text


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


# ── Shared formatting utilities ───────────────────────────────


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
    # Text with entities but no tags — just decode entities
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
