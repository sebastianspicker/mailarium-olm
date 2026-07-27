"""Exercises captured QA-report manifests and refresh commands for deterministic artifact maintenance.

It keeps validation mode non-mutating and rejects unknown scenario selections.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from pathlib import Path

from mailarium.qa_eval import run_evaluation_sync
from mailarium.qa_eval_captured_artifacts import captured_eval_scenarios, refresh_captured_eval_reports


def test_captured_eval_scenario_manifest_points_to_existing_files() -> None:
    scenarios = captured_eval_scenarios()

    assert [scenario.name for scenario in scenarios] == [
        "core",
        "quote",
        "inferred_thread",
        "attachment_ocr",
    ]
    assert all(scenario.questions_path.exists() for scenario in scenarios)
    assert all(scenario.results_path.exists() for scenario in scenarios)
    assert all(scenario.report_path.exists() for scenario in scenarios)


def test_refresh_captured_eval_reports_check_mode_matches_saved_reports() -> None:
    outcomes = refresh_captured_eval_reports(check_only=True)

    assert outcomes
    assert all(item["status"] == "match" for item in outcomes)


def test_refresh_captured_eval_reports_writes_selected_scenario(tmp_path: Path) -> None:
    fixtures_dir = tmp_path
    source_scenario = next(scenario for scenario in captured_eval_scenarios() if scenario.name == "core")
    for path in (source_scenario.questions_path, source_scenario.results_path):
        (fixtures_dir / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    outcomes = refresh_captured_eval_reports(
        fixtures_dir=fixtures_dir,
        scenario_names={"core"},
    )

    report_path = fixtures_dir / "qa_eval_report.core.captured.json"
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    rerun_report = run_evaluation_sync(
        questions_path=fixtures_dir / source_scenario.questions_path.name,
        results_path=fixtures_dir / source_scenario.results_path.name,
    )

    assert outcomes == [
        {
            "scenario": "core",
            "questions_path": str(fixtures_dir / source_scenario.questions_path.name),
            "results_path": str(fixtures_dir / source_scenario.results_path.name),
            "report_path": str(report_path),
            "status": "written",
        }
    ]
    assert saved_report["summary"] == rerun_report["summary"]
    assert saved_report["failure_taxonomy"] == rerun_report["failure_taxonomy"]


def test_refresh_qa_eval_captured_reports_script_lists_scenarios() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/refresh_qa_eval_captured_reports.py", "--list"],
        check=True,
        capture_output=True,
        text=True,
    )

    names = json.loads(completed.stdout)

    assert "core" in names
    assert "quote" in names


def test_refresh_qa_eval_captured_reports_script_rejects_unknown_scenarios(capsys) -> None:
    from scripts import refresh_qa_eval_captured_reports as runner

    exit_code = runner.main(["--scenario", "unknown_scenario"])

    assert exit_code == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "unknown_scenarios"
    assert error["unknown"] == ["unknown_scenario"]
    assert "core" in error["valid_scenarios"]


def test_refresh_qa_eval_captured_reports_script_check_mode_is_non_mutating(tmp_path: Path) -> None:
    from scripts import refresh_qa_eval_captured_reports as runner

    fixtures_dir = tmp_path / "qa_eval"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    source_scenario = next(scenario for scenario in captured_eval_scenarios() if scenario.name == "core")

    questions_copy = fixtures_dir / source_scenario.questions_path.name
    results_copy = fixtures_dir / source_scenario.results_path.name
    report_copy = fixtures_dir / source_scenario.report_path.name
    questions_copy.write_text(source_scenario.questions_path.read_text(encoding="utf-8"), encoding="utf-8")
    results_copy.write_text(source_scenario.results_path.read_text(encoding="utf-8"), encoding="utf-8")
    report_copy.write_text("{}\n", encoding="utf-8")

    exit_code = runner.main(
        [
            "--check",
            "--scenario",
            "core",
            "--fixtures-dir",
            str(fixtures_dir),
        ]
    )

    assert exit_code == 1
    assert report_copy.read_text(encoding="utf-8") == "{}\n"
