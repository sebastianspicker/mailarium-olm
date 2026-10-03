"""Rebuildable vector-state maintenance that spans dense, sparse, and ingest rows."""

from __future__ import annotations

from ..locking import ArchiveRepository, archive_repository


@archive_repository
class VectorMaintenanceRepository(ArchiveRepository):
    """Report body-vector provenance and reset all rebuildable vector state."""

    def body_vector_provenance(self) -> dict[str, tuple[str, str, str]]:
        """Return body-vector content hashes and model provenance keyed by chunk id."""
        rows = self.conn.execute(
            "SELECT chunk_id,content_sha256,model_id,model_revision FROM vector_chunks "
            "WHERE embedding_space='text' AND chunk_id NOT LIKE '%__att_%' AND chunk_id NOT LIKE '%__img_%'"
        ).fetchall()
        return {
            str(row["chunk_id"]): (
                str(row["content_sha256"]),
                str(row["model_id"] or ""),
                str(row["model_revision"] or ""),
            )
            for row in rows
        }

    def reset_vector_data(self) -> dict[str, int]:
        """Clear rebuildable vector/sparse rows while retaining email metadata."""
        vector_count_row = self.conn.execute("SELECT COUNT(*) AS count FROM vector_chunks").fetchone()
        sparse_count_row = self.conn.execute("SELECT COUNT(*) AS count FROM sparse_vectors").fetchone()
        vector_count = int(vector_count_row["count"]) if vector_count_row else 0
        sparse_count = int(sparse_count_row["count"]) if sparse_count_row else 0
        self.conn.execute("DELETE FROM vector_index_ops")
        self.conn.execute("DELETE FROM vector_index_state")
        self.conn.execute("DELETE FROM vector_chunks")
        self.conn.execute("DELETE FROM sparse_vectors")
        self.conn.execute(
            """UPDATE email_ingest_state
                  SET vector_status = 'pending',
                      vector_chunk_count = 0,
                      last_error = '',
                      updated_at = datetime('now')"""
        )
        self.conn.commit()
        return {"dense_vectors": vector_count, "sparse_vectors": sparse_count}
