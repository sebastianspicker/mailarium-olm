"""SQLite-authoritative vector storage with an optional USearch accelerator."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .database import ArchiveDatabase
from .usearch_loader import import_index

DEFAULT_PAGE_SIZE = 1000
_OVERFETCH_MULTIPLIER = 4

logger = logging.getLogger(__name__)


def _operation_context(operation: Callable[[], AbstractContextManager[None]]) -> AbstractContextManager[None]:
    """Open a verified database-operation context-manager factory."""
    return operation()


@dataclass(frozen=True)
class VectorRecord:
    """Canonical vector row persisted in SQLite."""

    vector_id: int
    chunk_id: str
    email_uid: str
    embedding_space: str
    kind: str
    document: str
    metadata: dict[str, Any]
    embedding: np.ndarray


@dataclass(frozen=True)
class VectorHit:
    """One hydrated vector-search result."""

    chunk_id: str
    document: str
    metadata: dict[str, Any]
    distance: float


def to_builtin_list(value: Any) -> list[list[float]]:
    """Convert array-like query results to nested Python lists."""
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


class SQLiteVectorCollection:
    """Collection-like facade backed by SQLite and accelerated by USearch.

    SQLite owns IDs, documents, metadata, and float32 vectors.  The USearch
    file is derived state and can always be rebuilt from the database.
    """

    def __init__(
        self,
        *,
        database: ArchiveDatabase,
        vector_index_path: str,
        embedding_space: str = "text",
        model_id: str = "",
        model_revision: str = "",
    ) -> None:
        """Configure explicitly bound SQLite storage and its rebuildable accelerator.

        Raises:
            ValueError: If ``embedding_space`` is empty.
        """
        if not embedding_space:
            raise ValueError("embedding_space must not be empty")
        self.vector_index_path = Path(vector_index_path)
        self.embedding_space = embedding_space
        self.model_id = model_id
        self.model_revision = model_revision
        self._database: ArchiveDatabase | None = database
        self._index: Any | None = None
        self._index_dimensions: int | None = None
        self._cached_index_state: tuple[Any, ...] | None = None
        self._accelerator_error: str = ""
        self._lock = threading.RLock()

    @property
    def metadata(self) -> dict[str, Any]:
        """Report durable index revision, status, item count, and checksum for the embedding space."""
        row = (
            self._connection()
            .execute(
                """SELECT applied_seq, item_count, file_sha256, status, updated_at
               FROM vector_index_state
              WHERE embedding_space = ?""",
                (self.embedding_space,),
            )
            .fetchone()
        )
        if row is None:
            pending = self._pending_sequence()
            return {
                "backend": "usearch",
                "embedding_space": self.embedding_space,
                "index_revision": str(pending),
                "status": "pending" if pending else "empty",
            }
        return {
            "backend": "usearch",
            "embedding_space": self.embedding_space,
            "index_revision": str(row["applied_seq"]),
            "item_count": int(row["item_count"]),
            "file_sha256": str(row["file_sha256"] or ""),
            "status": str(row["status"]),
            "updated_at": str(row["updated_at"] or ""),
        }

    def close(self) -> None:
        """Release derived resources without closing the caller-owned archive."""
        with self._lock:
            self._database = None
            self._index = None
            self._cached_index_state = None

    def count(self) -> int:
        """Count vectors only after confirming the active embedding generation is consistent."""
        with self._database_operation():
            self._assert_active_generation()
            row = (
                self._connection()
                .execute(
                    "SELECT COUNT(*) AS count FROM vector_chunks WHERE embedding_space = ?",
                    (self.embedding_space,),
                )
                .fetchone()
            )
        return int(row["count"]) if row else 0

    def add(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
    ) -> None:
        """Insert new vectors and reject duplicate chunk IDs."""
        self._write_rows(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            replace=False,
        )

    def upsert(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
    ) -> None:
        """Insert or replace vectors while retaining stable integer keys."""
        self._write_rows(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            replace=True,
        )

    def delete(self, *, ids: Sequence[str]) -> None:
        """Delete explicit chunk IDs from canonical storage and journal the change."""
        filtered = [str(chunk_id) for chunk_id in ids if str(chunk_id)]
        if not filtered:
            return
        with self._lock, self._database_operation():
            conn = self._connection()
            self._assert_active_generation()
            external_transaction = conn.in_transaction
            encoded_ids = json.dumps(filtered)
            rows = conn.execute(
                """SELECT vector_id FROM vector_chunks
                   WHERE embedding_space = ?
                     AND chunk_id IN (SELECT value FROM json_each(?))""",
                (self.embedding_space, encoded_ids),
            ).fetchall()
            vector_ids = [int(row["vector_id"]) for row in rows]
            if not vector_ids:
                return
            conn.executemany(
                "INSERT INTO vector_index_ops(embedding_space, operation, vector_id) VALUES(?, 'delete', ?)",
                [(self.embedding_space, vector_id) for vector_id in vector_ids],
            )
            conn.execute(
                """DELETE FROM vector_chunks
                   WHERE embedding_space = ?
                     AND chunk_id IN (SELECT value FROM json_each(?))""",
                (self.embedding_space, encoded_ids),
            )
            if not external_transaction:
                conn.commit()
                self.checkpoint()

    def reset(self) -> int:
        """Clear this embedding space without deleting relational email data."""
        with self._lock, self._database_operation():
            conn = self._connection()
            rows = conn.execute(
                "SELECT vector_id FROM vector_chunks WHERE embedding_space = ?",
                (self.embedding_space,),
            ).fetchall()
            vector_ids = [int(row["vector_id"]) for row in rows]
            conn.executemany(
                "INSERT INTO vector_index_ops(embedding_space, operation, vector_id) VALUES(?, 'delete', ?)",
                [(self.embedding_space, vector_id) for vector_id in vector_ids],
            )
            conn.execute(
                "DELETE FROM vector_chunks WHERE embedding_space = ?",
                (self.embedding_space,),
            )
            conn.commit()
            self.checkpoint()
            return len(vector_ids)

    def get(
        self,
        *,
        ids: Sequence[str] | None = None,
        include: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        where: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Hydrate canonical rows using the established collection response shape."""
        requested = set(include or ())
        with self._database_operation():
            self._assert_active_generation()
            # Filtering must precede pagination: applying SQL LIMIT first can
            # make a later matching row invisible to callers.
            rows = self._select_records(ids=ids)
        records = [record for record in rows if _metadata_matches(record.metadata, where)]
        start = max(int(offset), 0)
        stop = None if limit is None else start + max(int(limit), 0)
        records = records[start:stop]
        payload: dict[str, Any] = {"ids": [record.chunk_id for record in records]}
        if "documents" in requested:
            payload["documents"] = [record.document for record in records]
        if "metadatas" in requested:
            payload["metadatas"] = [record.metadata for record in records]
        if "embeddings" in requested:
            payload["embeddings"] = [record.embedding.tolist() for record in records]
        return payload

    def query(
        self,
        *,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int,
        include: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search vectors, hydrate from SQLite, and exact-rerank candidates."""
        query = _validated_query_vector(query_embeddings, n_results)
        if query is None:
            return _empty_query_result(include)
        with self._lock, self._database_operation():
            self._assert_active_generation()
            records = self._candidate_records(query, n_results, where)
        hits = _exact_hits(query, records, n_results)
        return _query_result(hits, include)

    def checkpoint(self) -> None:
        """Rebuild and atomically persist the derived USearch accelerator.

        A snapshot is tagged with the highest journal sequence it observed.  It
        is published only while that sequence is still current, so a concurrent
        writer can never have its newer operation deleted by this checkpoint.
        """
        with self._lock, self._database_operation(), self._checkpoint_file_lock():
            conn = self._connection()
            if conn.in_transaction:
                return
            self._assert_active_generation()
            for _attempt in range(2):
                records, applied_seq, dimensions, index = self._checkpoint_snapshot(conn)

                # This transaction excludes writers through the file publish and
                # state update.  If the snapshot is stale, release it and retry.
                conn.execute("BEGIN IMMEDIATE")
                current_seq = self._pending_sequence()
                if current_seq != applied_seq:
                    conn.rollback()
                    continue
                status = self._publish_checkpoint(
                    conn,
                    records=records,
                    applied_seq=applied_seq,
                    dimensions=dimensions,
                    index=index,
                )
                if status == "usearch_unavailable":
                    logger.warning(
                        "USearch is unavailable; using exact SQLite vector search for %s vectors",
                        self.embedding_space,
                    )
                return
            logger.info("Vector checkpoint for %s deferred because its snapshot became stale", self.embedding_space)

    def _checkpoint_snapshot(
        self,
        conn: sqlite3.Connection,
    ) -> tuple[list[VectorRecord], int, int, Any | None]:
        """Read one durable vector snapshot and build its optional accelerator."""
        conn.execute("BEGIN")
        try:
            records = self._select_records()
            applied_seq = self._pending_sequence()
        finally:
            conn.rollback()
        dimensions = _uniform_vector_dimensions(records, self.embedding_space)
        try:
            index = _build_usearch_index(records, dimensions) if records else None
        except ImportError as exc:
            index = None
            self._accelerator_error = str(exc)
        return records, applied_seq, dimensions, index

    def _publish_checkpoint(
        self,
        conn: sqlite3.Connection,
        *,
        records: Sequence[VectorRecord],
        applied_seq: int,
        dimensions: int,
        index: Any | None,
    ) -> str:
        """Publish a current snapshot and consume its journal rows atomically."""
        try:
            file_sha256, status = self._publish_index_file(records, index, dimensions)
            self._record_state(
                dimensions=dimensions,
                applied_seq=applied_seq,
                item_count=len(records),
                file_sha256=file_sha256,
                status=status,
            )
            conn.execute(
                "DELETE FROM vector_index_ops WHERE embedding_space = ? AND sequence <= ?",
                (self.embedding_space, applied_seq),
            )
            conn.commit()
            if index is not None and self._index is index:
                self._cached_index_state = self._index_state_snapshot()
        except Exception:
            conn.rollback()
            raise
        return status

    def _publish_index_file(
        self,
        records: Sequence[VectorRecord],
        index: Any | None,
        dimensions: int,
    ) -> tuple[str, str]:
        """Replace derived index state for one already-validated snapshot."""
        if not records:
            self._remove_index_file()
            self._index = None
            self._index_dimensions = None
            self._cached_index_state = None
            return "", "healthy"
        if index is None:
            return "", "usearch_unavailable"
        file_sha256 = self._save_index_atomically(index)
        self._index = index
        self._index_dimensions = dimensions
        self._accelerator_error = ""
        return file_sha256, "healthy"

    def verify(self) -> dict[str, Any]:
        """Validate the derived file checksum against recorded state."""
        state = self.metadata
        expected = str(state.get("file_sha256") or "")
        path = self._index_file
        actual = _sha256_file(path) if path.exists() else ""
        healthy = state.get("status") in {"healthy", "usearch_unavailable"} and (
            state.get("status") == "usearch_unavailable" or expected == actual
        )
        return {
            **state,
            "path": str(path),
            "actual_sha256": actual,
            "healthy": bool(healthy),
            "accelerator_error": self._accelerator_error,
        }

    def _write_rows(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
        replace: bool,
    ) -> None:
        """Validate parallel inputs, persist vector rows transactionally, and checkpoint owned transactions."""
        _validate_parallel_rows(ids, embeddings, documents, metadatas)
        if not ids:
            return
        with self._lock, self._database_operation():
            conn = self._connection()
            self._assert_active_generation()
            external_transaction = conn.in_transaction
            for chunk_id, embedding_value, document, metadata_value in zip(
                ids,
                embeddings,
                documents,
                metadatas,
                strict=True,
            ):
                metadata = dict(metadata_value)
                embedding = np.asarray(embedding_value, dtype=np.float32)
                if embedding.ndim != 1 or embedding.size == 0:
                    raise ValueError(f"Embedding for {chunk_id!r} must be a non-empty 1-D vector")
                self._write_record(
                    conn,
                    chunk_id=str(chunk_id),
                    document=str(document or ""),
                    metadata=metadata,
                    embedding=embedding,
                    replace=replace,
                )
            if not external_transaction:
                conn.commit()
                self.checkpoint()

    def _write_record(
        self,
        conn: sqlite3.Connection,
        *,
        chunk_id: str,
        document: str,
        metadata: dict[str, Any],
        embedding: np.ndarray,
        replace: bool,
    ) -> None:
        """Upsert chunk metadata and float32 vector bytes, then journal the accelerator update."""
        existing = conn.execute(
            "SELECT vector_id FROM vector_chunks WHERE chunk_id = ? AND embedding_space = ?",
            (chunk_id, self.embedding_space),
        ).fetchone()
        if existing is not None and not replace:
            raise ValueError(f"Vector already exists for chunk {chunk_id!r}")
        email_uid = str(metadata.get("uid") or metadata.get("email_uid") or _email_uid_from_chunk_id(chunk_id))
        kind = str(metadata.get("chunk_type") or metadata.get("kind") or self.embedding_space)
        metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_sha256 = hashlib.sha256(document.encode("utf-8")).hexdigest()
        conn.execute(
            """INSERT INTO vector_chunks(
                   chunk_id, email_uid, embedding_space, kind, document,
                   metadata_json, content_sha256, model_id, model_revision, updated_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(chunk_id, embedding_space) DO UPDATE SET
                   email_uid=excluded.email_uid,
                   kind=excluded.kind,
                   document=excluded.document,
                   metadata_json=excluded.metadata_json,
                   content_sha256=excluded.content_sha256,
                   model_id=excluded.model_id,
                   model_revision=excluded.model_revision,
                   updated_at=datetime('now')""",
            (
                chunk_id,
                email_uid,
                self.embedding_space,
                kind,
                document,
                metadata_json,
                content_sha256,
                self.model_id,
                self.model_revision,
            ),
        )
        row = conn.execute(
            "SELECT vector_id FROM vector_chunks WHERE chunk_id = ? AND embedding_space = ?",
            (chunk_id, self.embedding_space),
        ).fetchone()
        assert row is not None
        vector_id = int(row["vector_id"])
        vector_blob = embedding.astype("<f4", copy=False).tobytes()
        vector_sha256 = hashlib.sha256(vector_blob).hexdigest()
        conn.execute(
            """INSERT INTO dense_vectors(vector_id, dimensions, vector_f32, vector_sha256)
               VALUES(?, ?, ?, ?)
               ON CONFLICT(vector_id) DO UPDATE SET
                   dimensions=excluded.dimensions,
                   vector_f32=excluded.vector_f32,
                   vector_sha256=excluded.vector_sha256""",
            (vector_id, int(embedding.size), vector_blob, vector_sha256),
        )
        conn.execute(
            "INSERT INTO vector_index_ops(embedding_space, operation, vector_id) VALUES(?, 'upsert', ?)",
            (self.embedding_space, vector_id),
        )

    def _candidate_records(
        self,
        query: np.ndarray,
        n_results: int,
        where: Mapping[str, Any] | None,
    ) -> list[VectorRecord]:
        """Query USearch with overfetch and fall back to exact SQLite filtering when needed."""
        self._ensure_index()
        if self._index is None or self._index_dimensions != int(query.size):
            return self._filtered_records(where)
        requested = min(max(n_results * _OVERFETCH_MULTIPLIER, n_results), self.count())
        try:
            matches = self._index.search(query, requested)
            vector_ids = [int(key) for key in matches.keys]
        except Exception:
            logger.warning("USearch query failed; using exact SQLite scan", exc_info=True)
            return self._filtered_records(where)
        records = self._select_records(vector_ids=vector_ids)
        filtered = [record for record in records if _metadata_matches(record.metadata, where)]
        if len(filtered) >= min(n_results, self.count()):
            return filtered
        return self._filtered_records(where)

    def _filtered_records(self, where: Mapping[str, Any] | None) -> list[VectorRecord]:
        """Return all canonical records that satisfy one metadata predicate."""
        return [record for record in self._select_records() if _metadata_matches(record.metadata, where)]

    def _ensure_index(self) -> None:
        """Checkpoint pending operations and restore or rebuild the cached USearch accelerator when stale."""
        if self._accelerator_error:
            return
        self._assert_active_generation()
        pending = (
            self._connection()
            .execute(
                "SELECT 1 FROM vector_index_ops WHERE embedding_space = ? LIMIT 1",
                (self.embedding_space,),
            )
            .fetchone()
        )
        if pending is not None:
            self.checkpoint()
        path = self._index_file
        state = self._index_state_snapshot()
        if self._index is not None:
            if self._cached_index_state == state and self._index_state_matches_storage(path):
                return
            # Another process may have checkpointed after this collection loaded
            # its accelerator. The journal can already be empty, so state, not
            # pending operations, is the authority for invalidating this cache.
            self._index = None
            self._index_dimensions = None
            self._cached_index_state = None
        if not self._index_state_matches_storage(path):
            self.checkpoint()
            return
        try:
            Index = import_index()
            index = Index.restore(str(path), view=False)
            if index is None:
                raise RuntimeError("USearch index restore returned no index")
            self._index = index
            self._index_dimensions = int(index.ndim)
            self._cached_index_state = self._index_state_snapshot()
        except ImportError as exc:
            self._accelerator_error = str(exc)
        except Exception:
            logger.warning("USearch index restore failed; rebuilding from SQLite", exc_info=True)
            self._index = None
            self._index_dimensions = None
            self._cached_index_state = None
            self.checkpoint()

    def _select_records(
        self,
        *,
        ids: Sequence[str] | None = None,
        vector_ids: Sequence[int] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[VectorRecord]:
        """Load vector records by chunk or vector ID while preserving accelerator rank order."""
        where_parts = ["vc.embedding_space = ?"]
        params: list[Any] = [self.embedding_space]
        if ids is not None:
            filtered_ids = [str(chunk_id) for chunk_id in ids if str(chunk_id)]
            if not filtered_ids:
                return []
            where_parts.append(f"vc.chunk_id IN ({','.join('?' for _ in filtered_ids)})")
            params.extend(filtered_ids)
        if vector_ids is not None:
            filtered_vector_ids = [int(vector_id) for vector_id in vector_ids]
            if not filtered_vector_ids:
                return []
            where_parts.append(f"vc.vector_id IN ({','.join('?' for _ in filtered_vector_ids)})")
            params.extend(filtered_vector_ids)
        sql = f"""SELECT vc.vector_id, vc.chunk_id, vc.email_uid, vc.embedding_space,
                         vc.kind, vc.document, vc.metadata_json,
                         dv.dimensions, dv.vector_f32
                    FROM vector_chunks AS vc
                    JOIN dense_vectors AS dv ON dv.vector_id = vc.vector_id
                   WHERE {" AND ".join(where_parts)}
                ORDER BY vc.vector_id"""
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend((max(int(limit), 0), max(int(offset), 0)))
        rows = self._connection().execute(sql, params).fetchall()
        records = [_record_from_row(row) for row in rows]
        if vector_ids is not None:
            rank = {int(vector_id): index for index, vector_id in enumerate(vector_ids)}
            records.sort(key=lambda record: rank.get(record.vector_id, len(rank)))
        return records

    def _connection(self) -> sqlite3.Connection:
        """Return the connection from the explicitly bound archive database."""
        if self._database is None:
            raise RuntimeError("SQLiteVectorCollection is closed")
        return self._database.conn

    @contextmanager
    def _database_operation(self) -> Iterator[None]:
        """Cooperate with the explicitly bound archive operation lock."""
        if self._database is None:
            raise RuntimeError("SQLiteVectorCollection is closed")
        with _operation_context(self._database.operation):
            yield

    @contextmanager
    def _checkpoint_file_lock(self) -> Iterator[None]:
        """Serialize checkpoint publication across processes for one index file."""
        import fcntl

        self.vector_index_path.mkdir(parents=True, exist_ok=True)
        lock_path = self.vector_index_path / f".{self.embedding_space}.usearch.lock"
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _assert_active_generation(self) -> None:
        """Reject mixed or mismatched embeddings instead of searching them together."""
        rows = (
            self._connection()
            .execute(
                """SELECT model_id, model_revision FROM vector_chunks
                 WHERE embedding_space = ? GROUP BY model_id, model_revision""",
                (self.embedding_space,),
            )
            .fetchall()
        )
        generations = {(str(row["model_id"] or ""), str(row["model_revision"] or "")) for row in rows}
        expected = (self.model_id, self.model_revision)
        if generations and generations != {expected}:
            raise ValueError(
                f"Embedding generation mismatch in space {self.embedding_space!r}; "
                "reset and re-embed this space before reading or writing it"
            )

    def _index_state_matches_storage(self, path: Path) -> bool:
        """Verify index status, model generation, checksum, and item count against SQLite."""
        row = (
            self._connection()
            .execute(
                """SELECT item_count, file_sha256, status, model_id, model_revision
                 FROM vector_index_state WHERE embedding_space = ?""",
                (self.embedding_space,),
            )
            .fetchone()
        )
        if row is None or str(row["status"]) != "healthy" or not path.exists():
            return False
        if (str(row["model_id"] or ""), str(row["model_revision"] or "")) != (self.model_id, self.model_revision):
            return False
        if str(row["file_sha256"] or "") != _sha256_file(path):
            return False
        return int(row["item_count"]) == self.count()

    def _index_state_snapshot(self) -> tuple[Any, ...] | None:
        """Return the durable index fields used to invalidate an in-memory accelerator."""
        row = (
            self._connection()
            .execute(
                """SELECT applied_seq, dimensions, item_count, file_sha256, status, model_id, model_revision
                     FROM vector_index_state WHERE embedding_space = ?""",
                (self.embedding_space,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return (
            int(row["applied_seq"]),
            int(row["dimensions"]),
            int(row["item_count"]),
            str(row["file_sha256"] or ""),
            str(row["status"]),
            str(row["model_id"] or ""),
            str(row["model_revision"] or ""),
        )

    @property
    def _index_file(self) -> Path:
        return self.vector_index_path / f"{self.embedding_space}.usearch"

    def _pending_sequence(self) -> int:
        """Return the newest unapplied journal sequence or last applied sequence."""
        row = (
            self._connection()
            .execute(
                "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM vector_index_ops WHERE embedding_space = ?",
                (self.embedding_space,),
            )
            .fetchone()
        )
        if row and int(row["sequence"]):
            return int(row["sequence"])
        row = (
            self._connection()
            .execute(
                "SELECT COALESCE(MAX(applied_seq), 0) AS sequence FROM vector_index_state WHERE embedding_space = ?",
                (self.embedding_space,),
            )
            .fetchone()
        )
        return int(row["sequence"]) if row else 0

    def _save_index_atomically(self, index: Any) -> str:
        """Fsync a temporary USearch file, atomically publish it, and return its checksum."""
        self.vector_index_path.mkdir(parents=True, exist_ok=True)
        target = self._index_file
        temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        index.save(str(temporary))
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return _sha256_file(target)

    def _remove_index_file(self) -> None:
        """Delete the derived accelerator file without failing when it is absent."""
        self._index_file.unlink(missing_ok=True)

    def _record_state(
        self,
        *,
        dimensions: int,
        applied_seq: int,
        item_count: int,
        file_sha256: str,
        status: str,
    ) -> None:
        """Upsert durable accelerator dimensions, revision, checksum, and health status."""
        self._connection().execute(
            """INSERT INTO vector_index_state(
                   embedding_space, backend, metric, dimensions, model_id,
                   model_revision, applied_seq, item_count, file_sha256, status, updated_at
               ) VALUES(?, 'usearch', 'cos', ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(embedding_space) DO UPDATE SET
                   backend='usearch',
                   metric='cos',
                   dimensions=excluded.dimensions,
                   model_id=excluded.model_id,
                   model_revision=excluded.model_revision,
                   applied_seq=excluded.applied_seq,
                   item_count=excluded.item_count,
                   file_sha256=excluded.file_sha256,
                   status=excluded.status,
                   updated_at=datetime('now')""",
            (
                self.embedding_space,
                dimensions,
                self.model_id,
                self.model_revision,
                applied_seq,
                item_count,
                file_sha256,
                status,
            ),
        )


def get_vector_collection(
    *,
    database: ArchiveDatabase,
    vector_index_path: str,
    embedding_space: str = "text",
    model_id: str = "",
    model_revision: str = "",
) -> SQLiteVectorCollection:
    """Create the canonical vector collection for one embedding space."""
    return SQLiteVectorCollection(
        database=database,
        vector_index_path=vector_index_path,
        embedding_space=embedding_space,
        model_id=model_id,
        model_revision=model_revision,
    )


def iter_vector_ids(collection: SQLiteVectorCollection, page_size: int = DEFAULT_PAGE_SIZE) -> Iterator[str]:
    """Iterate all IDs in stable vector-ID order."""
    offset = 0
    while True:
        batch = collection.get(include=[], limit=page_size, offset=offset)
        rows = batch.get("ids") or []
        if not rows:
            break
        yield from rows
        offset += len(rows)


def iter_vector_metadatas(
    collection: SQLiteVectorCollection,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    """Iterate all metadata rows in stable vector-ID order."""
    offset = 0
    while True:
        batch = collection.get(include=["metadatas"], limit=page_size, offset=offset)
        rows = batch.get("metadatas") or []
        if not rows:
            break
        yield from (dict(row) for row in rows if row)
        offset += len(rows)


def _validate_parallel_rows(
    ids: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    documents: Sequence[str],
    metadatas: Sequence[Mapping[str, Any]],
) -> None:
    """Reject vector write batches whose IDs, vectors, documents, and metadata differ in length."""
    lengths = {len(ids), len(embeddings), len(documents), len(metadatas)}
    if len(lengths) != 1:
        raise ValueError("ids, embeddings, documents, and metadatas must have equal lengths")


def _record_from_row(row: sqlite3.Row) -> VectorRecord:
    """Decode one SQLite vector row into owned float32 data and safe metadata."""
    dimensions = int(row["dimensions"])
    embedding = np.frombuffer(row["vector_f32"], dtype="<f4", count=dimensions).copy()
    try:
        metadata = json.loads(str(row["metadata_json"] or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return VectorRecord(
        vector_id=int(row["vector_id"]),
        chunk_id=str(row["chunk_id"]),
        email_uid=str(row["email_uid"] or ""),
        embedding_space=str(row["embedding_space"]),
        kind=str(row["kind"] or ""),
        document=str(row["document"] or ""),
        metadata=metadata,
        embedding=embedding,
    )


def _build_usearch_index(records: Sequence[VectorRecord], dimensions: int) -> Any:
    """Build a cosine USearch index keyed by stable database vector IDs."""
    Index = import_index()
    index = Index(
        ndim=dimensions,
        metric="cos",
        dtype="f32",
        connectivity=16,
        expansion_add=128,
        expansion_search=128,
    )
    keys = np.asarray([record.vector_id for record in records], dtype=np.uint64)
    vectors = np.vstack([record.embedding for record in records]).astype(np.float32, copy=False)
    index.add(keys, vectors, copy=True)
    return index


def _uniform_vector_dimensions(records: Sequence[VectorRecord], embedding_space: str) -> int:
    """Return the shared vector width or reject mixed dimensions in one space."""
    if not records:
        return 0
    dimensions = int(records[0].embedding.size)
    if any(record.embedding.size != dimensions for record in records):
        raise ValueError(f"Mixed vector dimensions in embedding space {embedding_space!r}")
    return dimensions


def _exact_hits(query: np.ndarray, records: Sequence[VectorRecord], n_results: int) -> list[VectorHit]:
    """Rank records by bounded cosine distance when the accelerator is unavailable."""
    query_norm = float(np.linalg.norm(query))
    if query_norm <= 1e-12:
        return []
    scored: list[tuple[float, int, VectorRecord]] = []
    for record in records:
        if record.embedding.size != query.size:
            continue
        vector_norm = float(np.linalg.norm(record.embedding))
        similarity = 0.0 if vector_norm <= 1e-12 else float(np.dot(query, record.embedding) / (query_norm * vector_norm))
        distance = max(0.0, min(2.0, 1.0 - similarity))
        scored.append((distance, record.vector_id, record))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [
        VectorHit(
            chunk_id=record.chunk_id,
            document=record.document,
            metadata=record.metadata,
            distance=distance,
        )
        for distance, _vector_id, record in scored[:n_results]
    ]


def _metadata_matches(metadata: Mapping[str, Any], where: Mapping[str, Any] | None) -> bool:
    """Evaluate equality, logical, and operator metadata filters against one record."""
    if not where:
        return True
    for key, expected in where.items():
        if key in {"$and", "$or"}:
            return _logical_metadata_matches(metadata, key, expected)
        if not _field_metadata_matches(metadata.get(key), expected):
            return False
    return True


def _logical_metadata_matches(metadata: Mapping[str, Any], operator: str, expected: Any) -> bool:
    """Evaluate a logical metadata predicate with the original short-circuit rules."""
    if not isinstance(expected, Sequence):
        return False
    matches = (isinstance(condition, Mapping) and _metadata_matches(metadata, condition) for condition in expected)
    return all(matches) if operator == "$and" else any(matches)


def _field_metadata_matches(actual: Any, expected: Any) -> bool:
    """Evaluate one direct or operator-based metadata field predicate."""
    if isinstance(expected, Mapping):
        return _operator_matches(actual, expected)
    return actual == expected


def _operator_matches(actual: Any, conditions: Mapping[str, Any]) -> bool:
    """Require every operator condition in a metadata predicate to pass."""
    return all(_operator_condition_matches(actual, operator, expected) for operator, expected in conditions.items())


def _operator_condition_matches(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate supported equality, membership, comparison, and containment operators."""
    if operator == "$eq":
        return actual == expected
    if operator == "$ne":
        return actual != expected
    if operator in {"$in", "$nin"}:
        return _sequence_operator_matches(actual, operator, expected)
    if operator in {"$gt", "$gte", "$lt", "$lte"}:
        return _comparison_operator_matches(actual, operator, expected)
    if operator == "$contains":
        return str(expected) in str(actual or "")
    return False


def _sequence_operator_matches(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate $in or $nin only when the expected operand is a non-string sequence."""
    if not isinstance(expected, Sequence) or isinstance(expected, str):
        return False
    contained = actual in expected
    return contained if operator == "$in" else not contained


def _comparison_operator_matches(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate ordered comparisons and treat incompatible types as non-matches."""
    try:
        comparisons = {
            "$gt": actual > expected,
            "$gte": actual >= expected,
            "$lt": actual < expected,
            "$lte": actual <= expected,
        }
    except TypeError:
        return False
    return bool(comparisons[operator])


def _email_uid_from_chunk_id(chunk_id: str) -> str:
    """Recover the parent email UID from the stable chunk-ID prefix."""
    return chunk_id.split("__", 1)[0]


def _sha256_file(path: Path) -> str:
    """Hash a file incrementally in one-megabyte blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validated_query_vector(
    query_embeddings: Sequence[Sequence[float]],
    n_results: int,
) -> np.ndarray | None:
    """Validate the single-query contract and return a usable float32 vector."""
    if len(query_embeddings) > 1:
        raise ValueError("SQLiteVectorCollection supports exactly one query embedding")
    if not query_embeddings or n_results <= 0:
        return None
    query = np.asarray(query_embeddings[0], dtype=np.float32)
    if query.ndim != 1 or query.size == 0:
        return None
    return query


def _query_result(hits: Sequence[VectorHit], include: Sequence[str] | None) -> dict[str, Any]:
    """Project exact hits into the collection's nested query response shape."""
    requested = set(include or ("documents", "metadatas", "distances"))
    result: dict[str, Any] = {"ids": [[hit.chunk_id for hit in hits]]}
    if "documents" in requested:
        result["documents"] = [[hit.document for hit in hits]]
    if "metadatas" in requested:
        result["metadatas"] = [[hit.metadata for hit in hits]]
    if "distances" in requested:
        result["distances"] = [[hit.distance for hit in hits]]
    return result


def _empty_query_result(include: Sequence[str] | None) -> dict[str, Any]:
    """Return correctly nested empty fields for the requested collection query includes."""
    requested = set(include or ("documents", "metadatas", "distances"))
    payload: dict[str, Any] = {"ids": [[]]}
    for field in ("documents", "metadatas", "distances"):
        if field in requested:
            payload[field] = [[]]
    return payload
