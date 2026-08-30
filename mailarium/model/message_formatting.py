"""Pure message headers and bounded context formatting."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .data_shapes import as_list


def format_sender(name: str | None, email: str | None) -> str:
    """Format sender consistently for headers and output."""
    clean_name = (name or "").strip()
    clean_email = (email or "").strip()
    if clean_name and clean_email:
        return f"{clean_name} <{clean_email}>"
    if clean_name:
        return clean_name
    return clean_email


def build_email_header(email_dict: Mapping[str, Any]) -> str:
    """Build a concise metadata header for embedding context."""
    parts: list[str] = []
    _append_header_value(parts, "Date", email_dict.get("date"))
    _append_header_value(parts, "From", format_sender(email_dict.get("sender_name"), email_dict.get("sender_email")))
    _append_header_value(parts, "To", ", ".join(as_list(email_dict.get("to"))[:3]))
    _append_header_value(parts, "CC", ", ".join(as_list(email_dict.get("cc"))[:3]))
    _append_header_value(parts, "Subject", email_dict.get("subject"))
    _append_header_value(parts, "Folder", email_dict.get("folder"))
    categories = email_dict.get("categories")
    if categories and isinstance(categories, list):
        parts.append(f"Categories: {', '.join(str(category) for category in categories[:5])}")
    if email_dict.get("is_calendar_message"):
        parts.append("[Calendar/Meeting]")
    if email_dict.get("has_attachments"):
        attachment_names = as_list(email_dict.get("attachment_names"))
        parts.append(f"Attachments: {', '.join(attachment_names[:5])}" if attachment_names else "Has attachments")
    return "\n".join(parts)


def _append_header_value(parts: list[str], label: str, value: Any) -> None:
    if value:
        parts.append(f"{label}: {value}")


def build_result_header(metadata: Mapping[str, Any]) -> str:
    """Build the compact metadata header used in LLM result context."""
    parts: list[str] = []
    date_value = metadata.get("date")
    _append_header_value(parts, "Date", str(date_value)[:10] if date_value else "")
    _append_header_value(parts, "From", format_sender(metadata.get("sender_name"), metadata.get("sender_email")))
    to_value = metadata.get("to")
    if to_value:
        _append_header_value(parts, "To", ", ".join(str(item) for item in to_value) if isinstance(to_value, list) else to_value)
    _append_header_value(parts, "Subject", metadata.get("subject"))
    _append_nondefault_header(parts, "Type", metadata.get("email_type"), "original")
    _append_nondefault_header(parts, "Folder", metadata.get("folder"), "Inbox")
    _append_nondefault_header(parts, "Priority", metadata.get("priority"), "0")
    _append_nondefault_header(parts, "Categories", metadata.get("categories"))
    if str(metadata.get("is_calendar_message", "")).lower() in ("true", "1"):
        parts.append("[Calendar/Meeting]")
    attachment_names = metadata.get("attachment_names")
    if attachment_names and str(attachment_names).strip():
        parts.append(f"Attachments: {attachment_names}")
    return "\n".join(parts)


def _append_nondefault_header(parts: list[str], label: str, value: Any, default: str = "") -> None:
    if value and str(value).strip() and str(value) != default:
        parts.append(f"{label}: {value}")


def truncate_body(text: str | None, max_chars: int) -> str:
    """Bound message text while preserving the existing deep-context hint."""
    if text is None:
        return ""
    text = text.replace("\xa0", " ")
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    total_chars = len(text)
    return (
        text[:max_chars] + f"\n[...truncated at {max_chars:,}/{total_chars:,} chars. "
        f"Use email_deep_context with the UID to read the full {total_chars:,}-character body.]"
    )


def format_context_block(text: str, metadata: Mapping[str, Any], score: float, *, max_body_chars: int = 0) -> str:
    """Format one result block for LLM context."""
    return f"---\n{build_result_header(metadata)}\nRelevance: {score:.2f}\n---\n{truncate_body(text, max_body_chars)}\n"


def estimate_tokens(text: str | None) -> int:
    """Rough token estimate for LLM context budgeting."""
    return max(1, len(text) // 4) if text else 1


def format_triage_results(results: list[Any], preview_chars: int = 200) -> list[dict[str, Any]]:
    """Format results as compact triage entries without retrieval dependencies."""
    compact: list[dict[str, Any]] = []
    for result in results:
        metadata = result.metadata
        entry: dict[str, Any] = {
            "uid": metadata.get("uid", ""),
            "sender": metadata.get("sender_email", ""),
            "date": str(metadata.get("date", ""))[:10],
            "subject": metadata.get("subject", ""),
            "score": round(result.score, 3),
        }
        if preview_chars > 0:
            body = _strip_metadata_header(result.text or "")
            entry["preview"] = body[:preview_chars] + "..." if len(body) > preview_chars else body
        compact.append(entry)
    return compact


_META_HEADER_PREFIXES = (
    "Date:",
    "From:",
    "To:",
    "CC:",
    "Subject:",
    "Folder:",
    "Categories:",
    "Attachments:",
    "Type:",
    "Priority:",
    "Relevance:",
    "Has attachments",
)


def _strip_metadata_header(text: str) -> str:
    header_end = 0
    saw_header = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if (
            stripped.startswith(_META_HEADER_PREFIXES)
            or stripped.startswith("[Calendar/Meeting]")
            or (stripped.startswith("[Part ") and "/" in stripped and stripped.endswith("]"))
        ):
            saw_header = True
            header_end += len(line)
        elif saw_header and not stripped:
            header_end += len(line)
        else:
            break
    return text[header_end:].strip() if saw_header else text
