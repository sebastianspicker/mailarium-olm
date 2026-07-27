"""Exercises publication privacy scanning across history, index state, fixtures, tool artifacts, and unreadable files.

It fails closed without exposing detected secret material in scanner output.
"""

from __future__ import annotations

import subprocess  # nosec B404
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


def test_tracked_local_tool_state_and_audit_logs_are_publication_risks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    audit = repo / "AUDIT_REPORT_2026-07-12.md"
    audit.write_text("local-only evidence\n", encoding="utf-8")
    tool_state = repo / ".codegraph" / "state.json"
    tool_state.parent.mkdir()
    tool_state.write_text("{}\n", encoding="utf-8")
    documentation = repo / "docs" / "agent" / "Documentation.md"
    documentation.parent.mkdir(parents=True)
    documentation.write_text("execution log\n", encoding="utf-8")
    snapshot = repo / "pre-clean" / "opaque.snapshot"
    snapshot.parent.mkdir()
    snapshot.write_text("must not be inspected\n", encoding="utf-8")
    archived_snapshot = repo / "archive" / "local" / "opaque.snapshot"
    archived_snapshot.parent.mkdir(parents=True)
    archived_snapshot.write_text("must not be inspected\n", encoding="utf-8")
    _git(
        repo,
        "add",
        "-f",
        audit.name,
        ".codegraph/state.json",
        "docs/agent/Documentation.md",
        "archive/local/opaque.snapshot",
        "pre-clean/opaque.snapshot",
    )

    monkeypatch.setattr(privacy_scan, "REPO_ROOT", repo)
    findings = privacy_scan.scan(include_untracked=False)

    assert privacy_scan.Finding("tracked-forbidden-path", audit.name) in findings
    assert privacy_scan.Finding("tracked-forbidden-path", ".codegraph/state.json") in findings
    assert privacy_scan.Finding("tracked-forbidden-path", "docs/agent/Documentation.md") in findings
    assert privacy_scan.Finding("tracked-forbidden-path", "archive/local/opaque.snapshot") in findings
    assert privacy_scan.Finding("tracked-forbidden-path", "pre-clean/opaque.snapshot") in findings

    audit.unlink()
    tool_state.unlink()
    documentation.unlink()
    archived_snapshot.unlink()
    snapshot.unlink()
    assert set(privacy_scan.scan(include_untracked=False)) == {
        privacy_scan.Finding("tracked-forbidden-path", audit.name),
        privacy_scan.Finding("tracked-forbidden-path", ".codegraph/state.json"),
        privacy_scan.Finding("tracked-forbidden-path", "docs/agent/Documentation.md"),
        privacy_scan.Finding("tracked-forbidden-path", "archive/local/opaque.snapshot"),
        privacy_scan.Finding("tracked-forbidden-path", "pre-clean/opaque.snapshot"),
    }

    _git(repo, "add", "-u")
    assert privacy_scan.scan(include_untracked=False) == []


def test_deleted_but_unstaged_tracked_text_is_scanned_from_index(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    marker = "se" + "bas" + "tian"
    note = repo / "notes.md"
    note.write_text(f"private marker: {marker}\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    note.unlink()
    monkeypatch.setattr(privacy_scan, "REPO_ROOT", repo)

    assert privacy_scan.Finding("private-person-or-org-marker", "notes.md") in privacy_scan.scan(include_untracked=False)

    _git(repo, "add", "-u")
    assert privacy_scan.scan(include_untracked=False) == []


def test_tracked_qa_fixture_rejects_live_or_real_provenance_language(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    fixture = repo / "tests" / "fixtures" / "qa_eval" / "questions.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"notes": "Real six-message conversation from a live eval corpus."}\n', encoding="utf-8")
    _git(repo, "add", "tests/fixtures/qa_eval/questions.json")
    monkeypatch.setattr(privacy_scan, "REPO_ROOT", repo)

    assert privacy_scan.scan(include_untracked=False) == [
        privacy_scan.Finding("non-synthetic-qa-provenance", "tests/fixtures/qa_eval/questions.json")
    ]


def test_redaction_key_name_is_not_reported_as_a_secret_value(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    safe_source = repo / "safe.py"
    safe_source.write_text('REDACTED_KEYS = {"api_key"}\n', encoding="utf-8")
    synthetic_leak = repo / "leak.txt"
    secret_name = "api" + "_key"
    synthetic_leak.write_text(f"{secret_name}=abcdefghijk\n", encoding="utf-8")
    _git(repo, "add", "safe.py", "leak.txt")
    monkeypatch.setattr(privacy_scan, "REPO_ROOT", repo)

    findings = privacy_scan.scan(include_untracked=False)

    assert privacy_scan.Finding("secret-or-meeting-token", "leak.txt") in findings
    assert all(finding.path != "safe.py" for finding in findings)


def test_unreadable_tracked_file_fails_closed(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    note = repo / "candidate.md"
    note.write_text("synthetic public fixture\n", encoding="utf-8")
    _git(repo, "add", "candidate.md")

    original_read_text = Path.read_text

    def deny_candidate(path: Path, *args, **kwargs) -> str:
        if path == note:
            raise PermissionError("candidate is unreadable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_candidate)
    monkeypatch.setattr(privacy_scan, "REPO_ROOT", repo)

    assert privacy_scan.scan(include_untracked=False) == [privacy_scan.Finding("unreadable-candidate-file", "candidate.md")]
