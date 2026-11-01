"""Multi-lane retrieval, merging, and diagnostics for answer-context payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mailarium.model.data_shapes import as_dict

from .lane_execution import _lane_runtime_results, _record_lane_match
from .lanes import _lane_recovered_expansion_terms
from .ranking import (
    _remember_best_result,
    _result_competition_key,
    _result_identity_key,
)


@dataclass(slots=True)
class LaneCollectionState:
    """Accumulate deduplicated lane hits, diagnostics, and reserved evidence keys."""

    combined: dict[str, Any]
    lane_hits: dict[str, list[str]]
    lane_queries_by_key: dict[str, list[str]]
    reserved_keys: list[str]
    lane_diagnostics: list[dict[str, Any]]


@dataclass(slots=True)
class LaneProcessingInput:
    """Provide one lane's retrieval request and merge policy to the worker."""

    retriever: Any
    search_kwargs: dict[str, Any]
    lane_query: str
    lane_id: str
    scan_id: str | None
    lane_search_top_k: int
    bank_limit: int
    reserve_per_lane: int
    exact_wording: bool
    base_lane_query: str


def _record_raw_lane_matches(
    *,
    lane_results: list[Any],
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
) -> None:
    """Record which lane matched each result.

    Iterates through lane results and records the lane_id and lane_query
    for each result's identity key in the tracking dictionaries.

    Args:
        lane_results: List of results from the lane search.
        lane_id: Identifier for this lane.
        lane_query: The query string for this lane.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
    """
    for result in lane_results:
        key = _result_identity_key(result, fallback=lane_id)
        _record_lane_match(
            key=key,
            lane_id=lane_id,
            lane_query=lane_query,
            lane_hits=lane_hits,
            lane_queries_by_key=lane_queries_by_key,
        )


def _merge_lane_results_for_diagnostics(
    *,
    combined: dict[str, Any],
    lane_results: list[Any],
    segment_results: list[Any],
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
    exact_wording: bool,
) -> list[str]:
    """Merge lane results into combined dict and return reserved keys.

    Merges both regular and segment results into the combined dictionary,
    recording matches and returning the list of keys reserved by this lane.

    Args:
        combined: The shared dictionary for combined results.
        lane_results: Regular results from the lane search.
        segment_results: Segment-level results from the lane search.
        lane_id: Identifier for this lane.
        lane_query: The query string for this lane.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
        exact_wording: Whether exact wording is requested.

    Returns:
        List of keys reserved by this lane (including both regular and segment results).
    """
    lane_reserved_keys = _merge_lane_result_set(
        combined=combined,
        lane_results=lane_results,
        lane_id=lane_id,
        lane_query=lane_query,
        lane_hits=lane_hits,
        lane_queries_by_key=lane_queries_by_key,
        exact_wording=exact_wording,
        record_matches_for_all=False,
    )
    for key in _merge_lane_result_set(
        combined=combined,
        lane_results=segment_results,
        lane_id=lane_id,
        lane_query=lane_query,
        lane_hits=lane_hits,
        lane_queries_by_key=lane_queries_by_key,
        exact_wording=exact_wording,
        record_matches_for_all=True,
    ):
        if key not in lane_reserved_keys:
            lane_reserved_keys.append(key)
    return lane_reserved_keys


def _update_lane_recovery_diagnostics(
    *,
    diagnostics: dict[str, Any],
    combined: dict[str, Any],
    lane_initial_keys: set[str],
    expansion_terms: list[str],
) -> None:
    """Update diagnostics with information about recovered keys from expansion.

    Identifies new keys added to combined that weren't in the initial set,
    and records which expansion terms led to those recoveries.

    Args:
        diagnostics: The diagnostics dictionary to update.
        combined: The combined results dictionary.
        lane_initial_keys: Set of keys that were present before lane processing.
        expansion_terms: List of query expansion terms used for this lane.
    """
    lane_new_keys = [key for key in combined if key not in lane_initial_keys]
    diagnostics["new_key_count"] = len(lane_new_keys)
    recovered_terms, recovered_key_count = _lane_recovered_expansion_terms(
        expansion_terms=expansion_terms,
        new_keys=lane_new_keys,
        result_lookup=combined,
    )
    diagnostics["recovered_expansion_terms"] = recovered_terms
    diagnostics["recovered_expansion_key_count"] = recovered_key_count


def _remember_reserved_keys(
    *,
    reserved_keys: list[str],
    lane_reserved_keys: list[str],
    reserve_per_lane: int,
) -> None:
    """Add lane's reserved keys to the global reserved keys list.

    Takes up to reserve_per_lane keys from the lane's reserved keys and
    adds them to the global reserved_keys list if not already present.

    Args:
        reserved_keys: The global list of reserved keys.
        lane_reserved_keys: The list of keys reserved by this lane.
        reserve_per_lane: Maximum number of keys to reserve per lane.
    """
    for key in lane_reserved_keys[: max(reserve_per_lane, 0)]:
        if key not in reserved_keys:
            reserved_keys.append(key)


def _process_lane_results(context: LaneProcessingInput, state: LaneCollectionState) -> None:
    """Process results for a single lane and update collection state.

    Executes lane search, records matches, merges results, and updates diagnostics.

    Args:
        context: Input parameters for lane processing.
        state: Mutable state for collecting results across lanes.
    """
    lane_initial_keys = set(state.combined.keys())
    raw_lane_results, lane_results, segment_results, diagnostics, expansion_terms, _lane_scan_meta = _lane_runtime_results(
        retriever=context.retriever,
        search_kwargs=context.search_kwargs,
        lane_query=context.lane_query,
        lane_id=context.lane_id,
        scan_id=context.scan_id,
        lane_search_top_k=context.lane_search_top_k,
        bank_limit=context.bank_limit,
        base_lane_query=context.base_lane_query,
    )
    _record_raw_lane_matches(
        lane_results=raw_lane_results,
        lane_id=context.lane_id,
        lane_query=context.lane_query,
        lane_hits=state.lane_hits,
        lane_queries_by_key=state.lane_queries_by_key,
    )
    state.lane_diagnostics.append(diagnostics)
    lane_reserved_keys = _merge_lane_results_for_diagnostics(
        combined=state.combined,
        lane_results=lane_results,
        segment_results=segment_results,
        lane_id=context.lane_id,
        lane_query=context.lane_query,
        lane_hits=state.lane_hits,
        lane_queries_by_key=state.lane_queries_by_key,
        exact_wording=context.exact_wording,
    )
    _remember_reserved_keys(
        reserved_keys=state.reserved_keys,
        lane_reserved_keys=lane_reserved_keys,
        reserve_per_lane=context.reserve_per_lane,
    )
    _update_lane_recovery_diagnostics(
        diagnostics=state.lane_diagnostics[-1],
        combined=state.combined,
        lane_initial_keys=lane_initial_keys,
        expansion_terms=expansion_terms,
    )


def _collect_lane_results(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
    reserve_per_lane: int,
    exact_wording: bool,
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, list[str]], list[str], list[dict[str, Any]]]:
    """Collect results from all query lanes.

    Processes each lane sequentially, accumulating results and diagnostics.

    Args:
        retriever: The retriever instance to use for search.
        search_kwargs: Base search keyword arguments.
        query_lanes: List of query strings, one per lane.
        scan_id: Optional scan identifier.
        lane_search_top_k: Top k for each lane search.
        bank_limit: Maximum items in the evidence bank.
        reserve_per_lane: Maximum number of keys to reserve per lane.
        exact_wording: Whether exact wording is requested.

    Returns:
        A tuple of (combined, lane_hits, lane_queries_by_key, reserved_keys,
        lane_diagnostics).
    """
    base_lane_query = str(query_lanes[0] or "")
    state = LaneCollectionState(
        combined={},
        lane_hits={},
        lane_queries_by_key={},
        reserved_keys=[],
        lane_diagnostics=[],
    )
    for index, lane_query in enumerate(query_lanes, start=1):
        _process_lane_results(
            LaneProcessingInput(
                retriever=retriever,
                search_kwargs=search_kwargs,
                lane_query=lane_query,
                lane_id=f"lane_{index}",
                scan_id=scan_id,
                lane_search_top_k=lane_search_top_k,
                bank_limit=bank_limit,
                reserve_per_lane=reserve_per_lane,
                exact_wording=exact_wording,
                base_lane_query=base_lane_query,
            ),
            state=state,
        )
    return state.combined, state.lane_hits, state.lane_queries_by_key, state.reserved_keys, state.lane_diagnostics


def _merge_lane_result_set(
    *,
    combined: dict[str, Any],
    lane_results: list[Any],
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
    exact_wording: bool,
    record_matches_for_all: bool,
) -> list[str]:
    """Merge a set of lane results into the combined dictionary.

    For each result, stores the best version in combined and optionally
    records which lane matched it.

    Args:
        combined: The shared dictionary for combined results.
        lane_results: List of results to merge.
        lane_id: Identifier for this lane.
        lane_query: The query string for this lane.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
        exact_wording: Whether exact wording is requested.
        record_matches_for_all: If True, record matches for all results.

    Returns:
        List of keys that were added or updated in combined.
    """
    lane_reserved_keys: list[str] = []
    for result in lane_results:
        key = _result_identity_key(result, fallback=lane_id)
        if record_matches_for_all:
            _record_lane_match(
                key=key,
                lane_id=lane_id,
                lane_query=lane_query,
                lane_hits=lane_hits,
                lane_queries_by_key=lane_queries_by_key,
            )
        _remember_best_result(combined, key=key, result=result, exact_wording=exact_wording)
        if key not in lane_reserved_keys:
            lane_reserved_keys.append(key)
    return lane_reserved_keys


def _select_merged_keys(
    *,
    combined: dict[str, Any],
    ranked: list[tuple[str, Any]],
    reserved_keys: list[str],
    top_k: int,
) -> list[str]:
    """Select the top k keys from reserved and ranked results.

    First takes keys from reserved_keys (in order), then fills remaining
    slots from ranked results.

    Args:
        combined: The combined results dictionary.
        ranked: List of (key, result) tuples sorted by competition key.
        reserved_keys: List of keys that should be prioritized.
        top_k: Maximum number of keys to select.

    Returns:
        List of up to top_k selected keys.
    """
    merged_keys: list[str] = []
    for key in reserved_keys:
        if key in combined and key not in merged_keys:
            merged_keys.append(key)
        if len(merged_keys) >= top_k:
            return merged_keys
    for key, _result in ranked:
        if key not in merged_keys:
            merged_keys.append(key)
        if len(merged_keys) >= top_k:
            break
    return merged_keys


def _annotate_merged_results(
    *,
    merged: list[Any],
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
) -> None:
    """Annotate merged results with lane matching information.

    Adds metadata to each result's metadata indicating which lanes and
    queries matched it.

    Args:
        merged: List of merged result objects.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
    """
    for result in merged:
        metadata = as_dict(result.metadata)
        key = _result_identity_key(result, fallback="")
        metadata["matched_query_lanes"] = lane_hits.get(key, [])
        metadata["matched_query_queries"] = lane_queries_by_key.get(key, [])


def _search_multi_lane(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    top_k: int,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
    reserve_per_lane: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Execute multi-lane search and return merged results with diagnostics.

    Orchestrates the complete multi-lane search process: collects results
    from all lanes, ranks them, selects the top k, annotates with lane info,
    and returns an empty retrieval payload.

    Args:
        retriever: The retriever instance to use for search.
        search_kwargs: Base search keyword arguments.
        query_lanes: List of query strings, one per lane.
        top_k: Maximum number of results to return.
        scan_id: Optional scan identifier.
        lane_search_top_k: Top k for each individual lane search.
        bank_limit: Maximum items in the evidence bank.
        reserve_per_lane: Maximum number of keys to reserve per lane.

    Returns:
        A tuple of (merged_results, lane_diagnostics, empty payload).
    """
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    combined, lane_hits, lane_queries_by_key, reserved_keys, lane_diagnostics = _collect_lane_results(
        retriever=retriever,
        search_kwargs=search_kwargs,
        query_lanes=query_lanes,
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
        reserve_per_lane=reserve_per_lane,
        exact_wording=exact_wording,
    )
    ranked = sorted(
        combined.items(), key=lambda item: _result_competition_key(item[1], exact_wording=exact_wording), reverse=True
    )
    merged_keys = _select_merged_keys(combined=combined, ranked=ranked, reserved_keys=reserved_keys, top_k=top_k)
    merged = [combined[key] for key in merged_keys[:top_k]]
    _annotate_merged_results(merged=merged, lane_hits=lane_hits, lane_queries_by_key=lane_queries_by_key)
    return merged, lane_diagnostics, {}
