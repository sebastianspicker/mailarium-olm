"""Dependency-light validation for explicit retrieval scope labels."""

from __future__ import annotations

import re

MAX_SCOPE_LENGTH = 64
GENERAL_SCOPE = "general"

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_WHITESPACE = re.compile(r"\s+")


def normalize_scope(scope: str | None = None) -> str:
    """Normalize a user-declared scope without silently accepting invalid input."""
    if scope is None:
        return GENERAL_SCOPE
    if not isinstance(scope, str):
        raise TypeError("scope must be a string or None")
    if _CONTROL_CHARACTERS.search(scope):
        raise ValueError("scope must not contain control characters")
    normalized = _WHITESPACE.sub(" ", scope).strip().lower()
    if not normalized:
        raise ValueError("scope must not be empty")
    if len(normalized) > MAX_SCOPE_LENGTH:
        raise ValueError(f"scope must be at most {MAX_SCOPE_LENGTH} characters")
    return normalized
