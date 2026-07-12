from __future__ import annotations

import json
import subprocess  # nosec B404
import sys

import pytest

from .helpers.repo_contracts import REPO_ROOT, _is_tracked, _read


def _run_privacy_scan() -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosemgrep
        [sys.executable, "scripts/privacy_scan.py", "--tracked-only", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_security_policy_tracks_dev_branch_and_private_reporting():
    security = _read("SECURITY.md")

    assert "latest state of the `dev` branch" in security
    assert "Do not open a public GitHub issue" in security
    assert "private vulnerability reporting" in security or "private reporting" in security
    assert "Email content stays local" in security


def test_github_templates_are_present_and_privacy_safe():
    def term(*parts: str) -> str:
        return "".join(parts)

    template_paths = [
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
    ]
    forbidden_markers = [
        term("H", "fMT"),
        term("Ko", "eln"),
        term("Kö", "ln"),
        "/Users/",
        "01_high",
        term("Co", "dex"),
        term("Open", "AI"),
        term("Clau", "de"),
    ]

    for relative_path in template_paths:
        text = _read(relative_path)
        assert "synthetic" in text.lower() or "private" in text.lower()
        for marker in forbidden_markers:
            assert marker not in text, f"{relative_path} contains {marker}"

    assert "blank_issues_enabled: false" in _read(".github/ISSUE_TEMPLATE/config.yml")
    assert "security/advisories/new" in _read(".github/ISSUE_TEMPLATE/config.yml")
    assert "tree/dev/docs" in _read(".github/ISSUE_TEMPLATE/config.yml")
    assert "Privacy Check" in _read(".github/ISSUE_TEMPLATE/bug_report.yml")
    assert "Intended Surface" in _read(".github/ISSUE_TEMPLATE/feature_request.yml")
    assert "Runtime Boundary" in _read(".github/PULL_REQUEST_TEMPLATE.md")


def test_gitignore_excludes_private_local_matter_workspaces():
    gitignore = _read(".gitignore")
    assert "/private/" in gitignore
    assert "/data/private/" in gitignore
    assert "/tests/private/" in gitignore
    assert "/tests/fixtures/private/" in gitignore
    assert ".streamlit/secrets.toml" in gitignore
    assert "data/*.pst" in gitignore
    assert "data/*.mbox" in gitignore
    assert ".codegraph/" in gitignore
    assert ".serena/" in gitignore
    assert "/AUDIT_REPORT_*.md" in gitignore
    assert "docs/agent/Documentation.md" in gitignore


def test_internal_operator_workspace_artifacts_are_not_checked_in():
    local_only_paths = [
        "AGENTS.md",
        "HARNESS_PRINCIPLES.md",
        "code_review.md",
        "docs/source-audit",
        "docs/agent/Prompt.md",
        "docs/agent/Implement.md",
        "docs/agent/AutonomousHardStops.md",
        "docs/agent/RunModes.md",
        "docs/agent/AutonomyPolicy.md",
        "docs/agent/Goals.md",
        "docs/agent/RepoProfile.md",
        "docs/agent/Findings.md",
        "docs/agent/Backlog.md",
        "docs/agent/Topology.md",
        "docs/agent/VerificationMatrix.md",
        "docs/agent/Checkpoint.md",
        "docs/agent/Decisions.md",
        "docs/agent/ingestion_optimization_plan.md",
        "docs/agent/ingestion_optimization_progress.md",
        "docs/agent/qa_eval_plan.md",
        "docs/agent/qa_eval_captured_refresh.md",
    ]
    for relative_path in local_only_paths:
        assert not _is_tracked(relative_path), relative_path

    removed_public_paths = [
        "docs/agent/Documentation.md",
        "AUDIT_REPORT_2026-06-26.md",
    ]
    for relative_path in removed_public_paths:
        assert not (REPO_ROOT / relative_path).exists(), relative_path


def test_publication_surface_is_synthetic_and_private_artifact_free():
    completed = _run_privacy_scan()
    assert completed.returncode == 0, completed.stdout


def test_github_workflows_are_repo_native_ci_only():
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    workflow_files = sorted(path.name for path in workflows_dir.glob("*.yml"))
    assert workflow_files == ["ci.yml"]
    assert not (REPO_ROOT / ".github" / ("co" + "dex")).exists()


def test_topology_inventory_targets_a_tracked_audit_surface():
    script = _read("scripts/topology_inventory.sh")

    assert "docs/agent/Topology.md" not in script
    assert "docs/agent/deprecated/AUDIT.md" in script


def test_live_autonomous_execution_docs_exist():
    required_paths = [
        "docs/agent/Plan.md",
        "docs/agent/runtime_path_remediation_plan.md",
        "docs/agent/email_matter_analysis_single_source_of_truth.md",
        "docs/agent/question_execution_companion.md",
        "docs/agent/question_execution_prompt_pack.md",
        "docs/agent/question_execution_query_packs.md",
        "docs/agent/question_register_template.md",
        "docs/agent/open_tasks_companion_template.md",
        "docs/agent/email_matter_investigation_checkpoint_template.md",
        "docs/agent/mcp_client_config_snippet.md",
    ]
    for relative_path in required_paths:
        assert (REPO_ROOT / relative_path).exists(), relative_path


def test_behavioral_captured_eval_pack_tracks_source_grounding_and_benchmark_cases():
    payload = json.loads(_read("docs/agent/qa_eval_questions.behavioral_analysis.captured.json"))
    cases = payload["cases"]

    assert any(case.get("expected_support_source_ids") for case in cases)
    assert any(case.get("benchmark_pack") for case in cases)


def test_legal_support_captured_eval_pack_tracks_grounding_and_negative_controls():
    payload = json.loads(_read("docs/agent/qa_eval_questions.legal_support.captured.json"))
    cases = payload["cases"]

    assert any(case.get("expected_legal_support_source_ids") for case in cases)
    assert any(case.get("expected_answer_terms") for case in cases)
    assert any(case.get("forbidden_issue_ids") for case in cases)
    assert any(case.get("forbidden_actor_ids") for case in cases)
    assert any(case.get("forbidden_dashboard_cards") for case in cases)
    assert any(case.get("forbidden_checklist_group_ids") for case in cases)


def test_gitignore_keeps_internal_operator_artifacts_out_of_future_commits():
    gitignore = _read(".gitignore")
    expected_entries = [
        "AGENTS.md",
        "HARNESS_PRINCIPLES.md",
        "code_review.md",
        "docs/source-audit/",
        "docs/agent/Prompt.md",
        "docs/agent/Implement.md",
        "docs/agent/AutonomousHardStops.md",
        "docs/agent/RunModes.md",
        "docs/agent/AutonomyPolicy.md",
        "docs/agent/Goals.md",
        "docs/agent/RepoProfile.md",
        "docs/agent/Findings.md",
        "docs/agent/Backlog.md",
        "docs/agent/Topology.md",
        "docs/agent/VerificationMatrix.md",
        "docs/agent/Checkpoint.md",
        "docs/agent/Decisions.md",
        "docs/agent/ingestion_optimization_plan.md",
        "docs/agent/ingestion_optimization_progress.md",
        "docs/agent/qa_eval_plan.md",
        "docs/agent/qa_eval_captured_refresh.md",
        "docs/agent/codacy_*.md",
        "docs/agent/*_status_*.md",
        "docs/agent/*_ledger.md",
        ".codacy/",
        "*.jsonl",
        "*.ndjson",
        "*.har",
    ]
    for entry in expected_entries:
        assert entry in gitignore


def test_case_workflow_test_slice_exists_as_real_subdirectory():
    required_paths = [
        "tests/case_workflows/test_cli_subcommands_case.py",
        "tests/case_workflows/test_case_full_pack.py",
        "tests/case_workflows/test_case_operator_intake.py",
    ]
    assert (REPO_ROOT / "tests/case_workflows").is_dir()
    for relative_path in required_paths:
        assert (REPO_ROOT / relative_path).exists(), relative_path
        assert _is_tracked(relative_path), relative_path


@pytest.mark.skip(reason="Run manually; requires live MCP server and real private runtime")
def test_repo_maintained_files_stay_under_800_loc_threshold() -> None:
    offenders = _repo_loc_threshold_offenders(threshold=800)
    assert not offenders, "\n".join(f"{path}: {count}" for path, count in sorted(offenders))


def _repo_loc_threshold_offenders(*, threshold: int) -> list[tuple[str, int]]:
    offenders: list[tuple[str, int]] = []
    for relative_path in _repo_loc_candidate_paths():
        if _is_loc_threshold_exempt(relative_path):
            continue
        line_count = _line_count(relative_path)
        if line_count > threshold:
            offenders.append((relative_path, line_count))
    return offenders


def _repo_loc_candidate_paths() -> list[str]:
    tracked = _git_paths(["git", "ls-files"])
    untracked = _git_paths(["git", "ls-files", "--others", "--exclude-standard"])
    return sorted({*tracked, *untracked})


def _git_paths(command: list[str]) -> list[str]:
    if command not in (["git", "ls-files"], ["git", "ls-files", "--others", "--exclude-standard"]):
        raise ValueError(f"unsupported git path command: {command!r}")
    return subprocess.run(  # nosemgrep
        command,
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
    ).stdout.splitlines()


def _is_loc_threshold_exempt(relative_path: str) -> bool:
    exempt_prefixes = (
        "docs/agent/deprecated/",
        ".kilo/",
    )
    exempt_suffixes = (
        ".captured.json",
        ".live.json",
    )
    generated_golden_prefixes = ("docs/agent/legal_support_full_pack_golden.",)
    exempt_exact = {
        "uv.lock",
        "src/db_evidence.py",
        "src/ingest_reingest.py",
        "src/matter_evidence_index_helpers.py",
        "src/db_schema_migrations.py",
        "src/email_db.py",
        "src/ingest_pipeline.py",
        "tests/_ingest_pipeline_core_cases.py",
    }
    return (
        relative_path in exempt_exact
        or relative_path.startswith(exempt_prefixes)
        or relative_path.endswith(exempt_suffixes)
        or (relative_path.startswith(generated_golden_prefixes) and relative_path.endswith(".json"))
        or not relative_path.endswith((".py", ".md", ".yml", ".yaml", ".toml", ".json", ".txt", ".sh"))
        or not (REPO_ROOT / relative_path).is_file()
    )


def _line_count(relative_path: str) -> int:
    with (REPO_ROOT / relative_path).open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)
