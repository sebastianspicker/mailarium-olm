"""Packed sparse-vector rows for the learned sparse retrieval lane."""

from __future__ import annotations

import sqlite3
import struct

from ..locking import ArchiveRepository, archive_repository


def _decode_sparse_row(row: sqlite3.Row) -> tuple[str, dict[int, float]]:
    """Decode one packed sparse-vector row into its chunk identifier and weights."""
    count = int(row["num_tokens"])
    token_ids = struct.unpack(f"<{count}i", row["token_ids"])
    weights = struct.unpack(f"<{count}f", row["weights"])
    return str(row["chunk_id"]), dict(zip(token_ids, weights, strict=True))


@archive_repository
class SparseVectorRepository(ArchiveRepository):
    """Insert, count, iterate, and delete packed sparse vectors keyed by chunk id."""

    def insert_sparse_batch(
        self,
        chunk_ids: list[str],
        sparse_vectors: list[dict[int, float]],
        *,
        model_id: str = "",
        model_revision: str = "",
        vocab_hash: str = "",
        generation: int = 1,
    ) -> int:
        """Insert sparse vectors for chunks. Returns count of inserted rows."""
        if len(chunk_ids) != len(sparse_vectors):
            raise ValueError("chunk_ids and sparse_vectors must have same length")

        rows: list[tuple] = []
        for cid, sv in zip(chunk_ids, sparse_vectors, strict=True):
            if not sv:
                continue
            token_ids = sorted(sv.keys())
            weights = [sv[tid] for tid in token_ids]

            token_blob = struct.pack(f"<{len(token_ids)}i", *token_ids)
            weight_blob = struct.pack(f"<{len(weights)}f", *weights)

            rows.append(
                (
                    cid,
                    token_blob,
                    weight_blob,
                    len(token_ids),
                    model_id,
                    model_revision,
                    vocab_hash,
                    max(int(generation), 1),
                )
            )

        external_transaction = self.conn.in_transaction
        if rows:
            self.conn.executemany(
                """INSERT OR REPLACE INTO sparse_vectors(
                       chunk_id, token_ids, weights, num_tokens,
                       model_id, model_revision, vocab_hash, generation
                   ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            if not external_transaction:
                self.conn.commit()
        return len(rows)

    def sparse_vector_count(self) -> int:
        """Count of stored sparse vectors."""
        row = self.conn.execute("SELECT COUNT(*) AS c FROM sparse_vectors").fetchone()
        return row["c"] if row else 0

    def iter_sparse_vectors(
        self,
        *,
        model_id: str | None = None,
        model_revision: str | None = None,
    ):
        """Yield sparse vectors row-by-row to avoid full corpus materialization."""
        # A generator starts executing after the public-method wrapper has
        # returned, so it must retain the operation lock for iteration itself.
        with self.operation():
            for row in self._iter_sparse_rows(model_id=model_id, model_revision=model_revision):
                yield _decode_sparse_row(row)

    def _iter_sparse_rows(
        self,
        *,
        model_id: str | None,
        model_revision: str | None,
    ):
        """Yield sparse-index rows in bounded database batches."""
        sql = "SELECT chunk_id, token_ids, weights, num_tokens FROM sparse_vectors"
        conditions: list[str] = []
        params: list[str] = []
        if model_id is not None:
            conditions.append("model_id = ?")
            params.append(model_id)
        if model_revision is not None:
            conditions.append("model_revision = ?")
            params.append(model_revision)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return self.conn.execute(sql, params)

    def delete_sparse_by_chunk_ids(self, chunk_ids: list[str], *, commit: bool = True) -> int:
        """Delete sparse vectors for an explicit chunk-id list. Returns count deleted."""
        filtered_ids = [chunk_id for chunk_id in chunk_ids if chunk_id]
        if not filtered_ids:
            return 0
        before = self.conn.total_changes
        self.conn.executemany(
            "DELETE FROM sparse_vectors WHERE chunk_id = ?",
            [(chunk_id,) for chunk_id in filtered_ids],
        )
        if commit:
            self.conn.commit()
        return self.conn.total_changes - before
