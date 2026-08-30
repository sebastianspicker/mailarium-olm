"""JSON serialization, bounded-response, dependency, and database helpers for MCP tools."""

from __future__ import annotations

import copy
import json
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from mcp.types import ToolAnnotations

    from mailarium.archive import ArchiveDatabase
    from mailarium.mailbox.mailbox_service import MailboxService
    from mailarium.retrieval.retriever import SearchEngine

logger = logging.getLogger(__name__)


def _serialize_json(data: Any, *, pretty: bool, **kwargs: Any) -> str:
    """Serialize JSON in pretty or compact form."""
    dump_kwargs = dict(kwargs)
    if pretty:
        dump_kwargs.setdefault("indent", 2)
    else:
        dump_kwargs.setdefault("separators", (",", ":"))
    return json.dumps(data, **dump_kwargs)


def _fit_json_candidates(candidates: list[Any], max_chars: int, **kwargs: Any) -> str:
    """Return the first candidate whose compact JSON fits within *max_chars*."""
    for candidate in candidates:
        rendered = _serialize_json(candidate, pretty=False, **kwargs)
        if len(rendered) <= max_chars:
            return rendered
    return "0"


def _fit_truncated_snippet(
    template: Callable[[str], Any],
    snippet: str,
    max_chars: int,
    **kwargs: Any,
) -> str | None:
    """Return the largest snippet payload that still fits within *max_chars*."""
    if not snippet:
        rendered = _serialize_json(template(""), pretty=False, **kwargs)
        return rendered if len(rendered) <= max_chars else None

    lo, hi = 0, len(snippet)
    best: str | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        rendered = _serialize_json(template(snippet[:mid]), pretty=False, **kwargs)
        if len(rendered) <= max_chars:
            best = rendered
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _iter_string_paths(data: Any, *, max_depth: int = 3, _path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    """Collect nested dict string fields up to *max_depth* for budget trimming."""
    if len(_path) > max_depth:
        return []
    if isinstance(data, str):
        return [(_path, data)]
    if not isinstance(data, dict):
        return []
    paths: list[tuple[tuple[str, ...], str]] = []
    for key, value in data.items():
        if key == "_truncated" or not isinstance(key, str):
            continue
        paths.extend(_iter_string_paths(value, max_depth=max_depth, _path=(*_path, key)))
    return paths


def _set_nested_string_field(data: dict[str, Any], path: tuple[str, ...], value: str) -> None:
    """Set one nested dict string field identified by *path*."""
    cursor: dict[str, Any] = data
    for key in path[:-1]:
        next_value = cursor.get(key)
        if not isinstance(next_value, dict):
            return
        cursor = next_value
    if path:
        cursor[path[-1]] = value


def _truncate_largest_string_field(data: dict[str, Any], max_chars: int, **kwargs: Any) -> str | None:
    """Trim the largest nested string field in *data* until the payload fits."""
    string_paths = _iter_string_paths(data)
    if not string_paths:
        return None
    path, original_value = max(string_paths, key=lambda item: len(item[1]))
    if not original_value:
        return None

    lo, hi = 0, len(original_value)
    best: str | None = None
    field_name = ".".join(path)
    metadata_variants = (
        lambda mid: {
            "field": field_name,
            "shown_chars": mid,
            "original_chars": len(original_value),
            "note": "Response trimmed; nested string field compacted to fit limit.",
        },
        lambda mid: {
            "field": field_name,
            "shown_chars": mid,
            "original_chars": len(original_value),
        },
        lambda _mid: True,
    )
    for metadata_factory in metadata_variants:
        lo, hi = 0, len(original_value)
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = copy.deepcopy(data)
            _set_nested_string_field(candidate, path, original_value[:mid])
            candidate["_truncated"] = metadata_factory(mid)
            rendered = _serialize_json(candidate, pretty=False, **kwargs)
            if len(rendered) <= max_chars:
                best = rendered
                lo = mid + 1
            else:
                hi = mid - 1
        if best is not None:
            return best
    return best


def _fallback_truncated_json(
    max_chars: int,
    *,
    snippet: str | None = None,
    field: str | None = None,
    original_count: int | None = None,
    **kwargs: Any,
) -> str:
    """Return the smallest valid truncated JSON payload that fits the hard cap."""
    candidates: list[Any] = []
    if field is not None and original_count is not None:
        candidates.extend(
            [
                {
                    "results": [],
                    "_truncated": {
                        "field": field,
                        "shown": 0,
                        "original_count": original_count,
                        "note": "No items fit.",
                    },
                },
                {"results": [], "_truncated": {"field": field, "shown": 0, "original_count": original_count}},
            ]
        )
    if snippet is not None:
        for template in (
            lambda value: {"data": value, "_truncated": True, "note": "Response too large; truncated to fit limit."},
            lambda value: {"data": value, "_truncated": True},
        ):
            rendered = _fit_truncated_snippet(template, snippet, max_chars, **kwargs)
            if rendered is not None:
                return rendered
        candidates.append({"data": "", "_truncated": True})
    candidates.extend([{"_truncated": True}, [], 0])
    return _fit_json_candidates(candidates, max_chars, **kwargs)


class ToolDepsProto(Protocol):
    """Protocol describing the ToolDeps interface injected by mcp_server.

    Avoids circular imports while giving mypy full attr-defined checking.
    """

    def get_retriever(self) -> SearchEngine:
        """Return the process-scoped retriever used by read-only tool operations."""
        ...

    def get_archive_database(self) -> ArchiveDatabase | None:
        """Return the optional SQLite store so tools can fail closed when it is unavailable."""
        ...

    def get_mailbox_service(self) -> MailboxService | None:
        """Return the process-scoped mailbox service when SQLite is available."""
        ...

    def resolved_runtime_paths(self) -> tuple[str, str]:
        """Return the vector-index and SQLite paths used by the active runtime."""
        ...

    def reset_runtime_clients(self) -> None:
        """Invalidate archive-backed clients after a successful archive mutation."""
        ...

    async def offload(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run blocking work through the host executor instead of blocking the MCP event loop."""
        ...

    def tool_annotations(self, title: str) -> ToolAnnotations:
        """Describe a read-only MCP operation for clients and safety-aware tool dispatch."""
        ...

    def write_tool_annotations(self, title: str) -> ToolAnnotations:
        """Describe a mutating MCP operation so clients can surface its side effects."""
        ...

    def idempotent_write_annotations(self, title: str) -> ToolAnnotations:
        """Describe a repeat-safe write operation for client retry behavior."""
        ...

    def remote_sync_annotations(self, title: str) -> ToolAnnotations:
        """Describe open-world remote reads that also update local state."""
        ...

    def remote_execute_annotations(self, title: str) -> ToolAnnotations:
        """Describe an open-world proposal-bound destructive mailbox mutation."""
        ...

    DB_UNAVAILABLE: str

    def sanitize(self, text: str) -> str:
        """Redact private content before a tool returns text to its caller."""
        ...


def get_deps(deps: ToolDepsProto | None) -> ToolDepsProto:
    """Return *deps* after asserting it has been initialized by ``register()``."""
    if deps is None:
        raise RuntimeError("Tool module not registered - call register() first")
    return deps


async def run_with_db(deps: ToolDepsProto, fn: Callable[..., str]) -> str:
    """Offload ``fn(db)`` to a thread, returning DB_UNAVAILABLE if db is None."""

    def _run() -> str:
        db = deps.get_archive_database()
        if not db:
            return deps.DB_UNAVAILABLE
        # Some MCP helpers legitimately use db.conn directly. Keep the whole
        # facade callback serialized so those reads and writes share the same
        # transaction boundary as ArchiveDatabase methods.
        operation = getattr(db, "operation", None)
        if operation is None:
            return fn(db)
        with operation():
            return fn(db)

    return await deps.offload(_run)


async def run_with_retriever(deps: ToolDepsProto, fn: Callable[..., str]) -> str:
    """Offload ``fn(retriever)`` to a thread."""
    return await deps.offload(lambda: fn(deps.get_retriever()))


def _sanitize_floats(obj: Any) -> Any:
    """Replace NaN/Inf float values with None to produce valid JSON."""
    import math

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj


def json_response(data: Any, *, max_chars: int | None = None, **kwargs: Any) -> str:
    """Standardized JSON serialization with optional size guard.

    If the serialized JSON exceeds *max_chars* (default from
    ``mcp_max_json_response_chars`` setting), the largest top-level list
    is trimmed to fit and a ``_truncated`` metadata key is added.
    """
    data = _sanitize_floats(data)
    raw = _serialize_json(data, pretty=True, **kwargs)

    if max_chars is None:
        from mailarium.config import get_settings

        max_chars = get_settings().mcp_max_json_response_chars

    if max_chars > 0 and len(raw) > max_chars:
        return _truncate_json(data, raw, max_chars, **kwargs)
    return raw


def _truncate_json(data: Any, raw: str, max_chars: int, **kwargs: Any) -> str:
    """Trim the largest list in *data* until the JSON fits *max_chars*.

    Works on a shallow copy of *data* so the caller's dict is not mutated.
    """
    if not isinstance(data, dict):
        return _truncate_non_dict(data, raw, max_chars, **kwargs)

    # Work on a copy so we don't mutate the caller's dict
    data = {**data}
    compact_raw = _serialize_json(data, pretty=False, **kwargs)
    if len(compact_raw) <= max_chars:
        return compact_raw

    # Find the largest list value in the top-level dict
    largest_key, largest_len = _largest_list(data)

    if largest_key is None:
        return _truncate_string_or_fallback(data, raw, max_chars, **kwargs)
    if largest_len <= 1:
        if len(compact_raw) <= max_chars:
            return compact_raw
        return _truncate_string_or_fallback(data, raw, max_chars, **kwargs)

    # Binary search for how many items fit
    lo, hi = 0, largest_len
    original_list = data[largest_key]
    best = 0
    best_result: str | None = None

    while lo <= hi:
        mid = (lo + hi) // 2
        data[largest_key] = original_list[:mid]
        data["_truncated"] = {
            "field": largest_key,
            "shown": mid,
            "original_count": largest_len,
            "note": "No items fit." if mid == 0 else "Response trimmed; use pagination for more.",
        }
        candidate = _serialize_json(data, pretty=False, **kwargs)
        if len(candidate) <= max_chars:
            best = mid
            best_result = candidate
            lo = mid + 1
        else:
            hi = mid - 1

    if best_result is None:
        trimmed_string = _truncate_largest_string_field(data, max_chars, **kwargs)
        if trimmed_string is not None:
            return trimmed_string
        return _fallback_truncated_json(
            max_chars,
            snippet=raw[:max_chars],
            field=largest_key,
            original_count=largest_len,
            **kwargs,
        )

    logger.debug(
        "json_response truncated %s from %d to %d items (%d chars)",
        largest_key,
        largest_len,
        best,
        len(best_result),
    )
    return best_result


def _truncate_non_dict(data: Any, raw: str, max_chars: int, **kwargs: Any) -> str:
    """Wrap list responses for bounded JSON truncation and use a snippet fallback for other values."""
    if isinstance(data, list):
        wrapped = {"results": data}
        compact = _serialize_json(wrapped, pretty=False, **kwargs)
        return compact if len(compact) <= max_chars else _truncate_json(wrapped, compact, max_chars, **kwargs)
    return _fallback_truncated_json(max_chars, snippet=raw[:max_chars], **kwargs)


def _largest_list(data: dict[str, Any]) -> tuple[str | None, int]:
    """Identify the largest top-level list so response compaction removes the highest-volume field first."""
    lists = ((key, len(value)) for key, value in data.items() if isinstance(value, list))
    return max(lists, key=lambda item: item[1], default=(None, 0))


def _truncate_string_or_fallback(data: dict[str, Any], raw: str, max_chars: int, **kwargs: Any) -> str:
    """Trim the largest string field when possible, otherwise emit the bounded fallback envelope."""
    trimmed = _truncate_largest_string_field(data, max_chars, **kwargs)
    return trimmed or _fallback_truncated_json(max_chars, snippet=raw[:max_chars], **kwargs)


def json_error(message: str) -> str:
    """Serialize an error in the ``{\"error\": message, \"success\": false}`` JSON envelope."""
    return json.dumps({"error": message, "success": False})


_network_lock = threading.Lock()


async def run_with_network(deps: ToolDepsProto, fn: Callable[..., str]) -> str:
    """Offload ``fn(db, network)`` with DB guard and cached CommunicationNetwork.

    Thread-safe: uses ``_network_lock`` to prevent concurrent threads from
    both creating a ``CommunicationNetwork`` when ``_cached_comm_network`` is
    not yet set.  The lock only contends during the one-time initialization;
    subsequent calls see the cached instance immediately.
    """

    def _run() -> str:
        db = deps.get_archive_database()
        if not db:
            return deps.DB_UNAVAILABLE
        net = getattr(db, "_cached_comm_network", None)
        if net is None:
            with _network_lock:
                # Double-check under lock - another thread may have created it.
                net = getattr(db, "_cached_comm_network", None)
                if net is None:
                    from mailarium.investigation.network_analysis import CommunicationNetwork

                    try:
                        net = CommunicationNetwork(db)
                    except Exception as exc:
                        return json_error(f"Network analysis unavailable: {type(exc).__name__}")
                    db._cached_comm_network = net  # type: ignore[attr-defined]
        return fn(db, net)

    return await deps.offload(_run)
