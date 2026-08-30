"""Public answer-context orchestration entry points."""

from __future__ import annotations

from typing import Any

from .assembly import pack_answer_context, run_analysis_stage, run_enrichment_stage, run_retrieval_stage
from .contracts import AnswerContextDependencies, AnswerContextRequest
from .models import AnswerContextRuntime

"""Orchestration entry points for answer-context runtime assembly."""


async def build_answer_context_payload(
    deps: AnswerContextDependencies,
    params: AnswerContextRequest,
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


__all__ = ["build_answer_context_payload"]
