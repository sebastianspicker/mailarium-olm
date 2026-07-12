"""Core ingestion pipeline implementation."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-nested-blocks,too-many-statements

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import replace
from typing import Any

from ._ingest_context import _ingest_contexts, _IngestCounters, _IngestDependencies, _IngestRequest, _IngestRuntime
from .attachment_extractor import attachment_format_profile, attachment_ocr_available_for, attachment_supports_ocr
from .attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    DEFAULT_ATTACHMENT_OCR_LANG,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from .attachment_surfaces import build_attachment_surfaces, primary_surface_payload

logger = logging.getLogger(__name__)


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


def _normalize_unprocessed_attachments(
    email,
    *,
    extraction_requested: bool,
) -> None:
    """Mark unprocessed attachment metadata rows as explicit payload failures."""
    if not extraction_requested:
        return
    attachments = getattr(email, "attachments", None) or []
    if not attachments or not bool(getattr(email, "has_attachments", False)):
        return
    payload_extraction_failed = bool(getattr(email, "_attachment_payload_extraction_failed", False))
    default_reason = "attachment_payload_extraction_failed" if payload_extraction_failed else "attachment_payload_unavailable"
    for att_i, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            continue
        if str(attachment.get("extraction_state") or "").strip():
            continue
        filename = str(attachment.get("name") or f"attachment-{att_i}")
        attachment_id, content_sha256 = ensure_attachment_identity(attachment)
        _set_attachment_evidence(
            email,
            att_index=att_i,
            extraction_state="extraction_failed",
            evidence_strength="weak_reference",
            ocr_used=False,
            ocr_engine="",
            ocr_lang="",
            ocr_confidence=0.0,
            failure_reason=default_reason,
            text_preview="",
            extracted_text="",
            normalized_text="",
            text_normalization_version=0,
            text_source_path="",
            text_locator=_mailbox_attachment_locator(
                email_uid=str(getattr(email, "uid", "") or ""),
                att_index=att_i,
                filename=filename,
                extraction_state="extraction_failed",
                attachment_id=attachment_id,
                content_sha256=content_sha256,
            ),
            attachment_id=attachment_id,
            content_sha256=content_sha256,
            locator_version=2,
        )


def _attachments_safe_for_stale_cleanup(email: Any) -> bool:
    """Return whether attachment payload extraction completed well enough for broad stale cleanup."""
    if bool(getattr(email, "_attachment_payload_extraction_failed", False)):
        return False
    attachments = getattr(email, "attachments", None) or []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        state = str(attachment.get("extraction_state") or "").strip().lower()
        reason = str(attachment.get("failure_reason") or "").strip().lower()
        if state == "extraction_failed" and reason in {
            "attachment_payload_unavailable",
            "attachment_payload_extraction_failed",
        }:
            return False
    return True


def _set_attachment_evidence(
    email,
    *,
    att_index: int,
    **evidence: Any,
) -> None:
    """Persist attachment evidence semantics on the parsed email object."""
    attachments = getattr(email, "attachments", None) or []
    if 0 <= att_index < len(attachments):
        attachment = attachments[att_index]
        values = _attachment_evidence_values(evidence)
        attachment.update(values)
        attachment["surfaces"] = build_attachment_surfaces(
            attachment_id=attachment["attachment_id"],
            extracted_text=attachment["extracted_text"],
            normalized_text=attachment["normalized_text"],
            text_locator=attachment.get("text_locator") or {},
            extraction_state=attachment["extraction_state"],
            evidence_strength=attachment["evidence_strength"],
            ocr_used=bool(attachment["ocr_used"]),
            ocr_confidence=float(attachment["ocr_confidence"] or 0.0),
            surfaces=attachment.get("surfaces"),
        )


def _attachment_evidence_values(evidence: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "extraction_state": "",
        "evidence_strength": "",
        "ocr_used": False,
        "ocr_engine": "",
        "ocr_lang": "",
        "ocr_confidence": 0.0,
        "failure_reason": None,
        "text_preview": "",
        "extracted_text": "",
        "normalized_text": "",
        "text_normalization_version": 0,
        "text_source_path": "",
        "text_locator": {},
        "attachment_id": "",
        "content_sha256": "",
        "locator_version": 1,
    }
    values = defaults | evidence
    values["ocr_used"] = bool(values["ocr_used"])
    values["ocr_confidence"] = float(values["ocr_confidence"] or 0.0)
    values["text_normalization_version"] = int(values["text_normalization_version"] or 0)
    values["text_locator"] = dict(values["text_locator"] or {})
    values["attachment_id"] = str(values["attachment_id"] or "")
    values["content_sha256"] = str(values["content_sha256"] or "")
    values["locator_version"] = int(values["locator_version"] or 1)
    return values


def _attachment_text_preview(text: str, *, max_chars: int = 280) -> str:
    """Return a compact persisted preview for extracted attachment text."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _mailbox_attachment_locator(
    *,
    email_uid: str,
    att_index: int,
    filename: str,
    extraction_state: str,
    attachment_id: str = "",
    content_sha256: str = "",
    extracted_text: str = "",
) -> dict[str, Any]:
    """Create a locator dictionary for a mailbox attachment.

    Extracts metadata from attachment text such as page numbers, sheet names,
    cell ranges, and archive member paths.

    Args:
        email_uid: The unique identifier of the parent email.
        att_index: The attachment index within the email.
        filename: The attachment filename.
        extraction_state: The state of text extraction (e.g., 'text_extracted', 'ocr_text_extracted').
        attachment_id: Optional attachment identifier.
        content_sha256: Optional SHA256 hash of attachment content.
        extracted_text: The extracted text from the attachment.

    Returns:
        A dictionary containing locator metadata for the attachment.
    """
    return {
        "kind": "mailbox_attachment",
        "locator_version": 2,
        "email_uid": email_uid,
        "attachment_index": att_index,
        "filename": filename,
        "attachment_id": str(attachment_id or ""),
        "content_sha256": str(content_sha256 or ""),
        "extraction_state": extraction_state,
        **_attachment_locator_details(extracted_text),
    }


def _attachment_locator_details(extracted_text: str) -> dict[str, Any]:
    text = str(extracted_text or "")
    pages = [int(match) for match in re.findall(r"\[Page\s+(\d+)\]", text, flags=re.IGNORECASE) if match.isdigit()]
    return {
        "page_number": min(pages) if pages else None,
        "page_count": max(pages) if pages else None,
        "sheet_name": _locator_match(r"\[Sheet:\s*([^\]]+)\]", text),
        "cell_range": _locator_match(r"\b([A-Z]{1,4}\d{1,7}\s*:\s*[A-Z]{1,4}\d{1,7})\b", text).replace(" ", ""),
        "archive_member_path": _locator_match(r"\[Member:\s*([^\]]+)\]", text),
    }


def _locator_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return str(match.group(1) if match else "").strip()


def _is_locator_rich(locator: dict[str, Any]) -> bool:
    """Check if a locator dictionary contains meaningful metadata.

    Args:
        locator: A dictionary containing locator metadata.

    Returns:
        True if any of page_number, sheet_name, cell_range, or archive_member_path
        contain non-empty/non-zero values.
    """
    for key in ("page_number", "sheet_name", "cell_range", "archive_member_path"):
        value = locator.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, int) and value > 0:
            return True
    return False


def _looks_like_weak_language_signal(text: str) -> bool:
    """Determine if extracted text appears to be a weak language signal.

    Text is considered weak if it has fewer than 4 tokens total, or fewer than
    3 alphabetic tokens.

    Args:
        text: The text to evaluate.

    Returns:
        True if the text appears to be a weak language signal.
    """
    tokens = [token for token in re.split(r"\s+", str(text or "").strip()) if token]
    if len(tokens) < 4:
        return True
    alpha_tokens = [token for token in tokens if re.search(r"[A-Za-zÄÖÜäöüß]", token)]
    return len(alpha_tokens) < 3


def _textless_attachment_state(*, filename: str, mime_type: str) -> tuple[str, str]:
    """Determine attachment state for textless attachments without OCR.

    Args:
        filename: The attachment filename.
        mime_type: The MIME type of the attachment.

    Returns:
        A tuple of (extraction_state, failure_reason) for the attachment.
    """
    return _textless_attachment_state_with_ocr(
        filename=filename,
        mime_type=mime_type,
        ocr_attempted=False,
        ocr_available=False,
    )


def _textless_attachment_state_with_ocr(
    *,
    filename: str,
    mime_type: str,
    ocr_attempted: bool,
    ocr_available: bool,
) -> tuple[str, str]:
    """Determine attachment state for textless attachments considering OCR availability.

    Args:
        filename: The attachment filename.
        mime_type: The MIME type of the attachment.
        ocr_attempted: Whether OCR was attempted on the attachment.
        ocr_available: Whether OCR is available for this attachment type.

    Returns:
        A tuple of (extraction_state, failure_reason) for the attachment.
    """
    profile = attachment_format_profile(
        filename=filename,
        mime_type=mime_type,
        extraction_state="binary_only",
        evidence_strength="weak_reference",
        ocr_used=False,
        text_available=False,
    )
    if attachment_supports_ocr(filename, mime_type=mime_type):
        if ocr_attempted and ocr_available:
            return "ocr_failed", "ocr_failed"
        return "binary_only", "no_text_extracted_ocr_not_available"
    support_level = str(profile.get("support_level") or "")
    if support_level == "unsupported":
        return "unsupported", str(profile.get("degrade_reason") or "unsupported_format")
    return "binary_only", str(profile.get("degrade_reason") or "no_text_extracted")


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
            from .nlp_entity_extractor import preload as _preload_nlp

            _preload_nlp()
        except ImportError:
            logger.debug("Optional NLP component not available", exc_info=True)
    return time.monotonic() - start


def _build_runtime(
    *,
    settings,
    dry_run: bool,
    chromadb_path: str | None,
    sqlite_path: str | None,
) -> tuple[Any, Any]:
    """Build and configure the runtime components (embedder and email database).

    Args:
        settings: Application settings object.
        dry_run: If True, skip actual database/embedder initialization.
        chromadb_path: Optional path to ChromaDB directory.
        sqlite_path: Optional path to SQLite database file.

    Returns:
        A tuple of (embedder, email_db) instances, or (None, None) for dry run.

    Raises:
        RuntimeError: If required dependencies are missing.
    """
    embedder = None
    if not dry_run:
        try:
            from .embedder import EmailEmbedder
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing runtime dependency. Install project dependencies with 'pip install -r requirements.txt'"
            ) from exc
        embedder = EmailEmbedder(chromadb_path=chromadb_path)

    email_db = None
    if not dry_run:
        from .email_db import EmailDatabase

        resolved_sqlite = sqlite_path or settings.sqlite_path
        email_db = EmailDatabase(resolved_sqlite)

    if embedder and email_db:
        embedder.set_sparse_db(email_db)
    return embedder, email_db


def _ingest_extractors(request: _IngestRequest, dependencies: _IngestDependencies) -> tuple[Any, ...]:
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
    if not email_db:
        return None
    from .email_db import EmailDatabase

    if not isinstance(email_db, EmailDatabase):
        return None
    return EmailDatabase(
        sqlite_path,
        busy_timeout_ms=int(os.environ.get("INGEST_CHECKPOINT_BUSY_TIMEOUT_MS", "100")),
    )


def _initialize_ingest_runtime(request: _IngestRequest, dependencies: _IngestDependencies) -> _IngestRuntime:
    settings = dependencies.get_settings()
    sqlite_path = request.sqlite_path or settings.sqlite_path
    embedder, email_db = _build_runtime(
        settings=settings,
        dry_run=request.dry_run,
        chromadb_path=request.chromadb_path,
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
    _initialize_ingest_checkpoint(runtime)
    _initialize_ingest_pipeline(runtime)
    return runtime


def _initialize_ingest_checkpoint(runtime: _IngestRuntime) -> None:
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


def _attachment_surface(runtime: _IngestRuntime, email: Any, att_index: int) -> dict[str, Any]:
    attachments = getattr(email, "attachments", None) or []
    record = attachments[att_index] if 0 <= att_index < len(attachments) else {}
    surfaces = record.get("surfaces") if isinstance(record, dict) else []
    for surface in surfaces if isinstance(surfaces, list) else []:
        if isinstance(surface, dict):
            kind = str(surface.get("surface_kind") or "reference_only")
            runtime.surface_mix[kind] = runtime.surface_mix.get(kind, 0) + 1
    primary = primary_surface_payload(surfaces)
    locator = primary.get("locator") if isinstance(primary, dict) else {}
    runtime.counters.locator_rich += int(isinstance(locator, dict) and _is_locator_rich(locator))
    return primary


def _record_attachment_identity(runtime: _IngestRuntime, content_sha256: str) -> None:
    runtime.counters.attachments_seen += 1
    if not content_sha256:
        return
    if content_sha256 in runtime.content_hashes:
        runtime.counters.duplicate_content += 1
    else:
        runtime.content_hashes.add(content_sha256)


def _image_chunk_metadata(
    email: Any,
    email_dict: dict[str, Any],
    filename: str,
    att_index: int,
    identity: tuple[str, str],
    surface: dict[str, Any],
) -> dict[str, Any]:
    locator = surface.get("locator") if isinstance(surface.get("locator"), dict) else {}
    return {
        "uid": email.uid,
        "subject": email_dict.get("subject", ""),
        "sender_name": email_dict.get("sender_name", ""),
        "sender_email": email_dict.get("sender_email", ""),
        "date": email_dict.get("date", ""),
        "folder": email_dict.get("folder", ""),
        "chunk_type": "image",
        "candidate_kind": "attachment",
        "is_attachment": "True",
        "filename": filename,
        "attachment_name": filename,
        "attachment_filename": filename,
        "attachment_type": filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
        "attachment_id": identity[0],
        "content_sha256": identity[1],
        "extraction_state": "image_embedding_only",
        "evidence_strength": "weak_reference",
        "ocr_used": "False",
        "failure_reason": "no_text_extracted",
        "source_scope": "attachment_text",
        "segment_ordinal": str(att_index),
        "surface_id": str(surface.get("surface_id") or ""),
        "surface_kind": str(surface.get("surface_kind") or "reference_only"),
        "origin_kind": str(surface.get("origin_kind") or "reference"),
        "surface_locator_json": json.dumps(locator, ensure_ascii=False),
    }


def _process_image_attachment(
    runtime: _IngestRuntime,
    email: Any,
    email_dict: dict[str, Any],
    att_index: int,
    filename: str,
    content: bytes,
    identity: tuple[str, str],
) -> int | None:
    if not (runtime.image_embedder and runtime.image_matcher and runtime.image_matcher(filename)):
        return None
    from .chunker import EmailChunk

    embedding = runtime.image_embedder(filename, content)
    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state="image_embedding_only",
        evidence_strength="weak_reference",
        ocr_used=False,
        failure_reason="no_text_extracted_ocr_not_available",
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state="image_embedding_only",
            attachment_id=identity[0],
            content_sha256=identity[1],
        ),
        attachment_id=identity[0],
        content_sha256=identity[1],
        locator_version=2,
    )
    surface = _attachment_surface(runtime, email, att_index)
    if not embedding or not runtime.embedder:
        return 0
    runtime.pending_chunks.append(
        EmailChunk(
            uid=email.uid,
            chunk_id=f"{email.uid}__img_{att_index}",
            text=f"[Image attachment: {filename}]",
            metadata=_image_chunk_metadata(email, email_dict, filename, att_index, identity, surface),
            embedding=embedding,
        )
    )
    runtime.counters.chunks += 1
    runtime.counters.image_embeddings += 1
    return 1


def _extract_attachment_text(
    runtime: _IngestRuntime,
    filename: str,
    content: bytes,
    mime_type: str,
) -> tuple[str | None, str | None, bool]:
    text, failure_reason = runtime.attachment_extractor(filename, content, mime_type=mime_type)
    ocr_used = False
    if not text and runtime.attachment_ocr_extractor:
        ocr_text = runtime.attachment_ocr_extractor(filename, content)
        if ocr_text:
            text, ocr_used = ocr_text, True
    return text, failure_reason, ocr_used


def _persist_attachment_text(
    runtime: _IngestRuntime,
    email: Any,
    att_index: int,
    filename: str,
    identity: tuple[str, str],
    text: str,
    ocr_used: bool,
) -> tuple[str, str, dict[str, Any]]:
    state = runtime.classify_text_state(filename, text, ocr_used=ocr_used)
    normalized = normalize_attachment_search_text(text)
    ocr_lang = str(os.environ.get("ATTACHMENT_OCR_LANG", DEFAULT_ATTACHMENT_OCR_LANG) or "").strip()
    ocr_lang = ocr_lang or DEFAULT_ATTACHMENT_OCR_LANG
    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state=state,
        evidence_strength="strong_text",
        ocr_used=ocr_used,
        ocr_engine="tesseract" if ocr_used else "",
        ocr_lang=ocr_lang if ocr_used else "",
        failure_reason=None,
        text_preview=_attachment_text_preview(text),
        extracted_text=text,
        normalized_text=normalized,
        text_normalization_version=ATTACHMENT_TEXT_NORMALIZATION_VERSION if normalized else 0,
        text_source_path=f"attachment://{email.uid}/{att_index}/{filename}",
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state=state,
            attachment_id=identity[0],
            content_sha256=identity[1],
            extracted_text=text,
        ),
        attachment_id=identity[0],
        content_sha256=identity[1],
        locator_version=2,
    )
    runtime.counters.weak_language += int(_looks_like_weak_language_signal(text))
    runtime.counters.ocr_only += int(ocr_used and state == "ocr_text_extracted")
    return normalized, state, _attachment_surface(runtime, email, att_index)


def _attachment_parent_metadata(email: Any, email_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": email.uid,
        "subject": email_dict.get("subject", ""),
        "sender_name": email_dict.get("sender_name", ""),
        "sender_email": email_dict.get("sender_email", ""),
        "date": email_dict.get("date", ""),
        "folder": email_dict.get("folder", ""),
    }


def _chunk_attachment_text(
    runtime: _IngestRuntime,
    email: Any,
    email_dict: dict[str, Any],
    att_index: int,
    filename: str,
    identity: tuple[str, str],
    text: str,
    normalized: str,
    state: str,
    ocr_used: bool,
    surface: dict[str, Any],
) -> list[Any]:
    locator = surface.get("locator") if isinstance(surface.get("locator"), dict) else {}
    return runtime.dependencies.chunk_attachment(
        email_uid=email.uid,
        filename=filename,
        text=text,
        normalized_text=normalized,
        parent_metadata=_attachment_parent_metadata(email, email_dict),
        att_index=att_index,
        attachment_id=identity[0],
        content_sha256=identity[1],
        extraction_state=state,
        evidence_strength="strong_text",
        ocr_used=ocr_used,
        failure_reason=None,
        surface_id=str(surface.get("surface_id") or ""),
        surface_kind=str(surface.get("surface_kind") or "verbatim"),
        surface_origin_kind=str(surface.get("origin_kind") or "native"),
        surface_locator=locator,
        surface_ocr_confidence=float(surface.get("ocr_confidence") or 0.0),
    )


def _persist_attachment_failure(
    runtime: _IngestRuntime,
    email: Any,
    att_index: int,
    filename: str,
    mime_type: str,
    identity: tuple[str, str],
    extraction_reason: str | None,
) -> None:
    if extraction_reason:
        state, reason = "extraction_failed", extraction_reason
    else:
        state, reason = _textless_attachment_state_with_ocr(
            filename=filename,
            mime_type=mime_type,
            ocr_attempted=bool(runtime.attachment_ocr_extractor),
            ocr_available=attachment_ocr_available_for(filename, mime_type=mime_type),
        )
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
            attachment_id=identity[0],
            content_sha256=identity[1],
        ),
        attachment_id=identity[0],
        content_sha256=identity[1],
        locator_version=2,
    )
    _attachment_surface(runtime, email, att_index)
    profile = attachment_format_profile(
        filename=filename,
        mime_type=mime_type,
        extraction_state=state,
        evidence_strength="weak_reference",
        ocr_used=False,
        text_available=False,
    )
    key = str(profile.get("format_id") or filename.rsplit(".", 1)[-1].lower() or "unknown")
    runtime.format_failures[key] = runtime.format_failures.get(key, 0) + 1


def _process_attachment(
    runtime: _IngestRuntime,
    email: Any,
    email_dict: dict[str, Any],
    att_index: int,
    filename: str,
    content: bytes,
) -> tuple[int, int]:
    attachments = getattr(email, "attachments", None) or []
    metadata = attachments[att_index] if 0 <= att_index < len(attachments) else {}
    mime_type = str((metadata or {}).get("mime_type") or "")
    identity = ensure_attachment_identity(metadata, content_bytes=content)
    _record_attachment_identity(runtime, identity[1])
    image_count = _process_image_attachment(
        runtime,
        email,
        email_dict,
        att_index,
        filename,
        content,
        identity,
    )
    if image_count is not None:
        return 0, image_count
    text, extraction_reason, ocr_used = _extract_attachment_text(runtime, filename, content, mime_type)
    if not text:
        _persist_attachment_failure(
            runtime,
            email,
            att_index,
            filename,
            mime_type,
            identity,
            extraction_reason,
        )
        return 0, 0
    normalized, state, surface = _persist_attachment_text(
        runtime,
        email,
        att_index,
        filename,
        identity,
        text,
        ocr_used,
    )
    chunks = _chunk_attachment_text(
        runtime,
        email,
        email_dict,
        att_index,
        filename,
        identity,
        text,
        normalized,
        state,
        ocr_used,
        surface,
    )
    runtime.counters.chunks += len(chunks)
    runtime.counters.attachment_chunks += len(chunks)
    if runtime.embedder:
        runtime.pending_chunks.extend(chunks)
    return len(chunks), 0


def _process_ingest_email(runtime: _IngestRuntime, email: Any) -> None:
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
    started = time.monotonic()
    email = next(parser)
    runtime.parse_seconds += time.monotonic() - started
    return email


def _run_ingest_parser(runtime: _IngestRuntime) -> None:
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


def _complete_ingest(runtime: _IngestRuntime, stats: dict[str, Any]) -> None:
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
    if runtime.pipeline:
        try:
            worker_error = runtime.pipeline.abort()
            if worker_error is not None and worker_error is not exc:
                logger.warning("Background ingest pipeline error during abort: %s", worker_error)
        except Exception:  # pylint: disable=broad-exception-caught
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
    try:
        runtime.progress.close()
    except OSError:
        logger.debug("Failed to close progress bar", exc_info=True)
    if runtime.control_db:
        runtime.control_db.close()
    if runtime.email_db:
        runtime.email_db.close()


def ingest_impl(**options: Any) -> dict[str, Any]:
    """Parse an OLM file and ingest all emails into the vector database."""
    request, dependencies = _ingest_contexts(options)
    runtime = _initialize_ingest_runtime(request, dependencies)
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
