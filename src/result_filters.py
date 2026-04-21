"""Pure-function metadata filters and utilities extracted from retriever.py."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .retriever import SearchResult


def _normalize_filter(value: str | None) -> str | None:
    """Strip whitespace and convert empty strings to None."""
    if isinstance(value, str):
        value = value.strip()
    return value or None


# ── Data-driven string filter matchers ──
# Each entry: (metadata_keys, match_type)
#   match_type "contains" → needle in value
#   match_type "exact"    → needle == value
STRING_FILTERS: dict[str, tuple[tuple[str, ...], str]] = {
    "sender": (("sender_email", "sender_name"), "contains"),
    "subject": (("subject",), "contains"),
    "folder": (("folder",), "contains"),
    "cc": (("cc",), "contains"),
    "to": (("to",), "contains"),
    "bcc": (("bcc",), "contains"),
    "email_type": (("email_type",), "exact"),
}


def _matches_string(
    result: SearchResult,
    needle: str | None,
    metadata_keys: tuple[str, ...],
    match_type: str,
) -> bool:
    """Parameterized string matcher for metadata fields."""
    if not needle:
        return True
    needle_lower = needle.lower()
    for key in metadata_keys:
        value = str(result.metadata.get(key, "") or "").lower()
        if match_type == "contains" and needle_lower in value:
            return True
        if match_type == "exact" and needle_lower == value:
            return True
    return False


def _matches_date_from(result: SearchResult, date_from: str | None) -> bool:
    if not date_from:
        return True
    raw_date = result.metadata.get("date")
    if not raw_date:
        return False
    date_prefix = str(raw_date)[:10]
    if not date_prefix or not date_prefix[:1].isdigit():
        return False
    return date_prefix >= date_from


def _matches_date_to(result: SearchResult, date_to: str | None) -> bool:
    if not date_to:
        return True
    raw_date = result.metadata.get("date")
    if not raw_date:
        return False
    date_prefix = str(raw_date)[:10]
    if not date_prefix or not date_prefix[:1].isdigit():
        return False
    return date_prefix <= date_to


def _matches_has_attachments(result: SearchResult, has_attachments: bool | None) -> bool:
    if has_attachments is None:
        return True
    raw = result.metadata.get("has_attachments", False)
    value = str(raw).lower() in ("true", "1", "yes") if not isinstance(raw, bool) else raw
    return value == has_attachments


def _matches_priority(result: SearchResult, priority: int | None) -> bool:
    if priority is None:
        return True
    try:
        result_priority = int(result.metadata.get("priority", 0))
    except (TypeError, ValueError):
        return False
    return result_priority >= priority


def _matches_min_score(result: SearchResult, min_score: float | None) -> bool:
    if min_score is None:
        return True
    calibration = str(result.metadata.get("score_calibration") or "").strip().lower()
    if calibration == "synthetic":
        return True
    return result.score >= min_score


def _matches_allowed_uids(
    result: SearchResult,
    allowed_uids: set[str] | None,
) -> bool:
    if allowed_uids is None:
        return True
    uid = str(result.metadata.get("uid", "")).strip()
    return uid in allowed_uids


def _matches_category(result: SearchResult, category: str | None) -> bool:
    if not category:
        return True
    raw = str(result.metadata.get("categories", "") or "")
    # Categories are comma-separated; check for exact match per category
    cats = [c.strip().lower() for c in raw.split(",") if c.strip()]
    return category.lower() in cats


def _matches_is_calendar(result: SearchResult, is_calendar: bool | None) -> bool:
    if is_calendar is None:
        return True
    value = str(result.metadata.get("is_calendar_message", "False"))
    return (value.lower() in ("true", "1")) == is_calendar


def _matches_attachment_name(result: SearchResult, attachment_name: str | None) -> bool:
    """Partial match on attachment_names or attachment_filename metadata."""
    if not attachment_name:
        return True
    needle = attachment_name.lower()
    # Check attachment_names list (comma-separated string or list)
    names = result.metadata.get("attachment_names", "")
    if isinstance(names, list):
        names = ", ".join(names)
    if needle in str(names).lower():
        return True
    # Check attachment_filename (single-chunk metadata)
    fname = str(result.metadata.get("attachment_filename", "") or "").lower()
    if needle in fname:
        return True
    legacy_fname = str(result.metadata.get("filename", "") or "").lower()
    return needle in legacy_fname


def _matches_attachment_type(result: SearchResult, attachment_type: str | None) -> bool:
    """Match file extension in attachment_names or attachment_filename metadata."""
    if not attachment_type:
        return True
    ext = "." + attachment_type.lower().lstrip(".")

    def _has_ext(filename: str) -> bool:
        return filename.lower().endswith(ext)

    names = result.metadata.get("attachment_names", "")
    if isinstance(names, list):
        if any(_has_ext(n) for n in names):
            return True
    else:
        # Comma-separated string
        for n in str(names).split(","):
            if _has_ext(n.strip()):
                return True
    fname = str(result.metadata.get("attachment_filename", "") or "")
    if _has_ext(fname):
        return True
    legacy_fname = str(result.metadata.get("filename", "") or "")
    return _has_ext(legacy_fname)


def apply_metadata_filters(
    results: list[SearchResult],
    *,
    sender: str | None = None,
    subject: str | None = None,
    folder: str | None = None,
    cc: str | None = None,
    to: str | None = None,
    bcc: str | None = None,
    email_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    has_attachments: bool | None = None,
    priority: int | None = None,
    min_score: float | None = None,
    allowed_uids: set[str] | None = None,
    category: str | None = None,
    is_calendar: bool | None = None,
    attachment_name: str | None = None,
    attachment_type: str | None = None,
) -> list[SearchResult]:
    """Apply all metadata filters to search results in one pass."""
    _sf = STRING_FILTERS
    string_filters = [
        (sender, *_sf["sender"]),
        (subject, *_sf["subject"]),
        (folder, *_sf["folder"]),
        (cc, *_sf["cc"]),
        (to, *_sf["to"]),
        (bcc, *_sf["bcc"]),
        (email_type, *_sf["email_type"]),
    ]
    return [
        result
        for result in results
        if all(_matches_string(result, needle, keys, mtype) for needle, keys, mtype in string_filters)
        and _matches_date_from(result, date_from)
        and _matches_date_to(result, date_to)
        and _matches_has_attachments(result, has_attachments)
        and _matches_priority(result, priority)
        and _matches_min_score(result, min_score)
        and _matches_allowed_uids(result, allowed_uids)
        and _matches_category(result, category)
        and _matches_is_calendar(result, is_calendar)
        and _matches_attachment_name(result, attachment_name)
        and _matches_attachment_type(result, attachment_type)
    ]


# ── Deduplication ──


def _email_dedup_key(meta: dict[str, Any]) -> str | None:
    """Build a deduplication key from metadata."""
    uid = str(meta.get("uid", "")).strip()
    if uid:
        return f"uid:{uid}"

    message_id = str(meta.get("message_id", "")).strip()
    if message_id:
        return f"msg:{message_id}"

    sender_email = str(meta.get("sender_email", "")).strip().lower()
    date_value = str(meta.get("date", "")).strip()[:10]
    subject_val = str(meta.get("subject", "")).strip().lower()

    if sender_email or date_value or subject_val:
        return f"fallback:{sender_email}|{date_value}|{subject_val}"
    return None


def _attachment_dedup_key(meta: dict[str, Any]) -> str | None:
    email_key = _email_dedup_key(meta)
    if not email_key:
        return None
    attachment_name = str(meta.get("attachment_filename") or meta.get("attachment_name") or "").strip().lower()
    if not attachment_name and str(meta.get("candidate_kind") or "").strip().lower() != "attachment":
        return None
    return f"{email_key}|attachment:{attachment_name or 'unknown'}"


def _deduplicate_by_email(results: list[SearchResult]) -> list[SearchResult]:
    """Keep only the best-scoring chunk per unique email UID.

    Results are already sorted by relevance (best first), so the first
    occurrence of each UID is the best chunk.  When a result has no UID,
    uses a fallback dedup key (sender+date+subject) to still deduplicate.
    """
    seen_keys: set[str] = set()
    seen_attachment_keys: set[str] = set()
    deduped: list[SearchResult] = []
    for result in results:
        attachment_key = _attachment_dedup_key(result.metadata)
        if attachment_key:
            if attachment_key in seen_attachment_keys:
                continue
            seen_attachment_keys.add(attachment_key)
            deduped.append(result)
            continue
        key = _email_dedup_key(result.metadata)
        if not key:
            deduped.append(result)
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(result)
    return deduped


# ── JSON safety ──


def _safe_json_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 4)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value
