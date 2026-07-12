"""Dedicated workplace case-analysis wrapper over the answer-context pipeline."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .case_analysis_coverage import matter_coverage_ledger
from .case_analysis_harvest import build_archive_harvest_bundle
from .case_analysis_scope import derive_case_analysis_query
from .case_analysis_stages import (
    add_mixed_source_analyses,
    add_mixed_source_inputs,
    add_retrieval_plan,
    apply_review_and_persistence,
    build_runtime,
    transform_runtime,
)
from .case_analysis_transform import transform_case_analysis_payload
from .mcp_models import EmailCaseAnalysisInput

__all__ = [
    "build_case_analysis",
    "build_case_analysis_payload",
    "derive_case_analysis_query",
    "transform_case_analysis_payload",
]

if TYPE_CHECKING:
    from .tools.utils import ToolDepsProto


async def build_case_analysis_payload(deps: ToolDepsProto, params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Build the dedicated case-analysis payload as a Python object."""
    runtime = await build_runtime(deps, params, harvest_builder=build_archive_harvest_bundle)
    add_retrieval_plan(runtime, params)
    has_mixed_sources = add_mixed_source_inputs(runtime, params)
    add_mixed_source_analyses(runtime, params, has_mixed_sources)
    return apply_review_and_persistence(deps, params, transform_runtime(runtime, params))


async def build_case_analysis(deps: ToolDepsProto, params: EmailCaseAnalysisInput) -> str:
    """Build the dedicated case-analysis payload."""
    transformed = await build_case_analysis_payload(deps, params)
    return json.dumps(transformed, indent=2)


_matter_coverage_ledger = matter_coverage_ledger
