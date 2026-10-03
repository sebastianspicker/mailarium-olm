"""Typed request, dependency, and run-state contexts shared by the ingestion pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


@dataclass(frozen=True)
class IngestRequest:
    """Describe inputs required for the ingest operation."""

    olm_path: str
    vector_index_path: str | None
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


@dataclass(frozen=True, slots=True)
class ProductionIngestDependencies:
    """Typed production services accepted by the injectable core ingest operation."""

    get_settings: Callable[[], Any]
    resolve_runtime_summary: Callable[[Any], dict[str, Any]]
    should_enable_image_embedding: Callable[[], bool]
    parse_olm: Callable[..., Any]
    chunk_email: Callable[..., Any]
    chunk_attachment: Callable[..., Any]
    hash_file_sha256: Callable[[str], str]
    resolve_entity_extractor: Callable[[bool, bool], Callable[[str, str], list[Any]] | None]
    resolve_entity_extractor_provenance: Callable[[Callable[[str, str], list[Any]] | None], tuple[str, str]]
    exchange_entities_from_email: Callable[[Any], list[tuple[str, str, str]]]
    embed_pipeline_cls: type[Any]
    make_progress_bar: Callable[..., Any]
    build_runtime: Callable[..., tuple[Any, Any]]


@dataclass
class IngestCounters:
    """Track metrics accumulated during the ingest operation."""

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
class IngestRuntime:
    """Own initialized state for the ingest operation."""

    request: IngestRequest
    dependencies: ProductionIngestDependencies
    settings: Any
    embedder: Any
    email_db: ArchiveDatabase | None
    control_db: ArchiveDatabase | None
    checkpoint_store: ArchiveDatabase | None
    bookkeeping_db: ArchiveDatabase | None
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
    counters: IngestCounters
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
