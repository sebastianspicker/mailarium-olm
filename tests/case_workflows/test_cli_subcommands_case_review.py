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


def test_run_case_archive_results_impl_moves_superseded_paths(tmp_path, capsys) -> None:
    results_root = tmp_path / "results"
    report = results_root / "03_exhaustive_run" / "report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("{}", encoding="utf-8")

    args = type(
        "Args",
        (),
        {
            "results_root": str(results_root),
            "archive_label": "superseded_run",
            "relative_paths": ["03_exhaustive_run/report.json"],
        },
    )()

    run_case_archive_results_impl(args)
    data = json.loads(capsys.readouterr().out)
    assert data["workflow"] == "case_archive_results"
    assert data["archived_paths"] == ["_archive/superseded_run/03_exhaustive_run/report.json"]
    assert (results_root / data["archived_paths"][0]).read_text(encoding="utf-8") == "{}"


def test_run_case_review_status_impl_prints_snapshot_and_override_state(capsys) -> None:
    db = EmailDatabase(":memory:")
    persist_result = db.persist_matter_snapshot(
        payload={
            "matter_workspace": {
                "workspace_id": "workspace:123",
                "matter": {"matter_id": "matter:123", "bundle_id": "bundle:123", "case_label": "Case A"},
            },
            "review_governance": {
                "review_state_counts": {
                    "machine_extracted": 1,
                    "human_verified": 0,
                    "disputed": 0,
                    "draft_only": 0,
                    "export_approved": 0,
                }
            },
            "matter_coverage_ledger": {"summary": {"coverage_status": "complete"}},
        },
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert persist_result is not None
    db.upsert_matter_review_override(
        workspace_id="workspace:123",
        target_type="chronology_entry",
        target_id="CHR-001",
        review_state="human_verified",
        override_payload={"summary": "Human-reviewed chronology text."},
        source_evidence=[{"source_id": "email:uid-1"}],
    )

    args = type("Args", (), {"workspace_id": "workspace:123"})()
    run_case_review_status_impl(lambda: db, args)
    data = json.loads(capsys.readouterr().out)
    assert data["workflow"] == "case_review_status"
    assert data["latest_snapshot"]["workspace_id"] == "workspace:123"
    assert data["review_status"]["override_count"] == 1
    assert data["overrides"][0]["target_id"] == "CHR-001"
    db.close()


def test_run_case_review_override_impl_persists_override(tmp_path, capsys) -> None:
    db = EmailDatabase(":memory:")
    override_path = tmp_path / "override.json"
    source_evidence_path = tmp_path / "source-evidence.json"
    override_path.write_text(json.dumps({"summary": "Human-reviewed chronology text."}), encoding="utf-8")
    source_evidence_path.write_text(json.dumps([{"source_id": "email:uid-1"}]), encoding="utf-8")

    args = type(
        "Args",
        (),
        {
            "workspace_id": "workspace:123",
            "target_type": "chronology_entry",
            "target_id": "CHR-001",
            "review_state": "human_verified",
            "override_json": str(override_path),
            "machine_json": None,
            "source_evidence_json": str(source_evidence_path),
            "reviewer": "reviewer@example.org",
            "review_notes": "Confirmed by human review.",
            "no_apply_on_refresh": False,
        },
    )()

    run_case_review_override_impl(lambda: db, args)
    data = json.loads(capsys.readouterr().out)
    assert data["workspace_id"] == "workspace:123"
    assert data["target_type"] == "chronology_entry"
    assert data["review_state"] == "human_verified"
    overrides = db.list_matter_review_overrides(workspace_id="workspace:123")
    assert overrides[0]["override_payload"]["summary"] == "Human-reviewed chronology text."
    db.close()


def test_run_case_review_snapshot_impl_updates_snapshot_review_state(capsys) -> None:
    db = EmailDatabase(":memory:")
    persist_result = db.persist_matter_snapshot(
        payload={
            "matter_workspace": {
                "workspace_id": "workspace:123",
                "matter": {"matter_id": "matter:123", "bundle_id": "bundle:123", "case_label": "Case A"},
            },
            "review_governance": {
                "review_state_counts": {
                    "machine_extracted": 1,
                    "human_verified": 0,
                    "disputed": 0,
                    "draft_only": 0,
                    "export_approved": 0,
                }
            },
            "matter_coverage_ledger": {"summary": {"coverage_status": "complete"}},
        },
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert persist_result is not None

    args = type(
        "Args",
        (),
        {
            "snapshot_id": persist_result["snapshot_id"],
            "review_state": "human_verified",
            "reviewer": "reviewer@example.org",
        },
    )()

    run_case_review_snapshot_impl(lambda: db, args)
    data = json.loads(capsys.readouterr().out)
    assert data["snapshot_id"] == persist_result["snapshot_id"]
    assert data["review_state"] == "human_verified"
    latest = db.latest_matter_snapshot(workspace_id="workspace:123")
    assert latest is not None
    assert latest["review_state"] == "human_verified"
    db.close()
