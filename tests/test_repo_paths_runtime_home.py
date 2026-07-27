"""Exercises runtime-home resolution for checkout and installed-package deployments.

It requires absolute overrides and avoids defaulting writable state into the package tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import mailarium.repo_paths as repo_paths


def test_runtime_home_uses_checkout_root_without_an_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    (checkout / ".git").mkdir()
    monkeypatch.setattr(repo_paths, "repo_root", lambda: checkout)
    monkeypatch.delenv("MAILARIUM_RUNTIME_HOME", raising=False)

    assert repo_paths.runtime_home() == checkout.resolve()
    assert repo_paths.validate_runtime_path("data/email_metadata.db") == (checkout / "data/email_metadata.db").resolve()


def test_installed_package_relative_paths_use_explicit_runtime_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asset_root = tmp_path / "site-packages"
    (asset_root / "mailarium").mkdir(parents=True)
    runtime = tmp_path / "operator-data"
    monkeypatch.setattr(repo_paths, "repo_root", lambda: asset_root)
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime))

    assert repo_paths.runtime_home() == runtime.resolve()
    assert repo_paths.validate_runtime_path("data/vector-index") == (runtime / "data/vector-index").resolve()
    assert not repo_paths.validate_runtime_path("data/vector-index").is_relative_to(asset_root)


def test_installed_package_default_runtime_home_is_outside_package_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asset_root = tmp_path / "site-packages"
    (asset_root / "mailarium").mkdir(parents=True)
    monkeypatch.setattr(repo_paths, "repo_root", lambda: asset_root)
    monkeypatch.delenv("MAILARIUM_RUNTIME_HOME", raising=False)
    monkeypatch.setattr(repo_paths, "_platform_runtime_home", lambda: tmp_path / "user-data")

    runtime_path = repo_paths.validate_runtime_path("data/email_metadata.db")

    assert runtime_path == (tmp_path / "user-data" / "data/email_metadata.db").resolve()
    assert not runtime_path.is_relative_to(asset_root)


def test_runtime_home_requires_an_absolute_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", "relative-runtime")

    with pytest.raises(ValueError, match="must be an absolute path"):
        repo_paths.runtime_home()


@pytest.mark.parametrize(
    ("legacy_name", "replacement"),
    (
        ("EMAIL_RAG_RUNTIME_HOME", "MAILARIUM_RUNTIME_HOME"),
        ("EMAIL_RAG_ALLOWED_OUTPUT_ROOTS", "MAILARIUM_ALLOWED_OUTPUT_ROOTS"),
        ("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", "MAILARIUM_ALLOWED_LOCAL_READ_ROOTS"),
        ("EMAIL_RAG_ALLOWED_RUNTIME_ROOTS", "MAILARIUM_ALLOWED_RUNTIME_ROOTS"),
    ),
)
def test_removed_environment_variables_fail_with_migration_guidance(
    monkeypatch: pytest.MonkeyPatch,
    legacy_name: str,
    replacement: str,
) -> None:
    monkeypatch.setenv(legacy_name, "/tmp/legacy-mailarium-test")

    with pytest.raises(ValueError, match=rf"^{legacy_name} was removed in 0\.5; use {replacement}$"):
        repo_paths.runtime_home()


def test_platform_runtime_home_uses_mailarium_application_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(repo_paths.sys, "platform", "darwin")

    assert repo_paths._platform_runtime_home() == tmp_path / "Library" / "Application Support" / "mailarium"
