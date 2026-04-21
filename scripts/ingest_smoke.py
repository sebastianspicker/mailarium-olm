#!/usr/bin/env python3
"""Small end-to-end ingest smoke for acceptance runs."""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_smoke_olm(path: Path) -> None:
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
    chunk_total: int = 0
    collection: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(metadata={"hnsw:space": "cosine"}))

    def add_chunks(self, chunks, batch_size=32, skip_existing_check=False):
        self.chunk_total += len(chunks)
        return len(chunks)

    def count(self) -> int:
        return self.chunk_total

    def set_sparse_db(self, db) -> None:
        pass

    def warmup(self) -> None:
        pass

    def close(self) -> None:
        pass


@dataclass
class _FakeEmailDB:
    inserted_uids: set[str] = field(default_factory=set)
    completed_uids: set[str] = field(default_factory=set)
    conn: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(commit=lambda: None))
    run_counter: int = 0

    def record_ingestion_start(self, olm_path, olm_sha256=None, file_size_bytes=None):
        self.run_counter += 1
        return self.run_counter

    def insert_emails_batch(self, emails, ingestion_run_id=None):
        new_uids = {email.uid for email in emails if email.uid not in self.inserted_uids}
        self.inserted_uids.update(new_uids)
        return new_uids

    def completed_ingest_uids(self, attachment_required=False):
        return set(self.completed_uids)

    def mark_ingest_batch_pending(self, rows, commit=True):
        pass

    def mark_ingest_batch_completed(self, rows, commit=True):
        for row in rows:
            email_uid = str(row.get("email_uid") or "")
            if email_uid:
                self.completed_uids.add(email_uid)

    def mark_ingest_batch_failed(self, email_uids, *, error_message, commit=True):
        pass

    def update_analytics_batch(self, rows):
        return len(rows)

    def insert_entities_batch(self, uid, entities, commit=True):
        pass

    def record_ingestion_complete(self, ingestion_run_id, details):
        pass

    def close(self) -> None:
        pass


def _run_ingest_with_fake_runtime(
    *,
    olm_path: Path,
    sqlite_path: Path,
    chromadb_path: Path,
    incremental: bool,
) -> dict[str, object]:
    from src import ingest as ingest_module
    from src import ingest_pipeline as pipeline_family

    fake_embedder = _run_ingest_with_fake_runtime.embedder
    fake_email_db = _run_ingest_with_fake_runtime.email_db
    original_build_runtime = pipeline_family._build_runtime

    def _fake_build_runtime(*, settings, dry_run, chromadb_path, sqlite_path):
        return fake_embedder, fake_email_db

    pipeline_family._build_runtime = _fake_build_runtime
    try:
        return pipeline_family.ingest_impl(
            olm_path=str(olm_path),
            chromadb_path=str(chromadb_path),
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
    _run_ingest_with_fake_runtime.embedder = _FakeEmbedder()
    _run_ingest_with_fake_runtime.email_db = _FakeEmailDB()


def _configure_offline_runtime() -> None:
    os.environ["SPACY_AUTO_DOWNLOAD_DURING_INGEST"] = "0"
    os.environ["RUNTIME_PROFILE"] = "offline-test"
    os.environ["EMBEDDING_LOAD_MODE"] = "local_only"
    os.environ["DISABLE_SAFETENSORS_CONVERSION"] = "1"

    from src.config import get_settings

    get_settings.cache_clear()


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _should_fallback_to_fake_runtime(exc: BaseException) -> bool:
    for current in _exception_chain(exc):
        if current.__class__.__name__ == "EmbeddingModelUnavailableError":
            return True
        if current.__class__.__module__.startswith(("httpx", "httpcore")):
            return True
        if isinstance(current, socket.gaierror):
            return True
    return False


def _fake_runtime_reason(exc: BaseException) -> str:
    for current in _exception_chain(exc):
        if current.__class__.__name__ == "EmbeddingModelUnavailableError":
            return "missing_embedding_model"
        if current.__class__.__module__.startswith(("httpx", "httpcore")):
            return "offline_model_resolution"
        if isinstance(current, socket.gaierror):
            return "offline_model_resolution"
    return "native_runtime_error"


def main() -> int:
    _configure_offline_runtime()
    from src.ingest import ingest

    with tempfile.TemporaryDirectory(prefix="ingest-smoke-") as tmp:
        tmp_path = Path(tmp)
        olm_path = tmp_path / "smoke.olm"
        sqlite_path = tmp_path / "email_metadata.db"
        chromadb_path = tmp_path / "chromadb"
        _build_smoke_olm(olm_path)

        try:
            import chromadb  # noqa: F401
        except ModuleNotFoundError:
            _reset_fake_runtime()
            first = _run_ingest_with_fake_runtime(
                olm_path=olm_path,
                sqlite_path=sqlite_path,
                chromadb_path=chromadb_path,
                incremental=False,
            )
            second = _run_ingest_with_fake_runtime(
                olm_path=olm_path,
                sqlite_path=sqlite_path,
                chromadb_path=chromadb_path,
                incremental=True,
            )
            runtime_mode = "fake_runtime_missing_chromadb"
        else:
            try:
                first = ingest(
                    str(olm_path),
                    sqlite_path=str(sqlite_path),
                    chromadb_path=str(chromadb_path),
                    extract_attachments=True,
                    incremental=False,
                    timing=True,
                )
                second = ingest(
                    str(olm_path),
                    sqlite_path=str(sqlite_path),
                    chromadb_path=str(chromadb_path),
                    extract_attachments=True,
                    incremental=True,
                    timing=True,
                )
                runtime_mode = "native_runtime"
            except Exception as exc:
                if not _should_fallback_to_fake_runtime(exc):
                    raise
                _reset_fake_runtime()
                first = _run_ingest_with_fake_runtime(
                    olm_path=olm_path,
                    sqlite_path=sqlite_path,
                    chromadb_path=chromadb_path,
                    incremental=False,
                )
                second = _run_ingest_with_fake_runtime(
                    olm_path=olm_path,
                    sqlite_path=sqlite_path,
                    chromadb_path=chromadb_path,
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
