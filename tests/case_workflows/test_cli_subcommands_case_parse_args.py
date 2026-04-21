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


def test_case_analyze_parse_args() -> None:
    args = parse_args(["case", "analyze", "--input", "case.json", "--output", "report.json"])
    assert args.subcommand == "case"
    assert args.case_action == "analyze"
    assert args.input == "case.json"
    assert args.output == "report.json"
    assert args.format == "json"


def test_case_analyze_rejects_unsupported_text_format() -> None:
    with pytest.raises(SystemExit):
        parse_args(["case", "analyze", "--input", "case.json", "--format", "text"])


def test_case_counsel_pack_parse_args() -> None:
    args = parse_args(
        [
            "case",
            "counsel-pack",
            "--case-scope",
            "scope.json",
            "--materials-dir",
            "matter",
            "--output",
            "handoff.zip",
        ]
    )
    assert args.subcommand == "case"
    assert args.case_action == "counsel-pack"
    assert args.case_scope == "scope.json"
    assert args.materials_dir == "matter"
    assert args.output == "handoff.zip"
    assert args.delivery_target == "counsel_handoff_bundle"
    assert args.delivery_format == "bundle"
    assert args.output_language == "de"
    assert args.translation_mode == "source_only"
    assert args.allow_blocked_exit_zero is False


def test_case_prompt_preflight_parse_args() -> None:
    args = parse_args(["case", "prompt-preflight", "--input", "matter.md", "--output-language", "de"])
    assert args.subcommand == "case"
    assert args.case_action == "prompt-preflight"
    assert args.input == "matter.md"
    assert args.output_language == "de"


def test_case_execute_wave_parse_args() -> None:
    args = parse_args(
        ["case", "execute-wave", "--input", "case.json", "--wave", "5A", "--output", "wave.json", "--scan-id-prefix", "run-1"]
    )
    assert args.subcommand == "case"
    assert args.case_action == "execute-wave"
    assert args.input == "case.json"
    assert args.wave == "5A"
    assert args.output == "wave.json"
    assert args.scan_id_prefix == "run-1"


def test_case_execute_all_waves_parse_args() -> None:
    args = parse_args(["case", "execute-all-waves", "--input", "case.json", "--include-payloads", "--scan-id-prefix", "batch-1"])
    assert args.subcommand == "case"
    assert args.case_action == "execute-all-waves"
    assert args.input == "case.json"
    assert args.include_payloads is True
    assert args.scan_id_prefix == "batch-1"


def test_case_gather_evidence_parse_args() -> None:
    args = parse_args(
        [
            "case",
            "gather-evidence",
            "--input",
            "case.json",
            "--run-id",
            "investigation_2026-04-16_P60",
            "--phase-id",
            "P60",
            "--output",
            "harvest.json",
        ]
    )
    assert args.subcommand == "case"
    assert args.case_action == "gather-evidence"
    assert args.input == "case.json"
    assert args.run_id == "investigation_2026-04-16_P60"
    assert args.phase_id == "P60"
    assert args.output == "harvest.json"


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--harvest-limit-per-wave", "0"),
        ("--harvest-limit-per-wave", "51"),
        ("--promote-limit-per-wave", "-1"),
        ("--promote-limit-per-wave", "21"),
    ],
)
def test_case_gather_evidence_rejects_invalid_shared_limit_bounds(flag: str, value: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "case",
                "gather-evidence",
                "--input",
                "case.json",
                "--run-id",
                "investigation_2026-04-16_P60",
                "--phase-id",
                "P60",
                flag,
                value,
            ]
        )


def test_case_review_status_parse_args() -> None:
    args = parse_args(["case", "review-status", "--workspace-id", "workspace:123"])
    assert args.subcommand == "case"
    assert args.case_action == "review-status"
    assert args.workspace_id == "workspace:123"


def test_case_review_override_parse_args() -> None:
    args = parse_args(
        [
            "case",
            "review-override",
            "--workspace-id",
            "workspace:123",
            "--target-type",
            "chronology_entry",
            "--target-id",
            "CHR-001",
            "--review-state",
            "human_verified",
        ]
    )
    assert args.case_action == "review-override"
    assert args.target_type == "chronology_entry"
    assert args.target_id == "CHR-001"
    assert args.review_state == "human_verified"
    assert args.no_apply_on_refresh is False


def test_case_review_snapshot_parse_args() -> None:
    args = parse_args(["case", "review-snapshot", "--snapshot-id", "snapshot:123", "--review-state", "human_verified"])
    assert args.case_action == "review-snapshot"
    assert args.snapshot_id == "snapshot:123"
    assert args.review_state == "human_verified"


def test_case_refresh_active_run_parse_args() -> None:
    args = parse_args(
        [
            "case",
            "refresh-active-run",
            "--matter-id",
            "matter:123",
            "--run-id",
            "investigation_2026-04-16_P40",
            "--phase-id",
            "P40",
            "--active-checkpoint",
            "_checkpoints/run.md",
            "--active-result-path",
            "03_exhaustive_run/report.json",
        ]
    )
    assert args.case_action == "refresh-active-run"
    assert args.results_root == "private/tests/results"
    assert args.matter_id == "matter:123"
    assert args.run_id == "investigation_2026-04-16_P40"
    assert args.phase_id == "P40"
    assert args.active_checkpoint == "_checkpoints/run.md"
    assert args.active_result_paths == ["03_exhaustive_run/report.json"]


def test_case_archive_results_parse_args() -> None:
    args = parse_args(
        [
            "case",
            "archive-results",
            "--archive-label",
            "superseded_run",
            "--path",
            "03_exhaustive_run/report.json",
        ]
    )
    assert args.case_action == "archive-results"
    assert args.results_root == "private/tests/results"
    assert args.archive_label == "superseded_run"
    assert args.relative_paths == ["03_exhaustive_run/report.json"]


def test_case_full_pack_parse_args() -> None:
    args = parse_args(["case", "full-pack", "--prompt", "matter.md", "--materials-dir", "matter", "--output", "draft.json"])
    assert args.subcommand == "case"
    assert args.case_action == "full-pack"
    assert args.prompt == "matter.md"
    assert args.materials_dir == "matter"
    assert args.output == "draft.json"
    assert args.output_language == "de"
    assert args.translation_mode == "source_only"
    assert args.default_source_scope == "emails_and_attachments"
    assert args.assume_date_to_today is True
    assert args.delivery_target == "counsel_handoff_bundle"
    assert args.delivery_format == "bundle"
    assert args.compile_only is False
    assert args.allow_blocked_exit_zero is False
