"""Orchestration entry points for answer-context runtime assembly."""

from __future__ import annotations

from typing import Any

from ..mcp_models import EmailAnswerContextInput
from .search_answer_context_runtime_packing import pack_answer_context
from .search_answer_context_runtime_stages import run_analysis_stage, run_enrichment_stage, run_retrieval_stage
from .search_answer_context_runtime_state import AnswerContextRuntime
from .utils import ToolDepsProto, json_response


async def build_answer_context_payload(
    deps: ToolDepsProto,
    params: EmailAnswerContextInput,
    *,
    preloaded_results: list[Any] | None = None,
    preloaded_evidence_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run retrieval, enrichment, analysis, and budget packing for one request."""
    runtime = AnswerContextRuntime(
        deps=deps,
        params=params,
        preloaded_results=preloaded_results,
        preloaded_evidence_rows=preloaded_evidence_rows,
    )

    def _run() -> dict[str, Any]:
        run_retrieval_stage(runtime)
        run_enrichment_stage(runtime)
        run_analysis_stage(runtime)
        return pack_answer_context(runtime)

    if hasattr(deps, "offload"):
        return await deps.offload(_run)
    return _run()


async def build_answer_context(deps: ToolDepsProto, params: EmailAnswerContextInput) -> str:
    """Serialize the staged payload for the public MCP tool response."""
    return json_response(await build_answer_context_payload(deps, params))


__all__ = ["build_answer_context", "build_answer_context_payload"]
