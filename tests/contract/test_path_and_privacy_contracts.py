"""Configured root containment and repository privacy policy contracts."""

from __future__ import annotations

import pytest

from mailarium.platform.repo_paths import (
    allowed_local_read_roots,
    allowed_output_roots,
    allowed_runtime_roots,
    validate_output_path,
    validate_runtime_path,
)
from mailarium.privacy.privacy_scan_rules import TRACKED_FORBIDDEN_PATH_PATTERNS, path_matches


def test_runtime_paths_are_absolute_contained_by_the_configured_root(monkeypatch, tmp_path) -> None:
    root = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(root))
    monkeypatch.delenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", raising=False)

    assert validate_runtime_path("archive/mailarium.db") == root / "archive" / "mailarium.db"
    assert validate_runtime_path(str(root / "vectors")) == root / "vectors"


@pytest.mark.parametrize("value", ["../outside.db", "\x00invalid", "/tmp/not-mailarium.db"])
def test_runtime_paths_reject_traversal_invalid_or_outside_targets(monkeypatch, tmp_path, value: str) -> None:
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(tmp_path / "runtime"))
    monkeypatch.delenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", raising=False)

    with pytest.raises(ValueError):
        validate_runtime_path(value)


def test_output_paths_reject_tracked_repository_targets() -> None:
    with pytest.raises(ValueError, match="Output path"):
        validate_output_path("README.md")


@pytest.mark.parametrize(
    ("environment_name", "resolver"),
    [
        ("MAILARIUM_ALLOWED_OUTPUT_ROOTS", allowed_output_roots),
        ("MAILARIUM_ALLOWED_LOCAL_READ_ROOTS", allowed_local_read_roots),
        ("MAILARIUM_ALLOWED_RUNTIME_ROOTS", allowed_runtime_roots),
    ],
)
def test_configured_allowed_roots_must_be_absolute(monkeypatch, environment_name, resolver, tmp_path) -> None:
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(tmp_path / "runtime"))
    monkeypatch.setenv(environment_name, "relative-root")

    with pytest.raises(ValueError, match="absolute paths"):
        resolver()


def test_privacy_rules_allow_only_reviewed_codacy_configuration_paths() -> None:
    for path in (".codacy/codacy.config.json", ".codacy/codacy.yaml", ".codacy/codacy.yml"):
        assert not path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS)

    for path in (".codacy/private.json", ".agents/session.json", ".codex/config.toml"):
        assert path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS)


@pytest.mark.parametrize(
    "path",
    [
        ".env.production",
        "config/live.env",
        ".mcp/private-key",
        "config/secrets.toml",
        "config/credentials.json",
        "certificates/client.pem",
    ],
)
def test_privacy_rules_reject_local_credentials_and_secret_configuration(path: str) -> None:
    assert path_matches(path, TRACKED_FORBIDDEN_PATH_PATTERNS)
