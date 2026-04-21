"""Core ingestion pipeline implementation."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from typing import Any

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
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    ocr_engine: str = "",
    ocr_lang: str = "",
    ocr_confidence: float = 0.0,
    failure_reason: str | None = None,
    text_preview: str = "",
    extracted_text: str = "",
    normalized_text: str = "",
    text_normalization_version: int = 0,
    text_source_path: str = "",
    text_locator: dict[str, Any] | None = None,
    attachment_id: str = "",
    content_sha256: str = "",
    locator_version: int = 1,
) -> None:
    """Persist attachment evidence semantics on the parsed email object."""
    attachments = getattr(email, "attachments", None) or []
    if 0 <= att_index < len(attachments):
        attachment = attachments[att_index]
        attachment["extraction_state"] = extraction_state
        attachment["evidence_strength"] = evidence_strength
        attachment["ocr_used"] = bool(ocr_used)
        attachment["ocr_engine"] = str(ocr_engine or "")
        attachment["ocr_lang"] = str(ocr_lang or "")
        attachment["ocr_confidence"] = float(ocr_confidence or 0.0)
        attachment["failure_reason"] = failure_reason
        attachment["text_preview"] = text_preview
        attachment["extracted_text"] = extracted_text
        attachment["normalized_text"] = normalized_text
        attachment["text_normalization_version"] = int(text_normalization_version or 0)
        attachment["text_source_path"] = text_source_path
        attachment["text_locator"] = dict(text_locator or {})
        attachment["attachment_id"] = str(attachment_id or "")
        attachment["content_sha256"] = str(content_sha256 or "")
        attachment["locator_version"] = int(locator_version or 1)
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
    page_numbers = [
        int(match)
        for match in re.findall(r"\[Page\s+(\d+)\]", str(extracted_text or ""), flags=re.IGNORECASE)
        if str(match or "").isdigit()
    ]
    sheet_match = re.search(r"\[Sheet:\s*([^\]]+)\]", str(extracted_text or ""), flags=re.IGNORECASE)
    member_match = re.search(r"\[Member:\s*([^\]]+)\]", str(extracted_text or ""), flags=re.IGNORECASE)
    cell_match = re.search(r"\b([A-Z]{1,4}\d{1,7}\s*:\s*[A-Z]{1,4}\d{1,7})\b", str(extracted_text or ""))
    page_number = min(page_numbers) if page_numbers else None
    page_count = max(page_numbers) if page_numbers else None
    sheet_name = str(sheet_match.group(1) if sheet_match else "").strip()
    archive_member_path = str(member_match.group(1) if member_match else "").strip()
    cell_range = str(cell_match.group(1) if cell_match else "").replace(" ", "")
    return {
        "kind": "mailbox_attachment",
        "locator_version": 2,
        "email_uid": email_uid,
        "attachment_index": att_index,
        "filename": filename,
        "attachment_id": str(attachment_id or ""),
        "content_sha256": str(content_sha256 or ""),
        "extraction_state": extraction_state,
        "page_number": page_number,
        "page_count": page_count,
        "sheet_name": sheet_name,
        "cell_range": cell_range,
        "archive_member_path": archive_member_path,
    }


def _is_locator_rich(locator: dict[str, Any]) -> bool:
    for key in ("page_number", "sheet_name", "cell_range", "archive_member_path"):
        value = locator.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, int) and value > 0:
            return True
    return False


def _looks_like_weak_language_signal(text: str) -> bool:
    tokens = [token for token in re.split(r"\s+", str(text or "").strip()) if token]
    if len(tokens) < 4:
        return True
    alpha_tokens = [token for token in tokens if re.search(r"[A-Za-zÄÖÜäöüß]", token)]
    return len(alpha_tokens) < 3


def _textless_attachment_state(*, filename: str, mime_type: str) -> tuple[str, str]:
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
    start = time.monotonic()
    if embedder:
        embedder.warmup()
    if entity_extractor_fn:
        try:
            from .nlp_entity_extractor import preload as _preload_nlp

            _preload_nlp()
        except ImportError:
            pass
    return time.monotonic() - start


def _build_runtime(
    *,
    settings,
    dry_run: bool,
    chromadb_path: str | None,
    sqlite_path: str | None,
) -> tuple[Any, Any]:
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


def ingest_impl(
    *,
    olm_path: str,
    chromadb_path: str | None,
    sqlite_path: str | None,
    batch_size: int,
    max_emails: int | None,
    dry_run: bool,
    extract_attachments: bool,
    extract_entities: bool,
    incremental: bool,
    embed_images: bool,
    resume: bool,
    timing: bool,
    get_settings,
    resolve_runtime_summary,
    should_enable_image_embedding,
    parse_olm,
    chunk_email,
    chunk_attachment,
    hash_file_sha256,
    resolve_entity_extractor,
    resolve_entity_extractor_provenance,
    exchange_entities_from_email,
    embed_pipeline_cls,
    make_progress_bar,
) -> dict[str, Any]:
    """Parse an OLM file and ingest all emails into the vector database."""
    settings = get_settings()
    start_time = time.time()

    if embed_images:
        extract_attachments = True

    resolved_sqlite_path = sqlite_path or settings.sqlite_path

    embedder, email_db = _build_runtime(
        settings=settings,
        dry_run=dry_run,
        chromadb_path=chromadb_path,
        sqlite_path=resolved_sqlite_path,
    )
    control_db = None
    if email_db:
        from .email_db import EmailDatabase

        if isinstance(email_db, EmailDatabase):
            control_db = EmailDatabase(
                resolved_sqlite_path,
                busy_timeout_ms=int(os.environ.get("INGEST_CHECKPOINT_BUSY_TIMEOUT_MS", "100")),
            )

    entity_extractor_fn = resolve_entity_extractor(extract_entities, dry_run)
    entity_extractor_key, entity_extraction_version = resolve_entity_extractor_provenance(entity_extractor_fn)

    attachment_extractor = None
    attachment_ocr_extractor = None
    classify_text_extraction_state: Any = None
    if extract_attachments:
        from .attachment_extractor import classify_text_extraction_state, extract_attachment_text_ocr, extract_text

        attachment_extractor = extract_text
        attachment_ocr_extractor = extract_attachment_text_ocr

    image_embedder_fn = None
    image_attachment_matcher = None
    if embed_images and not dry_run:
        if should_enable_image_embedding():
            from .attachment_extractor import (
                _get_image_embedder,
                extract_image_embedding,
            )
            from .attachment_extractor import (
                is_image_attachment as _is_image,
            )

            image_embedder_fn = extract_image_embedding
            image_attachment_matcher = _is_image
            probe = _get_image_embedder()
            if not probe.is_available:
                image_embedder_fn = None
                embed_images = False
        else:
            embed_images = False

    _preload_models(embedder, entity_extractor_fn)

    ingestion_run_id = None
    resumed_from_checkpoint = False
    resume_skip_emails = 0
    last_processed_uid = ""
    batch_ordinal = 0
    checkpoint_store = control_db or email_db
    bookkeeping_db = control_db or email_db

    if checkpoint_store and resume and hasattr(checkpoint_store, "latest_ingest_checkpoint"):
        checkpoint = checkpoint_store.latest_ingest_checkpoint(olm_path=olm_path)
        if isinstance(checkpoint, dict):
            resume_skip_emails = max(int(checkpoint.get("emails_parsed") or 0), 0)
            resumed_from_checkpoint = resume_skip_emails > 0
    if bookkeeping_db:
        olm_sha256 = None
        olm_file_size = None
        if os.path.isfile(olm_path):
            olm_file_size = os.path.getsize(olm_path)
            if os.environ.get("INGEST_RECORD_OLM_SHA256", "0") == "1":
                olm_sha256 = hash_file_sha256(olm_path)
        ingestion_run_id = bookkeeping_db.record_ingestion_start(
            olm_path,
            olm_sha256=olm_sha256,
            file_size_bytes=olm_file_size,
        )
        _update_ingest_checkpoint_safe(
            checkpoint_store=checkpoint_store,
            run_id=ingestion_run_id,
            olm_path=olm_path,
            last_batch_ordinal=0,
            emails_parsed=0,
            emails_inserted=0,
            last_email_uid="",
            status="running",
            allow_locked_skip=False,
            stage="ingestion_start",
        )

    total_emails = 0
    total_chunks_created = 0
    total_attachment_chunks = 0
    total_image_embeddings = 0
    total_attachment_observed = 0
    total_locator_rich_attachments = 0
    total_ocr_only_attachments = 0
    total_weak_language_attachments = 0
    total_duplicate_content_attachments = 0
    total_skipped_incremental = 0
    total_skipped_resume = 0
    attachment_content_hashes_seen: set[str] = set()
    surface_kind_mix: dict[str, int] = {}
    format_extraction_failures: dict[str, int] = {}
    pending_chunks = []
    pending_emails = []
    parse_seconds = 0.0
    queue_wait_seconds = 0.0

    pipeline = None
    if not dry_run:
        pipeline = embed_pipeline_cls(
            embedder=embedder,
            email_db=email_db,
            entity_extractor_fn=entity_extractor_fn,
            entity_extractor_key=entity_extractor_key,
            entity_extraction_version=entity_extraction_version,
            batch_size=batch_size,
            ingestion_run_id=ingestion_run_id,
        )
        pipeline.start()

    progress = make_progress_bar(max_emails, desc="Ingesting", unit="email")
    completed_incremental_uids: set[str] = set()
    if incremental and bookkeeping_db and not embed_images:
        completed_incremental_uids = bookkeeping_db.completed_ingest_uids(
            attachment_required=extract_attachments,
        )

    try:
        parser = iter(parse_olm(olm_path, extract_attachments=extract_attachments))
        while True:
            t_parse_start = time.monotonic()
            try:
                email = next(parser)
            except StopIteration:
                break
            parse_seconds += time.monotonic() - t_parse_start
            total_emails += 1

            if resume_skip_emails > 0 and total_emails <= resume_skip_emails:
                total_skipped_resume += 1
                progress.update(1)
                continue

            email_uid = str(getattr(email, "uid", "") or "")

            if incremental and completed_incremental_uids and email_uid and email_uid in completed_incremental_uids:
                total_skipped_incremental += 1
                progress.update(1)
                continue

            last_processed_uid = email_uid

            email_dict = email.to_dict()
            chunks = chunk_email(email_dict)
            total_chunks_created += len(chunks)
            body_chunk_count = len(chunks)
            attachment_chunk_count = 0
            image_chunk_count = 0
            if embedder:
                pending_chunks.extend(chunks)
            if email_db:
                pending_emails.append(email)

            if attachment_extractor and email.attachment_contents:
                from .chunker import EmailChunk

                for att_i, (att_name, att_bytes) in enumerate(email.attachment_contents):
                    mime_type = ""
                    attachments = getattr(email, "attachments", None) or []
                    attachment_meta = attachments[att_i] if 0 <= att_i < len(attachments) else {}
                    if 0 <= att_i < len(attachments):
                        mime_type = str((attachments[att_i] or {}).get("mime_type") or "")
                    attachment_id, content_sha256 = ensure_attachment_identity(attachment_meta, content_bytes=att_bytes)
                    total_attachment_observed += 1
                    if content_sha256:
                        if content_sha256 in attachment_content_hashes_seen:
                            total_duplicate_content_attachments += 1
                        else:
                            attachment_content_hashes_seen.add(content_sha256)
                    if image_embedder_fn and image_attachment_matcher and image_attachment_matcher(att_name):
                        img_embedding = image_embedder_fn(att_name, att_bytes)
                        _set_attachment_evidence(
                            email,
                            att_index=att_i,
                            extraction_state="image_embedding_only",
                            evidence_strength="weak_reference",
                            ocr_used=False,
                            ocr_engine="",
                            ocr_lang="",
                            ocr_confidence=0.0,
                            failure_reason="no_text_extracted_ocr_not_available",
                            text_preview="",
                            extracted_text="",
                            normalized_text="",
                            text_normalization_version=0,
                            text_source_path="",
                            text_locator=_mailbox_attachment_locator(
                                email_uid=email.uid,
                                att_index=att_i,
                                filename=att_name,
                                extraction_state="image_embedding_only",
                                attachment_id=attachment_id,
                                content_sha256=content_sha256,
                            ),
                            attachment_id=attachment_id,
                            content_sha256=content_sha256,
                            locator_version=2,
                        )
                        attachment_record = attachments[att_i] if 0 <= att_i < len(attachments) else {}
                        attachment_surfaces = attachment_record.get("surfaces") if isinstance(attachment_record, dict) else []
                        for surface in attachment_surfaces if isinstance(attachment_surfaces, list) else []:
                            if isinstance(surface, dict):
                                surface_kind = str(surface.get("surface_kind") or "reference_only")
                                surface_kind_mix[surface_kind] = surface_kind_mix.get(surface_kind, 0) + 1
                        primary_surface = primary_surface_payload(attachment_surfaces)
                        locator = primary_surface.get("locator") if isinstance(primary_surface, dict) else {}
                        if isinstance(locator, dict) and _is_locator_rich(locator):
                            total_locator_rich_attachments += 1
                        if img_embedding and embedder:
                            img_chunk = EmailChunk(
                                uid=email.uid,
                                chunk_id=f"{email.uid}__img_{att_i}",
                                text=f"[Image attachment: {att_name}]",
                                metadata={
                                    "uid": email.uid,
                                    "subject": email_dict.get("subject", ""),
                                    "sender_name": email_dict.get("sender_name", ""),
                                    "sender_email": email_dict.get("sender_email", ""),
                                    "date": email_dict.get("date", ""),
                                    "folder": email_dict.get("folder", ""),
                                    "chunk_type": "image",
                                    "candidate_kind": "attachment",
                                    "is_attachment": "True",
                                    "filename": att_name,
                                    "attachment_name": att_name,
                                    "attachment_filename": att_name,
                                    "attachment_type": att_name.rsplit(".", 1)[-1].lower() if "." in att_name else "",
                                    "attachment_id": attachment_id,
                                    "content_sha256": content_sha256,
                                    "extraction_state": "image_embedding_only",
                                    "evidence_strength": "weak_reference",
                                    "ocr_used": "False",
                                    "failure_reason": "no_text_extracted",
                                    "source_scope": "attachment_text",
                                    "segment_ordinal": str(att_i),
                                    "surface_id": str(primary_surface.get("surface_id") or ""),
                                    "surface_kind": str(primary_surface.get("surface_kind") or "reference_only"),
                                    "origin_kind": str(primary_surface.get("origin_kind") or "reference"),
                                    "surface_locator_json": json.dumps(
                                        primary_surface.get("locator")
                                        if isinstance(primary_surface.get("locator"), dict)
                                        else {},
                                        ensure_ascii=False,
                                    ),
                                },
                                embedding=img_embedding,
                            )
                            pending_chunks.append(img_chunk)
                            total_chunks_created += 1
                            total_image_embeddings += 1
                            image_chunk_count += 1
                        continue

                    att_text = attachment_extractor(att_name, att_bytes, mime_type=mime_type)
                    ocr_used = False
                    extraction_state = "text_extracted"
                    failure_reason = None
                    if not att_text and attachment_ocr_extractor:
                        ocr_text = attachment_ocr_extractor(att_name, att_bytes)
                        if ocr_text:
                            att_text = ocr_text
                            ocr_used = True
                            extraction_state = "ocr_text_extracted"
                    if att_text:
                        assert classify_text_extraction_state is not None
                        extraction_state = classify_text_extraction_state(att_name, att_text, ocr_used=ocr_used)
                        normalized_text = normalize_attachment_search_text(att_text)
                        ocr_lang = str(os.environ.get("ATTACHMENT_OCR_LANG", DEFAULT_ATTACHMENT_OCR_LANG) or "").strip()
                        if not ocr_lang:
                            ocr_lang = DEFAULT_ATTACHMENT_OCR_LANG
                        locator = _mailbox_attachment_locator(
                            email_uid=email.uid,
                            att_index=att_i,
                            filename=att_name,
                            extraction_state=extraction_state,
                            attachment_id=attachment_id,
                            content_sha256=content_sha256,
                            extracted_text=att_text,
                        )
                        _set_attachment_evidence(
                            email,
                            att_index=att_i,
                            extraction_state=extraction_state,
                            evidence_strength="strong_text",
                            ocr_used=ocr_used,
                            ocr_engine="tesseract" if ocr_used else "",
                            ocr_lang=ocr_lang if ocr_used else "",
                            ocr_confidence=0.0,
                            failure_reason=failure_reason,
                            text_preview=_attachment_text_preview(att_text),
                            extracted_text=att_text,
                            normalized_text=normalized_text,
                            text_normalization_version=(ATTACHMENT_TEXT_NORMALIZATION_VERSION if normalized_text else 0),
                            text_source_path=f"attachment://{email.uid}/{att_i}/{att_name}",
                            text_locator=locator,
                            attachment_id=attachment_id,
                            content_sha256=content_sha256,
                            locator_version=2,
                        )
                        attachment_record = attachments[att_i] if 0 <= att_i < len(attachments) else {}
                        attachment_surfaces = attachment_record.get("surfaces") if isinstance(attachment_record, dict) else []
                        for surface in attachment_surfaces if isinstance(attachment_surfaces, list) else []:
                            if isinstance(surface, dict):
                                surface_kind = str(surface.get("surface_kind") or "reference_only")
                                surface_kind_mix[surface_kind] = surface_kind_mix.get(surface_kind, 0) + 1
                        primary_surface = primary_surface_payload(attachment_surfaces)
                        locator_payload = primary_surface.get("locator") if isinstance(primary_surface, dict) else {}
                        if isinstance(locator_payload, dict) and _is_locator_rich(locator_payload):
                            total_locator_rich_attachments += 1
                        if _looks_like_weak_language_signal(att_text):
                            total_weak_language_attachments += 1
                        if ocr_used and extraction_state == "ocr_text_extracted":
                            total_ocr_only_attachments += 1
                        att_chunks = chunk_attachment(
                            email_uid=email.uid,
                            filename=att_name,
                            text=att_text,
                            normalized_text=normalized_text,
                            parent_metadata={
                                "uid": email.uid,
                                "subject": email_dict.get("subject", ""),
                                "sender_name": email_dict.get("sender_name", ""),
                                "sender_email": email_dict.get("sender_email", ""),
                                "date": email_dict.get("date", ""),
                                "folder": email_dict.get("folder", ""),
                            },
                            att_index=att_i,
                            attachment_id=attachment_id,
                            content_sha256=content_sha256,
                            extraction_state=extraction_state,
                            evidence_strength="strong_text",
                            ocr_used=ocr_used,
                            failure_reason=failure_reason,
                            surface_id=str(primary_surface.get("surface_id") or ""),
                            surface_kind=str(primary_surface.get("surface_kind") or "verbatim"),
                            surface_origin_kind=str(primary_surface.get("origin_kind") or "native"),
                            surface_locator=locator_payload if isinstance(locator_payload, dict) else {},
                            surface_ocr_confidence=float(primary_surface.get("ocr_confidence") or 0.0),
                        )
                        total_chunks_created += len(att_chunks)
                        total_attachment_chunks += len(att_chunks)
                        attachment_chunk_count += len(att_chunks)
                        if embedder:
                            pending_chunks.extend(att_chunks)
                    else:
                        extraction_state, failure_reason = _textless_attachment_state_with_ocr(
                            filename=att_name,
                            mime_type=mime_type,
                            ocr_attempted=bool(attachment_ocr_extractor),
                            ocr_available=attachment_ocr_available_for(att_name, mime_type=mime_type),
                        )
                        _set_attachment_evidence(
                            email,
                            att_index=att_i,
                            extraction_state=extraction_state,
                            evidence_strength="weak_reference",
                            ocr_used=False,
                            ocr_engine="",
                            ocr_lang="",
                            ocr_confidence=0.0,
                            failure_reason=failure_reason,
                            text_preview="",
                            extracted_text="",
                            normalized_text="",
                            text_normalization_version=0,
                            text_source_path="",
                            text_locator=_mailbox_attachment_locator(
                                email_uid=email.uid,
                                att_index=att_i,
                                filename=att_name,
                                extraction_state=extraction_state,
                                attachment_id=attachment_id,
                                content_sha256=content_sha256,
                            ),
                            attachment_id=attachment_id,
                            content_sha256=content_sha256,
                            locator_version=2,
                        )
                        attachment_record = attachments[att_i] if 0 <= att_i < len(attachments) else {}
                        attachment_surfaces = attachment_record.get("surfaces") if isinstance(attachment_record, dict) else []
                        for surface in attachment_surfaces if isinstance(attachment_surfaces, list) else []:
                            if isinstance(surface, dict):
                                surface_kind = str(surface.get("surface_kind") or "reference_only")
                                surface_kind_mix[surface_kind] = surface_kind_mix.get(surface_kind, 0) + 1
                        primary_surface = primary_surface_payload(attachment_surfaces)
                        locator_payload = primary_surface.get("locator") if isinstance(primary_surface, dict) else {}
                        if isinstance(locator_payload, dict) and _is_locator_rich(locator_payload):
                            total_locator_rich_attachments += 1
                        format_profile = attachment_format_profile(
                            filename=att_name,
                            mime_type=mime_type,
                            extraction_state=extraction_state,
                            evidence_strength="weak_reference",
                            ocr_used=False,
                            text_available=False,
                        )
                        format_key = str(format_profile.get("format_id") or att_name.rsplit(".", 1)[-1].lower() or "unknown")
                        format_extraction_failures[format_key] = format_extraction_failures.get(format_key, 0) + 1

            _normalize_unprocessed_attachments(
                email,
                extraction_requested=bool(extract_attachments),
            )

            email._ingest_body_chunk_count = body_chunk_count
            email._ingest_attachment_chunk_count = attachment_chunk_count
            email._ingest_image_chunk_count = image_chunk_count
            email._ingest_attachment_requested = bool(extract_attachments)
            email._ingest_image_requested = bool(embed_images)

            progress.update(1)

            if max_emails is not None and total_emails >= max_emails:
                break

            if len(pending_chunks) >= batch_size or len(pending_emails) >= batch_size:
                if pipeline:
                    t_q = time.monotonic()
                    pipeline.submit(pending_chunks, pending_emails)
                    queue_wait_seconds += time.monotonic() - t_q
                    pending_chunks = []
                    pending_emails = []
                    batch_ordinal += 1
                    _update_ingest_checkpoint_safe(
                        checkpoint_store=checkpoint_store,
                        run_id=ingestion_run_id,
                        olm_path=olm_path,
                        last_batch_ordinal=batch_ordinal,
                        emails_parsed=total_emails,
                        emails_inserted=int(getattr(pipeline, "sqlite_inserted", 0) or 0),
                        last_email_uid=last_processed_uid,
                        status="running",
                        allow_locked_skip=True,
                        stage="mid_run_batch_submit",
                    )

        if pipeline:
            if pending_chunks or pending_emails:
                t_q = time.monotonic()
                pipeline.submit(pending_chunks, pending_emails)
                queue_wait_seconds += time.monotonic() - t_q
                batch_ordinal += 1
                _update_ingest_checkpoint_safe(
                    checkpoint_store=checkpoint_store,
                    run_id=ingestion_run_id,
                    olm_path=olm_path,
                    last_batch_ordinal=batch_ordinal,
                    emails_parsed=total_emails,
                    emails_inserted=int(getattr(pipeline, "sqlite_inserted", 0) or 0),
                    last_email_uid=last_processed_uid,
                    status="running",
                    allow_locked_skip=True,
                    stage="final_batch_submit",
                )
            pipeline.finish()

        elapsed = time.time() - start_time
        total_chunks_added = pipeline.chunks_added if pipeline else 0
        total_batches_written = pipeline.batches_written if pipeline else 0
        sqlite_inserted = pipeline.sqlite_inserted if pipeline else 0

        timing_dict: dict[str, float] = {}
        if pipeline:
            timing_dict["embed_seconds"] = round(pipeline.embed_seconds, 1)
            timing_dict["write_seconds"] = round(pipeline.write_seconds, 1)
            if timing:
                timing_dict["parse_seconds"] = round(parse_seconds, 1)
                timing_dict["queue_wait_seconds"] = round(queue_wait_seconds, 1)
                timing_dict["sqlite_seconds"] = round(pipeline.sqlite_seconds, 1)
                timing_dict["entity_seconds"] = round(pipeline.entity_seconds, 1)
                timing_dict["analytics_seconds"] = round(pipeline.analytics_seconds, 1)

        locator_ratio = (total_locator_rich_attachments / total_attachment_observed) if total_attachment_observed else 0.0
        ocr_ratio = (total_ocr_only_attachments / total_attachment_observed) if total_attachment_observed else 0.0
        weak_language_ratio = (total_weak_language_attachments / total_attachment_observed) if total_attachment_observed else 0.0
        ingest_attachment_telemetry = {
            "attachments_seen": total_attachment_observed,
            "locator_rich_count": total_locator_rich_attachments,
            "locator_rich_ratio": round(locator_ratio, 4),
            "ocr_only_count": total_ocr_only_attachments,
            "ocr_only_ratio": round(ocr_ratio, 4),
            "weak_language_count": total_weak_language_attachments,
            "weak_language_ratio": round(weak_language_ratio, 4),
            "duplicate_content_attachments": total_duplicate_content_attachments,
            "surface_kind_mix": dict(sorted(surface_kind_mix.items())),
            "format_extraction_failures": dict(sorted(format_extraction_failures.items())),
        }

        stats: dict[str, Any] = {
            "emails_parsed": total_emails,
            "chunks_created": total_chunks_created,
            "attachment_chunks": total_attachment_chunks,
            "image_embeddings": total_image_embeddings,
            "chunks_added": total_chunks_added,
            "chunks_skipped": (total_chunks_created - total_chunks_added) if embedder else 0,
            "batches_written": total_batches_written,
            "total_in_db": embedder.count() if embedder else None,
            "sqlite_inserted": sqlite_inserted,
            "skipped_incremental": total_skipped_incremental,
            "skipped_resume": total_skipped_resume,
            "dry_run": dry_run,
            "extract_attachments": extract_attachments,
            "extract_entities": extract_entities,
            "incremental": incremental,
            "resume": resume,
            "resumed_from_checkpoint": resumed_from_checkpoint,
            "elapsed_seconds": round(elapsed, 1),
            "timing": timing_dict,
            "ingest_attachment_telemetry": ingest_attachment_telemetry,
            "sparse_vectors_stored": int(getattr(embedder, "sparse_vectors_stored", 0) or 0) if embedder else 0,
            "sparse_store_failures": int(getattr(embedder, "sparse_store_failures", 0) or 0) if embedder else 0,
        }

        if bookkeeping_db and ingestion_run_id is not None:
            bookkeeping_db.record_ingestion_complete(
                ingestion_run_id,
                {
                    "emails_parsed": total_emails,
                    "emails_inserted": sqlite_inserted,
                },
            )
            if checkpoint_store and hasattr(checkpoint_store, "clear_ingest_checkpoint"):
                checkpoint_store.clear_ingest_checkpoint(ingestion_run_id, commit=True)

        resolve_runtime_summary(settings)
        return stats
    except Exception as exc:
        if pipeline:
            try:
                worker_error = pipeline.abort()
                if worker_error is not None and worker_error is not exc:
                    logger.warning("Background ingest pipeline error during abort: %s", worker_error)
            except Exception:
                logger.warning("Background ingest pipeline abort failed", exc_info=True)
        if bookkeeping_db and ingestion_run_id is not None:
            sqlite_inserted = pipeline.sqlite_inserted if pipeline else 0
            _update_ingest_checkpoint_safe(
                checkpoint_store=checkpoint_store,
                run_id=ingestion_run_id,
                olm_path=olm_path,
                last_batch_ordinal=batch_ordinal,
                emails_parsed=total_emails,
                emails_inserted=int(sqlite_inserted or 0),
                last_email_uid=last_processed_uid,
                status="failed",
                allow_locked_skip=False,
                stage="ingestion_failed",
            )
            bookkeeping_db.record_ingestion_failure(
                ingestion_run_id,
                error_message=str(exc),
                stats={
                    "emails_parsed": total_emails,
                    "emails_inserted": sqlite_inserted,
                },
            )
        raise
    finally:
        try:
            progress.close()
        except Exception:
            pass
        if control_db:
            control_db.close()
        if email_db:
            email_db.close()
