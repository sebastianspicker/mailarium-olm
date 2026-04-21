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


def test_run_case_full_pack_impl_writes_blocked_output(tmp_path, capsys) -> None:
    prompt_path = tmp_path / "matter.md"
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")
    prompt_path.write_text(
        "Claimant: employee. Review retaliation from November 2023 to present based on the email corpus.",
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "prompt": str(prompt_path),
            "materials_dir": str(materials_dir),
            "overrides": None,
            "output": None,
            "output_language": "en",
            "translation_mode": "translation_aware",
            "default_source_scope": "emails_and_attachments",
            "assume_date_to_today": True,
            "privacy_mode": "external_counsel_export",
            "delivery_target": "counsel_handoff_bundle",
            "delivery_format": "bundle",
            "compile_only": True,
            "allow_blocked_exit_zero": False,
        },
    )()

    exit_code = run_case_full_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["workflow"] == "case_full_pack"
    assert payload["status"] == "blocked"
    assert payload["execution_authority"]["status"] == "non_authoritative_cli_wrapper"
    blocker_fields = {item["field"] for item in payload["blockers"]}
    assert "case_scope.trigger_events" in blocker_fields
    assert payload["intake_compilation"]["override_suggestions"]["repair_mode"] == "explicit_override_required"


def test_run_case_full_pack_impl_applies_override_file(tmp_path, monkeypatch, capsys) -> None:
    prompt_path = tmp_path / "matter.md"
    materials_dir = tmp_path / "materials"
    overrides_path = tmp_path / "overrides.json"
    output_path = tmp_path / "handoff.bundle"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")
    prompt_path.write_text(
        "Claimant: employee. Review retaliation from 2025-01-01 to 2025-06-30 based on the email corpus.",
        encoding="utf-8",
    )
    overrides_path.write_text(
        json.dumps(
            {
                "case_scope": {
                    "trigger_events": [{"trigger_type": "complaint", "date": "2025-03-01"}],
                    "alleged_adverse_actions": [{"action_type": "task_withdrawal", "date": "2025-03-05"}],
                    "target_person": {"name": "employee", "email": "employee@example.test"},
                }
            }
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "prompt": str(prompt_path),
            "materials_dir": str(materials_dir),
            "overrides": str(overrides_path),
            "output": str(output_path),
            "output_language": "de",
            "translation_mode": "translation_aware",
            "default_source_scope": "emails_and_attachments",
            "assume_date_to_today": True,
            "privacy_mode": "external_counsel_export",
            "delivery_target": "counsel_handoff_bundle",
            "delivery_format": "bundle",
            "compile_only": False,
            "allow_blocked_exit_zero": False,
        },
    )()

    async def fake_execute_case_full_pack(_deps, params):
        assert params.output_path == str(output_path)
        assert params.intake_overrides["case_scope"]["trigger_events"][0]["trigger_type"] == "complaint"
        return {
            "workflow": "case_full_pack",
            "status": "completed",
            "export_result": {"output_path": str(output_path), "delivery_target": "counsel_handoff_bundle"},
        }

    monkeypatch.setattr("src.cli_commands_case.execute_case_full_pack", fake_execute_case_full_pack)

    exit_code = run_case_full_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["export_result"]["delivery_target"] == "counsel_handoff_bundle"
    assert payload["execution_authority"]["status"] == "non_authoritative_cli_wrapper"


@pytest.mark.parametrize("case_id", acceptance_case_ids())
def test_run_case_full_pack_impl_realistic_fixture_cases(case_id, monkeypatch, tmp_path, capsys) -> None:
    from src.legal_support_acceptance_fixtures import build_fixture_answer_context, build_fixture_full_pack_input

    async def fake_build_answer_context_payload(_deps, _params, **kwargs):
        return build_fixture_answer_context(case_id)

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    output_path = tmp_path / f"{case_id}.zip"
    params = build_fixture_full_pack_input(case_id, output_path=str(output_path))

    prompt_path = tmp_path / f"{case_id}.md"
    prompt_path.write_text(params.prompt_text, encoding="utf-8")

    overrides_path = tmp_path / f"{case_id}.overrides.json"
    overrides_path.write_text(json.dumps(params.intake_overrides), encoding="utf-8")

    args = SimpleNamespace(
        prompt=str(prompt_path),
        materials_dir=params.materials_dir,
        overrides=str(overrides_path),
        output=str(output_path),
        output_language=params.output_language,
        translation_mode=params.translation_mode,
        default_source_scope=params.default_source_scope,
        assume_date_to_today=params.assume_date_to_today,
        privacy_mode=params.privacy_mode,
        delivery_target=params.delivery_target,
        delivery_format=params.delivery_format,
        compile_only=False,
        allow_blocked_exit_zero=True,
    )

    exit_code = run_case_full_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] in {"completed", "blocked"}
    if payload["status"] == "completed":
        assert payload["export_result"]["output_path"] == str(output_path)
        assert output_path.exists()
    else:
        assert payload["execution"]["reason"] == "export_readiness_gate_blocked"
        assert payload["export_result"] is None
    assert payload["execution_authority"]["status"] == "non_authoritative_cli_wrapper"


def test_run_case_full_pack_impl_allows_legacy_zero_exit_for_blocked_payload(tmp_path, capsys) -> None:
    prompt_path = tmp_path / "matter.md"
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")
    prompt_path.write_text(
        "Claimant: employee. Review retaliation from November 2023 to present based on the email corpus.",
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "prompt": str(prompt_path),
            "materials_dir": str(materials_dir),
            "overrides": None,
            "output": None,
            "output_language": "en",
            "translation_mode": "translation_aware",
            "default_source_scope": "emails_and_attachments",
            "assume_date_to_today": True,
            "privacy_mode": "external_counsel_export",
            "delivery_target": "counsel_handoff_bundle",
            "delivery_format": "bundle",
            "compile_only": True,
            "allow_blocked_exit_zero": True,
        },
    )()

    exit_code = run_case_full_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "blocked"
    assert payload["execution_authority"]["status"] == "non_authoritative_cli_wrapper"


def test_run_case_counsel_pack_impl_builds_manifest_backed_export(tmp_path, monkeypatch, capsys) -> None:
    scope_path = tmp_path / "scope.json"
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "teams-chat.html").write_text("<html><body><p>Teams export</p></body></html>", encoding="utf-8")
    output_path = tmp_path / "handoff.zip"
    scope_path.write_text(
        json.dumps(
            {
                "target_person": {"name": "employee"},
                "allegation_focus": ["retaliation"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, params):
        assert params.review_mode == "exhaustive_matter_review"
        assert params.source_scope == "mixed_case_file"
        assert params.matter_manifest is not None
        return json.dumps({"workflow": "case_analysis", "review_mode": params.review_mode})

    class _FakeExporter:
        def export_file(self, *, payload, output_path, delivery_target, delivery_format):
            assert payload["workflow"] == "case_analysis"
            assert delivery_target == "counsel_handoff_bundle"
            assert delivery_format == "bundle"
            return {"output_path": output_path, "delivery_target": delivery_target, "delivery_format": delivery_format}

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)
    monkeypatch.setattr("src.cli_commands_case.LegalSupportExporter", lambda: _FakeExporter())

    args = type(
        "Args",
        (),
        {
            "case_scope": str(scope_path),
            "materials_dir": str(materials_dir),
            "output": str(output_path),
            "delivery_target": "counsel_handoff_bundle",
            "delivery_format": "bundle",
            "privacy_mode": "external_counsel_export",
            "output_language": "en",
            "translation_mode": "translation_aware",
        },
    )()

    run_case_counsel_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    data = json.loads(capsys.readouterr().out)
    assert data["workflow"] == "case_counsel_pack"
    assert data["delivery_target"] == "counsel_handoff_bundle"
    assert data["delivery_format"] == "bundle"
    assert data["execution_authority"]["status"] == "non_authoritative_cli_wrapper"


def test_run_case_counsel_pack_impl_uses_mixed_scope_for_non_email_manifest_records(tmp_path, monkeypatch, capsys) -> None:
    scope_path = tmp_path / "scope.json"
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "meeting-note.txt").write_text("Gedächtnisprotokoll zur BEM-Besprechung.", encoding="utf-8")
    output_path = tmp_path / "handoff.zip"
    scope_path.write_text(
        json.dumps(
            {
                "target_person": {"name": "employee"},
                "allegation_focus": ["retaliation"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, params):
        assert params.review_mode == "exhaustive_matter_review"
        assert params.source_scope == "mixed_case_file"
        assert params.matter_manifest is not None
        return json.dumps({"workflow": "case_analysis", "review_mode": params.review_mode})

    class _FakeExporter:
        def export_file(self, *, payload, output_path, delivery_target, delivery_format):
            assert payload["workflow"] == "case_analysis"
            assert delivery_target == "counsel_handoff_bundle"
            assert delivery_format == "bundle"
            return {"output_path": output_path, "delivery_target": delivery_target, "delivery_format": delivery_format}

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)
    monkeypatch.setattr("src.cli_commands_case.LegalSupportExporter", lambda: _FakeExporter())

    args = type(
        "Args",
        (),
        {
            "case_scope": str(scope_path),
            "materials_dir": str(materials_dir),
            "output": str(output_path),
            "delivery_target": "counsel_handoff_bundle",
            "delivery_format": "bundle",
            "privacy_mode": "external_counsel_export",
            "output_language": "en",
            "translation_mode": "translation_aware",
        },
    )()

    run_case_counsel_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    data = json.loads(capsys.readouterr().out)
    assert data["workflow"] == "case_counsel_pack"
    assert data["delivery_target"] == "counsel_handoff_bundle"
    assert data["delivery_format"] == "bundle"
    assert data["execution_authority"]["status"] == "non_authoritative_cli_wrapper"


def test_run_case_counsel_pack_impl_returns_blocked_payload_for_readiness_gate(tmp_path, monkeypatch, capsys) -> None:
    scope_path = tmp_path / "scope.json"
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")
    output_path = tmp_path / "handoff.zip"
    scope_path.write_text(
        json.dumps(
            {
                "target_person": {"name": "employee"},
                "allegation_focus": ["retaliation"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, params):
        assert params.review_mode == "exhaustive_matter_review"
        return json.dumps(
            {
                "workflow": "case_analysis",
                "analysis_query": "retaliation review",
                "matter_persistence": {
                    "snapshot_id": "snapshot:test",
                    "workspace_id": "workspace:test",
                    "matter_id": "matter:test",
                    "review_state": "machine_extracted",
                },
                "matter_ingestion_report": {"completeness_status": "complete"},
                "matter_coverage_ledger": {"summary": {"coverage_status": "complete"}},
            }
        )

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)

    args = type(
        "Args",
        (),
        {
            "case_scope": str(scope_path),
            "materials_dir": str(materials_dir),
            "output": str(output_path),
            "delivery_target": "counsel_handoff_bundle",
            "delivery_format": "bundle",
            "privacy_mode": "external_counsel_export",
            "output_language": "en",
            "translation_mode": "translation_aware",
        },
    )()

    exit_code = run_case_counsel_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert data["workflow"] == "case_counsel_pack"
    assert data["status"] == "blocked"
    assert data["execution_authority"]["status"] == "non_authoritative_cli_wrapper"
    assert data["delivery_target"] == "counsel_handoff_bundle"
    assert data["blockers"] == [
        {
            "field": "snapshot_review_state:machine_extracted",
            "severity": "blocking",
            "reason": "Counsel-facing export remains blocked until the recorded readiness issue is resolved.",
        }
    ]
    readiness = data["export_metadata"]["counsel_export_readiness"]
    assert readiness["ready"] is False
    assert readiness["blockers"] == ["snapshot_review_state:machine_extracted"]
    assert readiness["policy_state"] == "internal_only"
    assert readiness["recommended_internal_targets"] == ["dashboard", "exhibit_register"]


def test_run_case_counsel_pack_impl_allows_legacy_zero_exit_for_blocked_payload(tmp_path, monkeypatch, capsys) -> None:
    scope_path = tmp_path / "scope.json"
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")
    output_path = tmp_path / "handoff.zip"
    scope_path.write_text(
        json.dumps(
            {
                "target_person": {"name": "employee"},
                "allegation_focus": ["retaliation"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        ),
        encoding="utf-8",
    )

    async def fake_build_case_analysis(_deps, _params):
        return json.dumps(
            {
                "matter_persistence": {"review_state": "machine_extracted"},
                "matter_ingestion_report": {"completeness_status": "complete"},
                "matter_coverage_ledger": {"summary": {"coverage_status": "complete"}},
            }
        )

    monkeypatch.setattr("src.cli_commands_case.build_case_analysis", fake_build_case_analysis)

    args = type(
        "Args",
        (),
        {
            "case_scope": str(scope_path),
            "materials_dir": str(materials_dir),
            "output": str(output_path),
            "delivery_target": "counsel_handoff_bundle",
            "delivery_format": "bundle",
            "privacy_mode": "external_counsel_export",
            "output_language": "en",
            "translation_mode": "translation_aware",
            "allow_blocked_exit_zero": True,
        },
    )()

    exit_code = run_case_counsel_pack_impl(retriever=object(), get_email_db=lambda: None, args=args)
    data = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert data["status"] == "blocked"
    assert data["execution_authority"]["status"] == "non_authoritative_cli_wrapper"
