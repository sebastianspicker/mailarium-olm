# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405, RUF022
"""Compatibility facade for split archive-harvest helpers."""

from __future__ import annotations

from . import case_analysis_harvest_bundle as _case_analysis_harvest_bundle
from . import case_analysis_harvest_common as _case_analysis_harvest_common
from . import case_analysis_harvest_coverage as _case_analysis_harvest_coverage
from . import case_analysis_harvest_expansion as _case_analysis_harvest_expansion
from . import case_analysis_harvest_quality as _case_analysis_harvest_quality
from .case_analysis_harvest_bundle import *
from .case_analysis_harvest_common import *
from .case_analysis_harvest_coverage import *
from .case_analysis_harvest_expansion import *
from .case_analysis_harvest_quality import *

_SPLIT_MODULES = (
    _case_analysis_harvest_common,
    _case_analysis_harvest_coverage,
    _case_analysis_harvest_quality,
    _case_analysis_harvest_expansion,
    _case_analysis_harvest_bundle,
)
_WRAPPED_EXPORTS = {
    "build_archive_harvest_bundle",
}


def _bind_split_namespace() -> None:
    namespace = {}
    for module in _SPLIT_MODULES:
        namespace.update({name: getattr(module, name) for name in getattr(module, "__all__", ())})
    for module in _SPLIT_MODULES:
        module.__dict__.update(namespace)
    globals().update({key: value for key, value in namespace.items() if key not in _WRAPPED_EXPORTS})


_bind_split_namespace()


_build_archive_harvest_bundle_impl = _case_analysis_harvest_bundle.build_archive_harvest_bundle


def _sync_patchable_harvest_globals() -> None:
    patchable = {
        "_attachment_expansion_rows": globals().get("_attachment_expansion_rows"),
        "_thread_expansion_rows": globals().get("_thread_expansion_rows"),
        "_enrich_evidence_bank": globals().get("_enrich_evidence_bank"),
    }
    for module in _SPLIT_MODULES:
        module.__dict__.update({key: value for key, value in patchable.items() if value is not None})


async def build_archive_harvest_bundle(*args, **kwargs):  # type: ignore[no-redef]
    """Run a wider archive-harvest pass before compact wave synthesis."""
    _sync_patchable_harvest_globals()
    return await _build_archive_harvest_bundle_impl(*args, **kwargs)


__all__ = [
    "_compact",
    "_coerce_month_bucket",
    "_date_span_days",
    "_source_basis_summary",
    "_archive_size_hint",
    "_mixed_source_harvest_inputs",
    "_row_identity",
    "_dedupe_evidence_rows",
    "_annotate_round",
    "_round_recovered_keys",
    "_coverage_signature",
    "_adaptive_harvest_plan",
    "_append_unique_lane",
    "_expanded_zero_result_lane_variants",
    "_coverage_rerun_lanes",
    "_coverage_thresholds",
    "_coverage_metrics",
    "_split_evidence_bank_layers",
    "_coverage_gate_reasons",
    "_coverage_gate",
    "_seed_actor_keys",
    "_infer_actor_role",
    "_keyword_terms",
    "_text_overlap_score",
    "_seed_relevance_terms",
    "_actor_mentions",
    "_actor_discovery_summary",
    "_harvest_quality_summary",
    "_mixed_source_identity_rows",
    "augment_mixed_source_harvest_summary",
    "_best_body_text",
    "_email_language_fields",
    "_EXPANSION_ERROR_SAMPLE_LIMIT",
    "_default_expansion_stage_diagnostics",
    "_coerce_expansion_stage_result",
    "_aggregate_expansion_diagnostics",
    "_thread_expansion_rows",
    "_attachment_expansion_rows",
    "_enrich_evidence_bank",
    "build_archive_harvest_bundle",
]
