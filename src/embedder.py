"""Embedding and ChromaDB storage."""

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
        except Exception:
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

        # Deduplicate: skip chunks already in DB *and* duplicates within this batch
        seen: set[str] = set()
        new_chunks: list[EmailChunk] = []
        existing: set[str] = set()
        if not skip_existing_check:
            existing = self.get_existing_ids(refresh=False)
        for chunk in chunks:
            if (skip_existing_check or chunk.chunk_id not in existing) and chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                new_chunks.append(chunk)

        if not new_chunks:
            if show_progress:
                logger.info("All %s chunks already in database, skipping.", len(chunks))
            return 0

        if show_progress and not skip_existing_check:
            logger.info(
                "Embedding %s new chunks (%s already stored).",
                len(new_chunks),
                len(chunks) - len(new_chunks),
            )
        elif show_progress:
            logger.info("Embedding %s chunks with SQLite-ledger/upsert dedupe.", len(new_chunks))

        t_start = time.monotonic()

        # ── Encode ALL chunks in one pass (maximises GPU throughput) ────
        needs_encoding = [c for c in new_chunks if c.embedding is None]
        pre_embedded = [c for c in new_chunks if c.embedding is not None]

        encoded_embeddings: list[list[float]] = []
        result: MultiVectorResult | None = None
        t_encode_start = time.monotonic()
        if needs_encoding:
            texts = [c.text for c in needs_encoding]
            result = self.embedder.encode_all(texts)
            encoded_embeddings = to_builtin_list(result.dense)
        dt_encode = time.monotonic() - t_encode_start

        # Build merged lists: encoded chunks + pre-embedded chunks
        all_ids: list[str] = []
        all_embeddings: list[list[float]] = []
        all_texts: list[str] = []
        all_metadatas: list[dict] = []

        for i, chunk in enumerate(needs_encoding):
            all_ids.append(chunk.chunk_id)
            all_embeddings.append(encoded_embeddings[i])
            all_texts.append(chunk.text)
            all_metadatas.append(chunk.metadata)

        for chunk in pre_embedded:
            all_ids.append(chunk.chunk_id)
            if chunk.embedding is None:  # pragma: no cover — filtered above
                continue
            all_embeddings.append(chunk.embedding)
            all_texts.append(chunk.text)
            all_metadatas.append(chunk.metadata)

        # ── Store to ChromaDB in batches (HNSW-friendly writes) ────────
        added = 0
        t_write_start = time.monotonic()
        for batch_start in range(0, len(all_ids), batch_size):
            batch_end = batch_start + batch_size
            if skip_existing_check:
                self.collection.upsert(
                    ids=all_ids[batch_start:batch_end],
                    embeddings=all_embeddings[batch_start:batch_end],
                    documents=all_texts[batch_start:batch_end],
                    metadatas=all_metadatas[batch_start:batch_end],
                )
            else:
                self.collection.add(
                    ids=all_ids[batch_start:batch_end],
                    embeddings=all_embeddings[batch_start:batch_end],
                    documents=all_texts[batch_start:batch_end],
                    metadatas=all_metadatas[batch_start:batch_end],
                )
            batch_count = min(batch_size, len(all_ids) - batch_start)
            existing.update(all_ids[batch_start:batch_end])
            added += batch_count
        dt_write = time.monotonic() - t_write_start

        if result is not None and result.sparse is not None:
            self.sparse_vectors_stored += self._store_sparse(
                [c.chunk_id for c in needs_encoding],
                result.sparse,
            )
        self._touch_collection_revision()

        if show_progress:
            elapsed = time.monotonic() - t_start
            rate = added / elapsed if elapsed > 0 else 0
            logger.info(
                "Stored %s chunks (%.1fs total: encode=%.1fs, chromadb=%.1fs, %.0f chunks/s)",
                added,
                elapsed,
                dt_encode,
                dt_write,
                rate,
            )

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
        except Exception:
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
