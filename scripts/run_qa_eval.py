#!/usr/bin/env python3
"""Run a minimal answer-context evaluation against labeled mailbox questions."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate email_answer_context against labeled question cases.",
    )
    parser.add_argument(
        "--questions",
        help="Path to the question-set JSON file.",
    )
    parser.add_argument(
        "--results",
        help="Optional path to captured answer-context payloads keyed by case id.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the live answer-context path through ToolDeps instead of using only captured payloads.",
    )
    parser.add_argument(
        "--live-backend",
        choices=("auto", "sqlite", "embedding"),
        default="auto",
        help="Select the live backend: auto, sqlite fallback, or embedding-backed retriever.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on how many cases to evaluate.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the evaluation report as JSON.",
    )
    parser.add_argument(
        "--check-thresholds",
        action="store_true",
        help="Exit non-zero when the resolved report threshold profile fails.",
    )
    parser.add_argument(
        "--source-mode",
        choices=("auto", "captured_only", "live_only", "mixed"),
        default="auto",
        help=(
            "Select the evaluation source policy. 'auto' infers a single available source and rejects implicit mixing. "
            "Use 'mixed' only for explicit captured-vs-live comparison runs."
        ),
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Write a sampled reviewable question set from --questions plus --results instead of running scored evaluation.",
    )
    parser.add_argument(
        "--remediation-from",
        help="Optional path to a saved eval report JSON; writes a remediation summary instead of running evaluation.",
    )
    return parser


def _blocked_live_report(
    *,
    questions_path: Path,
    output_path: Path | None,
    exc: Exception,
    source_mode: str,
) -> dict[str, object]:
    from src.qa_eval_thresholds import infer_threshold_profile

    report: dict[str, object] = {
        "questions_path": str(questions_path),
        "results_path": None,
        "total_cases": 0,
        "cases": [],
        "results": [],
        "source_mode": source_mode,
        "summary": {"total_cases": 0},
        "failure_taxonomy": {"total_flagged_cases": 0, "categories": {}, "ranked_categories": []},
        "source_counts": {},
        "live_status": {
            "status": "blocked",
            "output_path": str(output_path) if output_path else None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
    }
    report["threshold_verdict"] = {
        "profile": infer_threshold_profile(report),
        "status": "fail",
        "failure_count": 1,
        "failures": [
            {
                "metric": "live_status",
                "field": "status",
                "expected": {"equals": "ok"},
                "actual": "blocked",
            }
        ],
        "reason": "live_execution_blocked",
    }
    return report


def _project_venv_python() -> Path:
    return ROOT / ".venv" / "bin" / "python"


def _interpreter_has_module(module_name: str) -> bool:
    try:
        __import__(module_name)
    except Exception:
        return False
    return True


def _maybe_reexec_embedding(argv: list[str], *, live_backend: str) -> int | None:
    if live_backend != "embedding":
        return None
    if _interpreter_has_module("chromadb"):
        return None
    venv_python = _project_venv_python()
    if not venv_python.exists():
        return None
    completed = subprocess.run([str(venv_python), str(Path(__file__).resolve()), *argv], cwd=ROOT)
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    from src.qa_eval import (
        bootstrap_question_set,
        build_remediation_summary,
        default_bootstrap_questions_path,
        default_live_report_path,
        default_remediation_report_path,
        evaluate_report_thresholds,
        load_eval_report,
        resolve_live_deps,
        run_evaluation_sync,
    )

    parser = _build_parser()
    args = parser.parse_args(argv)
    raw_argv = list(argv) if argv is not None else sys.argv[1:]

    reexec_code = _maybe_reexec_embedding(raw_argv, live_backend=args.live_backend)
    if reexec_code is not None:
        return reexec_code

    if args.bootstrap:
        if args.remediation_from:
            parser.error("--bootstrap cannot be combined with --remediation-from")
        if not args.questions:
            parser.error("--questions is required when --bootstrap is used")
        if not args.results:
            parser.error("--results is required when --bootstrap is used")
        if args.live:
            parser.error("--bootstrap cannot be combined with --live")
        output_path = Path(args.output) if args.output else default_bootstrap_questions_path(Path(args.questions))
        bootstrapped = bootstrap_question_set(
            questions_path=Path(args.questions),
            results_path=Path(args.results),
        )
        rendered = json.dumps(bootstrapped, indent=2, ensure_ascii=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output_path), "mode": "bootstrap", "status": "ok"}, indent=2))
        return 0

    if args.remediation_from:
        report_path = Path(args.remediation_from)
        output_path = Path(args.output) if args.output else default_remediation_report_path(report_path)
        remediation = build_remediation_summary(load_eval_report(report_path))
        rendered = json.dumps(remediation, indent=2, ensure_ascii=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        if not args.output:
            print(json.dumps({"output": str(output_path), "mode": "remediation", "status": "ok"}, indent=2))
        else:
            print(rendered)
        return 0

    if not args.questions:
        parser.error("--questions is required unless --remediation-from is used")
    if not args.results and not args.live:
        parser.error("provide at least one of --results or --live")
    if args.results and args.live and args.source_mode == "auto":
        parser.error("--source-mode is required when both --results and --live are provided")
    if args.source_mode == "captured_only" and not args.results:
        parser.error("--source-mode=captured_only requires --results")
    if args.source_mode == "live_only" and not args.live:
        parser.error("--source-mode=live_only requires --live")
    if args.source_mode == "mixed" and (not args.results or not args.live):
        parser.error("--source-mode=mixed requires both --results and --live")

    live_deps = None
    output_path = Path(args.output) if args.output else None
    if args.live and output_path is None:
        output_path = default_live_report_path(
            Path(args.questions),
            backend=args.live_backend if args.live_backend != "auto" else None,
        )
    try:
        if args.live:
            live_deps = resolve_live_deps(preferred_backend=args.live_backend)

        report = run_evaluation_sync(
            questions_path=Path(args.questions),
            results_path=Path(args.results) if args.results else None,
            live_deps=live_deps,
            limit=args.limit,
            source_mode=args.source_mode,
        )
        threshold_verdict = evaluate_report_thresholds(report)
        report["threshold_verdict"] = threshold_verdict
        rendered = json.dumps(report, indent=2, ensure_ascii=False)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
            if args.live and not args.output:
                print(
                    json.dumps(
                        {
                            "output": str(output_path),
                            "mode": "live",
                            "status": "ok",
                            "live_backend": getattr(live_deps, "live_backend", None),
                            "source_mode": args.source_mode,
                            "threshold_status": str(threshold_verdict.get("status") or ""),
                        },
                        indent=2,
                    )
                )
        else:
            print(rendered)
        if args.check_thresholds and str(threshold_verdict.get("status") or "") != "pass":
            return 2
        return 0
    except Exception as exc:
        if not args.live:
            raise
        report = _blocked_live_report(
            questions_path=Path(args.questions),
            output_path=output_path,
            exc=exc,
            source_mode=args.source_mode,
        )
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {"output": str(output_path), "mode": "live", "status": "blocked", "source_mode": args.source_mode},
                    indent=2,
                )
            )
        else:
            print(rendered)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
