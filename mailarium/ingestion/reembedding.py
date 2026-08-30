"""Bounded and rollback-safe vector rebuild operations."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from mailarium.config import get_settings

from .maintenance import _delete_chunk_ids


def reembed_impl(
    vector_index_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 100,
    resume: bool = False,
) -> dict[str, Any]:
    """Re-chunk and re-embed all emails from corrected SQLite body text."""
    from mailarium.archive import open_archive_database
    from mailarium.retrieval.embedder import EmailEmbedder

    from .chunker import _chunk_forensic_email_surface, chunk_email

    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")

    settings = get_settings()
    resolved_sqlite = sqlite_path or settings.sqlite_path
    email_db = open_archive_database(resolved_sqlite)
    try:
        embedder = EmailEmbedder(
            email_db,
            vector_index_path=vector_index_path,
            sqlite_path=resolved_sqlite,
        )
        try:
            all_uids = email_db.all_uids()
            if not all_uids:
                return {"reembedded": 0, "total": 0, "message": "No emails in database."}

            progress = _ReembedProgress()
            existing_ids = embedder.get_existing_ids(refresh=False)
            stored_body_rows = _stored_body_vector_rows(email_db) if resume else {}
            body_chunk_ids_by_uid: dict[str, list[str]] = {}
            for chunk_id in existing_ids:
                if "__att_" in chunk_id or "__img_" in chunk_id:
                    continue
                uid = chunk_id.split("__", 1)[0]
                body_chunk_ids_by_uid.setdefault(uid, []).append(chunk_id)

            for uid in sorted(all_uids):
                email_dict = email_db.get_email_for_reembed(uid)
                if email_dict is None:
                    progress.skipped_no_body += 1
                    continue
                chunks = [*chunk_email(email_dict), *_chunk_forensic_email_surface(email_dict)]
                old_ids = body_chunk_ids_by_uid.get(uid, [])
                if resume and _body_vectors_are_current(
                    chunks,
                    old_ids,
                    stored_body_rows,
                    model_id=embedder.model_name,
                    model_revision=embedder.settings.embedding_model_revision,
                ):
                    progress.resumed += 1
                    continue
                _queue_reembed_email(
                    email_db,
                    embedder,
                    progress,
                    uid,
                    chunks,
                    old_ids,
                    batch_size,
                )
            _flush_reembed_batch(email_db, embedder, progress, batch_size)

            return {
                "reembedded": progress.reembedded,
                "total": len(all_uids),
                "chunks_deleted": progress.chunks_deleted,
                "chunks_added": progress.chunks_added,
                "skipped_no_body": progress.skipped_no_body,
                "resumed": progress.resumed,
                "message": (
                    f"Re-embedded {progress.reembedded} of {len(all_uids)} emails "
                    f"({progress.chunks_added} chunks). {progress.resumed} resumed; "
                    f"{progress.skipped_no_body} skipped (no body text)."
                ),
            }
        finally:
            embedder.close()
    finally:
        email_db.close()


@dataclass
class _PendingReembedEmail:
    """Track one email until every bounded replacement batch has succeeded."""

    chunks: list[Any]
    old_ids: list[str]
    new_ids: set[str]
    queued: int = 0
    upserted: int = 0
    snapshot: dict[str, Any] | None = None

    @property
    def obsolete_ids(self) -> list[str]:
        """Return prior body chunks no longer represented by this email."""
        return sorted(chunk_id for chunk_id in self.old_ids if chunk_id not in self.new_ids)


@dataclass
class _ReembedProgress:
    """Keep bounded cross-email vector work and command result counters."""

    pending_chunks: list[Any]
    pending_counts: dict[str, int]
    active: dict[str, _PendingReembedEmail]
    reembedded: int = 0
    chunks_deleted: int = 0
    chunks_added: int = 0
    skipped_no_body: int = 0
    resumed: int = 0

    def __init__(self) -> None:
        self.pending_chunks = []
        self.pending_counts = {}
        self.active = {}


def _stored_body_vector_rows(email_db: Any) -> dict[str, tuple[str, str, str]]:
    """Load body-vector content and model provenance for resumable re-embedding."""
    rows = email_db.conn.execute(
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


def _body_vectors_are_current(
    chunks: list[Any],
    old_ids: list[str],
    stored_rows: dict[str, tuple[str, str, str]],
    *,
    model_id: str,
    model_revision: str,
) -> bool:
    """Return whether one email already has the exact requested body-vector projection."""
    expected_ids = {str(chunk.chunk_id) for chunk in chunks}
    if not expected_ids or expected_ids != set(old_ids):
        return False
    for chunk in chunks:
        expected = (
            hashlib.sha256(str(chunk.text).encode("utf-8")).hexdigest(),
            model_id,
            model_revision,
        )
        if stored_rows.get(str(chunk.chunk_id)) != expected:
            return False
    return True


def _queue_reembed_email(
    email_db: Any,
    embedder: Any,
    progress: _ReembedProgress,
    uid: str,
    chunks: list[Any],
    old_ids: list[str],
    batch_size: int,
) -> None:
    """Queue one email into capped cross-email upsert batches."""
    new_ids = {str(chunk.chunk_id) for chunk in chunks if str(getattr(chunk, "chunk_id", "") or "")}
    pending = _PendingReembedEmail(chunks=chunks, old_ids=sorted(old_ids), new_ids=new_ids)
    progress.active[uid] = pending
    if not chunks:
        _flush_reembed_batch(email_db, embedder, progress, batch_size)
        _complete_reembed_email(email_db, embedder, progress, uid)
        return

    while pending.queued < len(chunks):
        capacity = batch_size - len(progress.pending_chunks)
        count = min(capacity, len(chunks) - pending.queued)
        start = pending.queued
        progress.pending_chunks.extend(chunks[start : start + count])
        progress.pending_counts[uid] = progress.pending_counts.get(uid, 0) + count
        pending.queued += count
        if len(progress.pending_chunks) == batch_size:
            _flush_reembed_batch(email_db, embedder, progress, batch_size)


def _flush_reembed_batch(email_db: Any, embedder: Any, progress: _ReembedProgress, batch_size: int) -> None:
    """Upsert one bounded batch, restoring any email that spans a failed batch."""
    if not progress.pending_chunks:
        return
    batch_counts = progress.pending_counts
    try:
        for uid in batch_counts:
            pending = progress.active[uid]
            if pending.snapshot is None and (pending.upserted or pending.queued < len(pending.chunks)):
                pending.snapshot = _snapshot_vector_chunks(embedder, pending.old_ids)
        added = int(embedder.upsert_chunks(progress.pending_chunks, batch_size=batch_size))
    except Exception:
        _restore_pending_reembed_emails(embedder, progress.active)
        raise
    for uid, count in batch_counts.items():
        pending = progress.active[uid]
        pending.upserted += count
        if pending.upserted == len(pending.chunks):
            _complete_reembed_email(email_db, embedder, progress, uid)
    progress.chunks_added += added
    progress.pending_chunks = []
    progress.pending_counts = {}


def _complete_reembed_email(email_db: Any, embedder: Any, progress: _ReembedProgress, uid: str) -> None:
    """Delete obsolete chunks only after every replacement chunk has been written."""
    pending = progress.active.pop(uid)
    progress.chunks_deleted += _delete_chunk_ids(
        embedder=embedder,
        email_db=email_db,
        chunk_ids=pending.obsolete_ids,
    )
    progress.reembedded += 1
    pending.chunks.clear()


def _restore_pending_reembed_emails(embedder: Any, active: dict[str, _PendingReembedEmail]) -> None:
    """Restore every email that had already crossed a successful bounded batch."""
    try:
        for pending in active.values():
            if pending.snapshot is not None:
                _restore_vector_chunks(embedder, pending.snapshot, pending.new_ids.difference(pending.old_ids))
    except Exception as rollback_error:
        raise RuntimeError("Re-embedding failed and the prior vector rows could not be restored") from rollback_error


def _reembed_email(
    email_db: Any, embedder: Any, uid: str, ids_by_uid: dict[str, list[str]], batch_size: int, chunker: Any
) -> tuple[int, int] | None:
    """Replace one email's vector chunks and delete identifiers no longer produced."""
    email_dict = email_db.get_email_for_reembed(uid)
    if email_dict is None:
        return None
    chunks = chunker(email_dict)
    new_ids = {str(chunk.chunk_id) for chunk in chunks if str(getattr(chunk, "chunk_id", "") or "")}
    old_ids = sorted(ids_by_uid.get(uid, []))
    obsolete = sorted(chunk_id for chunk_id in old_ids if chunk_id not in new_ids)
    added = _upsert_reembed_chunks(
        embedder,
        chunks,
        old_ids=old_ids,
        new_ids=new_ids,
        batch_size=batch_size,
    )
    deleted = _delete_chunk_ids(embedder=embedder, email_db=email_db, chunk_ids=obsolete) if obsolete else 0
    return added, deleted


def _upsert_reembed_chunks(
    embedder: Any,
    chunks: list[Any],
    *,
    old_ids: list[str],
    new_ids: set[str],
    batch_size: int,
) -> int:
    """Upsert one email, restoring its prior rows if a later batch fails."""
    if len(chunks) <= batch_size:
        return int(embedder.upsert_chunks(chunks, batch_size=batch_size))

    snapshot = _snapshot_vector_chunks(embedder, old_ids)
    try:
        return int(embedder.upsert_chunks(chunks, batch_size=batch_size))
    except Exception:
        try:
            _restore_vector_chunks(embedder, snapshot, new_ids.difference(old_ids))
        except Exception as rollback_error:
            raise RuntimeError("Re-embedding failed and the prior vector rows could not be restored") from rollback_error
        raise


def _snapshot_vector_chunks(embedder: Any, chunk_ids: list[str]) -> dict[str, Any]:
    """Capture existing vector rows required for multi-batch rollback."""
    if not chunk_ids:
        return {"ids": []}
    snapshot = embedder.collection.get(
        ids=chunk_ids,
        include=["embeddings", "documents", "metadatas"],
    )
    returned_ids = list(snapshot.get("ids") or [])
    if set(returned_ids) != set(chunk_ids):
        raise RuntimeError("Cannot safely re-embed: failed to snapshot every existing body chunk")
    return dict(snapshot)


def _restore_vector_chunks(embedder: Any, snapshot: dict[str, Any], new_only_ids: set[str]) -> None:
    """Remove partially inserted IDs and restore every prior vector row."""
    if new_only_ids:
        embedder.collection.delete(ids=sorted(new_only_ids))
    old_ids = list(snapshot.get("ids") or [])
    if not old_ids:
        return
    restore_kwargs: dict[str, Any] = {"ids": old_ids}
    for key in ("embeddings", "documents", "metadatas"):
        value = snapshot.get(key)
        if value is not None:
            restore_kwargs[key] = value
    embedder.collection.upsert(**restore_kwargs)
