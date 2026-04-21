"""Public QA eval entrypoint with stable helper imports and runner surface."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from . import qa_eval_impl as _impl
from .qa_eval_bootstrap import benchmark_detection_recovery, bootstrap_question_set, default_bootstrap_questions_path
from .qa_eval_impl import (
    EvalSourceMode,
    LiveEvalDeps,
    QuestionCase,
    _display_path,
    _live_payload,
    _query_terms,
    _resolve_live_retriever,
    _results_payload_map,
    _serialize_case,
    _SQLiteEvalRetriever,
    build_failure_taxonomy,
    build_investigation_corpus_readiness,
    build_remediation_summary,
    default_live_report_path,
    default_remediation_report_path,
    evaluate_payload,
    load_eval_report,
    load_question_cases,
    repo_root,
    summarize_evaluation,
)
from .qa_eval_thresholds import evaluate_report_thresholds, infer_threshold_profile
from .tools.utils import ToolDepsProto

__all__ = [
    "EvalSourceMode",
    "LiveEvalDeps",
    "QuestionCase",
    "_SQLiteEvalRetriever",
    "_display_path",
    "_live_payload",
    "_query_terms",
    "_resolve_live_retriever",
    "_results_payload_map",
    "_serialize_case",
    "benchmark_detection_recovery",
    "bootstrap_question_set",
    "build_failure_taxonomy",
    "build_investigation_corpus_readiness",
    "build_remediation_summary",
    "default_bootstrap_questions_path",
    "default_live_report_path",
    "default_remediation_report_path",
    "evaluate_payload",
    "evaluate_report_thresholds",
    "infer_threshold_profile",
    "load_eval_report",
    "load_question_cases",
    "repo_root",
    "resolve_live_deps",
    "run_evaluation",
    "run_evaluation_sync",
    "summarize_evaluation",
]


def resolve_live_deps(*, preferred_backend: str = "auto") -> ToolDepsProto:
    """Resolve live eval deps while honoring wrapper-level monkeypatch seams."""
    _impl._resolve_live_retriever = _resolve_live_retriever
    return _impl.resolve_live_deps(preferred_backend=preferred_backend)


async def run_evaluation(
    *,
    questions_path: Path,
    results_path: Path | None = None,
    live_deps: ToolDepsProto | None = None,
    limit: int | None = None,
    source_mode: EvalSourceMode = "auto",
) -> dict[str, Any]:
    """Run a minimal answer-context evaluation from captured or live payloads."""
    _impl._resolve_live_retriever = _resolve_live_retriever
    return await _impl.run_evaluation(
        questions_path=questions_path,
        results_path=results_path,
        live_deps=live_deps,
        limit=limit,
        source_mode=source_mode,
    )


def run_evaluation_sync(
    *,
    questions_path: Path,
    results_path: Path | None = None,
    live_deps: ToolDepsProto | None = None,
    limit: int | None = None,
    source_mode: EvalSourceMode = "auto",
) -> dict[str, Any]:
    """Synchronous wrapper for CLI use."""
    return asyncio.run(
        run_evaluation(
            questions_path=questions_path,
            results_path=results_path,
            live_deps=live_deps,
            limit=limit,
            source_mode=source_mode,
        )
    )
