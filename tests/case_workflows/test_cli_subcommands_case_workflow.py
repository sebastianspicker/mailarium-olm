# ruff: noqa: F401
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.cli import parse_args
from src.cli_commands_case import (
    run_case_analyze_impl,
    run_case_archive_results_impl,
    run_case_counsel_pack_impl,
    run_case_execute_all_waves_impl,
    run_case_execute_wave_impl,
    run_case_full_pack_impl,
    run_case_gather_evidence_impl,
    run_case_prompt_preflight_impl,
    run_case_refresh_active_run_impl,
    run_case_review_override_impl,
    run_case_review_snapshot_impl,
    run_case_review_status_impl,
)
from src.email_db import EmailDatabase
from src.legal_support_acceptance_fixtures import acceptance_case_ids


def test_run_case_analyze_impl_writes_output(tmp_path, monkeypatch) -> None:
    case_path = tmp_path / "case.json"
    output_path = tmp_path / "report.json"
    case_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "allegation_focus": ["exclusion"],
                    "analysis_goal": "internal_review",
                    "date_from": "2025-01-01",
                    "date_to": "2025-02-01",
                },
                "source_scope": "emails_only",
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, params):
        assert params.source_scope == "emails_only"
        return json.dumps({"workflow": "case_analysis"})

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)

    class Args:
        input = str(case_path)
        output = str(output_path)
        format = "json"

    run_case_analyze_impl(retriever=object(), get_email_db=lambda: None, args=Args())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["workflow"] == "case_analysis"
    assert payload["execution_authority"]["status"] == "non_authoritative_cli_wrapper"
    assert payload["execution_authority"]["authoritative_surface"] == "mcp_server"


def test_run_case_analyze_impl_returns_stable_missing_input_error(capsys) -> None:
    class Args:
        input = "/tmp/does-not-exist-case-analysis.json"
        output = None
        format = "json"

    with pytest.raises(SystemExit) as exc_info:
        run_case_analyze_impl(retriever=object(), get_email_db=lambda: None, args=Args())

    assert exc_info.value.code == 2
    assert "case input read error" in capsys.readouterr().out


def test_run_case_analyze_impl_rejects_input_outside_allowed_roots(capsys, monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", "/tmp/allowed-case-inputs")

    class Args:
        input = "/etc/hosts"
        output = None
        format = "json"

    with pytest.raises(SystemExit) as exc_info:
        run_case_analyze_impl(retriever=object(), get_email_db=lambda: None, args=Args())

    assert exc_info.value.code == 2
    assert "allowed local read roots" in capsys.readouterr().out


def test_run_case_analyze_impl_returns_stable_json_decode_error(tmp_path, capsys) -> None:
    case_path = tmp_path / "case.json"
    case_path.write_text("{not valid json", encoding="utf-8")

    class Args:
        input = str(case_path)
        output = None
        format = "json"

    with pytest.raises(SystemExit) as exc_info:
        run_case_analyze_impl(retriever=object(), get_email_db=lambda: None, args=Args())

    assert exc_info.value.code == 3
    assert "case input json error" in capsys.readouterr().out


def test_run_case_analyze_impl_returns_stable_output_write_error(tmp_path, monkeypatch, capsys) -> None:
    case_path = tmp_path / "case.json"
    output_path = tmp_path / "report.json"
    case_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "allegation_focus": ["exclusion"],
                    "analysis_goal": "internal_review",
                    "date_from": "2025-01-01",
                    "date_to": "2025-02-01",
                },
                "source_scope": "emails_only",
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, _params):
        return json.dumps({"workflow": "case_analysis"})

    def fake_write_text(self, data, encoding=None):
        raise OSError("disk full")

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)
    monkeypatch.setattr("src.cli_commands_case.Path.write_text", fake_write_text)

    class Args:
        input = str(case_path)
        output = str(output_path)
        format = "json"

    with pytest.raises(SystemExit) as exc_info:
        run_case_analyze_impl(retriever=object(), get_email_db=lambda: None, args=Args())

    assert exc_info.value.code == 4
    assert "case output write error" in capsys.readouterr().out


def test_run_case_analyze_impl_rejects_tracked_repo_output_path(tmp_path, monkeypatch, capsys) -> None:
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "allegation_focus": ["exclusion"],
                    "analysis_goal": "internal_review",
                    "date_from": "2025-01-01",
                    "date_to": "2025-02-01",
                },
                "source_scope": "emails_only",
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, _params):
        return json.dumps({"workflow": "case_analysis"})

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)

    class Args:
        input = str(case_path)
        output = "README.md"
        format = "json"

    with pytest.raises(SystemExit) as exc_info:
        run_case_analyze_impl(retriever=object(), get_email_db=lambda: None, args=Args())

    assert exc_info.value.code == 4
    assert "case output write error" in capsys.readouterr().out


def test_run_case_gather_evidence_impl_writes_output(tmp_path, monkeypatch) -> None:
    case_path = tmp_path / "case.json"
    output_path = tmp_path / "harvest.json"
    case_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "allegation_focus": ["exclusion"],
                    "analysis_goal": "internal_review",
                    "date_from": "2025-01-01",
                    "date_to": "2025-02-01",
                },
                "source_scope": "emails_only",
            }
        ),
        encoding="utf-8",
    )

    async def fake_gather_evidence_payload(_deps, params, **kwargs):
        assert params.source_scope == "emails_only"
        assert kwargs["run_id"] == "investigation_2026-04-16_P60"
        assert kwargs["phase_id"] == "P60"
        return {"workflow": "case_gather_evidence", "status": "completed", "candidate_count": 12}

    monkeypatch.setattr("src.cli_commands_case.gather_evidence_payload", fake_gather_evidence_payload)

    class Args:
        input = str(case_path)
        output = str(output_path)
        scan_id_prefix = "scan-1"
        run_id = "investigation_2026-04-16_P60"
        phase_id = "P60"
        harvest_limit_per_wave = 12
        promote_limit_per_wave = 4
        include_payloads = False

    run_case_gather_evidence_impl(retriever=object(), get_email_db=lambda: None, args=Args())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["workflow"] == "case_gather_evidence"
    assert payload["candidate_count"] == 12
    assert payload["execution_authority"]["case_action"] == "gather-evidence"


def test_run_case_prompt_preflight_impl_writes_output(tmp_path) -> None:
    prompt_path = tmp_path / "matter.md"
    output_path = tmp_path / "preflight.json"
    prompt_path.write_text(
        ("Claimant: Target Employee. Review retaliation from November 2023 to present based on the email corpus."),
        encoding="utf-8",
    )

    class Args:
        input = str(prompt_path)
        output = str(output_path)
        output_language = "en"

    run_case_prompt_preflight_impl(Args())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["workflow"] == "case_prompt_preflight"
    assert payload["execution_authority"]["status"] == "non_authoritative_cli_wrapper"
    assert payload["draft_case_scope"]["target_person"]["name"] == "Target Employee"
    missing_fields = {item["field"] for item in payload["missing_required_inputs"]}
    assert "case_scope.trigger_events" in missing_fields


def test_run_case_execute_wave_impl_writes_output(tmp_path, monkeypatch) -> None:
    case_path = tmp_path / "case.json"
    output_path = tmp_path / "wave.json"
    case_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "suspected_actors": [{"name": "manager"}],
                    "allegation_focus": ["exclusion"],
                    "analysis_goal": "internal_review",
                    "date_from": "2025-01-01",
                    "date_to": "2025-02-01",
                },
                "source_scope": "emails_only",
                "output_language": "de",
                "translation_mode": "source_only",
            }
        ),
        encoding="utf-8",
    )

    async def fake_execute_wave_payload(_deps, _params, *, wave_id, scan_id_prefix):
        return {
            "workflow": "case_analysis",
            "retrieval_plan": {"effective_max_results": 8},
            "wave_execution": {
                "wave_id": wave_id,
                "query_lanes": ["lane one", "lane two"],
                "scan_id": f"{scan_id_prefix}:{wave_id}",
                "local_view_counts": {"master_chronology": 1},
            },
        }

    monkeypatch.setattr("src.cli_commands_case.execute_wave_payload", fake_execute_wave_payload)

    class Args:
        input = str(case_path)
        output = str(output_path)
        wave = "wave_1"
        scan_id_prefix = "run-1"

    run_case_execute_wave_impl(retriever=object(), get_email_db=lambda: None, args=Args())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["wave_execution"]["wave_id"] == "wave_1"
    assert payload["wave_execution"]["query_lanes"]
    assert payload["wave_execution"]["scan_id"] == "run-1:wave_1"
    assert payload["execution_authority"]["case_action"] == "execute-wave"
    assert payload["execution_authority"]["status"] == "shared_campaign_execution_surface"


def test_run_case_execute_all_waves_impl_prints_summary(tmp_path, monkeypatch, capsys) -> None:
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "suspected_actors": [{"name": "manager"}],
                    "allegation_focus": ["exclusion"],
                    "analysis_goal": "internal_review",
                    "date_from": "2025-01-01",
                    "date_to": "2025-02-01",
                },
                "source_scope": "emails_only",
                "output_language": "de",
                "translation_mode": "source_only",
            }
        ),
        encoding="utf-8",
    )

    seen_scan_ids: list[str] = []

    async def fake_execute_all_waves_payload(_deps, _params, *, scan_id_prefix, include_payloads):
        assert include_payloads is False
        waves = []
        for index in range(1, 13):
            wave_id = "wave_5a" if index == 6 else "wave_5b" if index == 7 else f"wave_{index if index < 6 else index - 2}"
            scan_id = f"{scan_id_prefix}:{wave_id}"
            seen_scan_ids.append(scan_id)
            waves.append(
                {
                    "wave_id": wave_id,
                    "scan_id": scan_id,
                    "archive_harvest": {
                        "status": "pass",
                        "primary_source": "email_archive_primary",
                        "unique_hits": 14,
                        "unique_threads": 5,
                        "unique_months": 3,
                    },
                    "wave_local_views": {"master_chronology": 2, "lawyer_issue_matrix": 1},
                }
            )
        return {
            "workflow": "case_execute_all_waves",
            "status": "completed",
            "wave_count": 12,
            "scan_id_prefix": scan_id_prefix,
            "waves": waves,
        }

    monkeypatch.setattr("src.cli_commands_case.execute_all_waves_payload", fake_execute_all_waves_payload)

    args = type(
        "Args",
        (),
        {
            "input": str(case_path),
            "output": None,
            "include_payloads": False,
            "scan_id_prefix": "batch-1",
        },
    )()

    run_case_execute_all_waves_impl(retriever=object(), get_email_db=lambda: None, args=args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"] == "case_execute_all_waves"
    assert payload["wave_count"] == 12
    assert payload["waves"][0]["wave_id"] == "wave_1"
    assert payload["waves"][0]["scan_id"] == "batch-1:wave_1"
    assert payload["waves"][0]["archive_harvest"]["status"] == "pass"
    assert payload["waves"][0]["archive_harvest"]["primary_source"] == "email_archive_primary"
    assert payload["waves"][0]["archive_harvest"]["unique_hits"] == 14
    assert payload["waves"][0]["wave_local_views"]["master_chronology"] == 2
    assert len(set(seen_scan_ids)) == 12
    assert payload["execution_authority"]["status"] == "shared_campaign_execution_surface"


def test_run_case_refresh_active_run_impl_writes_manifest(tmp_path, capsys) -> None:
    results_root = tmp_path / "results"
    checkpoint = results_root / "_checkpoints" / "run.md"
    report = results_root / "03_exhaustive_run" / "report.json"
    register = results_root / "11_memo_draft_dashboard" / "question_register.md"
    open_tasks = results_root / "11_memo_draft_dashboard" / "open_tasks_companion.md"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    register.parent.mkdir(parents=True, exist_ok=True)
    open_tasks.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("stub", encoding="utf-8")
    report.write_text("stub", encoding="utf-8")
    register.write_text("question register for P40 investigation_2026-04-16_P40", encoding="utf-8")
    open_tasks.write_text("open tasks for P40 investigation_2026-04-16_P40", encoding="utf-8")

    args = type(
        "Args",
        (),
        {
            "results_root": str(results_root),
            "matter_id": "matter:123",
            "run_id": "investigation_2026-04-16_P40",
            "phase_id": "P40",
            "active_checkpoint": str(checkpoint),
            "active_result_paths": [str(report)],
            "question_register_path": str(register),
            "open_tasks_companion_path": str(open_tasks),
        },
    )()

    run_case_refresh_active_run_impl(args)
    data = json.loads(capsys.readouterr().out)
    assert data["workflow"] == "case_refresh_active_run"
    assert data["manifest"]["active_checkpoint"] == "_checkpoints/run.md"
    assert data["manifest"]["active_result_paths"] == ["03_exhaustive_run/report.json"]
    assert data["manifest_path"].endswith("active_run.json")
    assert data["manifest"]["curation"]["status"] == "curated_current"


def test_run_case_analyze_impl_accepts_stronger_mixed_source_case_intake(tmp_path, monkeypatch) -> None:
    case_path = tmp_path / "case-rich.json"
    output_path = tmp_path / "report-rich.json"
    case_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "target_person": {"name": "Target Employee", "email": "employee@example.test"},
                    "suspected_actors": [{"name": "manager", "email": "manager@example.test"}],
                    "comparator_actors": [{"name": "Pat Vergleich", "email": "pat@example.org"}],
                    "allegation_focus": ["retaliation", "unequal_treatment"],
                    "analysis_goal": "lawyer_briefing",
                    "context_notes": "Projektkonflikt nach formeller Beschwerde.",
                    "trigger_events": [{"trigger_type": "complaint", "date": "2025-03-01"}],
                    "org_context": {
                        "reporting_lines": [
                            {
                                "manager": {"name": "manager", "email": "manager@example.test"},
                                "report": {"name": "Target Employee", "email": "employee@example.test"},
                                "source": "supplied_fact",
                            }
                        ]
                    },
                    "date_from": "2025-01-01",
                    "date_to": "2025-06-30",
                },
                "source_scope": "mixed_case_file",
                "chat_log_entries": [
                    {
                        "platform": "Teams",
                        "participants": ["employee@example.test", "manager@example.test"],
                        "date": "2025-03-02T09:00:00Z",
                        "text": "Bitte nicht erneut direkt an HR schreiben.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, params):
        assert params.source_scope == "mixed_case_file"
        assert len(params.case_scope.trigger_events) == 1
        assert len(params.case_scope.comparator_actors) == 1
        assert params.case_scope.org_context is not None
        assert len(params.chat_log_entries) == 1
        return json.dumps({"workflow": "case_analysis", "source_scope": params.source_scope})

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)

    class Args:
        input = str(case_path)
        output = str(output_path)
        format = "json"

    run_case_analyze_impl(retriever=object(), get_email_db=lambda: None, args=Args())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["workflow"] == "case_analysis"
    assert payload["source_scope"] == "mixed_case_file"
    assert payload["execution_authority"]["status"] == "non_authoritative_cli_wrapper"
