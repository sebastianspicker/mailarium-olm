#!/usr/bin/env python3
# pylint: disable=too-many-branches,too-many-locals,too-many-statements


"""Run a minimal answer-context evaluation against labeled mailbox questions."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
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
    except (ImportError, ModuleNotFoundError):
        return False
    return True


def _run_project_reexec(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    if len(command) < 2 or Path(command[1]).resolve() != Path(__file__).resolve():
        raise ValueError("QA eval re-exec must target this script")
    return subprocess.run(  # nosemgrep
        command,
        check=False,
        cwd=ROOT,
    )


def _maybe_reexec_embedding(argv: list[str], *, live_backend: str) -> int | None:
    if live_backend != "embedding":
        return None
    if _interpreter_has_module("chromadb"):
        return None
    venv_python = _project_venv_python()
    if not venv_python.exists():
        return None
    completed = _run_project_reexec([str(venv_python), str(Path(__file__).resolve()), *argv])
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    from src import qa_eval

    parser = _build_parser()
    args = parser.parse_args(argv)
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    reexec_code = _maybe_reexec_embedding(raw_argv, live_backend=args.live_backend)
    if reexec_code is not None:
        return reexec_code
    special_code = _run_special_mode(args, parser, qa_eval)
    if special_code is not None:
        return special_code
    _validate_evaluation_args(args, parser)
    return _run_standard_evaluation(args, qa_eval)


def _write_json(path: Path, payload: object) -> str:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")
    return rendered


def _run_special_mode(args, parser, qa_eval) -> int | None:
    if args.bootstrap:
        _validate_bootstrap_args(args, parser)
        output = Path(args.output) if args.output else qa_eval.default_bootstrap_questions_path(Path(args.questions))
        payload = qa_eval.bootstrap_question_set(questions_path=Path(args.questions), results_path=Path(args.results))
        _write_json(output, payload)
        print(json.dumps({"output": str(output), "mode": "bootstrap", "status": "ok"}, indent=2))
        return 0
    if not args.remediation_from:
        return None
    report_path = Path(args.remediation_from)
    output = Path(args.output) if args.output else qa_eval.default_remediation_report_path(report_path)
    payload = qa_eval.build_remediation_summary(qa_eval.load_eval_report(report_path))
    rendered = _write_json(output, payload)
    if not args.output:
        print(json.dumps({"output": str(output), "mode": "remediation", "status": "ok"}, indent=2))
    else:
        print(rendered)
    return 0


def _validate_bootstrap_args(args, parser) -> None:
    conflicts = (
        (args.remediation_from, "--bootstrap cannot be combined with --remediation-from"),
        (not args.questions, "--questions is required when --bootstrap is used"),
        (not args.results, "--results is required when --bootstrap is used"),
        (args.live, "--bootstrap cannot be combined with --live"),
    )
    for invalid, message in conflicts:
        if invalid:
            parser.error(message)


def _validate_evaluation_args(args, parser) -> None:
    errors = (
        (not args.questions, "--questions is required unless --remediation-from is used"),
        (not args.results and not args.live, "provide at least one of --results or --live"),
        (
            args.results and args.live and args.source_mode == "auto",
            "--source-mode is required when both --results and --live are provided",
        ),
        (args.source_mode == "captured_only" and not args.results, "--source-mode=captured_only requires --results"),
        (args.source_mode == "live_only" and not args.live, "--source-mode=live_only requires --live"),
        (
            args.source_mode == "mixed" and (not args.results or not args.live),
            "--source-mode=mixed requires both --results and --live",
        ),
    )
    for invalid, message in errors:
        if invalid:
            parser.error(message)


def _run_standard_evaluation(args, qa_eval) -> int:
    live_deps = None
    output = Path(args.output) if args.output else None
    if args.live and output is None:
        output = qa_eval.default_live_report_path(
            Path(args.questions), backend=args.live_backend if args.live_backend != "auto" else None
        )
    try:
        if args.live:
            live_deps = qa_eval.resolve_live_deps(preferred_backend=args.live_backend)
        report = qa_eval.run_evaluation_sync(
            questions_path=Path(args.questions),
            results_path=Path(args.results) if args.results else None,
            live_deps=live_deps,
            limit=args.limit,
            source_mode=args.source_mode,
        )
        verdict = qa_eval.evaluate_report_thresholds(report)
        report["threshold_verdict"] = verdict
        _render_successful_evaluation(args, report, verdict, output, live_deps)
        return 2 if args.check_thresholds and str(verdict.get("status") or "") != "pass" else 0
    except (RuntimeError, ValueError, OSError, ImportError) as exc:
        if not args.live:
            raise
        return _render_blocked_evaluation(args, output, exc)


def _render_successful_evaluation(args, report, verdict, output, live_deps) -> None:
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if not output:
        print(rendered)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")
    if args.live and not args.output:
        print(
            json.dumps(
                {
                    "output": str(output),
                    "mode": "live",
                    "status": "ok",
                    "live_backend": getattr(live_deps, "live_backend", None),
                    "source_mode": args.source_mode,
                    "threshold_status": str(verdict.get("status") or ""),
                },
                indent=2,
            )
        )


def _render_blocked_evaluation(args, output, exc) -> int:
    report = _blocked_live_report(questions_path=Path(args.questions), output_path=output, exc=exc, source_mode=args.source_mode)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "mode": "live", "status": "blocked", "source_mode": args.source_mode}, indent=2))
    else:
        print(rendered)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
