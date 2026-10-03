"""JSON presentation of search results shared by the CLI and MCP interfaces.

Limits default to the MCP budget settings of the caller-supplied ``Settings``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mailarium.model.message_formatting import estimate_tokens, truncate_body

if TYPE_CHECKING:
    from mailarium.platform.settings import Settings
    from mailarium.retrieval.models import SearchResult


def _settings_limit(settings: Any, attr: str, default: int) -> int:
    value = getattr(settings, attr, default) if settings else default
    return int(value)


def serialize_results(
    settings: Settings | None,
    query: str,
    results: list[SearchResult],
    max_body_chars: int | None = None,
    max_response_tokens: int | None = None,
) -> dict[str, Any]:
    """Serialize search results into a stable JSON-ready payload.

    Applies per-body truncation via *max_body_chars* and stops adding
    results when the cumulative output would exceed *max_response_tokens*.
    Both default to the MCP budget values in *settings*.
    """
    body_limit, response_limit = _format_limits(settings, max_body_chars, max_response_tokens)

    out: list[dict[str, Any]] = []
    cumulative_tokens = 0
    total_count = len(results)
    truncation_note = ""
    for result in results:
        entry = result.to_dict()
        if body_limit > 0:
            entry["text"] = truncate_body(entry.get("text", ""), body_limit)
        entry_tokens = estimate_tokens(str(entry))
        if response_limit > 0 and cumulative_tokens + entry_tokens > response_limit and out:
            remaining = total_count - len(out)
            truncation_note = f"{remaining} more result(s) omitted - narrow your search or use email_deep_context"
            break
        out.append(entry)
        cumulative_tokens += entry_tokens
    returned_count = len(out)
    omitted_count = max(total_count - returned_count, 0)
    return {
        "query": query,
        "count": returned_count,
        "total_count": total_count,
        "returned_count": returned_count,
        "omitted_count": omitted_count,
        "results_truncated": omitted_count > 0,
        "truncation_note": truncation_note,
        "results": out,
    }


def _format_limits(
    settings: Settings | None,
    max_body_chars: int | None,
    max_response_tokens: int | None,
) -> tuple[int, int]:
    """Resolve body and response limits from explicit values or the MCP budget settings."""
    body_limit = max_body_chars if max_body_chars is not None else _settings_limit(settings, "mcp_max_body_chars", 500)
    response_limit = (
        max_response_tokens if max_response_tokens is not None else _settings_limit(settings, "mcp_max_response_tokens", 8000)
    )
    return body_limit, response_limit
