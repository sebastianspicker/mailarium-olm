# mypy: disable-error-code=name-defined
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split archive-harvest helpers (case_analysis_harvest_coverage)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._utils import _compact
from .case_analysis_harvest_common import _date_span_days
from .mcp_models import EmailCaseAnalysisInput
from .question_execution_waves import get_wave_definition

if TYPE_CHECKING:
    pass


def _append_unique_lane(lanes: list[str], lane: str) -> bool:
    """Append a lane to a list if it's unique (case-insensitive comparison).

    Args:
        lanes: The list of existing lanes.
        lane: The new lane to add.

    Returns:
        True if the lane was added, False if it was a duplicate or empty.
    """
    compact = _compact(lane)[:500]
    if not compact:
        return False
    lowered = compact.casefold()
    if any(_compact(existing).casefold() == lowered for existing in lanes):
        return False
    lanes.append(compact)
    return True


def _expanded_zero_result_lane_variants(retriever: Any, lane_query: str) -> list[str]:
    """Get expanded query lane variants for a zero-result lane.

    Args:
        retriever: The retriever object with _expand_query_lanes method.
        lane_query: The original lane query string.

    Returns:
        A list of expanded variant queries (max 3), excluding the original query.
    """
    expand_query_lanes = getattr(retriever, "_expand_query_lanes", None)
    if not callable(expand_query_lanes):
        return []
    try:
        variants = expand_query_lanes(lane_query, max_lanes=3)
    except TypeError:
        try:
            variants = expand_query_lanes(lane_query)
        except (ValueError, AttributeError):
            return []
    except (ValueError, AttributeError):
        return []
    if not isinstance(variants, list):
        return []
    return [
        _compact(item) for item in variants if _compact(item) and _compact(item).casefold() != _compact(lane_query).casefold()
    ]


def _coverage_rerun_lanes(
    *,
    retriever: Any,
    params: EmailCaseAnalysisInput,
    query_lanes: list[str],
    lane_diagnostics: list[dict[str, Any]],
    actor_discovery: dict[str, Any],
    coverage_gate: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Determine additional lanes to run based on coverage gate results.

    Args:
        retriever: The retriever object for query expansion.
        params: The email case analysis input parameters.
        query_lanes: The current list of query lanes.
        lane_diagnostics: Diagnostics for each lane.
        actor_discovery: Discovery results for actors.
        coverage_gate: The coverage gate result dict.

    Returns:
        A tuple of (widened_query_lanes, rerun_actions) where widened_query_lanes
        includes additional lanes to try, and rerun_actions describes what was added.
    """
    from .case_analysis_harvest_coverage_stages import coverage_rerun_lanes_stage

    return coverage_rerun_lanes_stage(
        retriever=retriever,
        params=params,
        query_lanes=query_lanes,
        lane_diagnostics=lane_diagnostics,
        actor_discovery=actor_discovery,
        coverage_gate=coverage_gate,
    )


def _coverage_thresholds(
    *,
    params: EmailCaseAnalysisInput,
    query_lane_count: int,
    selected_top_k: int,
) -> dict[str, int]:
    """Calculate coverage thresholds based on case parameters and query configuration.

    Args:
        params: The email case analysis input parameters.
        query_lane_count: The number of query lanes.
        selected_top_k: The selected top-k value.

    Returns:
        A dict of threshold values for various coverage metrics.
    """
    span_days = _date_span_days(params)
    min_unique_months = 1
    if span_days > 120:
        min_unique_months = 3
    elif span_days > 45:
        min_unique_months = 2
    min_attachment_hits = 0
    if params.wave_id:
        definition = get_wave_definition(params.wave_id)
        if definition.attachment_terms and params.source_scope != "emails_only":
            min_attachment_hits = 1
    return {
        "min_unique_hits": max(selected_top_k, query_lane_count * 2),
        "min_unique_threads": 3 if selected_top_k >= 8 else 2,
        "min_unique_senders": 3 if selected_top_k >= 8 else 2,
        "min_unique_months": min_unique_months,
        "min_attachment_hits": min_attachment_hits,
        "min_lane_coverage": min(query_lane_count, 3) if query_lane_count else 0,
    }


def _coverage_metrics(
    *,
    evidence_bank: list[dict[str, Any]],
    lane_diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate coverage metrics from an evidence bank and lane diagnostics.

    Args:
        evidence_bank: List of evidence row dicts.
        lane_diagnostics: Diagnostics for each query lane.

    Returns:
        A dict with various coverage metrics including unique counts for hits,
        messages, threads, senders, months, attachments, segments, and lane coverage.
    """
    from .case_analysis_harvest_coverage_stages import coverage_metrics_stage

    return coverage_metrics_stage(evidence_bank=evidence_bank, lane_diagnostics=lane_diagnostics)


def _split_evidence_bank_layers(evidence_bank: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split evidence bank into direct rows and expanded rows.

    Args:
        evidence_bank: List of evidence row dicts.

    Returns:
        A tuple of (direct_rows, expanded_rows) where direct_rows are non-expansion
        rows and expanded_rows are those with harvest_source of 'thread_expansion' or
        'attachment_expansion'.
    """
    direct_rows: list[dict[str, Any]] = []
    expanded_rows: list[dict[str, Any]] = []
    for row in evidence_bank:
        if str(row.get("harvest_source") or "") in {"thread_expansion", "attachment_expansion"}:
            expanded_rows.append(row)
        else:
            direct_rows.append(row)
    return direct_rows, expanded_rows


def _coverage_gate_reasons(*, metrics: dict[str, Any], thresholds: dict[str, int]) -> tuple[list[str], list[str]]:
    """Determine coverage gate reasons and recommendations based on metrics vs thresholds.

    Args:
        metrics: Coverage metrics dict from _coverage_metrics.
        thresholds: Threshold values dict from _coverage_thresholds.

    Returns:
        A tuple of (reasons, recommendations) where reasons are machine-readable
        identifiers for threshold violations, and recommendations are human-readable
        suggestions for improvement.
    """
    from .case_analysis_harvest_coverage_stages import coverage_gate_reasons_stage

    return coverage_gate_reasons_stage(metrics=metrics, thresholds=thresholds)


def _coverage_gate(
    *,
    direct_metrics: dict[str, Any],
    expanded_metrics: dict[str, Any],
    thresholds: dict[str, int],
    evidence_bank: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate coverage gate based on direct and expanded metrics.

    Args:
        direct_metrics: Coverage metrics for direct (non-expanded) evidence.
        expanded_metrics: Coverage metrics for expanded evidence.
        thresholds: Threshold values for coverage evaluation.
        evidence_bank: The full evidence bank.

    Returns:
        A dict with coverage gate results including status (pass/needs_more_harvest),
        reasons for any failures, recommendations, and detailed sufficiency info.
    """
    from .case_analysis_harvest_coverage_stages import coverage_gate_stage

    return coverage_gate_stage(
        direct_metrics=direct_metrics,
        expanded_metrics=expanded_metrics,
        thresholds=thresholds,
        evidence_bank=evidence_bank,
    )


__all__ = [
    "_append_unique_lane",
    "_coverage_gate",
    "_coverage_gate_reasons",
    "_coverage_metrics",
    "_coverage_rerun_lanes",
    "_coverage_thresholds",
    "_expanded_zero_result_lane_variants",
    "_split_evidence_bank_layers",
]
