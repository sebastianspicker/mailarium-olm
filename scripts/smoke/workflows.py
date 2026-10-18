#!/usr/bin/env python3
"""Offline end-to-end smoke for Mailarium's core alpha workflows on a tiny synthetic archive."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingest as ingest_smoke  # noqa: E402  (sibling smoke owns the offline runtime and fallback classification)

_SMOKE_RUNTIME_ROOT = ROOT / "private" / "runtime" / "workflows-smoke"
_TOKEN = "zebracorn ledger"
_FAKE_DIMENSIONS = 1024
_FOLDER = "Accounts/test@example.com/com.microsoft.__Messages/Inbox"
_PRETTY_SENDER = """<OPFMessageCopySenderAddress>
    <emailAddress OPFContactEmailAddressAddress="alex@example.test" OPFContactEmailAddressName="Alex" />
  </OPFMessageCopySenderAddress>"""
_MESSAGES = (
    ("workflow-1", "Quarterly budget review", "Budget forecast and quarterly revenue planning for finance.", _PRETTY_SENDER, ""),
    (
        "workflow-2",
        "Attached ledger",
        "Please see the attached note about the shipment.",
        '<OPFMessageCopySenderAddress><emailAddress OPFContactEmailAddressAddress="bo@example.test" '
        'OPFContactEmailAddressName="Bo" /></OPFMessageCopySenderAddress>',
        "<OPFMessageCopyAttachmentList><messageAttachment><OPFAttachmentName>ledger.txt</OPFAttachmentName>"
        "<OPFAttachmentURL>ledger.txt</OPFAttachmentURL></messageAttachment></OPFMessageCopyAttachmentList>",
    ),
    (
        "workflow-3",
        "Team lunch plans",
        "Pizza and salad for the office lunch on Friday afternoon.",
        '<OPFMessageCopySenderAddress><emailAddress OPFContactEmailAddressAddress="cam@example.test" '
        'OPFContactEmailAddressName="Cam" /></OPFMessageCopySenderAddress>',
        "",
    ),
)


class _HashingModel:
    """Deterministic bag-of-words stand-in for the sentence-transformer model."""

    def encode(self, texts, **_kwargs):
        """Return L2-normalised vectors that bucket each word by hash, so shared words score higher."""
        import numpy as np

        vectors = np.zeros((len(texts), _FAKE_DIMENSIONS), dtype="float32")
        for row, text in enumerate(texts):
            for word in re.findall(r"\w+", text.lower()):
                vectors[row, int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % _FAKE_DIMENSIONS] += 1.0
            norm = float(np.linalg.norm(vectors[row])) or 1.0
            vectors[row] /= norm
        return vectors


def _build_olm(path: Path) -> None:
    """Write a three-message OLM: a pretty-printed sender, a text attachment, and an ordinary message."""
    with zipfile.ZipFile(path, "w") as archive:
        for index, (message_id, subject, body, sender, attachments) in enumerate(_MESSAGES, start=1):
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<email>
  <OPFMessageCopyMessageID>&lt;{message_id}@example.com&gt;</OPFMessageCopyMessageID>
  <OPFMessageCopySubject>{subject}</OPFMessageCopySubject>
  <OPFMessageCopySentTime>2026-04-1{index}T08:30:00</OPFMessageCopySentTime>
  <OPFMessageCopyBody>{body}</OPFMessageCopyBody>
  {sender}
  <OPFMessageCopyToAddresses>
    <emailAddress OPFContactEmailAddressAddress="recipient@example.com" OPFContactEmailAddressName="Recipient" />
  </OPFMessageCopyToAddresses>
  {attachments}
</email>
"""
            archive.writestr(f"{_FOLDER}/message-{index}.xml", xml)
        archive.writestr(f"{_FOLDER}/ledger.txt", f"The {_TOKEN} records every crate shipped this week.")


def _install_fake_model_if_unavailable() -> str:
    """Return "native" when the embedding model loads locally; otherwise patch in a hashing model and return "fallback"."""
    from mailarium.platform.settings import get_settings
    from mailarium.retrieval.multi_vector_embedder import MultiVectorEmbedder

    settings = get_settings()
    probe = MultiVectorEmbedder(
        model_name=settings.embedding_model,
        device=settings.device,
        load_mode="local_only",
        model_revision=settings.embedding_model_revision,
    )
    try:
        probe._ensure_loaded()
    except RuntimeError as exc:
        if not ingest_smoke._should_fallback_to_fake_runtime(exc):
            raise
    else:
        return "native"

    def _ensure_loaded(self: MultiVectorEmbedder) -> None:
        self._model = _HashingModel()

    MultiVectorEmbedder._ensure_loaded = _ensure_loaded  # type: ignore[method-assign]
    return "fallback"


def _invoke(entry_point: Callable[[list[str]], None], argv: list[str]) -> tuple[int, str]:
    """Run a CLI entry point in-process and return its exit code with combined stdout and stderr."""
    buffer = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            entry_point(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, buffer.getvalue()


def _check(condition: object, message: str) -> None:
    """Fail the smoke with a clear message."""
    if not condition:
        raise AssertionError(message)


def _query(sqlite_path: Path, sql: str) -> list[tuple]:
    """Read rows from the smoke archive."""
    with contextlib.closing(sqlite3.connect(sqlite_path)) as connection:
        return connection.execute(sql).fetchall()


def _attachment_chunk_ids(sqlite_path: Path) -> list[str]:
    """Return stored vector chunk ids that belong to attachment text."""
    rows = _query(sqlite_path, "SELECT chunk_id FROM vector_chunks")
    return [row[0] for row in rows if "__att_" in row[0]]


def _run_workflows(tmp_path: Path) -> dict[str, object]:
    """Exercise ingest, enrichment, topics, path policy, reset/re-embed, and search against one archive."""
    from mailarium.interfaces.cli.ingest import main as ingest_main
    from mailarium.interfaces.cli.main import main as cli_main

    olm_path = tmp_path / "workflows.olm"
    sqlite_path = tmp_path / "email_metadata.db"
    paths = ["--sqlite-path", str(sqlite_path), "--vector-index-path", str(tmp_path / "vector-index")]
    _build_olm(olm_path)

    # F-007: pretty-printed sender addresses survive a plain ingest.
    code, output = _invoke(ingest_main, [str(olm_path), *paths])
    _check(code == 0, f"plain ingest exited {code}:\n{output}")
    senders = dict(_query(sqlite_path, "SELECT subject, sender_email FROM emails"))
    _check(len(senders) == 3 and all(senders.values()), f"every email needs a sender_email: {senders}")
    _check(senders["Quarterly budget review"] == "alex@example.test", f"pretty-printed sender lost: {senders}")

    # F-009: a re-run requesting extraction enriches already-stored messages.
    code, output = _invoke(ingest_main, [str(olm_path), *paths, "--incremental", "--extract-attachments"])
    _check(code == 0, f"incremental extraction ingest exited {code}:\n{output}")
    texts = [row[0] for row in _query(sqlite_path, "SELECT extracted_text FROM attachments")]
    _check(any(_TOKEN in text for text in texts), f"attachment extracted_text missing token: {texts}")
    _check(_attachment_chunk_ids(sqlite_path), "no __att_ vector chunk after incremental extraction")

    # F-008: topic/cluster build persists clusters.
    code, output = _invoke(cli_main, [*paths, "topics", "build", "--n-topics", "2", "--n-clusters", "2"])
    _check(code == 0, f"topics build exited {code}:\n{output}")
    clusters = _query(sqlite_path, "SELECT COUNT(*) FROM cluster_info")[0][0]
    _check(clusters > 0, "topics build left cluster_info empty")

    # F-010: path-policy violations are one-line errors with exit 2.
    with tempfile.TemporaryDirectory(prefix="outside-") as outside:
        code, output = _invoke(cli_main, ["--sqlite-path", str(Path(outside) / "x.db"), "search", "q"])
    _check(code == 2 and "Traceback" not in output, f"path-policy violation: exit {code}, output:\n{output}")

    # F-016: reset then re-embed rebuilds attachment-text vectors from SQLite.
    code, output = _invoke(ingest_main, [*paths, "--reset-index", "--yes"])
    _check(code == 0, f"reset-index exited {code}:\n{output}")
    _check(not _attachment_chunk_ids(sqlite_path), "reset-index left __att_ chunks behind")
    code, output = _invoke(ingest_main, [*paths, "--reembed"])
    _check(code == 0, f"reembed exited {code}:\n{output}")
    _check(_attachment_chunk_ids(sqlite_path), "no __att_ vector chunk after reembed")

    # F-012: a missing .olm fails fast with exit 2.
    code, output = _invoke(ingest_main, [str(tmp_path / "missing.olm"), *paths])
    _check(code == 2 and "OLM file not found" in output, f"missing olm: exit {code}, output:\n{output}")

    # Search finds the attachment token (the hashing model is lexical, so this holds in both modes).
    code, output = _invoke(cli_main, [*paths, "search", _TOKEN, "--format", "json"])
    _check(code == 0, f"search exited {code}:\n{output}")
    payload = json.loads(output[output.index("{") :])
    _check(payload.get("results"), f"search for {_TOKEN!r} returned no results:\n{output}")

    return {"emails": len(senders), "clusters": clusters, "search_results": len(payload["results"])}


def main() -> int:
    """Run every workflow check on a fresh archive and print a JSON status line."""
    ingest_smoke._configure_offline_runtime()
    runtime_kind = _install_fake_model_if_unavailable()
    _SMOKE_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=_SMOKE_RUNTIME_ROOT) as tmp:
        summary = _run_workflows(Path(tmp))
    print(json.dumps({"status": "passed", "runtime_kind": runtime_kind, **summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
