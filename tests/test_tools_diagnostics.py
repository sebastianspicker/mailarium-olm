"""Exercises diagnostic summaries and candidate-path selection for repository maintenance signals.

It keeps live QA evaluation outputs within private runtime locations.
"""

from ._tools_diagnostics_cases import TestDiagnostics

_COLLECTED_TESTS = (TestDiagnostics,)


def test_qa_eval_candidate_paths_keep_live_outputs_private(tmp_path) -> None:
    from mailarium.tools.diagnostics_summary import (
        inferred_thread_prevalence_candidates_impl,
        qa_eval_remediation_candidates_impl,
        qa_eval_report_candidates_impl,
    )

    live_dir = tmp_path / "private" / "tests" / "results" / "qa_eval"
    fixture_dir = tmp_path / "tests" / "fixtures" / "qa_eval"
    live_dir.mkdir(parents=True)
    fixture_dir.mkdir(parents=True)
    live_report = live_dir / "qa_eval_report.core.live.json"
    captured_report = fixture_dir / "qa_eval_report.core.captured.json"
    live_report.write_text("{}\n", encoding="utf-8")
    captured_report.write_text("{}\n", encoding="utf-8")

    reports = qa_eval_report_candidates_impl(lambda: tmp_path)

    assert reports[:2] == [live_report, captured_report]
    assert all(path.is_relative_to(live_dir) for path in qa_eval_remediation_candidates_impl(lambda: tmp_path))
    assert all(path.is_relative_to(live_dir) for path in inferred_thread_prevalence_candidates_impl(lambda: tmp_path))
