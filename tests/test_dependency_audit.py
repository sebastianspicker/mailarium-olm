"""Exports locked dependencies through an isolated cache and fails closed when tracked locks cannot be reproduced."""

from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace

from scripts import dependency_audit


def test_only_current_documented_vulnerability_is_ignored() -> None:
    assert dependency_audit.IGNORED_VULNS == ("PYSEC-2026-597",)


def test_locked_export_uses_an_isolated_uv_cache(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dependency_audit.shutil, "which", lambda command: "/usr/bin/uv")
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(dependency_audit.subprocess, "run", fake_run)
    output_path = tmp_path / "requirements.locked.txt"

    assert dependency_audit._export_locked_requirements(output_path)
    assert "--locked" in observed["command"]
    extra_flags = [observed["command"][index + 1] for index, value in enumerate(observed["command"]) if value == "--extra"]
    assert extra_flags == list(dependency_audit.AUDITED_EXTRAS)
    assert observed["command"][-1] == str(output_path)
    assert observed["env"]["UV_CACHE_DIR"] == str(tmp_path / "uv-cache")


def test_audited_extras_have_representative_release_dependencies() -> None:
    project_config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    optional_dependencies = project_config["project"]["optional-dependencies"]
    representative_dependencies = {
        "nlp": "spacy==3.8.13",
        "image": "torchvision==0.28.0",
        "training": "datasets==5.0.0",
        "ews-ntlm": "requests-ntlm>=1.3.0,<2",
    }

    assert tuple(representative_dependencies) == dependency_audit.AUDITED_EXTRAS
    for extra, dependency in representative_dependencies.items():
        assert dependency in optional_dependencies[extra]


def test_locked_export_is_unavailable_without_uv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dependency_audit.shutil, "which", lambda command: None)

    assert not dependency_audit._export_locked_requirements(tmp_path / "requirements.locked.txt")


def test_main_fails_closed_when_tracked_lock_cannot_be_exported(tmp_path: Path, monkeypatch, capsys) -> None:
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dependency_audit, "_export_locked_requirements", lambda _path: False)

    assert dependency_audit.main([]) == 2
    assert "regenerate the lockfile" in capsys.readouterr().err
