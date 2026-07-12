"""Embedding and ChromaDB storage."""
# pylint: disable=too-many-branches,too-many-instance-attributes,too-many-locals,too-many-statements

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .chunker import EmailChunk

if TYPE_CHECKING:
    from .email_db import EmailDatabase
from .config import resolve_runtime_settings
from .multi_vector_embedder import MultiVectorEmbedder, MultiVectorResult
from .storage import (
    get_chroma_client,
    get_collection,
    iter_collection_ids,
    modify_collection_metadata,
    to_builtin_list,
)

logger = logging.getLogger(__name__)


def _new_chunks(chunks: list[EmailChunk], existing: set[str], skip_existing_check: bool) -> list[EmailChunk]:
    """Keep first-seen chunks that are not already stored."""
    seen: set[str] = set()
    selected: list[EmailChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        if skip_existing_check or chunk.chunk_id not in existing:
            selected.append(chunk)
    return selected


def _chunk_storage_values(
    chunks: list[EmailChunk], encoded_embeddings: list[list[float]]
) -> tuple[list[str], list[list[float]], list[str], list[dict]]:
    """Return parallel ChromaDB values, retaining the incoming chunk order."""
    needs_encoding = [chunk for chunk in chunks if chunk.embedding is None]
    pre_embedded = [chunk for chunk in chunks if chunk.embedding is not None]
    all_chunks = needs_encoding + pre_embedded
    embeddings = encoded_embeddings + [chunk.embedding for chunk in pre_embedded]
    return (
        [chunk.chunk_id for chunk in all_chunks],
        [embedding for embedding in embeddings if embedding is not None],
        [chunk.text for chunk in all_chunks],
        [chunk.metadata for chunk in all_chunks],
    )


def _store_chunk_batches(
    collection: object,
    values: tuple[list[str], list[list[float]], list[str], list[dict]],
    batch_size: int,
    use_upsert: bool,
    existing: set[str],
) -> int:
    """Persist prepared vectors in HNSW-friendly batches and update the ID cache."""
    all_ids, all_embeddings, all_texts, all_metadatas = values
    write = getattr(collection, "upsert" if use_upsert else "add")
    for batch_start in range(0, len(all_ids), batch_size):
        batch_end = batch_start + batch_size
        write(
            ids=all_ids[batch_start:batch_end],
            embeddings=all_embeddings[batch_start:batch_end],
            documents=all_texts[batch_start:batch_end],
            metadatas=all_metadatas[batch_start:batch_end],
        )
        existing.update(all_ids[batch_start:batch_end])
    return len(all_ids)


def _log_add_progress(added: int, elapsed: float, encode_time: float, write_time: float) -> None:
    """Log one add operation with its stable timing fields."""
    rate = added / elapsed if elapsed > 0 else 0
    logger.info(
        "Stored %s chunks (%.1fs total: encode=%.1fs, chromadb=%.1fs, %.0f chunks/s)",
        added,
        elapsed,
        encode_time,
        write_time,
        rate,
    )


def _log_embedding_start(show_progress: bool, skip_existing_check: bool, new_count: int, total_count: int) -> None:
    """Log the selected deduplication strategy without affecting write behavior."""
    if show_progress and not skip_existing_check:
        logger.info("Embedding %s new chunks (%s already stored).", new_count, total_count - new_count)
    elif show_progress:
        logger.info("Embedding %s chunks with SQLite-ledger/upsert dedupe.", new_count)


def _encode_new_chunks(
    embedder: MultiVectorEmbedder, chunks: list[EmailChunk]
) -> tuple[list[EmailChunk], list[list[float]], MultiVectorResult | None, float]:
    """Encode only chunks lacking vectors and report the elapsed encode time."""
    needs_encoding = [chunk for chunk in chunks if chunk.embedding is None]
    started = time.monotonic()
    result = embedder.encode_all([chunk.text for chunk in needs_encoding]) if needs_encoding else None
    embeddings = to_builtin_list(result.dense) if result is not None else []
    return needs_encoding, embeddings, result, time.monotonic() - started


class EmailEmbedder:
    """Manages embedding and storage of email chunks."""

    def __init__(
        self,
        chromadb_path: str | None = None,
        model_name: str | None = None,
        collection_name: str | None = None,
    ):
        self.settings = resolve_runtime_settings(
            chromadb_path=chromadb_path,
            embedding_model=model_name,
            collection_name=collection_name,
        )

        self.chromadb_path = self.settings.chromadb_path
        self.model_name = self.settings.embedding_model
        self.collection_name = self.settings.collection_name

        self._embedder: MultiVectorEmbedder | None = None
        self._existing_ids_cache: set[str] | None = None
        self._sparse_db: EmailDatabase | None = None  # injected via set_sparse_db()
        self._sparse_db_fallback: EmailDatabase | None = None  # lazy singleton
        self.sparse_store_failures = 0
        self.sparse_vectors_stored = 0

        self.client = get_chroma_client(self.chromadb_path)
        self.collection = get_collection(self.client, self.collection_name)

    @property
    def embedder(self) -> MultiVectorEmbedder:
        """Lazy-loaded multi-vector embedder."""
        if self._embedder is None:
            batch_size = self.settings.embedding_batch_size
            self._embedder = MultiVectorEmbedder(
                model_name=self.model_name,
                device=self.settings.device,
                sparse_enabled=self.settings.sparse_enabled,
                colbert_enabled=self.settings.colbert_rerank_enabled,
                batch_size=batch_size,
                mps_float16=self.settings.mps_float16,
                load_mode=self.settings.embedding_load_mode,
            )
        return self._embedder

    @property
    def model(self) -> MultiVectorEmbedder:
        """Backward-compatible alias for ``embedder``."""
        return self.embedder

    def set_sparse_db(self, db: EmailDatabase) -> None:
        """Inject a shared database connection for sparse vector storage."""
        self._sparse_db = db

    def close(self) -> None:
        """Close any fallback database connection created by _store_sparse."""
        if self._sparse_db_fallback is not None:
            self._sparse_db_fallback.close()
            self._sparse_db_fallback = None

    def get_existing_ids(self, refresh: bool = False) -> set[str]:
        """Get all known chunk IDs, cached for current embedder lifecycle."""
        if self._existing_ids_cache is None or refresh:
            if self.collection.count() == 0:
                self._existing_ids_cache = set()
            else:
                self._existing_ids_cache = set(iter_collection_ids(self.collection))
        return self._existing_ids_cache

    def warmup(self) -> None:
        """Force model load and run a test encode to ensure GPU readiness.

        Call this before starting a long ingestion run so that HuggingFace
        downloads and model loading happen upfront, not inside the first batch.
        """
        self.embedder.warmup()

    def _touch_collection_revision(self) -> None:
        """Bump a collection-level revision marker after successful writes."""
        try:
            modify_collection_metadata(self.collection, {"index_revision": str(time.time_ns())})
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Could not update collection revision metadata", exc_info=True)

    def add_chunks(
        self,
        chunks: list[EmailChunk],
        show_progress: bool = True,
        batch_size: int = 500,
        *,
        skip_existing_check: bool = False,
    ) -> int:
        """Embed and store chunks in ChromaDB and return number of inserted chunks.

        Encoding is performed in a single pass for maximum GPU throughput.
        ChromaDB storage uses ``batch_size`` for HNSW-friendly writes.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer.")

        if not chunks:
            return 0

        existing = set() if skip_existing_check else self.get_existing_ids(refresh=False)
        new_chunks = _new_chunks(chunks, existing, skip_existing_check)

        if not new_chunks:
            if show_progress:
                logger.info("All %s chunks already in database, skipping.", len(chunks))
            return 0

        _log_embedding_start(show_progress, skip_existing_check, len(new_chunks), len(chunks))

        t_start = time.monotonic()

        # ── Encode ALL chunks in one pass (maximises GPU throughput) ────
        needs_encoding, encoded_embeddings, result, dt_encode = _encode_new_chunks(self.embedder, new_chunks)

        # ── Store to ChromaDB in batches (HNSW-friendly writes) ────────
        t_write_start = time.monotonic()
        values = _chunk_storage_values(new_chunks, encoded_embeddings)
        added = _store_chunk_batches(self.collection, values, batch_size, skip_existing_check, existing)
        dt_write = time.monotonic() - t_write_start

        if result is not None and result.sparse is not None:
            self.sparse_vectors_stored += self._store_sparse(
                [c.chunk_id for c in needs_encoding],
                result.sparse,
            )
        self._touch_collection_revision()

        if show_progress:
            elapsed = time.monotonic() - t_start
            _log_add_progress(added, elapsed, dt_encode, dt_write)

        return added

    def _store_sparse(self, ids: list[str], sparse_vectors: list[dict[int, float]]) -> int:
        """Persist sparse vectors to SQLite alongside dense in ChromaDB."""
        try:
            # Use injected DB first, then lazy-cached fallback
            db = self._sparse_db
            if db is None:
                if self._sparse_db_fallback is None:
                    sqlite_path = self.settings.sqlite_path
                    if not sqlite_path or not Path(sqlite_path).exists():
                        logger.debug("Sparse vectors available but no SQLite DB found, skipping storage.")
                        return 0

                    from .email_db import EmailDatabase

                    self._sparse_db_fallback = EmailDatabase(sqlite_path)
                db = self._sparse_db_fallback
            inserted = db.insert_sparse_batch(ids, sparse_vectors)
            logger.debug("Stored %d sparse vectors in SQLite.", inserted)
            return int(inserted)
        except Exception:  # pylint: disable=broad-exception-caught
            self.sparse_store_failures += 1
            logger.warning("Failed to store sparse vectors", exc_info=True)
            return 0

    def delete_chunks_by_uid(self, uid: str) -> int:
        """Delete all chunks for an email UID from ChromaDB. Returns count deleted."""
        existing = self.get_existing_ids(refresh=False)
        chunk_ids = [cid for cid in existing if cid.startswith(f"{uid}__")]
        if not chunk_ids:
            return 0
        self.collection.delete(ids=chunk_ids)
        existing.difference_update(chunk_ids)
        self._touch_collection_revision()
        return len(chunk_ids)

    def upsert_chunks(
        self,
        chunks: list[EmailChunk],
        batch_size: int = 100,
    ) -> int:
        """Re-embed and upsert chunks in ChromaDB (overwrites existing). Returns count."""
        if not chunks:
            return 0

        # Encode all at once (single GPU pass)
        texts = [chunk.text for chunk in chunks]
        ids = [chunk.chunk_id for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        result: MultiVectorResult = self.embedder.encode_all(texts)
        embeddings = to_builtin_list(result.dense)

        # Upsert to ChromaDB in batches
        for batch_start in range(0, len(ids), batch_size):
            batch_end = batch_start + batch_size
            self.collection.upsert(
                ids=ids[batch_start:batch_end],
                embeddings=embeddings[batch_start:batch_end],
                documents=texts[batch_start:batch_end],
                metadatas=metadatas[batch_start:batch_end],
            )

        if result.sparse is not None:
            self.sparse_vectors_stored += self._store_sparse(ids, result.sparse)

        existing = self.get_existing_ids(refresh=False)
        existing.update(ids)
        self._touch_collection_revision()
        return len(chunks)

    def count(self) -> int:
        """Total number of chunks in the database."""
        return self.collection.count()
