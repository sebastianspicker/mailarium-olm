"""Private typed contexts used by the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _IngestRequest:
    olm_path: str
    chromadb_path: str | None
    sqlite_path: str | None
    batch_size: int
    max_emails: int | None
    dry_run: bool
    extract_attachments: bool
    extract_entities: bool
    incremental: bool
    embed_images: bool
    resume: bool
    timing: bool


@dataclass(frozen=True)
class _IngestDependencies:
    get_settings: Any
    resolve_runtime_summary: Any
    should_enable_image_embedding: Any
    parse_olm: Any
    chunk_email: Any
    chunk_attachment: Any
    hash_file_sha256: Any
    resolve_entity_extractor: Any
    resolve_entity_extractor_provenance: Any
    exchange_entities_from_email: Any
    embed_pipeline_cls: Any
    make_progress_bar: Any


@dataclass
class _IngestCounters:
    emails: int = 0
    chunks: int = 0
    attachment_chunks: int = 0
    image_embeddings: int = 0
    attachments_seen: int = 0
    locator_rich: int = 0
    ocr_only: int = 0
    weak_language: int = 0
    duplicate_content: int = 0
    skipped_incremental: int = 0
    skipped_resume: int = 0


@dataclass
class _IngestRuntime:
    request: _IngestRequest
    dependencies: _IngestDependencies
    settings: Any
    embedder: Any
    email_db: Any
    control_db: Any
    checkpoint_store: Any
    bookkeeping_db: Any
    entity_extractor: Any
    attachment_extractor: Any
    attachment_ocr_extractor: Any
    classify_text_state: Any
    image_embedder: Any
    image_matcher: Any
    pipeline: Any
    progress: Any
    run_id: int | None
    resume_skip: int
    resumed: bool
    completed_uids: set[str]
    counters: _IngestCounters
    pending_chunks: list[Any]
    pending_emails: list[Any]
    content_hashes: set[str]
    surface_mix: dict[str, int]
    format_failures: dict[str, int]
    start_time: float
    parse_seconds: float = 0.0
    queue_seconds: float = 0.0
    batch_ordinal: int = 0
    last_uid: str = ""


def _ingest_contexts(options: dict[str, Any]) -> tuple[_IngestRequest, _IngestDependencies]:
    request_names = tuple(_IngestRequest.__dataclass_fields__)
    dependency_names = tuple(_IngestDependencies.__dataclass_fields__)
    missing = [name for name in request_names + dependency_names if name not in options]
    unknown = sorted(set(options) - set(request_names) - set(dependency_names))
    if missing or unknown:
        raise TypeError(f"Invalid ingest_impl keyword arguments: missing={missing}, unexpected={unknown}")
    request_values = {name: options[name] for name in request_names}
    request_values["extract_attachments"] |= request_values["embed_images"]
    request = _IngestRequest(**request_values)
    dependencies = _IngestDependencies(**{name: options[name] for name in dependency_names})
    return request, dependencies
