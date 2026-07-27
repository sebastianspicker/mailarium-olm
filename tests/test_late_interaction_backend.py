"""Verifies the local late-interaction backend bounds resource use and follows its offline protocol."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mailarium.late_interaction_backend import LateInteractionError, LocalLateInteractionBackend
from mailarium.retriever_models import SearchResult


def _result(identifier: str) -> SearchResult:
    return SearchResult(chunk_id=identifier, text=identifier, metadata={}, distance=0.5)


def _artifact(tmp_path: Path) -> tuple[Path, Path]:
    runner = tmp_path / "runner"
    runner.write_text("runner", encoding="utf-8")
    model = tmp_path / "model"
    model.mkdir()
    payload = model / "artifact.bin"
    payload.write_bytes(b"artifact")
    (model / "late-interaction-manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "model_id": "local",
                "artifact": payload.name,
                "sha256": hashlib.sha256(b"artifact").hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return runner, model


def _executable_runner(tmp_path: Path, source: str) -> Path:
    runner = tmp_path / "executable-runner"
    runner.write_text(f"#!{sys.executable}\n{source}\n", encoding="utf-8")
    runner.chmod(0o700)
    return runner


def test_local_runner_reorders_by_returned_score(tmp_path):
    runner, model = _artifact(tmp_path)
    output = json.dumps({"version": 1, "scores": {"a": 0.1, "b": 0.9}})
    with patch("mailarium.late_interaction_backend._run_bounded_runner", return_value=(0, output)) as run:
        results = LocalLateInteractionBackend(str(runner), str(model)).rerank("q", [_result("a"), _result("b")], top_k=1)
    assert [item.chunk_id for item in results] == ["b"]
    assert results[0].metadata["reranker"] == "late_interaction_local"
    assert run.call_args.args[0] == runner.resolve()


def test_local_runner_rejects_response_ids_not_requested(tmp_path):
    runner, model = _artifact(tmp_path)
    output = json.dumps({"version": 1, "scores": {"other": 1.0}})
    with patch("mailarium.late_interaction_backend._run_bounded_runner", return_value=(0, output)):
        with pytest.raises(LateInteractionError, match="IDs do not match"):
            LocalLateInteractionBackend(str(runner), str(model)).rerank("q", [_result("a")], top_k=1)


def test_executable_local_runner_completes_protocol_round_trip(tmp_path):
    _runner, model = _artifact(tmp_path)
    runner = _executable_runner(
        tmp_path,
        "import json, sys\n"
        "payload = json.load(sys.stdin)\n"
        "scores = {item['chunk_id']: 0.75 for item in payload['documents']}\n"
        "print(json.dumps({'version': 1, 'scores': scores}))",
    )

    results = LocalLateInteractionBackend(str(runner), str(model)).rerank("query", [_result("a")], top_k=1)

    assert [result.chunk_id for result in results] == ["a"]


def test_local_runner_stops_oversized_stdout(tmp_path, monkeypatch):
    _runner, model = _artifact(tmp_path)
    runner = _executable_runner(tmp_path, "import sys\nsys.stdout.write('x' * 2048)")
    monkeypatch.setattr("mailarium.late_interaction_backend._MAX_RESPONSE_BYTES", 1024)

    with pytest.raises(LateInteractionError, match="stdout exceeds"):
        LocalLateInteractionBackend(str(runner), str(model)).rerank("private query", [_result("a")], top_k=1)


def test_local_runner_stops_oversized_stderr_without_disclosure(tmp_path, monkeypatch):
    _runner, model = _artifact(tmp_path)
    marker = "private-mailbox-content"
    runner = _executable_runner(tmp_path, f"import sys\nsys.stderr.write({marker!r} * 100)")
    monkeypatch.setattr("mailarium.late_interaction_backend._MAX_STDERR_BYTES", 128)

    with pytest.raises(LateInteractionError, match="stderr exceeds") as exc_info:
        LocalLateInteractionBackend(str(runner), str(model)).rerank("private query", [_result("a")], top_k=1)

    assert marker not in str(exc_info.value)


def test_local_runner_timeout_stops_child(tmp_path):
    _runner, model = _artifact(tmp_path)
    runner = _executable_runner(tmp_path, "import time\ntime.sleep(1)")

    with pytest.raises(subprocess.TimeoutExpired):
        LocalLateInteractionBackend(str(runner), str(model), timeout_seconds=0.1).rerank("private query", [_result("a")], top_k=1)


def test_local_runner_redacts_sensitive_stderr_on_failure(tmp_path):
    _runner, model = _artifact(tmp_path)
    marker = "private-mailbox-content"
    runner = _executable_runner(tmp_path, f"import sys\nsys.stderr.write({marker!r})\nraise SystemExit(7)")

    with pytest.raises(LateInteractionError, match="exited with 7") as exc_info:
        LocalLateInteractionBackend(str(runner), str(model)).rerank("private query", [_result("a")], top_k=1)

    assert marker not in str(exc_info.value)
