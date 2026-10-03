"""Shared value coercion and snippet helpers for answer-context modules."""

from __future__ import annotations

from typing import Any

from mailarium.model.data_shapes import as_list


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _float(value: Any) -> float:
    return float(value) if value else 0.0


def _int(value: Any) -> int:
    return int(value) if value else 0


def _snippet(text: str, *, max_chars: int = 280) -> str:
    """Return a compact single-line text preview capped at *max_chars* with a trailing ellipsis."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _truthy_strings(values: Any) -> list[str]:
    """Normalize iterable values to strings while discarding falsy entries."""
    return [str(item) for item in (values or []) if item]


def _nonblank_strings(values: Any) -> list[str]:
    """Normalize list values to strings while discarding blank entries and non-list inputs."""
    return [str(item) for item in as_list(values) if str(item).strip()]


def _dicts(values: Any) -> list[dict[str, Any]]:
    """Copy only mapping-shaped records from optional collections."""
    return [dict(item) for item in (values or []) if isinstance(item, dict)]
