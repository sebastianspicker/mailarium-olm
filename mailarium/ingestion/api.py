"""Production-bound ingestion facades for interface adapters.

The core ingestion operations accept injectable dependencies so lightweight
callers can supply fakes. Interfaces that perform real archive work use these
facades to bind Mailarium's production parser, extractors, and runtime
construction without importing the top-level CLI entry point.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mailarium.config import get_settings, resolve_runtime_summary, should_enable_image_embedding
from mailarium.ingestion.chunker import chunk_attachment, chunk_email
from mailarium.ingestion.ingest_embed_pipeline import _EmbedPipeline, _exchange_entities_from_email
from mailarium.ingestion.olm.parse_olm import parse_olm

from .maintenance import reextract_entities_impl as reextract_entities
from .maintenance import reingest_metadata_impl as reingest_metadata
from .orchestration import ingest_impl as ingest
from .runtime import build_ingest_runtime_resources

logger = logging.getLogger(__name__)

_SPACY_MODELS = ("en_core_web_sm", "de_core_news_sm")


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

    def as_kwargs(self) -> dict[str, Any]:
        """Project the bundle into the keyword-only dependencies of ``ingest``."""
        return {
            "get_settings": self.get_settings,
            "resolve_runtime_summary": self.resolve_runtime_summary,
            "should_enable_image_embedding": self.should_enable_image_embedding,
            "parse_olm": self.parse_olm,
            "chunk_email": self.chunk_email,
            "chunk_attachment": self.chunk_attachment,
            "hash_file_sha256": self.hash_file_sha256,
            "resolve_entity_extractor": self.resolve_entity_extractor,
            "resolve_entity_extractor_provenance": self.resolve_entity_extractor_provenance,
            "exchange_entities_from_email": self.exchange_entities_from_email,
            "embed_pipeline_cls": self.embed_pipeline_cls,
            "make_progress_bar": self.make_progress_bar,
            "build_runtime": self.build_runtime,
        }


def production_ingest_dependencies(
    *,
    build_runtime: Callable[..., tuple[Any, Any]] = build_ingest_runtime_resources,
) -> ProductionIngestDependencies:
    """Return Mailarium's production ingest dependencies, with an injectable runtime seam."""
    return ProductionIngestDependencies(
        get_settings=get_settings,
        resolve_runtime_summary=resolve_runtime_summary,
        should_enable_image_embedding=should_enable_image_embedding,
        parse_olm=parse_olm,
        chunk_email=chunk_email,
        chunk_attachment=chunk_attachment,
        hash_file_sha256=_hash_file_sha256,
        resolve_entity_extractor=_resolve_entity_extractor,
        resolve_entity_extractor_provenance=_resolve_entity_extractor_provenance,
        exchange_entities_from_email=_exchange_entities_from_email,
        embed_pipeline_cls=_EmbedPipeline,
        make_progress_bar=_make_progress_bar,
        build_runtime=build_runtime,
    )


def ingest_archive(
    olm_path: str,
    *,
    vector_index_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 500,
    max_emails: int | None = None,
    dry_run: bool = False,
    extract_attachments: bool = False,
    extract_entities: bool = False,
    incremental: bool = False,
    embed_images: bool = False,
    resume: bool = False,
    timing: bool = False,
) -> dict[str, Any]:
    """Ingest one Outlook archive with Mailarium's production dependencies."""
    return ingest(
        olm_path=olm_path,
        vector_index_path=vector_index_path,
        sqlite_path=sqlite_path,
        batch_size=batch_size,
        max_emails=max_emails,
        dry_run=dry_run,
        extract_attachments=extract_attachments,
        extract_entities=extract_entities,
        incremental=incremental,
        embed_images=embed_images,
        resume=resume,
        timing=timing,
        **production_ingest_dependencies().as_kwargs(),
    )


def reingest_metadata_archive(olm_path: str, *, sqlite_path: str | None = None) -> dict[str, Any]:
    """Backfill archive metadata, including entities derived from Exchange fields."""
    return reingest_metadata(
        olm_path,
        sqlite_path=sqlite_path,
        exchange_entities_from_email=_exchange_entities_from_email,
        parse_olm_fn=parse_olm,
    )


def reextract_entities_archive(*, sqlite_path: str | None = None, force: bool = False) -> dict[str, Any]:
    """Rebuild entity mentions with the configured production extractor and provenance."""
    entity_extractor_fn = _resolve_entity_extractor(extract_entities=True, dry_run=False)
    extractor_key, extraction_version = _resolve_entity_extractor_provenance(entity_extractor_fn)
    return reextract_entities(
        sqlite_path=sqlite_path,
        entity_extractor_fn=entity_extractor_fn,
        extractor_key=extractor_key,
        extraction_version=extraction_version,
        force=force,
    )


def reprocess_degraded_attachments_archive(
    olm_path: str,
    *,
    vector_index_path: str | None = None,
    sqlite_path: str | None = None,
    batch_size: int = 100,
    force: bool = False,
) -> dict[str, Any]:
    """Reprocess degraded attachments with Mailarium's parser and extraction services."""
    from .attachment_extractor import extract_attachment_text_ocr, extract_text
    from .attachment_reprocessing import reprocess_degraded_attachments_impl

    return reprocess_degraded_attachments_impl(
        olm_path,
        vector_index_path=vector_index_path,
        sqlite_path=sqlite_path,
        batch_size=batch_size,
        force=force,
        parse_olm_fn=parse_olm,
        chunk_attachment_fn=chunk_attachment,
        attachment_text_extractor=extract_text,
        attachment_ocr_extractor=extract_attachment_text_ocr,
    )


def _hash_file_sha256(filepath: str) -> str:
    """Compute a file hash with bounded streaming reads."""
    digest = hashlib.sha256()
    with open(filepath, "rb") as source:
        for chunk in iter(lambda: source.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_entity_extractor(extract_entities: bool, dry_run: bool) -> Callable[[str, str], list[Any]] | None:
    """Resolve the production entity extractor only when an ingest needs it."""
    if not extract_entities or dry_run:
        return None
    try:
        from mailarium.investigation.nlp_entity_extractor import extract_nlp_entities, is_spacy_available

        if not is_spacy_available():
            if os.environ.get("SPACY_AUTO_DOWNLOAD_DURING_INGEST", "1") != "0":
                _auto_download_spacy_models()
                from mailarium.investigation.nlp_entity_extractor import reset_model_cache

                reset_model_cache()
            else:
                logger.info("Entity extraction: spaCy models unavailable; automatic download disabled.")
        if is_spacy_available():
            logger.info("Entity extraction: spaCy NLP + regex (enhanced)")
            return extract_nlp_entities
        from mailarium.investigation.entity_extractor import extract_entities as extract_regex_entities

        logger.info("Entity extraction: regex-only (spaCy models not available)")
        return extract_regex_entities
    except ImportError:
        from mailarium.investigation.entity_extractor import extract_entities as extract_regex_entities

        logger.info("Entity extraction: regex-only")
        return extract_regex_entities


def _resolve_entity_extractor_provenance(
    entity_extractor_fn: Callable[[str, str], list[Any]] | None,
) -> tuple[str, str]:
    """Return the stable provenance label for the selected entity extractor."""
    if entity_extractor_fn is None:
        return "", ""
    module_name = str(getattr(entity_extractor_fn, "__module__", "") or "")
    if module_name.endswith("nlp_entity_extractor"):
        return "spacy_regex", "1"
    if module_name.endswith("entity_extractor"):
        return "regex_only", "1"
    return "custom", "1"


def _auto_download_spacy_models() -> None:
    """Install optional spaCy models when the current production policy allows it."""
    if os.environ.get("SPACY_AUTO_DOWNLOAD", "1") == "0":
        logger.debug("spaCy auto-download disabled via SPACY_AUTO_DOWNLOAD=0")
        return
    try:
        import spacy
    except ImportError:
        logger.debug("spaCy not installed, skipping model download")
        return

    import subprocess  # nosec B404
    import sys

    for model_name in _SPACY_MODELS:
        try:
            spacy.load(model_name)
            logger.debug("spaCy model already installed: %s", model_name)
        except OSError:
            logger.info("Downloading spaCy model: %s ...", model_name)
            try:
                subprocess.check_call(  # nosemgrep
                    [sys.executable, "-m", "spacy", "download", model_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("spaCy model installed: %s", model_name)
            except subprocess.CalledProcessError:
                logger.warning("Failed to download spaCy model: %s", model_name)


class _NoOpProgressBar:
    """Fallback progress reporter when tqdm is not installed."""

    def update(self, n: int = 1) -> None:
        """Accept progress updates without rendering them."""

    def close(self) -> None:
        """Satisfy the progress reporter close protocol."""

    def set_postfix(self, **kwargs: Any) -> None:
        """Accept progress metadata without rendering it."""


def _make_progress_bar(total: int | None, desc: str = "", unit: str = "it") -> Any:
    """Create the production progress reporter or a no-op fallback."""
    try:
        from tqdm import tqdm

        return tqdm(total=total, desc=desc, unit=unit)
    except ImportError:
        return _NoOpProgressBar()
