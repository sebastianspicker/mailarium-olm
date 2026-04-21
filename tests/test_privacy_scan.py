from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import privacy_scan


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, message: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Example Operator",
            "-c",
            "user.email=operator@example.com",
            "commit",
            "-m",
            message,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_include_history_scans_historical_blob_content_without_printing_secret(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    marker = "se" + "bas" + "tian"
    note = repo / "notes.md"
    note.write_text(f"historical private marker: {marker}\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    _commit(repo, "add private marker")

    note.write_text("synthetic public fixture\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    _commit(repo, "remove private marker")

    monkeypatch.setattr(privacy_scan, "REPO_ROOT", repo)
    findings = privacy_scan.scan(include_untracked=False, include_history=True)
    printed = capsys.readouterr()

    assert privacy_scan.Finding("history-private-person-or-org-marker", "notes.md") in findings
    assert marker not in printed.out
