"""Resets only derived index files inside approved runtime roots and preserves the archive database."""

from __future__ import annotations

import argparse

import pytest

from mailarium.email_db import EmailDatabase
from mailarium.ingest_reingest import reset_index_impl


def test_reset_index_impl_rejects_paths_outside_runtime_roots(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    sqlite_path = blocked_root / "email_metadata.db"
    vector_index_path = blocked_root / "vector-index"
    sqlite_path.write_text("sqlite", encoding="utf-8")
    vector_index_path.mkdir()

    monkeypatch.setenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", str(allowed_root))

    with pytest.raises(ValueError, match="allowed runtime roots"):
        reset_index_impl(argparse.Namespace(sqlite_path=str(sqlite_path), vector_index_path=str(vector_index_path)))

    assert sqlite_path.exists()
    assert vector_index_path.exists()


def test_reset_index_impl_preserves_database_and_deletes_derived_files(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    sqlite_path = runtime_root / "email_metadata.db"
    vector_index_path = runtime_root / "vector-index"
    EmailDatabase(str(sqlite_path)).close()
    vector_index_path.mkdir()

    monkeypatch.setenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", str(runtime_root))

    reset_index_impl(argparse.Namespace(sqlite_path=str(sqlite_path), vector_index_path=str(vector_index_path)))

    captured = capsys.readouterr().out
    assert "Reset vector index" in captured
    assert sqlite_path.exists()
    assert not vector_index_path.exists()


def test_reset_index_impl_uses_repo_root_for_relative_paths(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    data = repo / "data"
    data.mkdir(parents=True)
    sqlite_path = data / "email_metadata.db"
    vector_index_path = data / "vector-index"
    EmailDatabase(str(sqlite_path)).close()
    vector_index_path.mkdir()
    caller_cwd = tmp_path / "caller"
    caller_cwd.mkdir()

    monkeypatch.setattr("mailarium.repo_paths.repo_root", lambda: repo)
    monkeypatch.setattr("mailarium.repo_paths._is_repository_checkout", lambda: True)
    monkeypatch.setattr(
        "mailarium.ingest_reingest.get_settings",
        lambda: argparse.Namespace(sqlite_path="unused", vector_index_path="unused"),
    )
    monkeypatch.chdir(caller_cwd)

    reset_index_impl(argparse.Namespace(sqlite_path="data/email_metadata.db", vector_index_path="data/vector-index"))

    assert sqlite_path.exists()
    assert not vector_index_path.exists()
    assert not (caller_cwd / "data").exists()
