from __future__ import annotations

import argparse

import pytest

from src.ingest_reingest import reset_index_impl


def test_reset_index_impl_rejects_paths_outside_runtime_roots(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    sqlite_path = blocked_root / "email_metadata.db"
    chromadb_path = blocked_root / "chromadb"
    sqlite_path.write_text("sqlite", encoding="utf-8")
    chromadb_path.mkdir()

    monkeypatch.setenv("EMAIL_RAG_ALLOWED_RUNTIME_ROOTS", str(allowed_root))

    with pytest.raises(ValueError, match="allowed runtime roots"):
        reset_index_impl(argparse.Namespace(sqlite_path=str(sqlite_path), chromadb_path=str(chromadb_path)))

    assert sqlite_path.exists()
    assert chromadb_path.exists()


def test_reset_index_impl_deletes_paths_inside_runtime_roots(tmp_path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    sqlite_path = runtime_root / "email_metadata.db"
    chromadb_path = runtime_root / "chromadb"
    sqlite_path.write_text("sqlite", encoding="utf-8")
    chromadb_path.mkdir()

    monkeypatch.setenv("EMAIL_RAG_ALLOWED_RUNTIME_ROOTS", str(runtime_root))

    reset_index_impl(argparse.Namespace(sqlite_path=str(sqlite_path), chromadb_path=str(chromadb_path)))

    captured = capsys.readouterr().out
    assert "Deleted SQLite DB" in captured
    assert "Deleted ChromaDB" in captured
    assert not sqlite_path.exists()
    assert not chromadb_path.exists()
