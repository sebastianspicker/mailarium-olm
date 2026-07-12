"""Public archive-harvest bundle facade over typed orchestration stages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .case_analysis_harvest_bundle_stages import build_archive_harvest_bundle_stage
from .mcp_models import EmailCaseAnalysisInput

if TYPE_CHECKING:
    from .tools.utils import ToolDepsProto


async def build_archive_harvest_bundle(
    deps: ToolDepsProto,
    params: EmailCaseAnalysisInput,
    *,
    query_lanes: list[str],
    selected_top_k: int,
) -> dict[str, Any]:
    """Run a wider archive-harvest pass before compact wave synthesis."""
    return await build_archive_harvest_bundle_stage(
        deps,
        params,
        query_lanes=query_lanes,
        selected_top_k=selected_top_k,
    )


__all__ = ["build_archive_harvest_bundle"]
