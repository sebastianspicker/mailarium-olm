"""Shared utility functions for QA evaluation scoring.

This module consolidates duplicate code across qa_eval_scoring_*.py files
to follow the ponytail principle of code reuse.
"""

from __future__ import annotations

import re
from typing import Any

from ._utils import as_dict, as_list

# Regex pattern for extracting answer terms
ANSWER_TERM_RE = re.compile(r"[0-9a-zA-ZäöüÄÖÜß._-]+")

# Stopwords to filter out from answer text
ANSWER_STOPWORDS = {
    "aber",
    "after",
    "and",
    "auch",
    "because",
    "beim",
    "beziehungsweise",
    "dann",
    "dass",
    "dem",
    "denn",
    "der",
    "des",
    "die",
    "dies",
    "does",
    "eine",
    "einer",
    "eines",
    "evidence",
    "from",
    "have",
    "into",
    "kein",
    "keine",
    "likely",
    "message",
    "nach",
    "oder",
    "over",
    "says",
    "sein",
    "some",
    "that",
    "their",
    "there",
    "these",
    "this",
    "under",
    "used",
    "with",
    "without",
}


def normalize_eval_text(value: str) -> str:
    """Normalize evaluation text by casefolding and collapsing whitespace.

    Args:
        value: The text to normalize.

    Returns:
        Normalized text string.
    """
    return " ".join((value or "").casefold().split())


def append_unique(values: list[str], value: Any) -> None:
    """Append a value to a list if it's non-empty and not already present.

    Args:
        values: The list to append to.
        value: The value to append.
    """
    compact = str(value or "").strip()
    if compact and compact not in values:
        values.append(compact)


def ratio(numerator: int, denominator: int) -> float | None:
    """Calculate the ratio of numerator to denominator.

    Args:
        numerator: The numerator value.
        denominator: The denominator value (must be > 0).

    Returns:
        The ratio as a float (0.0-1.0), or None if denominator is <= 0.
    """
    if denominator <= 0:
        return None
    return numerator / denominator


def dict_has_substance(value: dict[str, Any]) -> bool:
    """Check if a dict contains any non-empty, non-null values recursively.

    Args:
        value: The dict to check.

    Returns:
        True if the dict has substance (non-empty nested dicts, non-empty lists,
        or non-null/non-empty primitive values), False otherwise.
    """
    for item in value.values():
        if isinstance(item, dict) and item and dict_has_substance(item):
            return True
        if isinstance(item, list) and any(
            (isinstance(member, dict) and bool(member)) or member not in (None, "", [], {}) for member in item
        ):
            return True
        if item not in (None, "", [], {}):
            return True
    return False


def collect_identifiers(value: Any, *, field_names: set[str], observed: list[str]) -> None:
    """Recursively collect identifier values from nested dicts/lists.

    Args:
        value: The value to search through (dict, list, or other).
        field_names: Set of field names whose values should be collected.
        observed: List to append unique found values to.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if key in field_names:
                if isinstance(item, list):
                    for member in item:
                        append_unique(observed, member)
                else:
                    append_unique(observed, item)
            collect_identifiers(item, field_names=field_names, observed=observed)
        return
    if isinstance(value, list):
        for item in value:
            collect_identifiers(item, field_names=field_names, observed=observed)


__all__ = [
    "ANSWER_STOPWORDS",
    "ANSWER_TERM_RE",
    "append_unique",
    "as_dict",
    "as_list",
    "collect_identifiers",
    "dict_has_substance",
    "normalize_eval_text",
    "ratio",
]
