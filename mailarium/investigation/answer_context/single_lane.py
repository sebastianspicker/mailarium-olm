"""Single-lane answer-context retrieval, result merging, and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mailarium.model.data_shapes import as_dict

from .lane_execution import _lane_runtime_results
from .lanes import _lane_recovered_expansion_terms
from .ranking import (
    _build_evidence_bank,
    _compute_support_type_counts,
    _evidence_bank_keys_with_lane_diversity,
    _evidence_bank_keys_with_support_diversity,
    _remember_best_result,
    _result_competition_key,
    _result_identity_key,
)


@dataclass(slots=True)
class SingleLanePayloadInput:
    """Provide ranked single-lane evidence and limits for response assembly."""

    ranked_results: list[tuple[str, Any]]
    combined_results: dict[str, Any]
    lane_queries_by_key: dict[str, list[str]]
    bank_keys: list[str]
    query: str
    expansion_terms: list[str]
    recovered_terms: list[str]
    recovered_key_count: int
    bank_limit: int
    lane_search_top_k: int
    top_k: int


def _merge_single_lane_results(results: list[Any], *, exact_wording: bool) -> dict[str, Any]:
    """Merge results from a single lane into a combined dictionary.

    Deduplicates results by their identity key, keeping the highest-scoring
    version of each result based on the competition key.

    Args:
        results: List of search results to merge.
        exact_wording: Whether exact wording matching is requested (affects scoring).

    Returns:
        A dictionary mapping result identity keys to the best result for each key.
    """
    combined_results: dict[str, Any] = {}
    for result in results:
        key = _result_identity_key(result, fallback="lane_1")
        _remember_best_result(combined_results, key=key, result=result, exact_wording=exact_wording)
    return combined_results


def _annotate_single_lane_results(ranked_results: list[tuple[str, Any]], *, query: str) -> dict[str, list[str]]:
    """Annotate single-lane results with lane and query information.

    Adds matched_query_lanes and matched_query_queries metadata to each result,
    and returns a dictionary mapping result keys to their matched queries.

    Args:
        ranked_results: List of (key, result) tuples sorted by relevance.
        query: The query string used for this lane.

    Returns:
        A dictionary mapping result keys to list of matched query strings.
    """
    for _key, result in ranked_results:
        metadata = as_dict(result.metadata)
        metadata["matched_query_lanes"] = ["lane_1"]
        metadata["matched_query_queries"] = [query]
    return {key: [query] for key, _result in ranked_results}


def _single_lane_bank_keys(
    *,
    ranked_results: list[tuple[str, Any]],
    bank_limit: int,
) -> list[str]:
    """Select bank keys for a single-lane search.

    Selects result keys for the evidence bank using both lane diversity
    and support type diversity criteria.

    Args:
        ranked_results: List of (key, result) tuples sorted by relevance.
        bank_limit: Maximum number of keys to select.

    Returns:
        A list of selected result keys with both lane and support type diversity.
    """
    bank_keys = _evidence_bank_keys_with_lane_diversity(
        ranked=ranked_results,
        lane_hits={key: ["lane_1"] for key, _result in ranked_results},
        bank_limit=bank_limit,
        reserve_per_lane=1,
    )
    return _evidence_bank_keys_with_support_diversity(
        ranked=ranked_results,
        selected_keys=bank_keys,
        bank_limit=bank_limit,
    )


def _single_lane_payload(context: SingleLanePayloadInput) -> dict[str, Any]:
    """Build the payload for a single-lane search result.

    Creates a structured payload containing evidence bank, support type
    diversity information, expansion attribution, and other metadata.

    Args:
        context: SingleLanePayloadInput dataclass containing all payload data.

    Returns:
        A dictionary containing the complete single-lane payload.
    """
    support_type_counts = _compute_support_type_counts(
        bank_keys=context.bank_keys,
        combined=context.combined_results,
    )
    evidence_bank = _build_evidence_bank(
        bank_keys=context.bank_keys,
        combined=context.combined_results,
        lane_hits={},
        lane_queries_by_key=context.lane_queries_by_key,
        is_single_lane=True,
        single_query=context.query,
    )
    return {
        "candidate_pool_count": len(context.ranked_results),
        "selected_result_count": min(len(context.ranked_results), context.top_k),
        "lane_top_k": context.lane_search_top_k,
        "merge_budget": context.bank_limit,
        "support_diversity": {
            "selected_support_types": sorted(support_type_counts.keys()),
            "counts_by_support_type": support_type_counts,
        },
        "expansion_attribution": [
            {
                "lane_id": "lane_1",
                "query": context.query,
                "new_key_count": len(context.ranked_results),
                "expansion_terms": context.expansion_terms,
                "recovered_expansion_terms": context.recovered_terms,
                "recovered_expansion_key_count": context.recovered_key_count,
            }
        ],
        "evidence_bank": evidence_bank[: context.bank_limit],
        "evidence_results": [result for _key, result in context.ranked_results[: context.bank_limit]],
    }


def _single_lane_runtime_context(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query: str,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Execute a single-lane search and return runtime context.

    Performs the actual search using the retriever, applies scan filtering,
    extracts expansion terms, runs segment search, builds diagnostics,
    and merges results.

    Args:
        retriever: The retriever object used for searching.
        search_kwargs: Base search keyword arguments.
        query: The query string for this lane.
        scan_id: Optional identifier for the scan session.
        lane_search_top_k: The top_k value for this lane's search.
        bank_limit: Maximum number of results to include in the evidence bank.

    Returns:
        A tuple of (combined_results, lane_diagnostics, expansion_terms).
    """
    _raw_results, results, segment_results, diagnostics, expansion_terms, _scan_meta = _lane_runtime_results(
        retriever=retriever,
        search_kwargs=search_kwargs,
        lane_query=query,
        lane_id="lane_1",
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
        base_lane_query=query,
    )
    lane_diagnostics = [diagnostics]
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    combined_results = _merge_single_lane_results([*results, *segment_results], exact_wording=exact_wording)
    return combined_results, lane_diagnostics, expansion_terms


def _search_single_lane(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    top_k: int,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Search a single lane and return results with diagnostics and payload.

    Main entry point for single-lane search. Executes the runtime context
    and assembles the final results.

    Args:
        retriever: The retriever object used for searching.
        search_kwargs: Base search keyword arguments.
        query_lanes: List of query lane strings (only the first is used).
        top_k: Maximum number of results to return.
        scan_id: Optional identifier for the scan session.
        lane_search_top_k: The top_k value for this lane's search.
        bank_limit: Maximum number of results to include in the evidence bank.

    Returns:
        A tuple of (results, lane_diagnostics, payload).
    """
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    query = query_lanes[0]
    combined_results, lane_diagnostics, expansion_terms = _single_lane_runtime_context(
        retriever=retriever,
        search_kwargs=search_kwargs,
        query=query,
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
    )
    return _assemble_single_lane_results(
        combined_results=combined_results,
        exact_wording=exact_wording,
        lane_diagnostics=lane_diagnostics,
        expansion_terms=expansion_terms,
        query_lanes=query_lanes,
        top_k=top_k,
        bank_limit=bank_limit,
        lane_search_top_k=lane_search_top_k,
    )


def _assemble_single_lane_results(
    *,
    combined_results: dict[str, Any],
    exact_wording: bool,
    lane_diagnostics: list[dict[str, Any]],
    expansion_terms: list[str],
    query_lanes: list[str],
    top_k: int,
    bank_limit: int,
    lane_search_top_k: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Assemble final results from combined single-lane results.

    Ranks results, computes expansion term recovery, annotates with lane
    information, selects bank keys, and builds the final payload.

    Args:
        combined_results: Dictionary of merged results from all sources.
        exact_wording: Whether exact wording matching is requested.
        lane_diagnostics: List of diagnostics items for each lane.
        expansion_terms: List of query expansion terms to track.
        query_lanes: List of query lane strings.
        top_k: Maximum number of results to return.
        bank_limit: Maximum number of results to include in the evidence bank.
        lane_search_top_k: The top_k value used for lane searches.

    Returns:
        A tuple of (results, lane_diagnostics, payload).
    """
    ranked_results = sorted(
        combined_results.items(),
        key=lambda item: _result_competition_key(item[1], exact_wording=exact_wording),
        reverse=True,
    )
    lane_diagnostics[0]["new_key_count"] = len(ranked_results)
    recovered_terms, recovered_key_count = _lane_recovered_expansion_terms(
        expansion_terms=expansion_terms,
        new_keys=[key for key, _result in ranked_results],
        result_lookup=combined_results,
    )
    lane_diagnostics[0]["recovered_expansion_terms"] = recovered_terms
    lane_diagnostics[0]["recovered_expansion_key_count"] = recovered_key_count
    query = query_lanes[0]
    lane_queries_by_key = _annotate_single_lane_results(ranked_results, query=query)
    bank_keys = _single_lane_bank_keys(
        ranked_results=ranked_results,
        bank_limit=bank_limit,
    )
    return (
        [result for _key, result in ranked_results[:top_k]],
        lane_diagnostics,
        _single_lane_payload(
            SingleLanePayloadInput(
                ranked_results=ranked_results,
                combined_results=combined_results,
                lane_queries_by_key=lane_queries_by_key,
                bank_keys=bank_keys,
                query=query,
                expansion_terms=expansion_terms,
                recovered_terms=recovered_terms,
                recovered_key_count=recovered_key_count,
                bank_limit=bank_limit,
                lane_search_top_k=lane_search_top_k,
                top_k=top_k,
            )
        ),
    )
