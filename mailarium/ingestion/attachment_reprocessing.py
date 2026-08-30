"""Recovery of degraded attachment surfaces and their vector projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mailarium.config import get_settings
from mailarium.model.attachment_identity import ensure_attachment_identity

from .maintenance import _delete_chunk_ids


@dataclass(frozen=True)
class _ReprocessRequest:
    """Describe the inputs that select attachment reprocessing work."""

    olm_path: str
    vector_index_path: str | None
    sqlite_path: str | None
    batch_size: int
    force: bool


@dataclass(frozen=True)
class _ReprocessDependencies:
    """Collect injectable services needed by attachment reprocessing."""

    parse_olm: Any
    chunk_attachment: Any
    extract_text: Any
    extract_ocr: Any


@dataclass
class _ReprocessProgress:
    """Track outcomes accumulated during attachment reprocessing."""

    updated: int = 0
    recovered_attachments: int = 0
    ocr_recovered: int = 0
    chunks_added: int = 0
    chunks_deleted: int = 0


@dataclass
class _ReprocessRuntime:
    """Own initialized state for a single attachment reprocessing run."""

    request: _ReprocessRequest
    dependencies: _ReprocessDependencies
    email_db: Any
    embedder: Any
    target_uids: set[str]
    attachment_ids_by_uid: dict[str, list[str]]
    progress: _ReprocessProgress
    pending_chunks: list[Any]
    pending_emails: list[Any]
    pending_completion_rows: list[dict[str, object]]
    pending_delete_ids: set[str]


def _select_reprocess_uids(email_db: Any, *, force: bool) -> set[str]:
    """Select all attachment owners or only owners with degraded extraction."""
    if force:
        rows = email_db.conn.execute("SELECT DISTINCT email_uid FROM attachments").fetchall()
    else:
        rows = email_db.conn.execute(
            "SELECT email_uid FROM email_ingest_state WHERE attachment_status IN ('degraded', 'unsupported')"
        ).fetchall()
    return {str(row["email_uid"]) for row in rows if str(row["email_uid"] or "")}


def _attachment_chunk_ids_by_uid(embedder: Any) -> dict[str, list[str]]:
    """Load existing attachment chunk identifiers grouped by email UID."""
    getter = getattr(embedder, "get_existing_ids", None)
    raw_ids = getter(refresh=False) if callable(getter) else set()
    result: dict[str, list[str]] = {}
    for raw_chunk_id in raw_ids if isinstance(raw_ids, set) else set():
        chunk_id = str(raw_chunk_id or "")
        email_uid, marker, _remainder = chunk_id.partition("__att_")
        if marker and email_uid:
            result.setdefault(email_uid, []).append(chunk_id)
    return result


def _initialize_reprocess_runtime(
    request: _ReprocessRequest,
    dependencies: _ReprocessDependencies,
) -> _ReprocessRuntime:
    """Open stores, select target messages, and prepare reprocessing state."""
    from mailarium.archive import open_archive_database
    from mailarium.retrieval.embedder import EmailEmbedder

    settings = get_settings()
    email_db = open_archive_database(request.sqlite_path or settings.sqlite_path)
    embedder = None
    try:
        embedder = EmailEmbedder(
            email_db,
            vector_index_path=request.vector_index_path,
            sqlite_path=request.sqlite_path or settings.sqlite_path,
        )
        return _ReprocessRuntime(
            request=request,
            dependencies=dependencies,
            email_db=email_db,
            embedder=embedder,
            target_uids=_select_reprocess_uids(email_db, force=request.force),
            attachment_ids_by_uid=_attachment_chunk_ids_by_uid(embedder),
            progress=_ReprocessProgress(),
            pending_chunks=[],
            pending_emails=[],
            pending_completion_rows=[],
            pending_delete_ids=set(),
        )
    except Exception:
        close_embedder = getattr(embedder, "close", None)
        if callable(close_embedder):
            close_embedder()
        email_db.close()
        raise


def _set_reprocessed_attachment_text(
    email: Any,
    *,
    att_index: int,
    filename: str,
    attachment_id: str,
    content_sha256: str,
    text: str,
    state: str,
    ocr_used: bool,
) -> str:
    """Attach recovered text, surfaces, and quality metadata to an attachment."""
    from .attachment_processing import _set_extracted_attachment_text_evidence

    return _set_extracted_attachment_text_evidence(
        email,
        att_index=att_index,
        filename=filename,
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        text=text,
        state=state,
        ocr_used=ocr_used,
    )


def _set_reprocessed_attachment_failure(
    email: Any,
    *,
    att_index: int,
    filename: str,
    attachment_id: str,
    content_sha256: str,
    state: str,
    reason: str | None,
) -> None:
    """Record extraction failure metadata without inventing searchable text."""
    from .attachment_processing import _mailbox_attachment_locator, _set_attachment_evidence

    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state=state,
        evidence_strength="weak_reference",
        ocr_used=False,
        failure_reason=reason,
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state=state,
            attachment_id=attachment_id,
            content_sha256=content_sha256,
        ),
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        locator_version=2,
    )


def _extract_reprocessed_attachment(
    runtime: _ReprocessRuntime,
    email: Any,
    att_index: int,
    filename: str,
    content: bytes,
) -> list[Any]:
    """Re-extract one attachment and create replacement chunks when text is usable."""
    from .attachment_extractor import attachment_ocr_available_for, classify_text_extraction_state
    from .attachment_processing import _textless_attachment_state_with_ocr

    attachments = getattr(email, "attachments", None) or []
    metadata = attachments[att_index] if 0 <= att_index < len(attachments) else {}
    mime_type = str((metadata or {}).get("mime_type") or "")
    attachment_id, content_sha256 = ensure_attachment_identity(metadata, content_bytes=content)
    text = runtime.dependencies.extract_text(filename, content, mime_type=mime_type)
    ocr_used = False
    state, reason = "text_extracted", None
    if not text:
        text = runtime.dependencies.extract_ocr(filename, content) if runtime.dependencies.extract_ocr else None
        ocr_used = bool(text)
    if not text:
        state, reason = _textless_attachment_state_with_ocr(
            filename=filename,
            mime_type=mime_type,
            ocr_attempted=bool(runtime.dependencies.extract_ocr),
            ocr_available=attachment_ocr_available_for(filename, mime_type=mime_type),
        )
        _set_reprocessed_attachment_failure(
            email,
            att_index=att_index,
            filename=filename,
            attachment_id=attachment_id,
            content_sha256=content_sha256,
            state=state,
            reason=reason,
        )
        return []
    state = classify_text_extraction_state(filename, text, ocr_used=ocr_used)
    normalized = _set_reprocessed_attachment_text(
        email,
        att_index=att_index,
        filename=filename,
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        text=text,
        state=state,
        ocr_used=ocr_used,
    )
    runtime.progress.recovered_attachments += 1
    runtime.progress.ocr_recovered += int(ocr_used)
    return runtime.dependencies.chunk_attachment(
        email.uid,
        filename,
        text,
        email.to_dict(),
        att_index=att_index,
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        normalized_text=normalized,
        extraction_state=state,
        evidence_strength="strong_text",
        ocr_used=ocr_used,
    )


def _reprocess_completion_row(runtime: _ReprocessRuntime, email: Any, chunk_count: int) -> dict[str, object]:
    """Build the ingest-state completion row after one email is reprocessed."""
    from .ingest_embed_pipeline import _attachment_completion_status

    state_row = runtime.email_db.conn.execute(
        "SELECT body_chunk_count, image_chunk_count FROM email_ingest_state WHERE email_uid = ?",
        (email.uid,),
    ).fetchone()
    body_count = int((state_row["body_chunk_count"] if state_row else 0) or 0)
    image_count = int((state_row["image_chunk_count"] if state_row else 0) or 0)
    email._ingest_body_chunk_count = body_count
    email._ingest_attachment_chunk_count = chunk_count
    email._ingest_image_chunk_count = image_count
    email._ingest_attachment_requested = True
    email._ingest_image_requested = bool(image_count)
    status = _attachment_completion_status(email)
    return {
        "email_uid": email.uid,
        "body_chunk_count": body_count,
        "attachment_chunk_count": chunk_count,
        "image_chunk_count": image_count,
        "vector_chunk_count": body_count + chunk_count + image_count,
        "attachment_status": "completed" if status == "pending" else status,
        "image_status": "completed" if image_count else "not_requested",
    }


def _queue_reprocessed_email(runtime: _ReprocessRuntime, email: Any, chunks: list[Any]) -> None:
    """Queue replacement chunks and stale IDs for one reprocessed email."""
    from .attachment_processing import _attachments_safe_for_stale_cleanup, _normalize_unprocessed_attachments

    _normalize_unprocessed_attachments(email, extraction_requested=True)
    old_ids = runtime.attachment_ids_by_uid.get(email.uid, [])
    new_ids = {str(chunk.chunk_id) for chunk in chunks if str(getattr(chunk, "chunk_id", "") or "")}
    if old_ids and _attachments_safe_for_stale_cleanup(email):
        runtime.pending_delete_ids.update(chunk_id for chunk_id in old_ids if chunk_id not in new_ids)
    runtime.pending_chunks.extend(chunks)
    runtime.pending_emails.append(email)
    runtime.pending_completion_rows.append(_reprocess_completion_row(runtime, email, len(chunks)))
    runtime.progress.updated += 1


def _flush_reprocess_batch(runtime: _ReprocessRuntime) -> None:
    """Persist queued metadata and vectors, then clear the reprocessing buffers."""
    if not any((runtime.pending_chunks, runtime.pending_emails, runtime.pending_completion_rows, runtime.pending_delete_ids)):
        return
    if runtime.pending_chunks:
        writer = getattr(runtime.embedder, "upsert_chunks", None) or runtime.embedder.add_chunks
        runtime.progress.chunks_added += writer(runtime.pending_chunks, batch_size=runtime.request.batch_size)
    if runtime.pending_delete_ids:
        runtime.progress.chunks_deleted += _delete_chunk_ids(
            embedder=runtime.embedder,
            email_db=runtime.email_db,
            chunk_ids=sorted(runtime.pending_delete_ids),
            commit_sparse=False,
        )
    for email in runtime.pending_emails:
        runtime.email_db.update_v7_metadata(email, commit=False)
    if runtime.pending_completion_rows:
        runtime.email_db.mark_ingest_batch_completed(runtime.pending_completion_rows, commit=False)
    runtime.email_db.conn.commit()
    runtime.pending_chunks.clear()
    runtime.pending_emails.clear()
    runtime.pending_completion_rows.clear()
    runtime.pending_delete_ids.clear()


def _run_attachment_reprocessing(runtime: _ReprocessRuntime) -> None:
    """Re-extract target attachments and flush bounded persistence batches."""
    parser = runtime.dependencies.parse_olm(runtime.request.olm_path, extract_attachments=True)
    threshold = max(int(runtime.request.batch_size), 1)
    for email in parser:
        if email.uid not in runtime.target_uids:
            continue
        chunks: list[Any] = []
        for att_index, (filename, content) in enumerate(getattr(email, "attachment_contents", []) or []):
            chunks.extend(_extract_reprocessed_attachment(runtime, email, att_index, filename, content))
        _queue_reprocessed_email(runtime, email, chunks)
        if len(runtime.pending_chunks) >= threshold or len(runtime.pending_emails) >= threshold:
            _flush_reprocess_batch(runtime)
    _flush_reprocess_batch(runtime)


def _close_reprocess_runtime(runtime: _ReprocessRuntime) -> None:
    """Close the embedder and email database after reprocessing."""
    close_embedder = getattr(runtime.embedder, "close", None)
    if callable(close_embedder):
        close_embedder()
    runtime.email_db.close()


def _reprocess_result(runtime: _ReprocessRuntime) -> dict[str, Any]:
    """Summarize reprocessing counts for the command result."""
    progress = runtime.progress
    return {
        "updated": progress.updated,
        "total_candidates": len(runtime.target_uids),
        "recovered_attachments": progress.recovered_attachments,
        "ocr_recovered": progress.ocr_recovered,
        "chunks_deleted": progress.chunks_deleted,
        "chunks_added": progress.chunks_added,
        "message": (
            f"Reprocessed degraded attachments for {progress.updated} emails; "
            f"recovered {progress.recovered_attachments} attachments ({progress.ocr_recovered} via OCR)."
        ),
    }


def reprocess_degraded_attachments_impl(
    olm_path: str,
    *,
    vector_index_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 100,
    force: bool = False,
    parse_olm_fn=None,
    chunk_attachment_fn=None,
    attachment_text_extractor=None,
    attachment_ocr_extractor=None,
) -> dict[str, Any]:
    """Re-parse degraded mailbox attachments and attempt OCR recovery for image attachments."""
    if parse_olm_fn is None or chunk_attachment_fn is None or attachment_text_extractor is None:
        return {"updated": 0, "total_candidates": 0, "message": "Attachment reprocessing dependencies are unavailable."}
    request = _ReprocessRequest(olm_path, vector_index_path, sqlite_path, batch_size, force)
    dependencies = _ReprocessDependencies(
        parse_olm_fn,
        chunk_attachment_fn,
        attachment_text_extractor,
        attachment_ocr_extractor,
    )
    runtime = _initialize_reprocess_runtime(request, dependencies)
    try:
        if not runtime.target_uids:
            return {"updated": 0, "total_candidates": 0, "message": "No degraded attachment rows require reprocessing."}
        _run_attachment_reprocessing(runtime)
        return _reprocess_result(runtime)
    finally:
        _close_reprocess_runtime(runtime)
