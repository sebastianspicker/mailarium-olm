"""Core ingestion pipeline implementation."""

from __future__ import annotations

import os
import time
from typing import Any


def _set_attachment_evidence(
    email,
    *,
    att_index: int,
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    failure_reason: str | None,
    text_preview: str = "",
) -> None:
    """Persist attachment evidence semantics on the parsed email object."""
    attachments = getattr(email, "attachments", None) or []
    if 0 <= att_index < len(attachments):
        attachment = attachments[att_index]
        attachment["extraction_state"] = extraction_state
        attachment["evidence_strength"] = evidence_strength
        attachment["ocr_used"] = bool(ocr_used)
        attachment["failure_reason"] = failure_reason
        attachment["text_preview"] = text_preview


def _attachment_text_preview(text: str, *, max_chars: int = 280) -> str:
    """Return a compact persisted preview for extracted attachment text."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


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
    timing: bool,
    get_settings,
    resolve_runtime_summary,
    should_enable_image_embedding,
    parse_olm,
    chunk_email,
    chunk_attachment,
    hash_file_sha256,
    resolve_entity_extractor,
    exchange_entities_from_email,
    embed_pipeline_cls,
    make_progress_bar,
) -> dict[str, Any]:
    """Parse an OLM file and ingest all emails into the vector database."""
    settings = get_settings()
    start_time = time.time()

    if embed_images:
        extract_attachments = True

    embedder, email_db = _build_runtime(
        settings=settings,
        dry_run=dry_run,
        chromadb_path=chromadb_path,
        sqlite_path=sqlite_path,
    )

    entity_extractor_fn = resolve_entity_extractor(extract_entities, dry_run)

    attachment_extractor = None
    if extract_attachments:
        from .attachment_extractor import extract_text

        attachment_extractor = extract_text

    image_embedder_fn = None
    is_image_attachment = None
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
            is_image_attachment = _is_image
            probe = _get_image_embedder()
            if not probe.is_available:
                image_embedder_fn = None
        else:
            embed_images = False

    _preload_models(embedder, entity_extractor_fn)

    ingestion_run_id = None
    if email_db:
        olm_sha256 = None
        olm_file_size = None
        if os.path.isfile(olm_path):
            olm_sha256 = hash_file_sha256(olm_path)
            olm_file_size = os.path.getsize(olm_path)
        ingestion_run_id = email_db.record_ingestion_start(
            olm_path,
            olm_sha256=olm_sha256,
            file_size_bytes=olm_file_size,
        )

    total_emails = 0
    total_chunks_created = 0
    total_attachment_chunks = 0
    total_image_embeddings = 0
    total_skipped_incremental = 0
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
            batch_size=batch_size,
            ingestion_run_id=ingestion_run_id,
        )
        pipeline.start()

    progress = make_progress_bar(max_emails, desc="Ingesting", unit="email")

    for email in parse_olm(olm_path, extract_attachments=extract_attachments):
        t_parse_start = time.monotonic()
        total_emails += 1

        if incremental and email_db and email_db.email_exists(email.uid):
            chroma_ok = True
            if embedder and hasattr(embedder, "collection"):
                try:
                    existing = embedder.collection.get(ids=[f"{email.uid}__0"], include=[])
                    chroma_ok = bool(existing and existing.get("ids"))
                except Exception:
                    chroma_ok = False
            if chroma_ok:
                total_skipped_incremental += 1
                progress.update(1)
                parse_seconds += time.monotonic() - t_parse_start
                continue

        email_dict = email.to_dict()
        chunks = chunk_email(email_dict)
        total_chunks_created += len(chunks)
        if embedder:
            pending_chunks.extend(chunks)
        if email_db:
            pending_emails.append(email)

        if attachment_extractor and email.attachment_contents:
            from .chunker import EmailChunk

            for att_i, (att_name, att_bytes) in enumerate(email.attachment_contents):
                if image_embedder_fn and is_image_attachment and is_image_attachment(att_name):
                    img_embedding = image_embedder_fn(att_name, att_bytes)
                    _set_attachment_evidence(
                        email,
                        att_index=att_i,
                        extraction_state="image_embedding_only",
                        evidence_strength="weak_reference",
                        ocr_used=False,
                        failure_reason="no_text_extracted",
                        text_preview="",
                    )
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
                                "filename": att_name,
                                "extraction_state": "image_embedding_only",
                                "evidence_strength": "weak_reference",
                                "ocr_used": "False",
                                "failure_reason": "no_text_extracted",
                            },
                            embedding=img_embedding,
                        )
                        pending_chunks.append(img_chunk)
                        total_chunks_created += 1
                        total_image_embeddings += 1
                    continue

                att_text = attachment_extractor(att_name, att_bytes)
                if att_text:
                    _set_attachment_evidence(
                        email,
                        att_index=att_i,
                        extraction_state="text_extracted",
                        evidence_strength="strong_text",
                        ocr_used=False,
                        failure_reason=None,
                        text_preview=_attachment_text_preview(att_text),
                    )
                    att_chunks = chunk_attachment(
                        email_uid=email.uid,
                        filename=att_name,
                        text=att_text,
                        parent_metadata={
                            "uid": email.uid,
                            "subject": email_dict.get("subject", ""),
                            "sender_name": email_dict.get("sender_name", ""),
                            "sender_email": email_dict.get("sender_email", ""),
                            "date": email_dict.get("date", ""),
                            "folder": email_dict.get("folder", ""),
                        },
                        att_index=att_i,
                        extraction_state="text_extracted",
                        evidence_strength="strong_text",
                        ocr_used=False,
                        failure_reason=None,
                    )
                    total_chunks_created += len(att_chunks)
                    total_attachment_chunks += len(att_chunks)
                    if embedder:
                        pending_chunks.extend(att_chunks)
                else:
                    _set_attachment_evidence(
                        email,
                        att_index=att_i,
                        extraction_state="binary_only",
                        evidence_strength="weak_reference",
                        ocr_used=False,
                        failure_reason="no_text_extracted",
                        text_preview="",
                    )

        progress.update(1)
        parse_seconds += time.monotonic() - t_parse_start

        if max_emails is not None and total_emails >= max_emails:
            break

        if len(pending_chunks) >= batch_size or len(pending_emails) >= batch_size:
            if pipeline:
                t_q = time.monotonic()
                pipeline.submit(pending_chunks, pending_emails)
                queue_wait_seconds += time.monotonic() - t_q
                pending_chunks = []
                pending_emails = []

    if pipeline:
        if pending_chunks or pending_emails:
            t_q = time.monotonic()
            pipeline.submit(pending_chunks, pending_emails)
            queue_wait_seconds += time.monotonic() - t_q
        pipeline.finish()

    progress.close()

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
        "dry_run": dry_run,
        "extract_attachments": extract_attachments,
        "extract_entities": extract_entities,
        "incremental": incremental,
        "elapsed_seconds": round(elapsed, 1),
        "timing": timing_dict,
    }

    if email_db and ingestion_run_id is not None:
        email_db.record_ingestion_complete(
            ingestion_run_id,
            {
                "emails_parsed": total_emails,
                "emails_inserted": sqlite_inserted,
            },
        )

    if email_db:
        email_db.close()

    resolve_runtime_summary(settings)
    return stats
