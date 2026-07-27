# ruff: noqa: RUF022
"""Public bridge that synchronizes patchable answer-context runtime helpers."""

from __future__ import annotations

from . import search_answer_context_runtime_budgeting as _search_answer_context_runtime_budgeting
from . import search_answer_context_runtime_builder as _search_answer_context_runtime_builder
from . import search_answer_context_runtime_candidate_rows as _search_answer_context_runtime_candidate_rows
from . import search_answer_context_runtime_lanes as _search_answer_context_runtime_lanes
from . import search_answer_context_runtime_multi_lane as _search_answer_context_runtime_multi_lane
from . import search_answer_context_runtime_ranking as _search_answer_context_runtime_ranking
from . import search_answer_context_runtime_search as _search_answer_context_runtime_search
from . import search_answer_context_runtime_single_lane as _search_answer_context_runtime_single_lane
from .search_answer_context_runtime_budgeting import (
    _trim_candidate_for_budget,
    _trim_provenance_for_budget,
    _trim_snippet_for_budget,
)
from .search_answer_context_runtime_builder import (
    build_answer_context_payload as _build_answer_context_payload_impl,
)
from .search_answer_context_runtime_lanes import (
    _derive_query_lanes,
    _segment_search_results,
)
from .search_answer_context_runtime_ranking import (
    _bank_entry,
    _evidence_bank_keys_with_lane_diversity,
    _evidence_bank_keys_with_support_diversity,
    _lane_expansion_terms,
    _lane_recovered_expansion_terms,
    _record_lane_match,
    _result_competition_key,
    _result_competition_score,
    _result_identity_key,
    _result_search_surface,
    _support_type_for_result,
    _support_type_for_row,
    _term_tokens,
)
from .search_answer_context_runtime_search import _search_across_query_lanes
from .utils import json_response

_SPLIT_MODULES = (
    _search_answer_context_runtime_lanes,
    _search_answer_context_runtime_ranking,
    _search_answer_context_runtime_budgeting,
    _search_answer_context_runtime_search,
    _search_answer_context_runtime_single_lane,
    _search_answer_context_runtime_multi_lane,
    _search_answer_context_runtime_candidate_rows,
    _search_answer_context_runtime_builder,
)


def _bind_split_namespace() -> None:
    """Cross-inject all split-module exports so sub-modules see each other's names."""
    namespace = {}
    for module in _SPLIT_MODULES:
        namespace.update({name: getattr(module, name) for name in getattr(module, "__all__", ())})
    for module in _SPLIT_MODULES:
        module.__dict__.update(namespace)


_bind_split_namespace()


def _sync_patchable_runtime_globals() -> None:
    """Propagate monkeypatchable runtime seams into split modules so tests and callers share one implementation."""
    patchable = {
        "_search_across_query_lanes": globals().get("_search_across_query_lanes"),
        "_derive_query_lanes": globals().get("_derive_query_lanes"),
        "_support_type_for_row": globals().get("_support_type_for_row"),
        "_support_type_for_result": globals().get("_support_type_for_result"),
    }
    for module in _SPLIT_MODULES:
        module.__dict__.update({key: value for key, value in patchable.items() if value is not None})


async def build_answer_context_payload(*args, **kwargs):
    """Synchronize patchable helpers before invoking the staged runtime builder."""
    _sync_patchable_runtime_globals()
    return await _build_answer_context_payload_impl(*args, **kwargs)


async def build_answer_context(deps, params) -> str:
    """Synchronize runtime seams and serialize the structured payload as JSON."""
    _sync_patchable_runtime_globals()
    return json_response(await build_answer_context_payload(deps, params))


__all__ = [
    "_segment_search_results",
    "_derive_query_lanes",
    "_bank_entry",
    "_support_type_for_result",
    "_support_type_for_row",
    "_term_tokens",
    "_lane_expansion_terms",
    "_result_search_surface",
    "_lane_recovered_expansion_terms",
    "_record_lane_match",
    "_result_identity_key",
    "_result_competition_score",
    "_result_competition_key",
    "_evidence_bank_keys_with_lane_diversity",
    "_evidence_bank_keys_with_support_diversity",
    "_trim_snippet_for_budget",
    "_trim_provenance_for_budget",
    "_trim_candidate_for_budget",
    "_search_across_query_lanes",
    "build_answer_context_payload",
    "build_answer_context",
]
