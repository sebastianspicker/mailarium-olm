"""Runs the offline ingestion smoke path with validated runtime locations and an explicit model-unavailable fallback."""

from __future__ import annotations

import json
import os
import sys
import types

import mailarium.ingest as ingest_module
from mailarium.config import get_settings
from mailarium.multi_vector_embedder import EmbeddingModelUnavailableError
from mailarium.repo_paths import validate_runtime_path
from scripts import ingest_smoke as runner


def _payload_from_stdout(stdout: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def _mark_usearch_available(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "usearch", types.ModuleType("usearch"))


def test_configure_offline_runtime_forces_offline_acceptance_profile(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("RUNTIME_PROFILE", "quality")
    monkeypatch.setenv("EMBEDDING_LOAD_MODE", "download")
    monkeypatch.setenv("SPACY_AUTO_DOWNLOAD_DURING_INGEST", "1")

    assert get_settings().runtime_profile == "quality"
    assert get_settings().embedding_load_mode == "download"

    runner._configure_offline_runtime()

    settings = get_settings()

    assert os.environ["RUNTIME_PROFILE"] == "offline-test"
    assert os.environ["EMBEDDING_LOAD_MODE"] == "local_only"
    assert os.environ["DISABLE_SAFETENSORS_CONVERSION"] == "1"
    assert os.environ["SPACY_AUTO_DOWNLOAD_DURING_INGEST"] == "0"
    assert settings.runtime_profile == "offline-test"
    assert settings.embedding_load_mode == "local_only"


def test_smoke_runtime_root_is_allowed_for_runtime_paths() -> None:
    root = runner._smoke_runtime_root()

    sqlite_path = root / "run-test" / "email_metadata.db"
    vector_index_path = root / "run-test" / "vector-index"

    assert validate_runtime_path(str(sqlite_path), field_name="sqlite_path") == sqlite_path.resolve()
    assert validate_runtime_path(str(vector_index_path), field_name="vector_index_path") == vector_index_path.resolve()


def test_main_falls_back_to_fake_runtime_when_embedding_model_is_unavailable(monkeypatch, capsys) -> None:
    def _raise_model_unavailable(*args, **kwargs):
        raise EmbeddingModelUnavailableError("cache miss")

    _mark_usearch_available(monkeypatch)
    monkeypatch.setattr(ingest_module, "ingest", _raise_model_unavailable)

    exit_code = runner.main()

    payload = _payload_from_stdout(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["runtime_kind"] == "fallback"
    assert payload["runtime_mode"] == "fake_runtime_missing_embedding_model"
    assert payload["first_run"] == {
        "emails_parsed": 1,
        "sqlite_inserted": 1,
        "attachment_chunks": 1,
        "chunks_added": 2,
    }
    assert payload["incremental_rerun"] == {
        "emails_parsed": 1,
        "skipped_incremental": 1,
    }


def test_main_resets_fake_runtime_state_between_runs(monkeypatch, capsys) -> None:
    def _raise_model_unavailable(*args, **kwargs):
        raise EmbeddingModelUnavailableError("cache miss")

    _mark_usearch_available(monkeypatch)
    monkeypatch.setattr(ingest_module, "ingest", _raise_model_unavailable)

    assert runner.main() == 0
    first_payload = _payload_from_stdout(capsys.readouterr().out)

    assert runner.main() == 0
    second_payload = _payload_from_stdout(capsys.readouterr().out)

    assert first_payload["runtime_mode"] == "fake_runtime_missing_embedding_model"
    assert second_payload["runtime_mode"] == "fake_runtime_missing_embedding_model"
    assert first_payload["first_run"] == second_payload["first_run"]
    assert first_payload["incremental_rerun"] == second_payload["incremental_rerun"]


def test_main_reports_native_runtime_when_embedding_stack_is_available(monkeypatch, capsys) -> None:
    native_runs = iter(
        [
            {"emails_parsed": 1, "sqlite_inserted": 1, "attachment_chunks": 1, "chunks_added": 2, "skipped_incremental": 0},
            {"emails_parsed": 1, "sqlite_inserted": 0, "attachment_chunks": 1, "chunks_added": 0, "skipped_incremental": 1},
        ]
    )

    _mark_usearch_available(monkeypatch)
    monkeypatch.setattr(ingest_module, "ingest", lambda *args, **kwargs: next(native_runs))

    exit_code = runner.main()

    payload = _payload_from_stdout(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["runtime_kind"] == "native"
    assert payload["runtime_mode"] == "native_runtime"
