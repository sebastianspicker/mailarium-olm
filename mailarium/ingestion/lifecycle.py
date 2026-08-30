"""Ingestion run lifecycle: checkpoints, terminal state, and resource ownership."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any

from .runtime import IngestRuntime

logger = logging.getLogger(__name__)

_IngestRuntime = IngestRuntime


def _update_ingest_checkpoint_safe(
    *,
    checkpoint_store: Any,
    run_id: int | None,
    olm_path: str,
    last_batch_ordinal: int,
    emails_parsed: int,
    emails_inserted: int,
    last_email_uid: str,
    status: str,
    allow_locked_skip: bool,
    stage: str,
) -> bool:
    """Attempt one checkpoint update without aborting ingest on expected mid-run lock contention."""
    if not checkpoint_store or run_id is None or not hasattr(checkpoint_store, "update_ingest_checkpoint"):
        return False
    started = time.monotonic()
    logger.debug(
        "Attempting ingest checkpoint update (stage=%s, run_id=%s, batch=%s, parsed=%s, inserted=%s, status=%s)",
        stage,
        run_id,
        last_batch_ordinal,
        emails_parsed,
        emails_inserted,
        status,
    )
    try:
        updated = checkpoint_store.update_ingest_checkpoint(
            run_id=run_id,
            olm_path=olm_path,
            last_batch_ordinal=last_batch_ordinal,
            emails_parsed=emails_parsed,
            emails_inserted=emails_inserted,
            last_email_uid=last_email_uid,
            status=status,
            commit=True,
            skip_locked=allow_locked_skip,
        )
    except TypeError:
        updated = checkpoint_store.update_ingest_checkpoint(
            run_id=run_id,
            olm_path=olm_path,
            last_batch_ordinal=last_batch_ordinal,
            emails_parsed=emails_parsed,
            emails_inserted=emails_inserted,
            last_email_uid=last_email_uid,
            status=status,
            commit=True,
        )
    except sqlite3.OperationalError as exc:
        if allow_locked_skip and "locked" in str(exc).lower():
            logger.debug(
                "Skipping ingest checkpoint update during %s because SQLite is locked; ingest will continue and "
                "the next checkpoint opportunity will retry.",
                stage,
                exc_info=True,
            )
            return False
        raise

    elapsed = time.monotonic() - started
    if updated is False and allow_locked_skip:
        logger.debug(
            "Skipping ingest checkpoint update during %s because SQLite is locked after %.3fs; ingest will continue "
            "and the next checkpoint opportunity will retry (run_id=%s)",
            stage,
            elapsed,
            run_id,
        )
        return False
    logger.debug(
        "Completed ingest checkpoint update in %.3fs (stage=%s, run_id=%s)",
        elapsed,
        stage,
        run_id,
    )
    return True


def _initialize_ingest_checkpoint(runtime: _IngestRuntime) -> None:
    """Load or create the checkpoint that controls resumable ingestion."""
    store = runtime.checkpoint_store
    if store and runtime.request.resume and hasattr(store, "latest_ingest_checkpoint"):
        checkpoint = store.latest_ingest_checkpoint(olm_path=runtime.request.olm_path)
        if isinstance(checkpoint, dict):
            runtime.resume_skip = max(int(checkpoint.get("emails_parsed") or 0), 0)
            runtime.resumed = runtime.resume_skip > 0
    if not runtime.bookkeeping_db:
        return
    file_hash = file_size = None
    if os.path.isfile(runtime.request.olm_path):
        file_size = os.path.getsize(runtime.request.olm_path)
        if os.environ.get("INGEST_RECORD_OLM_SHA256", "0") == "1":
            file_hash = runtime.dependencies.hash_file_sha256(runtime.request.olm_path)
    runtime.run_id = runtime.bookkeeping_db.record_ingestion_start(
        runtime.request.olm_path,
        olm_sha256=file_hash,
        file_size_bytes=file_size,
    )
    _checkpoint_ingest(runtime, status="running", stage="ingestion_start", allow_locked_skip=False)


def _initialize_ingest_pipeline(runtime: _IngestRuntime) -> None:
    """Create the parser, chunker, writer, and progress state for ingestion."""
    provenance = runtime.dependencies.resolve_entity_extractor_provenance(runtime.entity_extractor)
    if not runtime.request.dry_run:
        runtime.pipeline = runtime.dependencies.embed_pipeline_cls(
            embedder=runtime.embedder,
            email_db=runtime.email_db,
            entity_extractor_fn=runtime.entity_extractor,
            entity_extractor_key=provenance[0],
            entity_extraction_version=provenance[1],
            batch_size=runtime.request.batch_size,
            ingestion_run_id=runtime.run_id,
        )
        runtime.pipeline.start()
    runtime.progress = runtime.dependencies.make_progress_bar(
        runtime.request.max_emails,
        desc="Ingesting",
        unit="email",
    )
    if runtime.request.incremental and runtime.bookkeeping_db and not runtime.request.embed_images:
        runtime.completed_uids = runtime.bookkeeping_db.completed_ingest_uids(
            attachment_required=runtime.request.extract_attachments,
        )


def _checkpoint_ingest(runtime: _IngestRuntime, *, status: str, stage: str, allow_locked_skip: bool) -> None:
    """Persist progress after a processed batch so ingestion can resume safely."""
    _update_ingest_checkpoint_safe(
        checkpoint_store=runtime.checkpoint_store,
        run_id=runtime.run_id,
        olm_path=runtime.request.olm_path,
        last_batch_ordinal=runtime.batch_ordinal,
        emails_parsed=runtime.counters.emails,
        emails_inserted=int(getattr(runtime.pipeline, "sqlite_inserted", 0) or 0),
        last_email_uid=runtime.last_uid,
        status=status,
        allow_locked_skip=allow_locked_skip,
        stage=stage,
    )


def _complete_ingest(runtime: _IngestRuntime, stats: dict[str, Any]) -> None:
    """Flush outstanding work, close progress, and return final ingest metrics."""
    if runtime.bookkeeping_db and runtime.run_id is not None:
        runtime.bookkeeping_db.record_ingestion_complete(
            runtime.run_id,
            {
                "emails_parsed": runtime.counters.emails,
                "emails_inserted": stats["sqlite_inserted"],
            },
        )
        if runtime.checkpoint_store and hasattr(runtime.checkpoint_store, "clear_ingest_checkpoint"):
            runtime.checkpoint_store.clear_ingest_checkpoint(runtime.run_id, commit=True)
    runtime.dependencies.resolve_runtime_summary(runtime.settings)


def _fail_ingest(runtime: _IngestRuntime, exc: Exception) -> None:
    """Close progress and propagate an ingest failure after recording elapsed time."""
    if runtime.pipeline:
        try:
            worker_error = runtime.pipeline.abort()
            if worker_error is not None and worker_error is not exc:
                logger.warning("Background ingest pipeline error during abort: %s", worker_error)
        except Exception:
            logger.warning("Background ingest pipeline abort failed", exc_info=True)
    if not runtime.bookkeeping_db or runtime.run_id is None:
        return
    _checkpoint_ingest(runtime, status="failed", stage="ingestion_failed", allow_locked_skip=False)
    inserted = int(getattr(runtime.pipeline, "sqlite_inserted", 0) or 0)
    runtime.bookkeeping_db.record_ingestion_failure(
        runtime.run_id,
        error_message=str(exc),
        stats={"emails_parsed": runtime.counters.emails, "emails_inserted": inserted},
    )


def _close_ingest_runtime(runtime: _IngestRuntime) -> None:
    """Close every resource this ingestion invocation created.

    Cleanup is deliberately best-effort per resource: a failed progress,
    vector, or database close must not strand the remaining handles.  The
    control connection can be the same object as the primary archive database,
    so identity de-duplication also avoids a second close.
    """
    progress = getattr(runtime, "progress", None)
    if progress is not None:
        _close_ingest_resource(progress, "progress")

    resources = (
        (getattr(runtime, "embedder", None), "embedder"),
        (getattr(runtime, "control_db", None), "checkpoint database"),
        (getattr(runtime, "email_db", None), "archive database"),
    )
    closed_ids: set[int] = set()
    for resource, label in resources:
        if resource is None or id(resource) in closed_ids:
            continue
        closed_ids.add(id(resource))
        _close_ingest_resource(resource, label)


def _close_ingest_resource(resource: Any, label: str) -> None:
    """Invoke a resource close hook without preventing later cleanup."""
    close = getattr(resource, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        logger.warning("Failed to close ingest %s", label, exc_info=True)
