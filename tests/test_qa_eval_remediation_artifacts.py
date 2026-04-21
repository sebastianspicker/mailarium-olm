import json
from pathlib import Path


def test_saved_live_expanded_remediation_matches_builder_output():
    from src.qa_eval import build_remediation_summary, load_eval_report

    report_path = Path("docs/agent/qa_eval_report.live_expanded.live.json")
    remediation_path = Path("docs/agent/qa_eval_remediation.live_expanded.live.json")

    saved_remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
    rebuilt_remediation = build_remediation_summary(load_eval_report(report_path))

    assert saved_remediation == rebuilt_remediation
