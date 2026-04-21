"""Shared helpers for case-analysis modules."""

from __future__ import annotations

from typing import Any

CASE_ANALYSIS_VERSION = "1"


def warning(
    *,
    code: str,
    severity: str,
    message: str,
    affects: list[str],
) -> dict[str, Any]:
    """Return one structured scope warning."""
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "affects": affects,
    }


def as_dict(value: Any) -> dict[str, Any]:
    """Return a dict or an empty dict for untyped payload access."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Return a list or an empty list for untyped payload access."""
    return value if isinstance(value, list) else []


def merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dict overrides into a base payload."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict(as_dict(merged.get(key)), value)
        else:
            merged[key] = value
    return merged
