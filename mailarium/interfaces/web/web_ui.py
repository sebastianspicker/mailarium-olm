"""Pure helper utilities for Streamlit web UI behavior."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from html import escape
from typing import Any


def build_active_filter_labels(filters: Mapping[str, Any]) -> list[str]:
    """Convert active search filters into concise human-readable labels."""
    labels: list[str] = []

    sender_value = _normalize_optional_text(filters.get("sender"))
    subject_value = _normalize_optional_text(filters.get("subject"))
    folder_value = _normalize_optional_text(filters.get("folder"))
    cc_value = _normalize_optional_text(filters.get("cc"))
    to_value = _normalize_optional_text(filters.get("to"))
    bcc_value = _normalize_optional_text(filters.get("bcc"))

    text_labels = (
        ("Sender", sender_value),
        ("To", to_value),
        ("Subject", subject_value),
        ("Folder", folder_value),
        ("CC", cc_value),
        ("BCC", bcc_value),
    )
    labels.extend(f"{name}: {value}" for name, value in text_labels if value)
    if filters.get("has_attachments") is True:
        labels.append("Has attachments")
    priority = filters.get("priority")
    if priority is not None:
        labels.append(f"Priority ≥ {priority}")
    email_type = _normalize_optional_text(filters.get("email_type"))
    if email_type:
        labels.append(f"Type: {email_type}")
    date_from = _normalize_optional_text(filters.get("date_from"))
    if date_from:
        labels.append(f"From: {date_from}")
    date_to = _normalize_optional_text(filters.get("date_to"))
    if date_to:
        labels.append(f"To date: {date_to}")
    min_score = filters.get("min_score")
    if min_score is not None:
        labels.append(f"Min score: {min_score:.2f}")

    return labels


def sort_search_results(results: Iterable[Any], sort_by: str) -> list[Any]:
    """Sort search results by the specified criterion."""
    items = list(results)
    if sort_by == "date_desc":
        return sorted(items, key=_date_key, reverse=True)
    if sort_by == "date_asc":
        return sorted(items, key=_date_key)
    if sort_by == "sender_asc":
        return sorted(items, key=_sender_key)
    return sorted(items, key=lambda item: float(getattr(item, "score", 0.0)), reverse=True)


def build_filter_chip_html(labels: list[str]) -> str:
    """Render safe chip HTML for active filter labels."""
    return "".join(f"<span class='filter-chip'>{escape(label)}</span>" for label in labels)


def build_export_payload(
    query: str,
    results: Iterable[Any],
    filters: dict[str, Any],
    sort_by: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Serialize results with query, filters, sort order, count, and a UTC generation timestamp."""
    serialized_results = [_serialize_result(result) for result in results]
    timestamp = generated_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    return {
        "query": query,
        "count": len(serialized_results),
        "results": serialized_results,
        "filters": filters,
        "sort_by": sort_by,
        "generated_at": timestamp,
    }


def _serialize_result(result: Any) -> dict[str, Any]:
    """Serialize a search result to a dictionary for export."""
    if hasattr(result, "to_dict"):
        value = result.to_dict()
        if isinstance(value, dict):
            return value

    return {
        "chunk_id": str(getattr(result, "chunk_id", "")),
        "score": float(getattr(result, "score", 0.0)),
        "metadata": dict(getattr(result, "metadata", {})),
        "text": str(getattr(result, "text", "")),
    }


def _date_key(result: Any) -> str:
    """Extract the date string from result metadata for sorting."""
    metadata = getattr(result, "metadata", {}) or {}
    return str(metadata.get("date", "")).strip()


def _sender_key(result: Any) -> str:
    """Extract the sender name/email from result metadata for sorting."""
    metadata = getattr(result, "metadata", {}) or {}
    sender_name = str(metadata.get("sender_name", "")).strip()
    sender_email = str(metadata.get("sender_email", "")).strip()
    return (sender_name or sender_email).lower()


def _normalize_optional_text(value: str | None) -> str | None:
    """Normalize optional text by stripping whitespace, returning None if empty."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
