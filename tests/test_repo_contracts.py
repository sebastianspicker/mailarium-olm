from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_env_example_includes_analytics_timezone():
    env_example = _read(".env.example")
    assert "ANALYTICS_TIMEZONE=" in env_example
    assert "RUNTIME_PROFILE=" in env_example
    assert "EMBEDDING_LOAD_MODE=" in env_example


def test_readme_install_flow_includes_package_install_for_console_scripts():
    readme = _read("README.md")
    assert "pip install -e ." in readme
    assert "docs/RUNTIME_TUNING.md" in readme
    assert "RUNTIME_PROFILE=quality" in readme
    assert "# RERANK_ENABLED=false" in readme
    assert "# HYBRID_ENABLED=false" in readme
    assert "# SPARSE_ENABLED=false" in readme
    assert "# COLBERT_RERANK_ENABLED=false" in readme


def test_env_example_uses_profile_first_quality_setup():
    env_example = _read(".env.example")
    assert "RUNTIME_PROFILE=quality" in env_example
    assert "# SPARSE_ENABLED=true" in env_example
    assert "# COLBERT_RERANK_ENABLED=true" in env_example
    assert "# RERANK_ENABLED=true" in env_example
    assert "# HYBRID_ENABLED=true" in env_example


def test_readme_does_not_hardcode_test_count_badge():
    readme = _read("README.md")
    assert not re.search(r"badge/tests-\d+", readme)
    assert "tests (2147+)" not in readme


def test_readme_privacy_note_matches_first_run_download_boundary():
    readme = _read("README.md")
    assert "No API calls, no data leaves your machine." not in readme
    assert "Email content stays local" in readme
    assert "Hugging Face" in readme


def test_topic_surfaces_are_demoted_from_stable_contract():
    readme = _read("README.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")

    assert "default ingest workflow does not populate topic tables yet" in readme
    assert "Conditional Topic Surface" in compatibility
    assert "excluded from the stable `0.1.x` compatibility contract" in compatibility


def test_cli_reference_leads_with_subcommands_before_legacy_flags():
    cli_reference = _read("docs/CLI_REFERENCE.md")
    assert "## Subcommands (recommended)" in cli_reference
    assert "## Legacy Flat-Flag Reference" in cli_reference
    assert cli_reference.index("## Subcommands (recommended)") < cli_reference.index("## Legacy Flat-Flag Reference")
    assert "python -m src.cli search" in cli_reference
    assert "python -m src.cli --query" not in cli_reference


def test_diagnostics_docs_describe_resolved_runtime_summary():
    readme = _read("README.md")
    mcp_tools = _read("docs/MCP_TOOLS.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")

    assert "shows resolved runtime settings, embedder/backend state, MCP budgets, and sparse-index status" in readme
    assert "resolved runtime profile/load mode/device/batch size" in mcp_tools
    assert "current embedder backend state" in mcp_tools
    assert "resolved runtime settings" in compatibility
    assert "current embedder/backend state" in compatibility


def test_source_audit_repo_profile_has_no_stale_open_phase1_followups():
    repo_profile = _read("docs/source-audit/repo-profile.md")
    assert "SA-024" not in repo_profile
    assert "SA-026" not in repo_profile
    assert "three new phase-1 follow-ups are open" not in repo_profile
    assert "## Phase-1 rerun note" not in repo_profile
    assert "no currently open phase-1 follow-ups remain" in repo_profile


def test_source_audit_workspace_notes_are_synchronized():
    findings = _read("docs/source-audit/findings-index.md")
    verification = _read("docs/source-audit/verification-matrix.md")
    readme_companion = _read("docs/source-audit/files/README.md.md")
    stale_residual_risk = (
        "Residual risk: the current workspace still uses a Python 3.13 environment "
        "whose full coverage suite aborts in an unrelated clustering test"
    )

    assert "| SA-025 | low | high | verified |" in findings
    assert "| SA-026 | low | high | verified |" in findings
    assert "| SA-027 | low | high | verified |" in findings
    assert "condensed README MCP diagnostics summary can still drift" not in verification
    assert "Remaining drift risk is now concentrated in internal audit-workspace notes" in verification
    assert stale_residual_risk not in readme_companion
    assert "Later remediation rounds completed the full local acceptance matrix successfully" in readme_companion


def test_acceptance_matrix_tracks_ci_contracts():
    acceptance = _read("scripts/run_acceptance_matrix.sh")
    ci = _read(".github/workflows/ci.yml")

    expected_checks = [
        "python -m ruff check .",
        "python -m ruff format --check .",
        "python -m mypy src",
        "python -m pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80",
        "python -m bandit -r src -q -ll -ii",
        "python -m pip_audit -r requirements.txt --ignore-vuln CVE-2026-4539",
        "python scripts/streamlit_smoke.py",
    ]

    for check in expected_checks:
        assert check in acceptance
    for check in [
        "ruff check .",
        "ruff format --check .",
        "mypy src",
        "pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80",
        "bandit -r src -q -ll -ii",
        "python -m pip_audit -r requirements.txt --ignore-vuln CVE-2026-4539",
        "python scripts/streamlit_smoke.py",
    ]:
        assert check in ci

    assert "Skipping in local profile because pypi.org is unreachable from this environment." in acceptance
