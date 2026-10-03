"""Small coercion and text-normalization helpers shared across runtime modules."""

from __future__ import annotations

from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    """Safely convert a value to a dict, returning empty dict if not already a dict."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Safely convert a value to a list, returning empty list if not already a list."""
    return value if isinstance(value, list) else []


def compact(value: Any) -> str:
    """Normalize a value to a compact string with single spaces and no leading/trailing whitespace."""
    return " ".join(str(value or "").split()).strip()
