"""Manifest and refresh helpers for captured QA eval reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .qa_eval import _display_path, run_evaluation_sync

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_AGENT_DIR = ROOT / "docs" / "agent"


@dataclass(frozen=True)
class CapturedEvalScenario:
    """Filesystem contract for one captured QA eval scenario."""

    name: str
    questions_filename: str
    results_filename: str
    report_filename: str

    def resolve(self, docs_agent_dir: Path = DEFAULT_DOCS_AGENT_DIR) -> ResolvedCapturedEvalScenario:
        return ResolvedCapturedEvalScenario(
            name=self.name,
            questions_path=docs_agent_dir / self.questions_filename,
            results_path=docs_agent_dir / self.results_filename,
            report_path=docs_agent_dir / self.report_filename,
        )


@dataclass(frozen=True)
class ResolvedCapturedEvalScenario:
    """Fully resolved paths for a captured QA eval scenario."""

    name: str
    questions_path: Path
    results_path: Path
    report_path: Path


CAPTURED_EVAL_SCENARIOS: tuple[CapturedEvalScenario, ...] = (
    CapturedEvalScenario(
        name="core",
        questions_filename="qa_eval_questions.core.json",
        results_filename="qa_eval_results.core.captured.json",
        report_filename="qa_eval_report.core.captured.json",
    ),
    CapturedEvalScenario(
        name="quote",
        questions_filename="qa_eval_questions.quote.json",
        results_filename="qa_eval_results.quote.captured.json",
        report_filename="qa_eval_report.quote.captured.json",
    ),
    CapturedEvalScenario(
        name="inferred_thread",
        questions_filename="qa_eval_questions.inferred_thread.json",
        results_filename="qa_eval_results.inferred_thread.captured.json",
        report_filename="qa_eval_report.inferred_thread.captured.json",
    ),
    CapturedEvalScenario(
        name="attachment_ocr",
        questions_filename="qa_eval_questions.attachment_ocr.json",
        results_filename="qa_eval_results.attachment_ocr.captured.json",
        report_filename="qa_eval_report.attachment_ocr.captured.json",
    ),
    CapturedEvalScenario(
        name="behavioral_analysis",
        questions_filename="qa_eval_questions.behavioral_analysis.captured.json",
        results_filename="qa_eval_results.behavioral_analysis.captured.json",
        report_filename="qa_eval_report.behavioral_analysis.captured.json",
    ),
    CapturedEvalScenario(
        name="behavioral_analysis_german",
        questions_filename="qa_eval_questions.behavioral_analysis_german.captured.json",
        results_filename="qa_eval_results.behavioral_analysis_german.captured.json",
        report_filename="qa_eval_report.behavioral_analysis_german.captured.json",
    ),
    CapturedEvalScenario(
        name="legal_support",
        questions_filename="qa_eval_questions.legal_support.captured.json",
        results_filename="qa_eval_results.legal_support.captured.json",
        report_filename="qa_eval_report.legal_support.captured.json",
    ),
)


def captured_eval_scenarios(docs_agent_dir: Path = DEFAULT_DOCS_AGENT_DIR) -> tuple[ResolvedCapturedEvalScenario, ...]:
    """Return the resolved captured QA eval scenario manifest."""

    return tuple(scenario.resolve(docs_agent_dir) for scenario in CAPTURED_EVAL_SCENARIOS)


def render_captured_eval_report(scenario: ResolvedCapturedEvalScenario) -> dict[str, object]:
    """Rebuild one captured QA eval report from its stored question/results pair."""

    return run_evaluation_sync(
        questions_path=scenario.questions_path,
        results_path=scenario.results_path,
    )


def refresh_captured_eval_reports(
    *,
    docs_agent_dir: Path = DEFAULT_DOCS_AGENT_DIR,
    scenario_names: set[str] | None = None,
    check_only: bool = False,
) -> list[dict[str, object]]:
    """Refresh or check the captured QA eval reports declared in the manifest."""

    outcomes: list[dict[str, object]] = []
    for scenario in captured_eval_scenarios(docs_agent_dir):
        if scenario_names and scenario.name not in scenario_names:
            continue
        report = render_captured_eval_report(scenario)
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        existing = scenario.report_path.read_text(encoding="utf-8") if scenario.report_path.exists() else None
        status = "match" if existing == rendered else "updated"
        if not check_only and status == "updated":
            scenario.report_path.write_text(rendered, encoding="utf-8")
        outcomes.append(
            {
                "scenario": scenario.name,
                "questions_path": _display_path(scenario.questions_path),
                "results_path": _display_path(scenario.results_path),
                "report_path": _display_path(scenario.report_path),
                "status": status if check_only else ("written" if status == "updated" else "unchanged"),
            }
        )
    return outcomes
