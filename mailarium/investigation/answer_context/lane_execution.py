"""Per-lane retrieval execution, scan filtering, and lane diagnostics shared by search pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mailarium.retrieval.scan_session import filter_seen

from .lanes import _lane_expansion_terms, _segment_search_results


@dataclass(slots=True)
class LaneDiagnosticsInput:
    """Capture one executed lane's search output and diagnostics inputs."""

    lane_id: str
    query: str
    executed_query: str
    results: list[Any]
    scan_id: str | None
    scan_meta: dict[str, Any] | None
    lane_search_top_k: int
    expansion_terms: list[str]
    debug: dict[str, Any]
    segment_diag: dict[str, Any]


def _apply_filter_seen(scan_id: str | None, results: list[Any]) -> tuple[list[Any], dict[str, Any] | None]:
    """Apply scan session filtering to results.

    Filters out results that have already been seen in a previous scan session.
    If no scan_id is provided, returns the results unchanged.

    Args:
        scan_id: Optional identifier for the scan session.
        results: List of search results to filter.

    Returns:
        A tuple of (filtered_results, scan_meta) where scan_meta contains
        metadata about the filtering operation, or None if no filtering was done.
    """
    if scan_id:
        return filter_seen(scan_id, results)
    return results, None


def _build_lane_diagnostics_item(context: LaneDiagnosticsInput) -> dict[str, Any]:
    """Build a diagnostics item for a single lane.

    Creates a structured diagnostics dictionary containing information about
    a lane's search operation, including query, results count, expansion terms,
    and scan metadata.

    Args:
        context: LaneDiagnosticsInput dataclass containing all lane diagnostics data.

    Returns:
        A dictionary with lane diagnostics information.
    """
    item: dict[str, Any] = {
        "lane_id": context.lane_id,
        "query": context.query,
        "executed_query": context.executed_query,
        "result_count": len(context.results),
        "used_query_expansion": bool(context.debug.get("used_query_expansion")),
        "scan_id": context.scan_id or "",
        "excluded_count": int((context.scan_meta or {}).get("excluded_count") or 0),
        "search_top_k": context.lane_search_top_k,
        "expansion_terms": context.expansion_terms,
    }
    item.update(context.segment_diag)
    return item


def _lane_search_kwargs(search_kwargs: dict[str, Any], *, lane_query: str, lane_search_top_k: int) -> dict[str, Any]:
    """Create search kwargs for a specific lane.

    Combines base search kwargs with lane-specific query and top_k,
    filtering out keys that start with underscore.

    Args:
        search_kwargs: Base search keyword arguments.
        lane_query: The query string for this lane.
        lane_search_top_k: The top_k value for this lane.

    Returns:
        A dictionary of search kwargs for the lane.
    """
    return {
        key: value
        for key, value in {**search_kwargs, "query": lane_query, "top_k": lane_search_top_k}.items()
        if not str(key).startswith("_")
    }


def _lane_runtime_results(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    lane_query: str,
    lane_id: str,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
    base_lane_query: str,
) -> tuple[list[Any], list[Any], list[Any], dict[str, Any], list[str], dict[str, Any] | None]:
    """Execute search for a single lane and return results with diagnostics.

    Performs the main search, applies seen filters, extracts segment results,
    and builds lane diagnostics.

    Args:
        retriever: The retriever instance to use for search.
        search_kwargs: Base search keyword arguments.
        lane_query: The query string for this lane.
        lane_id: Identifier for this lane.
        scan_id: Optional scan identifier.
        lane_search_top_k: Top k for lane search.
        bank_limit: Maximum items in the evidence bank.
        base_lane_query: The base query for this lane.

    Returns:
        A tuple of (raw_lane_results, lane_results, segment_results,
        diagnostics, expansion_terms, lane_scan_meta).
    """
    lane_results = retriever.search_filtered(
        **_lane_search_kwargs(
            search_kwargs,
            lane_query=lane_query,
            lane_search_top_k=lane_search_top_k,
        )
    )
    raw_lane_results = list(lane_results)
    lane_results, lane_scan_meta = _apply_filter_seen(scan_id, lane_results)
    debug = dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)) or {})
    executed_query = str(debug.get("executed_query") or lane_query)
    expansion_terms = _lane_expansion_terms(
        base_query=base_lane_query,
        lane_query=lane_query,
        executed_query=executed_query,
        query_expansion_suffix=str(debug.get("query_expansion_suffix") or ""),
    )
    segment_results, segment_diag = _segment_search_results(
        retriever=retriever,
        lane_query=lane_query,
        lane_id=lane_id,
        limit=max(4, min(bank_limit, lane_search_top_k // 2 or 4)),
        scan_id=scan_id,
    )
    diagnostics = _build_lane_diagnostics_item(
        LaneDiagnosticsInput(
            lane_id=lane_id,
            query=lane_query,
            executed_query=executed_query,
            results=lane_results,
            scan_id=scan_id,
            scan_meta=lane_scan_meta,
            lane_search_top_k=lane_search_top_k,
            expansion_terms=expansion_terms,
            debug=debug,
            segment_diag=segment_diag,
        )
    )
    return raw_lane_results, lane_results, segment_results, diagnostics, expansion_terms, lane_scan_meta


def _record_lane_match(
    *,
    key: str,
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
) -> None:
    """Record that a result key was matched by a specific lane and query.

    Updates the lane_hits and lane_queries_by_key dictionaries to track
    which lanes and queries matched each result key. Avoids duplicates.

    Args:
        key: The result key being matched.
        lane_id: The ID of the lane that matched.
        lane_query: The query string from the lane that matched.
        lane_hits: Dictionary mapping result keys to list of lane IDs.
        lane_queries_by_key: Dictionary mapping result keys to list of queries.
    """
    lane_hits.setdefault(key, [])
    lane_queries_by_key.setdefault(key, [])
    if lane_id not in lane_hits[key]:
        lane_hits[key].append(lane_id)
    if lane_query not in lane_queries_by_key[key]:
        lane_queries_by_key[key].append(lane_query)
