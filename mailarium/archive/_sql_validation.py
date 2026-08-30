"""SQL identifier and query fragment validation helpers.

Separated from ``db_schema`` to avoid circular imports with
``db_schema_migrations``.
"""

from __future__ import annotations

import re
from typing import Any

_VALID_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_sql_identifier(name: str, *, allowlist: set[str] | None = None) -> str:
    """Validate *name* as a safe SQL table/column identifier.

    If *allowlist* is provided, *name* must be in the set.
    Otherwise, only basic alphanumeric/underscore identifiers are accepted.
    Raises ``ValueError`` for invalid names.
    """
    if not name or not isinstance(name, str):
        raise ValueError(f"Invalid SQL identifier type or empty: {name!r}")
    if allowlist is not None:
        if name not in allowlist:
            raise ValueError(f"SQL identifier {name!r} not in allowlist")
        return name
    if not _VALID_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def validate_sql_identifiers(
    names: list[str] | tuple[str, ...],
    *,
    allowlist: set[str] | None = None,
) -> list[str]:
    """Validate multiple SQL identifiers (table/column names)."""
    return [validate_sql_identifier(n, allowlist=allowlist) for n in names]


def validate_order_by(
    sort_by: str,
    sort_order: str,
    *,
    allowed_columns: set[str] | None = None,
) -> tuple[str, str]:
    """Validate and return (safe_sort_by, safe_sort_order) for ORDER BY clauses.

    Limits sort direction to ``ASC`` / ``DESC`` and validates column names.
    """
    safe_sort_by = validate_sql_identifier(sort_by, allowlist=allowed_columns)
    safe_sort_order = "ASC" if _VALID_IDENTIFIER_RE.match(sort_order) and sort_order.upper() == "ASC" else "DESC"
    return safe_sort_by, safe_sort_order


def validate_column_update_pairs(
    updates: dict[str, Any],
    *,
    allowed_columns: set[str],
) -> str:
    """Build a safe ``SET col=?, col2=?`` fragment from validated column names.

    Returns the SET clause string (without leading ``SET``).
    """
    validated = validate_sql_identifiers(list(updates.keys()), allowlist=allowed_columns)
    return ", ".join(f"{col} = ?" for col in validated)


def sql_in_placeholders(items: list | tuple) -> str:
    """Return a comma-separated ``?`` placeholder string for an IN clause.

    Example: ``sql_in_placeholders(["a", "b"])`` returns ``"?,?"``.
    The result contains only ``?`` and ``,`` characters -- no SQL injection risk.
    """
    if not items:
        raise ValueError("Cannot build IN clause for empty items list")
    return ",".join("?" for _ in items)
