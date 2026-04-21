# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405, RUF022
"""Compatibility facade for split answer-context runtime helpers."""

from __future__ import annotations

from . import search_answer_context_runtime_budgeting as _search_answer_context_runtime_budgeting
from . import search_answer_context_runtime_builder as _search_answer_context_runtime_builder
from . import search_answer_context_runtime_candidate_rows as _search_answer_context_runtime_candidate_rows
from . import search_answer_context_runtime_lanes as _search_answer_context_runtime_lanes
from . import search_answer_context_runtime_ranking as _search_answer_context_runtime_ranking
from . import search_answer_context_runtime_search as _search_answer_context_runtime_search
from .search_answer_context_runtime_budgeting import *
from .search_answer_context_runtime_builder import *
from .search_answer_context_runtime_candidate_rows import *
from .search_answer_context_runtime_lanes import *
from .search_answer_context_runtime_ranking import *
from .search_answer_context_runtime_search import *
from .utils import json_response

_SPLIT_MODULES = (
    _search_answer_context_runtime_lanes,
    _search_answer_context_runtime_ranking,
    _search_answer_context_runtime_budgeting,
    _search_answer_context_runtime_search,
    _search_answer_context_runtime_candidate_rows,
    _search_answer_context_runtime_builder,
)
_WRAPPED_EXPORTS = {
    "build_answer_context",
    "build_answer_context_payload",
}


def _bind_split_namespace() -> None:
    namespace = {}
    for module in _SPLIT_MODULES:
        namespace.update({name: getattr(module, name) for name in getattr(module, "__all__", ())})
    for module in _SPLIT_MODULES:
        module.__dict__.update(namespace)
    globals().update({key: value for key, value in namespace.items() if key not in _WRAPPED_EXPORTS})


_bind_split_namespace()


_build_answer_context_payload_impl = _search_answer_context_runtime_builder.build_answer_context_payload


def _sync_patchable_runtime_globals() -> None:
    patchable = {
        "_search_across_query_lanes": globals().get("_search_across_query_lanes"),
        "_derive_query_lanes": globals().get("_derive_query_lanes"),
        "_support_type_for_row": globals().get("_support_type_for_row"),
        "_support_type_for_result": globals().get("_support_type_for_result"),
    }
    for module in _SPLIT_MODULES:
        module.__dict__.update({key: value for key, value in patchable.items() if value is not None})


async def build_answer_context_payload(*args, **kwargs):  # type: ignore[no-redef]
    """Build the structured answer-context payload before outward JSON rendering."""
    _sync_patchable_runtime_globals()
    return await _build_answer_context_payload_impl(*args, **kwargs)


async def build_answer_context(deps, params) -> str:  # type: ignore[no-redef]
    """Build the answer-context payload for ``email_answer_context``."""
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
