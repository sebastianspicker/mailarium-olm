"""Explicit OLM ingestion orchestration API."""

from __future__ import annotations

import time
from typing import Any

from ._ingest_context import _ingest_contexts
from .attachment_processing import _normalize_unprocessed_attachments, _process_attachment
from .lifecycle import _checkpoint_ingest, _close_ingest_runtime, _complete_ingest, _fail_ingest
from .runtime import IngestRuntime, initialize_ingest_runtime

_IngestRuntime = IngestRuntime


def _process_ingest_email(runtime: _IngestRuntime, email: Any) -> None:
    """Chunk one email and queue its database, vector, attachment, and entity work."""
    email_dict = email.to_dict()
    body_chunks = runtime.dependencies.chunk_email(email_dict)
    runtime.counters.chunks += len(body_chunks)
    if runtime.embedder:
        runtime.pending_chunks.extend(body_chunks)
    if runtime.email_db:
        runtime.pending_emails.append(email)
    attachment_count = image_count = 0
    if runtime.attachment_extractor and email.attachment_contents:
        for att_index, (filename, content) in enumerate(email.attachment_contents):
            attachment_delta, image_delta = _process_attachment(
                runtime,
                email,
                email_dict,
                att_index,
                filename,
                content,
            )
            attachment_count += attachment_delta
            image_count += image_delta
    _normalize_unprocessed_attachments(
        email,
        extraction_requested=runtime.request.extract_attachments,
    )
    email._ingest_body_chunk_count = len(body_chunks)
    email._ingest_attachment_chunk_count = attachment_count
    email._ingest_image_chunk_count = image_count
    email._ingest_attachment_requested = runtime.request.extract_attachments
    email._ingest_image_requested = runtime.request.embed_images


def _skip_ingest_email(runtime: _IngestRuntime, email: Any) -> bool:
    """Advance counters and checkpoint state for an already processed message."""
    if runtime.resume_skip and runtime.counters.emails <= runtime.resume_skip:
        runtime.counters.skipped_resume += 1
        return True
    uid = str(getattr(email, "uid", "") or "")
    if runtime.request.incremental and runtime.completed_uids and uid and uid in runtime.completed_uids:
        runtime.counters.skipped_incremental += 1
        return True
    runtime.last_uid = uid
    return False


def _submit_ingest_batch(runtime: _IngestRuntime, *, stage: str) -> None:
    """Queue accumulated emails and chunks, then clear the producer buffers."""
    if not runtime.pipeline or not (runtime.pending_chunks or runtime.pending_emails):
        return
    started = time.monotonic()
    runtime.pipeline.submit(runtime.pending_chunks, runtime.pending_emails)
    runtime.queue_seconds += time.monotonic() - started
    runtime.pending_chunks = []
    runtime.pending_emails = []
    runtime.batch_ordinal += 1
    _checkpoint_ingest(runtime, status="running", stage=stage, allow_locked_skip=True)


def _next_parsed_email(runtime: _IngestRuntime, parser: Any) -> Any:
    """Read the next parser item while measuring parser time."""
    started = time.monotonic()
    email = next(parser)
    runtime.parse_seconds += time.monotonic() - started
    return email


def _run_ingest_parser(runtime: _IngestRuntime) -> None:
    """Consume parsed emails, skip completed work, and flush the final ingest batch."""
    parser = iter(
        runtime.dependencies.parse_olm(
            runtime.request.olm_path,
            extract_attachments=runtime.request.extract_attachments,
        )
    )
    while True:
        try:
            email = _next_parsed_email(runtime, parser)
        except StopIteration:
            break
        runtime.counters.emails += 1
        if not _skip_ingest_email(runtime, email):
            _process_ingest_email(runtime, email)
        runtime.progress.update(1)
        if runtime.request.max_emails is not None and runtime.counters.emails >= runtime.request.max_emails:
            break
        if max(len(runtime.pending_chunks), len(runtime.pending_emails)) >= runtime.request.batch_size:
            _submit_ingest_batch(runtime, stage="mid_run_batch_submit")
    _submit_ingest_batch(runtime, stage="final_batch_submit")
    if runtime.pipeline:
        runtime.pipeline.finish()


def _ingest_timing(runtime: _IngestRuntime) -> dict[str, float]:
    """Report pipeline timings, adding detailed stage metrics when requested."""
    if not runtime.pipeline:
        return {}
    result = {
        "embed_seconds": round(runtime.pipeline.embed_seconds, 1),
        "write_seconds": round(runtime.pipeline.write_seconds, 1),
    }
    if runtime.request.timing:
        result.update(
            parse_seconds=round(runtime.parse_seconds, 1),
            queue_wait_seconds=round(runtime.queue_seconds, 1),
            sqlite_seconds=round(runtime.pipeline.sqlite_seconds, 1),
            entity_seconds=round(runtime.pipeline.entity_seconds, 1),
            analytics_seconds=round(runtime.pipeline.analytics_seconds, 1),
        )
    return result


def _ingest_attachment_telemetry(runtime: _IngestRuntime) -> dict[str, Any]:
    """Summarize attachment provenance, OCR quality, duplication, and failures."""
    counters = runtime.counters
    total = counters.attachments_seen

    def ratio(value: int) -> float:
        return round(value / total, 4) if total else 0.0

    return {
        "attachments_seen": total,
        "locator_rich_count": counters.locator_rich,
        "locator_rich_ratio": ratio(counters.locator_rich),
        "ocr_only_count": counters.ocr_only,
        "ocr_only_ratio": ratio(counters.ocr_only),
        "weak_language_count": counters.weak_language,
        "weak_language_ratio": ratio(counters.weak_language),
        "duplicate_content_attachments": counters.duplicate_content,
        "surface_kind_mix": dict(sorted(runtime.surface_mix.items())),
        "format_extraction_failures": dict(sorted(runtime.format_failures.items())),
    }


def _ingest_result(runtime: _IngestRuntime) -> dict[str, Any]:
    """Assemble the final ingestion counters, timing, and attachment telemetry."""
    pipeline = runtime.pipeline
    counters = runtime.counters
    request = runtime.request
    chunks_added = pipeline.chunks_added if pipeline else 0
    return {
        "emails_parsed": counters.emails,
        "chunks_created": counters.chunks,
        "attachment_chunks": counters.attachment_chunks,
        "image_embeddings": counters.image_embeddings,
        "chunks_added": chunks_added,
        "chunks_skipped": counters.chunks - chunks_added if runtime.embedder else 0,
        "batches_written": pipeline.batches_written if pipeline else 0,
        "total_in_db": runtime.embedder.count() if runtime.embedder else None,
        "sqlite_inserted": pipeline.sqlite_inserted if pipeline else 0,
        "skipped_incremental": counters.skipped_incremental,
        "skipped_resume": counters.skipped_resume,
        "dry_run": request.dry_run,
        "extract_attachments": request.extract_attachments,
        "extract_entities": request.extract_entities,
        "incremental": request.incremental,
        "resume": request.resume,
        "resumed_from_checkpoint": runtime.resumed,
        "elapsed_seconds": round(time.time() - runtime.start_time, 1),
        "timing": _ingest_timing(runtime),
        "ingest_attachment_telemetry": _ingest_attachment_telemetry(runtime),
        "sparse_vectors_stored": (int(getattr(runtime.embedder, "sparse_vectors_stored", 0) or 0) if runtime.embedder else 0),
        "sparse_store_failures": (int(getattr(runtime.embedder, "sparse_store_failures", 0) or 0) if runtime.embedder else 0),
    }


def ingest_impl(**options: Any) -> dict[str, Any]:
    """Parse an OLM file and ingest all emails into the vector database."""
    request, dependencies = _ingest_contexts(options)
    runtime = initialize_ingest_runtime(request, dependencies)
    try:
        _run_ingest_parser(runtime)
        stats = _ingest_result(runtime)
        _complete_ingest(runtime, stats)
        return stats
    except Exception as exc:
        _fail_ingest(runtime, exc)
        raise
    finally:
        _close_ingest_runtime(runtime)
