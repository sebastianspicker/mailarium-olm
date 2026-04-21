from __future__ import annotations

import json
from pathlib import Path
from shutil import copy2


def test_legal_support_full_pack_golden_files_exist_and_cover_key_products() -> None:
    from src.legal_support_acceptance_cases import acceptance_case_ids
    from src.legal_support_acceptance_goldens import legal_support_golden_scenarios

    scenarios = legal_support_golden_scenarios()

    assert len(scenarios) == len(acceptance_case_ids())
    assert {scenario.case_id for scenario in scenarios} == set(acceptance_case_ids())

    payloads = {scenario.case_id: json.loads(Path(scenario.golden_path).read_text(encoding="utf-8")) for scenario in scenarios}

    for case_id, payload in payloads.items():
        assert payload["scenario"] == f"legal_support_full_pack_{case_id}"
        assert payload["case_id"] == case_id
        assert payload["projection"]["acceptance_lane"] == {"mode": "fixture_assembly", "retrieval_sensitive": False}
        assert payload["projection"]["evidence_rows"]
        assert payload["projection"]["chronology_entries"]
        assert payload["projection"]["issue_rows"]
        assert payload["projection"]["dashboard_cards"]["main_claims_or_issues"]

    retaliation = payloads["retaliation_rights_assertion"]
    assert retaliation["projection"]["memo_sections"]["executive_summary"]
    assert retaliation["projection"]["draft_preflight"]
    assert retaliation["projection"]["retaliation_points"]
    assert retaliation["projection"]["provenance_examples"]
    assert retaliation["projection"]["cross_output_checks"]

    comparator = payloads["comparator_unequal_treatment"]
    assert comparator["projection"]["comparator_points"]


def test_refresh_captured_reports_check_mode_includes_full_pack_goldens(tmp_path: Path) -> None:
    from scripts import refresh_qa_eval_captured_reports as runner
    from src.legal_support_acceptance_goldens import FULL_PACK_GOLDEN_ALIAS, legal_support_golden_scenarios
    from src.qa_eval_captured_artifacts import captured_eval_scenarios

    listed = json.loads(_capture_stdout(lambda: runner.main(["--list"])))
    assert FULL_PACK_GOLDEN_ALIAS in listed
    assert {scenario.name for scenario in captured_eval_scenarios()} <= set(listed)

    docs_agent_dir = tmp_path / "docs_agent"
    docs_agent_dir.mkdir(parents=True, exist_ok=True)

    legal_support_scenario = next(s for s in captured_eval_scenarios() if s.name == "legal_support")
    for source in (
        legal_support_scenario.questions_path,
        legal_support_scenario.results_path,
        legal_support_scenario.report_path,
    ):
        copy2(source, docs_agent_dir / source.name)

    for scenario in legal_support_golden_scenarios():
        copy2(Path(scenario.golden_path), docs_agent_dir / Path(scenario.golden_path).name)

    refresh_exit = runner.main(
        [
            "--scenario",
            FULL_PACK_GOLDEN_ALIAS,
            "--scenario",
            "legal_support",
            "--docs-agent-dir",
            str(docs_agent_dir),
        ]
    )
    assert refresh_exit == 0
    check_exit = runner.main(
        [
            "--check",
            "--scenario",
            FULL_PACK_GOLDEN_ALIAS,
            "--scenario",
            "legal_support",
            "--docs-agent-dir",
            str(docs_agent_dir),
        ]
    )
    assert check_exit == 0


def test_build_golden_projection_reads_nested_chronology_and_skeptical_shapes() -> None:
    from src.legal_support_acceptance_projection import build_golden_projection

    projection = build_golden_projection(
        {
            "workflow": "case_full_pack",
            "status": "completed",
            "full_case_analysis": {
                "master_chronology": {
                    "entries": [
                        {
                            "chronology_id": "CHR-1",
                            "date": "2025-03-01",
                            "title": "BEM meeting",
                            "source_document": {"source_id": "email:uid-1"},
                            "source_linkage": {"source_ids": ["email:uid-1"]},
                            "event_support_matrix": {"retaliation_after_protected_event": {"status": "direct_event_support"}},
                        }
                    ]
                },
                "skeptical_employer_review": {
                    "weaknesses": [
                        {
                            "weakness_id": "weakness-1",
                            "category": "chronology_problem",
                            "critique": "There is a chronology gap.",
                            "repair_guidance": {"how_to_fix": "Add the missing dated record."},
                        }
                    ]
                },
                "matter_evidence_index": {"rows": []},
                "lawyer_issue_matrix": {"rows": []},
            },
        }
    )

    assert projection["chronology_entries"][0]["source_id"] == "email:uid-1"
    assert projection["chronology_entries"][0]["issue_category"] == ["retaliation after protected event"]
    assert projection["skeptical_weaknesses"][0]["category"] == "chronology_problem"
    assert projection["skeptical_weaknesses"][0]["critique"] == "There is a chronology gap."


def test_build_golden_projection_prefers_ranked_exhibits_when_available() -> None:
    from src.legal_support_acceptance_projection import build_golden_projection

    projection = build_golden_projection(
        {
            "workflow": "case_full_pack",
            "status": "completed",
            "full_case_analysis": {
                "matter_evidence_index": {
                    "rows": [
                        {
                            "exhibit_id": "EXH-OLD",
                            "document_type": "email_body",
                            "main_issue_tags": ["legacy"],
                            "source_id": "email:old",
                            "exhibit_reliability": {"strength": "weak"},
                        }
                    ],
                    "top_15_exhibits": [
                        {
                            "exhibit_id": "EXH-TOP",
                            "document_type": "attached_document",
                            "main_issue_tags": ["ranked"],
                            "source_id": "manifest:doc:1",
                            "exhibit_reliability": {"strength": "strong"},
                        }
                    ],
                },
                "lawyer_issue_matrix": {"rows": []},
            },
        }
    )

    assert projection["evidence_rows"][0]["exhibit_id"] == "EXH-TOP"


def test_build_golden_projection_ignores_context_only_chronology_issue_reads() -> None:
    from src.legal_support_acceptance_projection import build_golden_projection

    projection = build_golden_projection(
        {
            "workflow": "case_full_pack",
            "status": "completed",
            "full_case_analysis": {
                "master_chronology": {
                    "entries": [
                        {
                            "chronology_id": "CHR-2",
                            "date": "2025-03-01",
                            "title": "Context-only item",
                            "source_document": {"source_id": "email:uid-2"},
                            "source_linkage": {"source_ids": ["email:uid-2"]},
                            "event_support_matrix": {
                                "retaliation_after_protected_event": {
                                    "status": "contextual_support_only",
                                    "support_class": "scope_context_only",
                                }
                            },
                        }
                    ]
                },
                "matter_evidence_index": {"rows": []},
                "lawyer_issue_matrix": {"rows": []},
            },
        }
    )

    assert projection["chronology_entries"][0]["issue_category"] == []


def _capture_stdout(fn) -> str:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        fn()
    return buffer.getvalue()
