"""Base classes and utilities for MCP tool input models.

Two base classes eliminate repeated ``model_config`` declarations:

- ``StrictInput``: strips whitespace from strings, forbids extra fields.
- ``PlainInput``: forbids extra fields only (no string stripping).

``DateRangeInput`` is a mixin providing ISO-date validation for
``date_from`` / ``date_to`` pairs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .repo_paths import normalize_local_path, validate_local_read_path, validate_output_path, validate_runtime_path
from .validation import parse_iso_date
from .validation import validate_date_window as ensure_valid_date_window


def _resolve_local_path(v: str | None, *, field_name: str = "path") -> Path | None:
    """Normalize a local path while rejecting null bytes and parent traversal."""
    if v is None:
        return None
    return normalize_local_path(v, field_name=field_name)


def _validate_local_path(v: str | None, *, field_name: str = "path") -> str | None:
    """Reject null bytes and path traversal for local paths."""
    _resolve_local_path(v, field_name=field_name)
    return v


def _validate_local_read_path(v: str | None, *, field_name: str = "path") -> str | None:
    """Reject local read paths outside configured allowlisted roots."""
    if v is None:
        return None
    validate_local_read_path(v, field_name=field_name)
    return v


def _validate_readable_file_path(v: str | None, *, field_name: str = "path") -> str | None:
    """Validate a readable local file path."""
    if v is None:
        return None
    resolved = validate_local_read_path(v, field_name=field_name)
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"{field_name} must resolve to an existing file")
    if not os.access(resolved, os.R_OK):
        raise ValueError(f"{field_name} must be readable")
    return v


def _validate_readable_dir_path(v: str | None, *, field_name: str = "path") -> str | None:
    """Validate a readable local directory path."""
    if v is None:
        return None
    resolved = validate_local_read_path(v, field_name=field_name)
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"{field_name} must resolve to an existing directory")
    if not os.access(resolved, os.R_OK):
        raise ValueError(f"{field_name} must be readable")
    return v


def _validate_runtime_path(v: str | None, *, field_name: str = "path") -> str | None:
    """Validate runtime override paths with local-path safety checks."""
    if v is None:
        return None
    validate_runtime_path(v, field_name=field_name)
    return v


def _validate_output_path(v: str | None) -> str | None:
    """Validate output paths against allowlisted writable roots."""
    if v is None:
        return None
    validate_output_path(v, field_name="Output path")
    return v


def _coerce_json_object_input(value: object) -> object:
    """Accept JSON-object strings from MCP wrappers that serialize params eagerly."""
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Input must be a JSON object or JSON-encoded object string.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Input JSON must decode to an object.")
    return parsed


# ── Base Classes ─────────────────────────────────────────────


class StrictInput(BaseModel):
    """Base for MCP inputs with whitespace stripping."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def coerce_json_object_string(cls, value: object) -> object:
        return _coerce_json_object_input(value)


class PlainInput(BaseModel):
    """Base for MCP inputs without whitespace stripping."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def coerce_json_object_string(cls, value: object) -> object:
        return _coerce_json_object_input(value)


class DateRangeInput(BaseModel):
    """Reusable date-range validation mixin for MCP inputs."""

    date_from: str | None = Field(
        default=None,
        description="Start date in YYYY-MM-DD format (inclusive). E.g., '2023-01-01'.",
    )
    date_to: str | None = Field(
        default=None,
        description="End date in YYYY-MM-DD format (inclusive). E.g., '2023-12-31'.",
    )

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return parse_iso_date(value)

    @model_validator(mode="after")
    def validate_date_window(self):
        ensure_valid_date_window(self.date_from, self.date_to)
        return self
