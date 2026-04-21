"""Helpers for evaluating answer-context quality against labeled questions."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from . import qa_eval_live as _live
from . import qa_eval_taxonomy as _taxonomy
from .mcp_models import EmailAnswerContextInput
from .qa_eval_cases import QuestionCase, _load_json, load_question_cases
from .qa_eval_scoring import evaluate_payload, summarize_evaluation
from .qa_eval_thresholds import evaluate_report_thresholds
from .tools.search_answer_context import build_answer_context
from .tools.utils import ToolDepsProto

LiveEvalDeps = _live.LiveEvalDeps
_SQLiteEvalRetriever = _live._SQLiteEvalRetriever
_query_terms = _live._query_terms
_resolve_live_retriever = _live._resolve_live_retriever
default_live_report_path = _live.default_live_report_path
default_remediation_report_path = _live.default_remediation_report_path
repo_root = _live.repo_root
build_failure_taxonomy = _taxonomy.build_failure_taxonomy
build_investigation_corpus_readiness = _taxonomy.build_investigation_corpus_readiness
build_remediation_summary = _taxonomy.build_remediation_summary

EvalSourceMode = Literal["auto", "captured_only", "live_only", "mixed"]


def _display_path(path: Path | None) -> str | None:
    """Serialize repo-owned paths without leaking local absolute filesystem roots."""
    if path is None:
        return None
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


def resolve_live_deps(*, preferred_backend: str = "auto") -> ToolDepsProto:
    return _live.resolve_live_deps(
        preferred_backend=preferred_backend,
        resolve_retriever=_resolve_live_retriever,
    )


def _results_payload_map(path: Path) -> dict[str, dict[str, Any]]:
    raw = _load_json(path)
    if isinstance(raw, dict) and "results" in raw and isinstance(raw["results"], list):
        mapped: dict[str, dict[str, Any]] = {}
        for item in raw["results"]:
            case_id = str(item["id"])
            payload = item.get("payload")
            if not isinstance(payload, dict):
                raise ValueError(f"results payload for case {case_id} must be an object")
            mapped[case_id] = payload
        return mapped
    if isinstance(raw, dict):
        return {str(case_id): payload for case_id, payload in raw.items()}
    raise ValueError("results file must be an object keyed by case id or a {'results': [...]} object")


def load_eval_report(path: Path) -> dict[str, Any]:
    """Load a saved eval report JSON document."""
    return _load_json(path)


async def _live_payload(case: QuestionCase, deps: ToolDepsProto) -> dict[str, Any]:
    params = EmailAnswerContextInput(
        question=case.question,
        evidence_mode=case.evidence_mode,  # type: ignore[arg-type]
        case_scope=case.case_scope,
        **case.filters,
    )
    raw = await build_answer_context(deps, params)
    return json.loads(raw)


def _serialize_case(case: QuestionCase) -> dict[str, Any]:
    payload = asdict(case)
    if case.case_scope is not None:
        payload["case_scope"] = case.case_scope.model_dump(mode="json")
    return payload


def _resolve_source_mode(
    *,
    results_path: Path | None,
    live_deps: ToolDepsProto | None,
    source_mode: EvalSourceMode,
) -> Literal["captured_only", "live_only", "mixed"]:
    has_captured = results_path is not None
    has_live = live_deps is not None
    if source_mode == "auto":
        if has_captured and has_live:
            raise ValueError(
                "captured results and live deps were both provided; set source_mode to 'captured_only', 'live_only', or 'mixed'"
            )
        if has_captured:
            return "captured_only"
        if has_live:
            return "live_only"
        raise ValueError("no payload source configured; provide captured results or live deps")
    if source_mode == "captured_only":
        if not has_captured:
            raise ValueError("source_mode='captured_only' requires results_path")
        return "captured_only"
    if source_mode == "live_only":
        if not has_live:
            raise ValueError("source_mode='live_only' requires live_deps")
        return "live_only"
    if not has_captured or not has_live:
        raise ValueError("source_mode='mixed' requires both results_path and live_deps")
    return "mixed"


async def _evaluate_case_with_source(
    *,
    case: QuestionCase,
    source: Literal["captured", "live"],
    captured: dict[str, dict[str, Any]],
    live_deps: ToolDepsProto | None,
) -> dict[str, Any]:
    if source == "captured":
        if case.id not in captured:
            raise ValueError(f"no captured payload available for case {case.id}")
        payload = captured[case.id]
        return evaluate_payload(case, payload, source="captured")
    if live_deps is None:
        raise ValueError(f"no live payload available for case {case.id}; provide --live")
    payload = await _live_payload(case, live_deps)
    return evaluate_payload(case, payload, source="live")


async def run_evaluation(
    *,
    questions_path: Path,
    results_path: Path | None = None,
    live_deps: ToolDepsProto | None = None,
    limit: int | None = None,
    source_mode: EvalSourceMode = "auto",
) -> dict[str, Any]:
    """Run a minimal answer-context evaluation from captured or live payloads."""
    cases = load_question_cases(questions_path)
    if limit is not None:
        cases = cases[:limit]

    captured = _results_payload_map(results_path) if results_path else {}
    resolved_source_mode = _resolve_source_mode(
        results_path=results_path,
        live_deps=live_deps,
        source_mode=source_mode,
    )

    report: dict[str, Any] = {
        "questions_path": _display_path(questions_path),
        "results_path": _display_path(results_path),
        "total_cases": len(cases),
        "cases": [_serialize_case(case) for case in cases],
        "source_mode": resolved_source_mode,
        "live_backend": getattr(live_deps, "live_backend", None) if live_deps is not None else None,
    }

    if resolved_source_mode == "mixed":
        captured_results: list[dict[str, Any]] = []
        live_results: list[dict[str, Any]] = []
        comparison_results: list[dict[str, Any]] = []
        for case in cases:
            captured_result = await _evaluate_case_with_source(
                case=case,
                source="captured",
                captured=captured,
                live_deps=live_deps,
            )
            live_result = await _evaluate_case_with_source(
                case=case,
                source="live",
                captured=captured,
                live_deps=live_deps,
            )
            captured_results.append(captured_result)
            live_results.append(live_result)
            comparison_results.append(
                {
                    "id": case.id,
                    "bucket": case.bucket,
                    "question": case.question,
                    "captured": captured_result,
                    "live": live_result,
                }
            )
        report.update(
            {
                "results": comparison_results,
                "source_counts": {"captured": len(captured_results), "live": len(live_results)},
                "summary": {
                    "total_cases": len(cases),
                    "comparison_case_count": len(comparison_results),
                    "source_summaries": {
                        "captured": summarize_evaluation(captured_results),
                        "live": summarize_evaluation(live_results),
                    },
                },
                "failure_taxonomy": {
                    "captured": build_failure_taxonomy(cases, captured_results),
                    "live": build_failure_taxonomy(cases, live_results),
                },
                "investigation_corpus_readiness": {
                    "captured": build_investigation_corpus_readiness(
                        cases=cases,
                        results=captured_results,
                        live_deps=None,
                    ),
                    "live": build_investigation_corpus_readiness(
                        cases=cases,
                        results=live_results,
                        live_deps=live_deps,
                    ),
                },
            }
        )
        report["threshold_verdict"] = evaluate_report_thresholds(report)
        return report

    source_label: Literal["captured", "live"] = "captured" if resolved_source_mode == "captured_only" else "live"
    results = [
        await _evaluate_case_with_source(
            case=case,
            source=source_label,
            captured=captured,
            live_deps=live_deps,
        )
        for case in cases
    ]

    report.update(
        {
            "results": results,
            "summary": summarize_evaluation(results),
            "failure_taxonomy": build_failure_taxonomy(cases, results),
            "source_counts": dict(sorted(Counter(result["source"] for result in results).items())),
            "investigation_corpus_readiness": build_investigation_corpus_readiness(
                cases=cases,
                results=results,
                live_deps=live_deps if source_label == "live" else None,
            ),
        }
    )
    report["threshold_verdict"] = evaluate_report_thresholds(report)
    return report


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
