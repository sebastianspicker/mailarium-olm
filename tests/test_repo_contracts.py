from __future__ import annotations

from pathlib import Path

import pytest

from .helpers.repo_contracts import REPO_ROOT, _read


def test_acceptance_matrix_tracks_ci_contracts():
    acceptance = _read("scripts/run_acceptance_matrix.sh")
    ci = _read(".github/workflows/ci.yml")

    expected_checks = [
        "python -m ruff check .",
        "python -m ruff format --check .",
        "python -m mypy src",
        "python -m pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80",
        "tests/test_bm25_index_extended.py::TestBuildFromCollection::test_multi_batch_collection -W error::ResourceWarning",
        "python -m bandit -r src -q -ll -ii",
        "python scripts/dependency_audit.py",
        "python scripts/streamlit_smoke.py",
    ]

    for check in expected_checks:
        assert check in acceptance
    for check in [
        "ruff check .",
        "ruff format --check .",
        "mypy src",
        "pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80",
        "python scripts/wave_workflow_smoke.py",
        "bandit -r src -q -ll -ii",
        "python scripts/dependency_audit.py",
        "python scripts/streamlit_smoke.py",
    ]:
        assert check in ci
    assert "python scripts/refresh_qa_eval_captured_reports.py --check" not in ci

    assert 'python_bin="${PYTHON_BIN:-}"' in acceptance
    assert 'if [[ -x ".venv/bin/python" ]]; then' in acceptance
    assert 'python_bin=".venv/bin/python"' in acceptance
    assert "RUNTIME_PROFILE=offline-test" in acceptance
    assert "EMBEDDING_LOAD_MODE=local_only" in acceptance
    assert "DISABLE_SAFETENSORS_CONVERSION=1" in acceptance
    assert "SPACY_AUTO_DOWNLOAD_DURING_INGEST=0" in acceptance
    assert "Skipping in local profile because pypi.org is unreachable from this environment." in acceptance


def test_acceptance_matrix_exposes_release_profile_with_required_dependency_audit():
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "Usage: bash scripts/run_acceptance_matrix.sh [local|ci|release]" in acceptance
    assert "Running release profile. Dependency audit is required and may not be skipped." in acceptance
    expected = "Release profile requires a real dependency-audit result, but pypi.org is unreachable from this environment."
    assert expected in acceptance


def test_acceptance_matrix_ruff_contract_uses_python_module_invocation_only() -> None:
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "python -m ruff check ." in acceptance
    assert "python -m ruff format --check ." in acceptance
    assert "require_command ruff" not in acceptance


def test_acceptance_matrix_runs_campaign_workflow_smoke():
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "Campaign workflow smoke (python scripts/wave_workflow_smoke.py)" in acceptance
    assert "scripts/wave_workflow_smoke.py" in acceptance


def test_runtime_hygiene_contracts_protect_private_runtime_and_sqlite_sidecars():
    gitignore = _read(".gitignore")
    clean_workspace = _read("scripts/clean_workspace.sh")
    clean_ingest_reset = _read("scripts/clean_ingest_reset.sh")
    operations = _read("docs/README_USAGE_AND_OPERATIONS.md")
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "*.db-wal" in gitignore
    assert "*.db-shm" in gitignore
    assert "./private/runtime/*" in clean_workspace
    assert "./private/tests/results/*" in clean_workspace
    assert "private/files" in clean_ingest_reset
    assert "private/matter.md" in clean_ingest_reset
    assert "private/ingest/my-export.olm" in clean_ingest_reset
    assert "private/tests/materials" in clean_ingest_reset
    assert "private/tests/results" in clean_ingest_reset
    assert "private/tests/exports" in clean_ingest_reset
    assert "private/runtime/current" in clean_ingest_reset
    assert "--dry-run" in clean_ingest_reset
    assert "--yes" in clean_ingest_reset
    assert "scripts/clean_ingest_reset.sh" in operations
    assert "Ingest smoke (reports native vs fallback runtime)" in acceptance


def test_private_runtime_launcher_targets_current_runtime():
    launcher = _read("scripts/private_runtime_current_env.sh")

    assert "set -euo pipefail" in launcher
    assert "private/runtime/current" in launcher
    assert 'chromadb_path="${runtime_root}/chromadb"' in launcher
    assert 'sqlite_path="${runtime_root}/email_metadata.db"' in launcher
    assert "CHROMADB_PATH" in launcher
    assert "SQLITE_PATH" in launcher
    assert 'exec "$@"' in launcher


def test_private_runtime_current_topology_matches_live_layout():
    runtime_root = REPO_ROOT / "private/runtime"
    current = runtime_root / "current"
    baseline_run = runtime_root / "runs/baseline-p73-2026-04-17"
    legacy_run = runtime_root / "runs/live-default-legacy-2026-04-17"

    if not current.exists():
        pytest.skip("local private runtime not present")

    if not current.is_symlink():
        pytest.skip("local private runtime is not wired to the expected symlink topology")

    assert current.is_symlink()
    assert current.readlink() == Path("runs/baseline-p73-2026-04-17")

    baseline_chromadb = baseline_run / "chromadb"
    baseline_sqlite = baseline_run / "email_metadata.db"
    assert baseline_run.is_dir()
    assert baseline_chromadb.is_dir()
    assert not baseline_chromadb.is_symlink()
    assert baseline_sqlite.is_file()
    assert not baseline_sqlite.is_symlink()

    chromadb_alias = runtime_root / "chromadb_p73"
    sqlite_alias = runtime_root / "email_metadata_p73.db"
    assert chromadb_alias.is_symlink()
    assert chromadb_alias.readlink() == Path("runs/baseline-p73-2026-04-17/chromadb")
    assert sqlite_alias.is_symlink()
    assert sqlite_alias.readlink() == Path("runs/baseline-p73-2026-04-17/email_metadata.db")

    legacy_chromadb = legacy_run / "chromadb"
    legacy_sqlite = legacy_run / "email_metadata.db"
    assert legacy_chromadb.is_symlink()
    assert legacy_chromadb.readlink() == Path("../../chromadb")
    assert legacy_sqlite.is_symlink()
    assert legacy_sqlite.readlink() == Path("../../email_metadata.db")


def test_local_results_workspace_contract_uses_active_manifest():
    local_results_path = REPO_ROOT / "private/tests/results/README.local.md"
    if not local_results_path.exists():
        pytest.skip("local results workspace not present")

    local_results = local_results_path.read_text(encoding="utf-8")
    runbook = _read("docs/agent/email_matter_analysis_single_source_of_truth.md")
    prompt_pack = _read("docs/agent/question_execution_prompt_pack.md")

    assert "active_run.json" in local_results
    assert "refresh-active-run" in local_results
    assert "archive-results" in local_results
    assert "_archive/" in local_results
    assert "curation.status" in local_results
    assert "execute-wave" in local_results
    assert "execute-all-waves" in local_results
    assert "active_run.json" in runbook
    assert "curation.status" in runbook
    assert "refresh-active-run" in runbook
    assert "execute-wave" in runbook
    assert "active_run.json" in prompt_pack
    assert "curation.status" in prompt_pack
    assert "refresh-active-run" in prompt_pack
