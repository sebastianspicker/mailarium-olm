#!/usr/bin/env python3
"""Small offline ingest smoke for acceptance runs."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

try:
    from scripts._bootstrap import add_repository_root
except ModuleNotFoundError:  # Direct execution resolves helpers from the script directory.
    from _bootstrap import add_repository_root

ROOT = add_repository_root(__file__)

_SMOKE_RUNTIME_ROOT = ROOT / "tests" / "private" / "ingest-smoke"


def _smoke_runtime_root() -> Path:
    """Create the ignored runtime root used to contain all smoke-test artifacts."""
    _SMOKE_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    return _SMOKE_RUNTIME_ROOT


def _build_smoke_olm(path: Path) -> None:
    """Write a minimal OLM archive containing one email and one text attachment."""
    xml_path = "Accounts/test@example.com/com.microsoft.__Messages/Inbox/message-1.xml"
    attachment_path = "Accounts/test@example.com/com.microsoft.__Messages/Inbox/supporting-note.txt"
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<email>
  <OPFMessageCopyMessageID>&lt;smoke-1@example.com&gt;</OPFMessageCopyMessageID>
  <OPFMessageCopySubject>Smoke ingest message</OPFMessageCopySubject>
  <OPFMessageCopySentTime>2026-04-13T08:30:00</OPFMessageCopySentTime>
  <OPFMessageCopyBody>Hello from the ingest smoke fixture.</OPFMessageCopyBody>
  <OPFMessageCopyToAddresses>
    <emailAddress OPFContactEmailAddressAddress="recipient@example.com" OPFContactEmailAddressName="Recipient Example" />
  </OPFMessageCopyToAddresses>
  <OPFMessageCopyAttachmentList>
    <messageAttachment>
      <OPFAttachmentName>supporting-note.txt</OPFAttachmentName>
      <OPFAttachmentURL>supporting-note.txt</OPFAttachmentURL>
    </messageAttachment>
  </OPFMessageCopyAttachmentList>
</email>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(xml_path, xml)
        archive.writestr(attachment_path, "Attachment evidence line for smoke ingest.")


@dataclass
class _FakeEmbedder:
    """Minimal embedder that records chunk counts while satisfying ingest interfaces."""

    chunk_total: int = 0
    collection: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(metadata={"hnsw:space": "cosine"}))

    def add_chunks(self, chunks, batch_size=32, skip_existing_check=False):
        """Count accepted chunks without loading or persisting an embedding model."""
        self.chunk_total += len(chunks)
        return len(chunks)

    def count(self) -> int:
        """Expose the accumulated chunk count for incremental-ingest assertions."""
        return self.chunk_total

    def set_sparse_db(self, db) -> None:
        """Accept sparse-index wiring without creating a second persistence layer."""

    def warmup(self) -> None:
        """Model successful embedder readiness without loading weights."""

    def close(self) -> None:
        """Satisfy pipeline teardown without owning external resources."""


@dataclass
class _FakeEmailDB:
    """In-memory ingestion ledger used to verify first-run and incremental semantics."""

    inserted_uids: set[str] = field(default_factory=set)
    completed_uids: set[str] = field(default_factory=set)
    conn: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(commit=lambda: None))
    run_counter: int = 0

    def record_ingestion_start(self, olm_path, olm_sha256=None, file_size_bytes=None):
        """Allocate a monotonically increasing fake ingestion-run identifier."""
        self.run_counter += 1
        return self.run_counter

    def insert_emails_batch(self, emails, ingestion_run_id=None):
        """Record only previously unseen email UIDs and return the newly inserted set."""
        new_uids = {email.uid for email in emails if email.uid not in self.inserted_uids}
        self.inserted_uids.update(new_uids)
        return new_uids

    def completed_ingest_uids(self, attachment_required=False):
        """Return a copy of completed UIDs so callers cannot mutate fake database state."""
        return set(self.completed_uids)

    def mark_ingest_batch_pending(self, rows, commit=True):
        """Accept pending-batch writes; completion state is recorded separately."""

    def mark_ingest_batch_completed(self, rows, commit=True):
        """Promote non-empty batch UIDs into the fake database's completed set."""
        for row in rows:
            email_uid = str(row.get("email_uid") or "")
            if email_uid:
                self.completed_uids.add(email_uid)

    def mark_ingest_batch_failed(self, email_uids, *, error_message, commit=True):
        """Accept failure callbacks without marking affected UIDs complete."""

    def update_analytics_batch(self, rows):
        """Accept analytics writes and report the number of rows processed."""
        return len(rows)

    def insert_entities_batch(self, uid, entities, commit=True):
        """Accept entity writes because this smoke test measures ingest flow, not entity storage."""

    def record_ingestion_complete(self, ingestion_run_id, details):
        """Accept run-finalization metadata after batch processing succeeds."""

    def close(self) -> None:
        """Satisfy database teardown for an object with no external handle."""


def _run_ingest_with_fake_runtime(
    *,
    olm_path: Path,
    sqlite_path: Path,
    vector_index_path: Path,
    incremental: bool,
) -> dict[str, object]:
    """Run the real ingest pipeline against in-memory storage doubles, restoring runtime construction afterward."""
    from mailarium import ingest as ingest_module
    from mailarium import ingest_pipeline as pipeline_family

    fake_embedder = _run_ingest_with_fake_runtime.embedder
    fake_email_db = _run_ingest_with_fake_runtime.email_db
    original_build_runtime = pipeline_family._build_runtime

    def _fake_build_runtime(*, settings, dry_run, vector_index_path, sqlite_path):
        return fake_embedder, fake_email_db

    pipeline_family._build_runtime = _fake_build_runtime
    try:
        return pipeline_family.ingest_impl(
            olm_path=str(olm_path),
            vector_index_path=str(vector_index_path),
            sqlite_path=str(sqlite_path),
            batch_size=500,
            max_emails=None,
            dry_run=False,
            extract_attachments=True,
            extract_entities=False,
            incremental=incremental,
            embed_images=False,
            resume=False,
            timing=True,
            get_settings=ingest_module.get_settings,
            resolve_runtime_summary=ingest_module.resolve_runtime_summary,
            should_enable_image_embedding=ingest_module.should_enable_image_embedding,
            parse_olm=ingest_module.parse_olm,
            chunk_email=ingest_module.chunk_email,
            chunk_attachment=ingest_module.chunk_attachment,
            hash_file_sha256=ingest_module._hash_file_sha256,
            resolve_entity_extractor=ingest_module._resolve_entity_extractor,
            resolve_entity_extractor_provenance=ingest_module._entity_extractor_provenance,
            exchange_entities_from_email=ingest_module._exchange_entities_from_email,
            embed_pipeline_cls=ingest_module._EmbedPipeline,
            make_progress_bar=ingest_module._make_progress_bar,
        )
    finally:
        pipeline_family._build_runtime = original_build_runtime


_run_ingest_with_fake_runtime.embedder = _FakeEmbedder()
_run_ingest_with_fake_runtime.email_db = _FakeEmailDB()


def _reset_fake_runtime() -> None:
    """Replace accumulated fake embedder and database state before an isolated smoke run."""
    _run_ingest_with_fake_runtime.embedder = _FakeEmbedder()
    _run_ingest_with_fake_runtime.email_db = _FakeEmailDB()


def _configure_offline_runtime() -> None:
    """Disable model downloads, force local-only loading, and invalidate cached settings."""
    os.environ["SPACY_AUTO_DOWNLOAD_DURING_INGEST"] = "0"
    os.environ["RUNTIME_PROFILE"] = "offline-test"
    os.environ["EMBEDDING_LOAD_MODE"] = "local_only"
    os.environ["DISABLE_SAFETENSORS_CONVERSION"] = "1"

    from mailarium.config import get_settings

    get_settings.cache_clear()


def _exception_chain(exc: BaseException) -> list[BaseException]:
    """Walk explicit causes and implicit contexts without losing the original exception order."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _should_fallback_to_fake_runtime(exc: BaseException) -> bool:
    """Allow the fake backend only for missing models or offline resolution failures."""
    for current in _exception_chain(exc):
        if current.__class__.__name__ == "EmbeddingModelUnavailableError":
            return True
        if current.__class__.__module__.startswith(("httpx", "httpcore")):
            return True
        if isinstance(current, socket.gaierror):
            return True
    return False


def _fake_runtime_reason(exc: BaseException) -> str:
    """Classify model absence and network resolution failures separately from native runtime errors."""
    for current in _exception_chain(exc):
        if current.__class__.__name__ == "EmbeddingModelUnavailableError":
            return "missing_embedding_model"
        if current.__class__.__module__.startswith(("httpx", "httpcore")):
            return "offline_model_resolution"
        if isinstance(current, socket.gaierror):
            return "offline_model_resolution"
    return "native_runtime_error"


def main() -> int:
    """Ingest the synthetic archive twice, using the native backend when available and a bounded fake fallback offline."""
    _configure_offline_runtime()
    from mailarium.ingest import ingest

    with tempfile.TemporaryDirectory(prefix="run-", dir=_smoke_runtime_root()) as tmp:
        tmp_path = Path(tmp)
        olm_path = tmp_path / "smoke.olm"
        sqlite_path = tmp_path / "email_metadata.db"
        vector_index_path = tmp_path / "vector-index"
        _build_smoke_olm(olm_path)

        try:
            import usearch  # noqa: F401
        except ModuleNotFoundError:
            _reset_fake_runtime()
            first = _run_ingest_with_fake_runtime(
                olm_path=olm_path,
                sqlite_path=sqlite_path,
                vector_index_path=vector_index_path,
                incremental=False,
            )
            second = _run_ingest_with_fake_runtime(
                olm_path=olm_path,
                sqlite_path=sqlite_path,
                vector_index_path=vector_index_path,
                incremental=True,
            )
            runtime_mode = "fake_runtime_missing_usearch"
        else:
            try:
                first = ingest(
                    str(olm_path),
                    sqlite_path=str(sqlite_path),
                    vector_index_path=str(vector_index_path),
                    extract_attachments=True,
                    incremental=False,
                    timing=True,
                )
                second = ingest(
                    str(olm_path),
                    sqlite_path=str(sqlite_path),
                    vector_index_path=str(vector_index_path),
                    extract_attachments=True,
                    incremental=True,
                    timing=True,
                )
                runtime_mode = "native_runtime"
            except (RuntimeError, ImportError, OSError, ValueError) as exc:
                if not _should_fallback_to_fake_runtime(exc):
                    raise
                _reset_fake_runtime()
                first = _run_ingest_with_fake_runtime(
                    olm_path=olm_path,
                    sqlite_path=sqlite_path,
                    vector_index_path=vector_index_path,
                    incremental=False,
                )
                second = _run_ingest_with_fake_runtime(
                    olm_path=olm_path,
                    sqlite_path=sqlite_path,
                    vector_index_path=vector_index_path,
                    incremental=True,
                )
                runtime_mode = f"fake_runtime_{_fake_runtime_reason(exc)}"

        assert first["emails_parsed"] == 1
        assert first["sqlite_inserted"] == 1
        assert first["attachment_chunks"] >= 1
        assert first["chunks_added"] >= 1
        assert second["skipped_incremental"] == 1
        runtime_kind = "native" if runtime_mode == "native_runtime" else "fallback"

        print(
            json.dumps(
                {
                    "status": "passed",
                    "runtime_kind": runtime_kind,
                    "runtime_mode": runtime_mode,
                    "first_run": {
                        "emails_parsed": first["emails_parsed"],
                        "sqlite_inserted": first["sqlite_inserted"],
                        "attachment_chunks": first["attachment_chunks"],
                        "chunks_added": first["chunks_added"],
                    },
                    "incremental_rerun": {
                        "emails_parsed": second["emails_parsed"],
                        "skipped_incremental": second["skipped_incremental"],
                    },
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
