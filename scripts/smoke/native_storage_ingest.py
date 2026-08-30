#!/usr/bin/env python3
"""Release smoke for one native SQLite archive and USearch-backed vector round trip.

This lane deliberately has no fake database, vector collection, or fallback
backend.  It feeds a deterministic precomputed vector into the production
ingest pipeline, avoiding any embedding-model download while exercising the
same relational transaction and SQLiteVectorCollection write path as ingest.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_RUNTIME_ROOT = ROOT / "private" / "runtime" / "native-storage-smoke"


def _email():
    """Return one synthetic parsed message suitable for the production pipeline."""
    from mailarium.ingestion.records import ParsedMessage

    return ParsedMessage(
        message_id="native-storage-smoke@example.test",
        subject="Native storage smoke",
        sender_name="Smoke Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date="2026-08-28T10:00:00",
        body_text="Native SQLite and vector collection proof.",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


def _run_native_pipeline(*, sqlite_path: Path, vector_path: Path) -> dict[str, object]:
    """Persist and reopen one pre-embedded chunk through real production storage."""
    from mailarium.archive import open_archive_database
    from mailarium.ingestion.ingest_embed_pipeline import _EmbedPipeline
    from mailarium.model.chunks import EmailChunk
    from mailarium.retrieval.embedder import EmailEmbedder

    database = open_archive_database(str(sqlite_path))
    embedder = EmailEmbedder(database, vector_index_path=str(vector_path), sqlite_path=str(sqlite_path))
    email = _email()
    email._ingest_body_chunk_count = 1
    email._ingest_attachment_chunk_count = 0
    email._ingest_image_chunk_count = 0
    email._ingest_attachment_requested = False
    email._ingest_image_requested = False
    chunk = EmailChunk(
        uid=email.uid,
        chunk_id=f"{email.uid}__0",
        text="Native SQLite and vector collection proof.",
        metadata={"uid": email.uid, "folder": "Inbox", "sender_email": "sender@example.test"},
        embedding=[1.0, 0.0],
    )
    try:
        pipeline = _EmbedPipeline(embedder, database, entity_extractor_fn=None, batch_size=8)
        pipeline.start()
        pipeline.submit([chunk], [email])
        pipeline.finish()
        if pipeline.sqlite_inserted != 1 or pipeline.chunks_added != 1:
            raise RuntimeError(f"native pipeline counts were not one: {pipeline.sqlite_inserted=}, {pipeline.chunks_added=}")
        if database.get_email_full(email.uid) is None or embedder.collection.count() != 1:
            raise RuntimeError("native pipeline did not persist both canonical email and vector rows")
    finally:
        embedder.close()
        database.close()

    reopened = open_archive_database(str(sqlite_path))
    reopened_embedder = EmailEmbedder(reopened, vector_index_path=str(vector_path), sqlite_path=str(sqlite_path))
    try:
        result = reopened_embedder.collection.query(
            query_embeddings=[[1.0, 0.0]],
            n_results=1,
            include=["metadatas", "distances"],
        )
        if result.get("ids") != [[chunk.chunk_id]]:
            raise RuntimeError("reopened SQLiteVectorCollection did not return the native chunk")
        verification = reopened_embedder.collection.verify()
        if not verification.get("healthy"):
            raise RuntimeError(f"native vector collection verification failed: {verification}")
        return {
            "email_uid": email.uid,
            "chunk_id": chunk.chunk_id,
            "vector_backend": verification.get("backend"),
            "vector_status": verification.get("status"),
            "collection_count": reopened_embedder.collection.count(),
        }
    finally:
        reopened_embedder.close()
        reopened.close()


def main() -> int:
    """Run the non-fallback native storage closure smoke and print structured proof."""
    os.environ.setdefault("RUNTIME_PROFILE", "offline-test")
    os.environ.setdefault("EMBEDDING_LOAD_MODE", "local_only")
    os.environ.setdefault("SPACY_AUTO_DOWNLOAD_DURING_INGEST", "0")
    _RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=_RUNTIME_ROOT) as temporary:
        temp = Path(temporary)
        result = _run_native_pipeline(sqlite_path=temp / "archive.db", vector_path=temp / "vectors")
    print(json.dumps({"status": "passed", "runtime_kind": "native_storage", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
