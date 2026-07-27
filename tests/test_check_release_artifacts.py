"""Validates release archives contain the expected versioned templates and reject private or incomplete payloads."""

from __future__ import annotations

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "check_release_artifacts.py"
SPEC = importlib.util.spec_from_file_location("check_release_artifacts", SCRIPT_PATH)
assert SPEC and SPEC.loader
release_artifacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_artifacts)


REQUIRED = {"mailarium/templates/report.html", "mailarium/templates/dossier/footer.html"}


def _wheel(path: Path, *, version: str = "0.2.0", members: set[str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mailarium-0.2.0.dist-info/METADATA", f"Metadata-Version: 2.1\nVersion: {version}\n")
        for member in members or REQUIRED:
            archive.writestr(member, "template")
    return path


def _sdist(path: Path, *, version: str = "0.2.0", members: set[str] | None = None) -> Path:
    prefix = "mailarium-0.2.0"
    with tarfile.open(path, "w:gz") as archive:
        contents = f"Metadata-Version: 2.1\nVersion: {version}\n".encode()
        info = tarfile.TarInfo(f"{prefix}/PKG-INFO")
        info.size = len(contents)
        archive.addfile(info, io.BytesIO(contents))
        for member in members or REQUIRED:
            contents = b"template"
            info = tarfile.TarInfo(f"{prefix}/{member}")
            info.size = len(contents)
            archive.addfile(info, io.BytesIO(contents))
    return path


def test_accepts_wheel_with_expected_version_and_templates(tmp_path: Path) -> None:
    errors = release_artifacts.validate_artifact(_wheel(tmp_path / "package.whl"), version="0.2.0", required_templates=REQUIRED)

    assert errors == []


def test_accepts_sdist_with_top_level_prefix(tmp_path: Path) -> None:
    errors = release_artifacts.validate_artifact(
        _sdist(tmp_path / "package.tar.gz"), version="0.2.0", required_templates=REQUIRED
    )

    assert errors == []


def test_reports_missing_template_and_version_mismatch(tmp_path: Path) -> None:
    errors = release_artifacts.validate_artifact(
        _wheel(tmp_path / "package.whl", version="0.1.0", members={"mailarium/templates/report.html"}),
        version="0.2.0",
        required_templates=REQUIRED,
    )

    assert any("metadata version '0.1.0'" in error for error in errors)
    assert any("mailarium/templates/dossier/footer.html" in error for error in errors)


def test_reports_private_and_agent_workspace_members(tmp_path: Path) -> None:
    members = REQUIRED | {
        "docs/agent/Plan.md",
        ".agents/state.json",
        "archive/local/source-snapshots/ews-inbox-assistant/private/state.json",
        "docs/audit/findings.json",
        "pre-clean/ews-inbox-assistant/private/state.json",
    }
    errors = release_artifacts.validate_artifact(
        _sdist(tmp_path / "package.tar.gz", members=members), version="0.2.0", required_templates=REQUIRED
    )

    assert len(errors) == 1
    assert "docs/agent/Plan.md" in errors[0]
    assert ".agents/state.json" in errors[0]
    assert "archive/local/source-snapshots/ews-inbox-assistant/private/state.json" in errors[0]
    assert "docs/audit/findings.json" in errors[0]
    assert "pre-clean/ews-inbox-assistant/private/state.json" in errors[0]


def test_cli_returns_nonzero_and_explains_validation_failure(tmp_path: Path, capsys) -> None:
    artifact = _wheel(tmp_path / "package.whl", members={"mailarium/templates/report.html"})

    assert release_artifacts.main([str(artifact)]) == 1

    assert "Release artifact validation failed:" in capsys.readouterr().err


def test_cli_accepts_release_directory_and_ignores_support_files(tmp_path: Path, monkeypatch, capsys) -> None:
    _wheel(tmp_path / "package.whl")
    _sdist(tmp_path / "package.tar.gz")
    (tmp_path / "requirements.locked.txt").write_text("example==1.0\n", encoding="utf-8")
    (tmp_path / "SHA256SUMS").write_text("synthetic checksum fixture\n", encoding="utf-8")
    monkeypatch.setattr(release_artifacts, "expected_version", lambda: "0.2.0")
    monkeypatch.setattr(release_artifacts, "required_template_paths", lambda: REQUIRED)

    assert release_artifacts.main([str(tmp_path)]) == 0
    assert "passed for 2 artifact(s)" in capsys.readouterr().out


def test_cli_requires_frozen_constraints_for_release_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    _wheel(tmp_path / "package.whl")
    _sdist(tmp_path / "package.tar.gz")
    monkeypatch.setattr(release_artifacts, "expected_version", lambda: "0.2.0")
    monkeypatch.setattr(release_artifacts, "required_template_paths", lambda: REQUIRED)

    assert release_artifacts.main([str(tmp_path)]) == 1
    assert "missing requirements.locked.txt" in capsys.readouterr().err


def test_cli_requires_wheel_and_sdist(tmp_path: Path, monkeypatch, capsys) -> None:
    wheel = _wheel(tmp_path / "package.whl")
    monkeypatch.setattr(release_artifacts, "expected_version", lambda: "0.2.0")
    monkeypatch.setattr(release_artifacts, "required_template_paths", lambda: REQUIRED)

    assert release_artifacts.main([str(wheel)]) == 1
    assert "missing a source distribution" in capsys.readouterr().err


def test_cli_rejects_duplicate_release_archives(tmp_path: Path, monkeypatch, capsys) -> None:
    _wheel(tmp_path / "package-one.whl")
    _wheel(tmp_path / "package-two.whl")
    _sdist(tmp_path / "package-one.tar.gz")
    _sdist(tmp_path / "package-two.tar.gz")
    (tmp_path / "requirements.locked.txt").write_text("example==1.0\n", encoding="utf-8")
    monkeypatch.setattr(release_artifacts, "expected_version", lambda: "0.2.0")
    monkeypatch.setattr(release_artifacts, "required_template_paths", lambda: REQUIRED)

    assert release_artifacts.main([str(tmp_path)]) == 1
    errors = capsys.readouterr().err
    assert "exactly one wheel; found 2" in errors
    assert "exactly one source distribution; found 2" in errors
