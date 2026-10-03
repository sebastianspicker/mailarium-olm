"""Support-type classification for retrieved results and preloaded evidence rows."""

from __future__ import annotations

from typing import Any

from mailarium.model.data_shapes import as_dict

from .text import _text


def _basic_support_type(metadata: dict[str, Any], text: str) -> str | None:
    """Classify attachment, segment, or calendar support from metadata and conservative text cues."""
    if _text(metadata.get("attachment_filename") or metadata.get("filename")).strip():
        return "attachment"
    if _text(metadata.get("score_kind")) == "segment_sql" or _text(metadata.get("segment_type")).strip():
        return "segment"
    if bool(metadata.get("is_calendar_message")) or any(
        token in text for token in ("calendar", "meeting", "invite", "termin", "besprechung")
    ):
        return "calendar"
    return None


def _support_type_for_result(result: Any) -> str:
    """Determine the support type for a search result.

    Classifies a result as body, segment, attachment, or calendar evidence.

    Args:
        result: The search result object to classify.

    Returns:
        A string representing the support type classification.
    """
    metadata = as_dict(result.metadata)
    explicit_support_type = _text(metadata.get("support_type")).strip().lower()
    if explicit_support_type in {"body", "segment", "attachment", "calendar"}:
        return explicit_support_type

    text = " ".join(
        part
        for part in (
            _text(getattr(result, "text", "")),
            _text(metadata.get("subject")),
            _text(metadata.get("body_render_source")),
            _text(metadata.get("segment_type")),
            _text(metadata.get("source_type")),
        )
        if part
    ).lower()

    basic = _basic_support_type(metadata, text)
    if basic is not None:
        return basic
    return "body"


def _support_type_for_row(row: dict[str, Any]) -> str:
    """Determine the support type for a result row from the database.

    Classifies a database row into a support type, similar to _support_type_for_result
    but working with raw row data instead of result objects.

    Args:
        row: A dictionary containing the database row data.

    Returns:
        A string representing the support type classification.
    """
    declared = _text(row.get("support_type")).strip().lower()
    if declared in {"body", "segment", "attachment", "calendar"}:
        return declared
    attachment_filename = ""
    attachment_value: Any = row.get("attachment")
    if isinstance(attachment_value, dict):
        attachment_filename = _text(attachment_value.get("filename"))
    metadata = {
        "attachment_filename": _text(row.get("attachment_filename")),
        "filename": attachment_filename,
        "score_kind": _text(row.get("score_kind")),
        "segment_type": _text(row.get("segment_type")),
        "is_calendar_message": row.get("is_calendar_message"),
        "subject": _text(row.get("subject")),
        "body_render_source": _text(row.get("body_render_source")),
    }
    proxy = type("_RowProxy", (), {"metadata": metadata, "text": _text(row.get("snippet"))})()
    return _support_type_for_result(proxy)
