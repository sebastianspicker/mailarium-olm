"""CI composes one PR gate with package checks while local release remains complete."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts import verify


def test_ci_package_profile_requires_successful_pr_gate(monkeypatch) -> None:
    jobs = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())["jobs"]
    package_job = jobs["release-package"]
    assert package_job["needs"] == "pull-request"
    assert any(step.get("run", "").endswith("scripts/verify.py package") for step in package_job["steps"])
    assert any(step.get("run", "").endswith("scripts/verify.py release") for step in jobs["supported-macos-smoke"]["steps"])
    operations = []
    monkeypatch.setattr(verify, "_run", lambda label, *_args, **_kwargs: operations.append(label))
    monkeypatch.setattr(verify, "_run_pull_request", lambda: operations.append("pr"))
    monkeypatch.setattr(verify, "_build_release_artifacts", lambda: operations.append("build"))
    monkeypatch.setattr(verify, "_run_installed_wheel_smoke", lambda: operations.append("installed"))
    assert verify.main(["package"]) == 0
    assert operations == ["Check lockfile", "Streamlit AppTest smoke", "build", "installed"]
    operations.clear()
    assert verify.main(["release"]) == 0
    assert operations == ["Check lockfile", "pr", "Streamlit AppTest smoke", "build", "installed"]


def test_pr_profile_runs_each_test_once_and_every_gate(monkeypatch) -> None:
    operations: list[str] = []
    monkeypatch.setattr(verify, "_run", lambda label, *_args, **_kwargs: operations.append(label))
    assert verify.main(["pr"]) == 0
    assert operations == [
        "Check lockfile",
        "Lint",
        "Format check",
        "Architecture dependencies",
        "Type check",
        "Test suite with branch coverage",
        "Coverage JSON",
        "Critical per-module branch coverage",
        "Offline ingest smoke",
        "Native SQLite storage ingest smoke",
        "Security scan",
        "Dependency audit",
        "Publication privacy scan",
    ]
