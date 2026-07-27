"""Ensures CI acceptance commands and local runtime-maintenance scripts match the current repository topology.

It keeps optional private runtime state separate from tracked release requirements.
"""

from __future__ import annotations

import pytest

from .helpers.repo_contracts import REPO_ROOT, _read


def test_acceptance_matrix_matches_current_ci_gates() -> None:
    acceptance = _read("scripts/run_acceptance_matrix.sh")
    ci = _read(".github/workflows/ci.yml")

    for command in (
        "ruff check .",
        "ruff format --check .",
        "mypy mailarium",
        "pytest -q --tb=short --cov=mailarium --cov-report=term-missing --cov-fail-under=80",
        "python scripts/streamlit_smoke.py",
        "bandit -r mailarium -q -ll -ii",
        "python scripts/dependency_audit.py",
    ):
        assert command in acceptance
        assert command in ci

    assert "scripts/refresh_qa_eval_captured_reports.py --check" in acceptance
    assert "LEGAL_DOMAIN_PACK_ENABLED" not in acceptance
    assert "wave_workflow_smoke.py" not in acceptance


def test_acceptance_matrix_exposes_release_profile() -> None:
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "Usage: bash scripts/run_acceptance_matrix.sh [local|ci|release]" in acceptance
    assert "Running release profile. Dependency audit is required and may not be skipped." in acceptance
    assert "Release profile requires a real dependency-audit result" in acceptance


def test_runtime_hygiene_scripts_preserve_sources_and_purge_derived_state() -> None:
    gitignore = _read(".gitignore")
    clean_workspace = _read("scripts/clean_workspace.sh")
    clean_ingest = _read("scripts/clean_ingest_reset.sh")

    assert "*.db-wal" in gitignore
    assert "*.db-shm" in gitignore
    assert "./private/runtime/*" in clean_workspace
    assert "private/files/" in clean_ingest
    assert "private/context.md" in clean_ingest
    assert "private/ingest/" in clean_ingest
    assert "private/runtime/current" in clean_ingest
    assert "private/tests/results" in clean_ingest
    assert "--dry-run" in clean_ingest
    assert "--yes" in clean_ingest
    assert "Source inputs preserved" in clean_ingest


def test_private_runtime_launcher_targets_current_storage_layout() -> None:
    launcher = _read("scripts/private_runtime_current_env.sh")

    assert "set -euo pipefail" in launcher
    assert 'vector_index_path="${runtime_root}/vector-index"' in launcher
    assert 'sqlite_path="${runtime_root}/email_metadata.db"' in launcher
    assert "VECTOR_INDEX_PATH" in launcher
    assert "SQLITE_PATH" in launcher
    assert 'exec "$@"' in launcher


def test_private_runtime_current_topology_is_optional_local_state() -> None:
    current = REPO_ROOT / "private/runtime/current"
    if not current.exists():
        pytest.skip("local private runtime not present")
    assert current.is_dir() or current.is_symlink()
