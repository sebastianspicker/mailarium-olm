"""Classification and deterministic fallback for empty normalized bodies."""
# pylint: disable=too-many-arguments,too-many-boolean-expressions,too-many-branches,too-many-locals,too-many-positional-arguments,too-many-return-statements

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


@dataclass(frozen=True)
class _BodySurfaces:
    raw_text_visible: str
    raw_html_visible: str
    preview_visible: str
    source_text_visible: str
    source_html_visible: str
    source_visible_is_sentinel: bool


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
    surfaces = _body_surfaces(raw_body_text, raw_body_html, raw_source, preview_text)
    initial_state = _initial_body_state(surfaces, raw_body_text, raw_body_html, raw_source, email_type, has_attachments)
    if isinstance(initial_state, BodyRecovery):
        return initial_state
    return _recover_body(initial_state, surfaces, raw_body_text, raw_body_html, email_type)


def _body_surfaces(raw_text: str, raw_html: str, raw_source: str, preview: str) -> _BodySurfaces:
    source_text, source_html = _extract_body_from_source(raw_source) if raw_source else ("", "")
    source_text_visible = _normalize_visible_text(source_text, "text")
    source_html_visible = _normalize_visible_text(source_html, "html")
    return _BodySurfaces(
        _normalize_visible_text(raw_text, "text"),
        _normalize_visible_text(raw_html, "html"),
        _normalize_visible_text(preview, "text"),
        source_text_visible,
        source_html_visible,
        source_text_visible in _SOURCE_SENTINELS and not source_html_visible,
    )


def _has_no_visible_body(surfaces: _BodySurfaces) -> bool:
    return not surfaces.raw_text_visible and not surfaces.raw_html_visible


def _has_no_visible_source(surfaces: _BodySurfaces) -> bool:
    return (not surfaces.source_text_visible and not surfaces.source_html_visible) or surfaces.source_visible_is_sentinel


def _initial_body_state(
    surfaces: _BodySurfaces, raw_text: str, raw_html: str, raw_source: str, email_type: str, has_attachments: bool
) -> str | BodyRecovery:
    no_visible_body = _has_no_visible_body(surfaces)
    no_visible_source = _has_no_visible_source(surfaces)
    if _looks_image_only(raw_text, raw_html):
        return "image_only"
    if _is_source_shell(raw_source, no_visible_body, no_visible_source):
        return "source_shell_only"
    if _is_html_shell(raw_html, no_visible_body):
        return "html_shell_only"
    if _is_attachment_only(has_attachments, no_visible_body, no_visible_source):
        return BodyRecovery("attachment_only", "attachment_only", "", 0.0, "", "")
    if _is_metadata_reply(email_type, no_visible_body, no_visible_source):
        return BodyRecovery(
            "content", "metadata_only_reply", "metadata_summary", 0.2, _METADATA_ONLY_REPLY_SUMMARY, "metadata_only_reply_summary"
        )
    return "html_shell_only" if raw_text.strip() or raw_html.strip() else "true_blank"


def _is_source_shell(raw_source: str, no_visible_body: bool, no_visible_source: bool) -> bool:
    return bool(raw_source.strip()) and no_visible_body and no_visible_source


def _is_html_shell(raw_html: str, no_visible_body: bool) -> bool:
    return bool(raw_html.strip()) and no_visible_body


def _is_attachment_only(has_attachments: bool, no_visible_body: bool, no_visible_source: bool) -> bool:
    return has_attachments and no_visible_body and no_visible_source


def _is_metadata_reply(email_type: str, no_visible_body: bool, no_visible_source: bool) -> bool:
    return email_type in {"reply", "forward"} and no_visible_body and no_visible_source


def _recover_body(reason: str, surfaces: _BodySurfaces, raw_text: str, raw_html: str, email_type: str) -> BodyRecovery:
    if surfaces.preview_visible:
        return BodyRecovery("content", reason, "preview", 0.7, surfaces.preview_visible, "preview")
    if surfaces.source_text_visible and not surfaces.source_visible_is_sentinel:
        return BodyRecovery("content", reason, "source", 0.5, surfaces.source_text_visible, "raw_source_text")
    if surfaces.source_html_visible:
        return BodyRecovery("content", reason, "source", 0.5, surfaces.source_html_visible, "raw_source_html")
    summary = _recovery_summary(reason, raw_text, raw_html, email_type)
    if summary:
        return summary
    body_kind = "metadata_only" if email_type in {"reply", "forward"} else "empty"
    return BodyRecovery(body_kind, reason, "", 0.0, "", "")


def _recovery_summary(reason: str, raw_text: str, raw_html: str, email_type: str) -> BodyRecovery | None:
    if reason == "image_only":
        return BodyRecovery("content", reason, "image_summary", 0.2, _IMAGE_ONLY_SUMMARY, "image_only_summary")
    if reason == "source_shell_only":
        return BodyRecovery("content", reason, "source_shell_summary", 0.2, _SOURCE_SHELL_SUMMARY, "source_shell_summary")
    if reason == "html_shell_only" and email_type == "original" and (raw_text.strip() or raw_html.strip()):
        return BodyRecovery("content", reason, "shell_summary", 0.2, _HTML_SHELL_SUMMARY, "html_shell_summary")
    return None
