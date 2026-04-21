"""Classification and deterministic fallback for empty normalized bodies."""

from __future__ import annotations

from dataclasses import dataclass

from .html_converter import clean_text as _clean_text
from .html_converter import html_to_text as _html_to_text
from .html_converter import looks_like_html as _looks_like_html
from .rfc2822 import _extract_body_from_source

_HTML_SHELL_SUMMARY = "HTML shell message with no recoverable visible text."
_IMAGE_ONLY_SUMMARY = "Image-only message with attachments and no recoverable body text."
_SOURCE_SHELL_SUMMARY = "Source-shell message with no recoverable visible body text."
_METADATA_ONLY_REPLY_SUMMARY = "Metadata-only reply with no recoverable authored body text."
_SOURCE_SENTINELS = frozenset({"[Attachment-only email]"})


@dataclass(frozen=True)
class BodyRecovery:
    """Recovery result for an empty or near-empty normalized body."""

    body_kind: str
    body_empty_reason: str
    recovery_strategy: str
    recovery_confidence: float
    recovered_text: str
    recovered_source: str


def _normalize_visible_text(raw: str, source: str) -> str:
    """Derive visible text from a raw source surface without retrieval stripping."""
    if not raw or not raw.strip():
        return ""
    if source == "html" or _looks_like_html(raw):
        return _html_to_text(raw).strip()
    return _clean_text(raw).strip()


def _looks_image_only(raw_body_text: str, raw_body_html: str) -> bool:
    """Detect markup that only contains images and no visible text."""
    html = raw_body_html or raw_body_text
    if not html or "<img" not in html.lower():
        return False
    return not _normalize_visible_text(html, "html")


def classify_body_state(
    raw_body_text: str,
    raw_body_html: str,
    raw_source: str,
    preview_text: str,
    clean_body: str,
    email_type: str,
    has_attachments: bool,
) -> BodyRecovery:
    """Classify an empty normalized body and recover a safer fallback when justified."""
    if clean_body.strip():
        return BodyRecovery("content", "", "", 1.0, "", "")

    raw_text_visible = _normalize_visible_text(raw_body_text, "text")
    raw_html_visible = _normalize_visible_text(raw_body_html, "html")
    preview_visible = _normalize_visible_text(preview_text, "text")
    source_text, source_html = _extract_body_from_source(raw_source) if raw_source else ("", "")
    source_text_visible = _normalize_visible_text(source_text, "text")
    source_html_visible = _normalize_visible_text(source_html, "html")
    source_visible_is_sentinel = source_text_visible in _SOURCE_SENTINELS and not source_html_visible

    if _looks_image_only(raw_body_text, raw_body_html):
        reason = "image_only"
    elif raw_source.strip() and not raw_text_visible and not raw_html_visible and (
        (not source_text_visible and not source_html_visible) or source_visible_is_sentinel
    ):
        reason = "source_shell_only"
    elif raw_body_html.strip() and not raw_html_visible and not raw_text_visible:
        reason = "html_shell_only"
    elif (
        has_attachments
        and not raw_text_visible
        and not raw_html_visible
        and ((not source_text_visible and not source_html_visible) or source_visible_is_sentinel)
    ):
        return BodyRecovery("attachment_only", "attachment_only", "", 0.0, "", "")
    elif (
        email_type in {"reply", "forward"}
        and not raw_text_visible
        and not raw_html_visible
        and ((not source_text_visible and not source_html_visible) or source_visible_is_sentinel)
    ):
        return BodyRecovery(
            "content",
            "metadata_only_reply",
            "metadata_summary",
            0.2,
            _METADATA_ONLY_REPLY_SUMMARY,
            "metadata_only_reply_summary",
        )
    elif raw_body_text.strip() or raw_body_html.strip():
        reason = "html_shell_only"
    else:
        reason = "true_blank"

    if preview_visible:
        return BodyRecovery("content", reason, "preview", 0.7, preview_visible, "preview")

    if source_text_visible and not source_visible_is_sentinel:
        return BodyRecovery("content", reason, "source", 0.5, source_text_visible, "raw_source_text")

    if source_html_visible:
        return BodyRecovery("content", reason, "source", 0.5, source_html_visible, "raw_source_html")

    if reason == "image_only":
        return BodyRecovery("content", reason, "image_summary", 0.2, _IMAGE_ONLY_SUMMARY, "image_only_summary")

    if reason == "source_shell_only":
        return BodyRecovery("content", reason, "source_shell_summary", 0.2, _SOURCE_SHELL_SUMMARY, "source_shell_summary")

    if reason == "html_shell_only" and email_type == "original" and (raw_body_text.strip() or raw_body_html.strip()):
        return BodyRecovery("content", reason, "shell_summary", 0.2, _HTML_SHELL_SUMMARY, "html_shell_summary")

    return BodyRecovery(
        "metadata_only" if email_type in {"reply", "forward"} else "empty",
        reason,
        "",
        0.0,
        "",
        "",
    )
