"""Shared validation helpers for date-like CLI/MCP/UI inputs."""

from __future__ import annotations

from datetime import date


def parse_iso_date(value: str) -> str:
    """Validate and return a YYYY-MM-DD date string."""
    date.fromisoformat(value)
    return value


def normalize_optional_iso_date(value: str | None) -> str | None:
    """Trim an optional date string and validate when present."""
    if value is None:
        return None
    clean = value.strip()
    if not clean:
        return None
    return parse_iso_date(clean)


def validate_date_window(date_from: str | None, date_to: str | None) -> None:
    """Ensure the date range is non-inverted when both bounds exist."""
    if date_from and date_to:
        from datetime import date

        if date.fromisoformat(date_from) > date.fromisoformat(date_to):
            raise ValueError("date_from cannot be later than date_to")


def positive_int(value: str) -> int:
    """Parse and return a positive integer from a string."""
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("Value must be a positive integer.")
    return parsed


def score_float(value: str) -> float:
    """Parse and return a float bounded to [0.0, 1.0]."""
    import math

    parsed = float(value)
    if math.isnan(parsed) or math.isinf(parsed):
        raise ValueError("Value must be a finite number between 0.0 and 1.0.")
    if not (0.0 <= parsed <= 1.0):
        raise ValueError("Value must be between 0.0 and 1.0.")
    return parsed
