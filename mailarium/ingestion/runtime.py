"""Owned runtime construction for an ingestion invocation."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import replace
from typing import Any

from ._ingest_context import _IngestCounters, _IngestDependencies, _IngestRequest, _IngestRuntime

IngestCounters = _IngestCounters
IngestDependencies = _IngestDependencies
IngestRequest = _IngestRequest
IngestRuntime = _IngestRuntime

logger = logging.getLogger(__name__)


def _preload_models(embedder, entity_extractor_fn) -> float:
    """Preload models for embedder and entity extractor to avoid first-use latency.

    Args:
        embedder: The embedder instance to warm up.
        entity_extractor_fn: Optional entity extraction function to preload.

    Returns:
        The number of seconds spent preloading models.
    """
    start = time.monotonic()
    if embedder:
        embedder.warmup()
    if entity_extractor_fn:
        try:
            from mailarium.investigation.nlp_entity_extractor import preload as _preload_nlp

            _preload_nlp()
        except ImportError:
            logger.debug("Optional NLP component not available", exc_info=True)
    return time.monotonic() - start


def build_ingest_runtime_resources(
    *,
    settings,
    dry_run: bool,
    vector_index_path: str | None,
    sqlite_path: str | None,
) -> tuple[Any, Any]:
    """Build and configure the runtime components (embedder and email database).

    Args:
        settings: Application settings object.
        dry_run: If True, skip actual database/embedder initialization.
        vector_index_path: Optional path to the rebuildable USearch directory.
        sqlite_path: Optional path to SQLite database file.

    Returns:
        A tuple of (embedder, email_db) instances, or (None, None) for dry run.

    Raises:
        RuntimeError: If required dependencies are missing.
    """
    email_db = None
    if not dry_run:
        from mailarium.archive import open_archive_database

        resolved_sqlite = sqlite_path or settings.sqlite_path
        email_db = open_archive_database(resolved_sqlite)
    embedder = None
    if email_db is not None:
        try:
            from mailarium.retrieval.embedder import EmailEmbedder
        except ModuleNotFoundError as exc:
            email_db.close()
            raise RuntimeError("Missing runtime dependency. Install project dependencies with 'uv sync --all-extras'") from exc
        embedder = EmailEmbedder(
            email_db,
            vector_index_path=vector_index_path,
            sqlite_path=sqlite_path or settings.sqlite_path,
        )
    return embedder, email_db


def _ingest_extractors(request: _IngestRequest, dependencies: _IngestDependencies) -> tuple[Any, ...]:
    """Load only the attachment and image extractors enabled by the request."""
    attachment_extractor = attachment_ocr_extractor = classify_text_state = None
    if request.extract_attachments:
        from .attachment_extractor import classify_text_extraction_state, extract_attachment_text_ocr, extract_text_with_reason

        attachment_extractor = extract_text_with_reason
        attachment_ocr_extractor = extract_attachment_text_ocr
        classify_text_state = classify_text_extraction_state
    image_embedder = image_matcher = None
    if request.embed_images and not request.dry_run and dependencies.should_enable_image_embedding():
        from .attachment_extractor import _get_image_embedder, extract_image_embedding, is_image_attachment

        if _get_image_embedder().is_available:
            image_embedder = extract_image_embedding
            image_matcher = is_image_attachment
    return attachment_extractor, attachment_ocr_extractor, classify_text_state, image_embedder, image_matcher


def _ingest_control_db(email_db: Any, sqlite_path: str) -> Any:
    """Open a short-timeout control connection only for the real database backend."""
    if not email_db:
        return None
    from mailarium.archive import ArchiveDatabase, open_archive_database

    if not isinstance(email_db, ArchiveDatabase):
        return None
    return open_archive_database(
        sqlite_path,
        busy_timeout_ms=int(os.environ.get("INGEST_CHECKPOINT_BUSY_TIMEOUT_MS", "100")),
    )


def _initialize_ingest_runtime(request: _IngestRequest, dependencies: _IngestDependencies) -> _IngestRuntime:
    """Open configured stores and construct the runtime objects for one ingest run."""
    settings = dependencies.get_settings()
    sqlite_path = request.sqlite_path or settings.sqlite_path
    embedder, email_db = dependencies.build_runtime(
        settings=settings,
        dry_run=request.dry_run,
        vector_index_path=request.vector_index_path,
        sqlite_path=sqlite_path,
    )
    control_db = _ingest_control_db(email_db, sqlite_path)
    entity_extractor = dependencies.resolve_entity_extractor(request.extract_entities, request.dry_run)
    extractors = _ingest_extractors(request, dependencies)
    if request.embed_images and extractors[3] is None:
        request = replace(request, embed_images=False)
    _preload_models(embedder, entity_extractor)
    runtime = _IngestRuntime(
        request=request,
        dependencies=dependencies,
        settings=settings,
        embedder=embedder,
        email_db=email_db,
        control_db=control_db,
        checkpoint_store=control_db or email_db,
        bookkeeping_db=control_db or email_db,
        entity_extractor=entity_extractor,
        attachment_extractor=extractors[0],
        attachment_ocr_extractor=extractors[1],
        classify_text_state=extractors[2],
        image_embedder=extractors[3],
        image_matcher=extractors[4],
        pipeline=None,
        progress=None,
        run_id=None,
        resume_skip=0,
        resumed=False,
        completed_uids=set(),
        counters=_IngestCounters(),
        pending_chunks=[],
        pending_emails=[],
        content_hashes=set(),
        surface_mix={},
        format_failures={},
        start_time=time.time(),
    )
    # Lifecycle setup takes ownership only after all resources above exist.
    # Keep this import local to avoid a construction/lifecycle import cycle.
    from .lifecycle import _initialize_ingest_checkpoint, _initialize_ingest_pipeline

    _initialize_ingest_checkpoint(runtime)
    _initialize_ingest_pipeline(runtime)
    return runtime


initialize_ingest_runtime = _initialize_ingest_runtime
