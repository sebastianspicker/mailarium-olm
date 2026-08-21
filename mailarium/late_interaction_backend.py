"""Isolated local late-interaction reranking protocol."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .retriever_models import SearchResult

_PROTOCOL_VERSION = 1
_MAX_CANDIDATES = 100
_MAX_PAYLOAD_CHARS = 2_000_000
_MAX_RESPONSE_BYTES = _MAX_PAYLOAD_CHARS * 4
_MAX_STDERR_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_DEFAULT_TIMEOUT_SECONDS = 30.0
_MANIFEST_NAME = "late-interaction-manifest.json"


class LateInteractionError(RuntimeError):
    """Raised when the isolated reranker violates its local protocol."""


@dataclass(frozen=True)
class LocalLateInteractionBackend:
    """Run a checksum-verified local reranker subprocess without a shell."""

    runner_path: str
    model_path: str
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        *,
        top_k: int,
    ) -> list[SearchResult]:
        """Rerank a bounded candidate set through the verified local protocol.

        The request is capped at 100 candidates and two million serialized
        characters. Stable input order breaks equal-score ties.

        Raises:
            LateInteractionError: If local artifacts, payloads, runner output,
                or the runner exit status violate the protocol.
            subprocess.TimeoutExpired: If the runner exceeds its timeout.
        """
        if not results:
            return []
        runner = _validated_file(self.runner_path, label="late-interaction runner")
        model_dir, manifest = _validated_model(self.model_path)
        candidates = results[:_MAX_CANDIDATES]
        payload = {
            "version": _PROTOCOL_VERSION,
            "model_path": str(model_dir),
            "model_id": str(manifest.get("model_id") or ""),
            "query": query,
            "documents": [{"chunk_id": result.chunk_id, "text": result.text} for result in candidates],
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(serialized) > _MAX_PAYLOAD_CHARS:
            raise LateInteractionError("late-interaction payload exceeds the configured safety limit")
        returncode, output = _run_bounded_runner(
            runner,
            serialized,
            timeout_seconds=max(float(self.timeout_seconds), 0.1),
        )
        if returncode != 0:
            raise LateInteractionError(f"late-interaction runner exited with {returncode}; runner diagnostics were redacted")
        scores = _parse_scores(output, candidates)
        ranked = sorted(
            enumerate(candidates),
            key=lambda item: (-scores[item[1].chunk_id], item[0]),
        )
        from .retriever_models import SearchResult as SearchResultModel

        return [
            SearchResultModel(
                chunk_id=result.chunk_id,
                text=result.text,
                metadata={
                    **result.metadata,
                    "reranker": "late_interaction_local",
                    "score_kind": "late_interaction",
                },
                distance=max(0.0, min(2.0, 1.0 - scores[result.chunk_id])),
            )
            for _position, result in ranked[:top_k]
        ]


def _run_bounded_runner(runner: Path, serialized: str, *, timeout_seconds: float) -> tuple[int, str]:
    """Run the local protocol with bounded stdout and redacted, bounded stderr."""
    command = [str(runner)]
    deadline = time.monotonic() + timeout_seconds
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": _MAX_RESPONSE_BYTES, "stderr": _MAX_STDERR_BYTES}

    with tempfile.TemporaryFile() as request_stream:
        request_stream.write(serialized.encode("utf-8"))
        request_stream.seek(0)
        process = subprocess.Popen(
            command,
            stdin=request_stream,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.stdout is None or process.stderr is None:
            _kill_process(process)
            raise LateInteractionError("late-interaction runner pipes were unavailable")

        selector = selectors.DefaultSelector()
        streams = {"stdout": process.stdout, "stderr": process.stderr}
        try:
            for label, stream in streams.items():
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, data=label)

            exceeded = _collect_runner_output(
                selector,
                streams,
                buffers,
                limits,
                deadline=deadline,
                command=command,
                timeout_seconds=timeout_seconds,
            )
            if exceeded is not None:
                _kill_process(process)
                raise LateInteractionError(f"late-interaction runner {exceeded} exceeds the configured safety limit")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            returncode = process.wait(timeout=remaining)
        except BaseException:
            _kill_process(process)
            raise
        finally:
            selector.close()
            for stream in streams.values():
                stream.close()

    try:
        output = bytes(buffers["stdout"]).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LateInteractionError("late-interaction runner returned non-UTF-8 output") from exc
    return returncode, output


def _collect_runner_output(
    selector: selectors.BaseSelector,
    streams: dict[str, Any],
    buffers: dict[str, bytearray],
    limits: dict[str, int],
    *,
    deadline: float,
    command: list[str],
    timeout_seconds: float,
) -> str | None:
    """Drain both runner pipes until EOF, timeout, or the first overflow."""
    while selector.get_map():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout_seconds)
        for key, _events in selector.select(timeout=min(remaining, 0.1)):
            exceeded = _read_runner_chunk(selector, key, streams, buffers, limits)
            if exceeded is not None:
                return exceeded
    return None


def _read_runner_chunk(
    selector: selectors.BaseSelector,
    key: selectors.SelectorKey,
    streams: dict[str, Any],
    buffers: dict[str, bytearray],
    limits: dict[str, int],
) -> str | None:
    """Read one bounded chunk and return the overflowing stream name, if any."""
    label = str(key.data)
    stream = streams[label]
    buffer = buffers[label]
    limit = limits[label]
    try:
        chunk = os.read(stream.fileno(), min(_READ_CHUNK_BYTES, limit + 1 - len(buffer)))
    except BlockingIOError:
        return None
    if not chunk:
        selector.unregister(stream)
        stream.close()
        return None
    buffer.extend(chunk)
    return label if len(buffer) > limit else None


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    """Stop and reap a runner that exceeded a protocol resource boundary."""
    if process.poll() is None:
        process.kill()
    process.wait()


def _validated_file(value: str, *, label: str) -> Path:
    """Resolve a configured local artifact and reject absent runner paths."""
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise LateInteractionError(f"{label} does not exist: {path}")
    return path


def _validated_model(value: str) -> tuple[Path, dict[str, Any]]:
    """Verify the model manifest, containment, and checksum before invoking the runner."""
    model_dir = Path(value).expanduser().resolve()
    if not model_dir.is_dir():
        raise LateInteractionError(f"late-interaction model directory does not exist: {model_dir}")
    manifest_path = model_dir / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise LateInteractionError(f"missing {_MANIFEST_NAME} in {model_dir}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LateInteractionError(f"invalid late-interaction manifest: {exc}") from exc
    if not isinstance(manifest, dict) or int(manifest.get("version", 0)) != _PROTOCOL_VERSION:
        raise LateInteractionError("unsupported late-interaction manifest version")
    artifact_name = str(manifest.get("artifact") or "")
    expected_sha256 = str(manifest.get("sha256") or "").lower()
    artifact = (model_dir / artifact_name).resolve()
    if model_dir not in artifact.parents or not artifact.is_file():
        raise LateInteractionError("manifest artifact must be a file inside the model directory")
    actual_sha256 = _sha256(artifact)
    if not expected_sha256 or actual_sha256 != expected_sha256:
        raise LateInteractionError("late-interaction artifact checksum mismatch")
    return model_dir, manifest


def _parse_scores(output: str, results: list[SearchResult]) -> dict[str, float]:
    """Parse scores into the internal representation."""
    raw_scores = _parse_score_envelope(output)
    _validate_score_ids(raw_scores, results)
    return _validate_score_values(raw_scores)


def _parse_score_envelope(output: str) -> dict[Any, Any]:
    """Parse and validate the response envelope and protocol version."""
    if len(output) > _MAX_PAYLOAD_CHARS:
        raise LateInteractionError("late-interaction response exceeds the configured safety limit")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise LateInteractionError(f"late-interaction runner returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or int(payload.get("version", 0)) != _PROTOCOL_VERSION:
        raise LateInteractionError("late-interaction runner returned an unsupported protocol version")
    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, dict):
        raise LateInteractionError("late-interaction response must contain a scores object")
    return raw_scores


def _validate_score_ids(raw_scores: dict[Any, Any], results: list[SearchResult]) -> None:
    """Require the response to score exactly the requested candidate IDs."""
    expected_ids = {result.chunk_id for result in results}
    if set(raw_scores) != expected_ids:
        raise LateInteractionError("late-interaction response IDs do not match the request")


def _validate_score_values(raw_scores: dict[Any, Any]) -> dict[str, float]:
    """Convert each response score and enforce the normalized score range."""
    scores: dict[str, float] = {}
    for chunk_id, raw_score in raw_scores.items():
        try:
            score = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise LateInteractionError(f"invalid score for {chunk_id!r}") from exc
        if not (-1.0 <= score <= 1.0):
            raise LateInteractionError(f"out-of-range score for {chunk_id!r}")
        scores[str(chunk_id)] = score
    return scores


def _sha256(path: Path) -> str:
    """Stream a local artifact into SHA-256 without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
