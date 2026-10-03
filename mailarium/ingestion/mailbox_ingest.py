"""Adapt source-neutral mailbox records into the canonical email archive."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Protocol

from mailarium.ingestion.olm.body_forensics import render_forensic_text
from mailarium.ingestion.records import ParsedMessage
from mailarium.model.attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    attachment_chunk_token,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from mailarium.model.conversation_segments import extract_segments
from mailarium.model.mailbox_models import MailboxMessageRecord

from .attachments.extract import classify_text_extraction_state, extract_text_with_reason
from .chunker import _chunk_forensic_email_surface, chunk_attachment, chunk_email

if TYPE_CHECKING:
    import sqlite3

    from mailarium.archive import ArchiveDatabase


class MailboxSourceStore(Protocol):
    """Persistence operations required to project one mailbox record."""

    def shares_archive(self, database: ArchiveDatabase) -> bool: ...

    def batch_write(self) -> AbstractContextManager[None]: ...

    def upsert_source(self, record: MailboxMessageRecord) -> None: ...

    def finalize_source_projection(self, record: MailboxMessageRecord) -> None: ...

    def tombstone_source(
        self,
        *,
        account_id: str,
        folder_id: str,
        source: str,
        source_identity: str,
        change_key: str = "",
    ) -> None: ...

    def canonical_email_uid_for_remote_item(self, account_id: str, source: str, remote_item_id: str) -> str: ...

    def projection_marker(self, account_id: str, source: str, remote_item_id: str) -> Any: ...

    def sources_for_canonical_email(self, canonical_email_uid: str) -> list[Any]: ...


@dataclass(frozen=True)
class MailboxIngestResult:
    """Describe the canonical persistence and indexing outcome for one item."""

    canonical_email_uid: str
    inserted: bool = False
    content_changed: bool = False
    metadata_changed: bool = False
    tombstoned: bool = False
    indexed_chunks: int = 0
    possible_duplicate: bool = False


def canonical_uid_for_record(record: MailboxMessageRecord, *, db: ArchiveDatabase, store: MailboxSourceStore) -> tuple[str, bool]:
    """Resolve stable identity without binding canonical IDs to mutable EWS IDs."""
    remote_item_id = record.remote_item_id or record.source_identity
    linked_uid = store.canonical_email_uid_for_remote_item(record.account_id, record.source, remote_item_id)
    if linked_uid:
        return linked_uid, False

    if record.canonical_email_uid:
        return record.canonical_email_uid, False

    if record.internet_message_id:
        candidate = hashlib.sha256(record.internet_message_id.encode()).hexdigest()
        existing = db.queries.email_identity_fingerprint(candidate)
        if existing is None or _fingerprint_matches(record, existing, db):
            return candidate, False

    source_key = f"{record.source}:{record.account_id}:{remote_item_id}"
    return hashlib.sha256(source_key.encode()).hexdigest(), bool(record.internet_message_id)


def _fingerprint_matches(record: MailboxMessageRecord, existing: sqlite3.Row, db: ArchiveDatabase) -> bool:
    """Require consistent envelope and content before cross-source identity reuse."""
    sender_matches = not record.sender_email or not existing["sender_email"] or record.sender_email == existing["sender_email"]
    date_matches = not record.received_at or not existing["date"] or record.received_at == existing["date"]
    body_hash = db.custody.compute_content_hash(record.body_text) if record.body_text else None
    content_matches = not body_hash or not existing["content_sha256"] or body_hash == existing["content_sha256"]
    return bool(sender_matches and date_matches and content_matches)


def mailbox_record_to_email(record: MailboxMessageRecord, canonical_uid: str) -> ParsedMessage:
    """Project an EWS record into the archive's exercised email model."""
    attachments = _attachment_projection(record)
    forensic_body = render_forensic_text(record.body_text, record.body_html, "ews")
    email = ParsedMessage(
        message_id=record.internet_message_id,
        subject=record.subject,
        sender_name=record.sender_name,
        sender_email=record.sender_email,
        to=list(record.to),
        cc=list(record.cc),
        bcc=list(record.bcc),
        date=record.received_at,
        body_text=record.body_text,
        body_html=record.body_html,
        raw_body_text=record.body_text,
        raw_body_html=record.body_html,
        forensic_body_text=forensic_body.text,
        forensic_body_source=f"ews_{forensic_body.source}",
        folder=record.folder_id,
        has_attachments=bool(attachments),
        attachment_names=[str(value.get("name") or "") for value in attachments if value.get("name")],
        attachments=attachments,
        attachment_contents=list(record.attachment_contents),
        conversation_id=record.conversation_id,
        in_reply_to=record.in_reply_to,
        priority={"Low": -1, "Normal": 0, "High": 1}.get(record.importance, 0),
        is_read=record.is_read,
        categories=list(record.categories),
        raw_source="ews",
        recipient_identity_source="ews",
        canonical_uid_override=canonical_uid,
    )
    email.segments = extract_segments(record.body_text, record.body_html, "ews", email.email_type)
    return email


@dataclass(frozen=True)
class _PreparedProjection:
    email: ParsedMessage | None
    source: MailboxMessageRecord | None
    result: MailboxIngestResult
    finalize: bool = False


def persist_mailbox_record(
    record: MailboxMessageRecord,
    *,
    db: ArchiveDatabase,
    store: MailboxSourceStore,
    embedder: Any | None = None,
) -> MailboxIngestResult:
    """Upsert one mailbox record and refresh affected body/attachment vectors."""
    prepared = _prepare_record_projection(record, db=db, store=store, batch=False)
    result = _index_prepared_projection(prepared, embedder)
    _finalize_prepared_projection(prepared, store)
    return result


def persist_mailbox_records(
    records: Sequence[MailboxMessageRecord],
    *,
    db: ArchiveDatabase,
    store: MailboxSourceStore,
    embedder: Any | None = None,
) -> list[MailboxIngestResult]:
    """Project a bounded page with durable pending markers before vector work.

    Canonical rows and pending source markers commit together. Final source
    hashes commit only after every record's vector work succeeds. A failure
    leaves the page replayable without advancing its cursor.
    """
    if not store.shares_archive(db):
        raise ValueError("mailbox batches require the canonical shared connection")
    return [
        result
        for batch in _source_batches(records)
        for result in _persist_record_batch(batch, db=db, store=store, embedder=embedder)
    ]


def _source_batches(records: Sequence[MailboxMessageRecord]) -> Iterator[list[MailboxMessageRecord]]:
    """Bound batches and finish each source observation before a repeated identity."""
    batch: list[MailboxMessageRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        identity = (record.account_id, record.source, record.remote_item_id or record.source_identity)
        if len(batch) == 100 or identity in seen:
            yield batch
            batch = []
            seen.clear()
        batch.append(record)
        seen.add(identity)
    if batch:
        yield batch


def _persist_record_batch(
    records: Sequence[MailboxMessageRecord], *, db: ArchiveDatabase, store: MailboxSourceStore, embedder: Any
) -> list[MailboxIngestResult]:
    with db.operation():
        with store.batch_write():
            prepared = [_prepare_record_projection(record, db=db, store=store, batch=True) for record in records]
        defer = getattr(embedder, "defer_checkpoints", None)
        with defer() if callable(defer) else nullcontext():
            results = [_index_prepared_projection(projection, embedder) for projection in prepared]
        with store.batch_write():
            for projection in prepared:
                _finalize_prepared_projection(projection, store)
        return results


def _index_prepared_projection(prepared: _PreparedProjection, embedder: Any) -> MailboxIngestResult:
    if prepared.email is None:
        return prepared.result
    indexed = _index_mailbox_projection(
        embedder,
        prepared.email,
        prepared.result.canonical_email_uid,
        inserted=prepared.result.inserted,
        changed=prepared.result.content_changed or prepared.result.metadata_changed,
    )
    return replace(prepared.result, indexed_chunks=indexed)


def _finalize_prepared_projection(prepared: _PreparedProjection, store: MailboxSourceStore) -> None:
    if prepared.source is None:
        return
    if prepared.finalize:
        store.finalize_source_projection(prepared.source)
    else:
        store.upsert_source(prepared.source)


def _prepare_record_projection(
    record: MailboxMessageRecord, *, db: ArchiveDatabase, store: MailboxSourceStore, batch: bool
) -> _PreparedProjection:
    """Persist canonical content and the retry marker, leaving vector work outside the transaction."""
    canonical_uid, possible_duplicate = canonical_uid_for_record(record, db=db, store=store)
    if record.is_tombstone:
        _persist_tombstone(record, store)
        return _PreparedProjection(
            None, None, MailboxIngestResult(canonical_uid, tombstoned=True, possible_duplicate=possible_duplicate)
        )

    email, existing, source_row, content_hash, source_folders, canonical_preexisting = _prepare_mailbox_projection(
        record, canonical_uid, db=db, store=store
    )
    inserted = existing is None and (
        canonical_uid in db.messages.insert_emails_batch([email], commit=False)
        if batch
        else bool(db.messages.insert_email(email))
    )
    content_changed = existing is not None and (
        content_hash != existing["content_sha256"] or _body_evidence_changed(email, existing)
    )
    projection_hash = _projection_hash(
        record,
        content_hash,
        source_folders=source_folders,
    )
    previous_metadata = json.loads(source_row["metadata_json"]) if source_row is not None else {}
    metadata_changed = existing is not None and previous_metadata.get("projection_hash") != projection_hash
    if content_changed or metadata_changed:
        db.messages.refresh_mailbox_message(email, content_hash, commit=not batch)

    metadata = dict(record.metadata)
    metadata["possible_duplicate"] = possible_duplicate
    metadata["projection_hash"] = projection_hash
    metadata["canonical_preexisting"] = canonical_preexisting
    projection_pending = bool(previous_metadata.get("projection_pending"))
    source_values = {
        **record.__dict__,
        "canonical_email_uid": canonical_uid,
        "remote_item_id": record.remote_item_id or record.source_identity,
        "metadata": metadata,
    }
    needs_finalization = batch or (inserted and source_row is None) or projection_pending
    if needs_finalization and not projection_pending:
        pending_metadata = dict(metadata)
        pending_metadata.pop("projection_hash")
        pending_metadata["projection_pending"] = True
        store.upsert_source(
            MailboxMessageRecord(
                **{
                    **source_values,
                    "metadata": pending_metadata,
                }
            )
        )
    return _PreparedProjection(
        email,
        MailboxMessageRecord(**source_values),
        MailboxIngestResult(
            canonical_uid,
            inserted=inserted,
            content_changed=content_changed,
            metadata_changed=metadata_changed,
            possible_duplicate=possible_duplicate,
        ),
        needs_finalization,
    )


def _persist_tombstone(record: MailboxMessageRecord, store: MailboxSourceStore) -> None:
    store.tombstone_source(
        account_id=record.account_id,
        folder_id=record.folder_id,
        source=record.source,
        source_identity=record.source_identity,
        change_key=record.change_key,
    )


def _prepare_mailbox_projection(
    record: MailboxMessageRecord,
    canonical_uid: str,
    *,
    db: ArchiveDatabase,
    store: MailboxSourceStore,
) -> tuple[ParsedMessage, Any, Any, str | None, tuple[str, ...], bool]:
    email = mailbox_record_to_email(record, canonical_uid)
    content_hash = db.custody.compute_content_hash(email.clean_body) if email.clean_body else None
    existing = _existing_canonical_email(db, canonical_uid, email)
    source_row = _existing_mailbox_source(store, record)
    canonical_preexisting = _canonical_preexisting(existing, source_row)
    source_folders, canonical_preexisting = _project_record_source_folders(
        record,
        canonical_uid,
        store=store,
        canonical_folder=str(existing["folder"] or "") if existing is not None else "",
        canonical_preexisting=canonical_preexisting,
    )
    email.source_folders = list(source_folders)
    if existing is not None and canonical_preexisting:
        email.folder = str(existing["folder"] or email.folder)
    elif source_folders:
        email.folder = source_folders[0]
    return email, existing, source_row, content_hash, source_folders, canonical_preexisting


def _existing_canonical_email(db: ArchiveDatabase, canonical_uid: str, email: ParsedMessage) -> sqlite3.Row | None:
    existing = db.queries.email_projection_state(canonical_uid)
    if existing is not None:
        _preserve_existing_attachment_metadata(email, db)
    return existing


def _body_evidence_changed(email: ParsedMessage, existing: Any) -> bool:
    """Detect recovered source text even when normalized authored content is unchanged."""
    if str(existing["raw_source"] or "") not in {"", "ews"}:
        return False
    return any(
        (
            email.raw_body_text != str(existing["raw_body_text"] or ""),
            email.raw_body_html != str(existing["raw_body_html"] or ""),
            email.forensic_body_text != str(existing["forensic_body_text"] or ""),
        )
    )


def _existing_mailbox_source(store: MailboxSourceStore, record: MailboxMessageRecord) -> Any:
    return store.projection_marker(record.account_id, record.source, record.remote_item_id or record.source_identity)


def _canonical_preexisting(existing: Any, source_row: Any) -> bool:
    if source_row is not None:
        return bool(source_row["canonical_preexisting"])
    return bool(existing is not None and str(existing["raw_source"] or "") != "ews")


def _index_mailbox_projection(
    embedder: Any | None,
    email: ParsedMessage,
    canonical_uid: str,
    *,
    inserted: bool,
    changed: bool,
) -> int:
    if embedder is None or not (inserted or changed):
        return 0
    chunks, preserved_attachment_prefixes = _mailbox_chunks(email)
    if not changed:
        return int(embedder.add_chunks(chunks, show_progress=False))
    indexed = int(embedder.upsert_chunks(chunks))
    _delete_obsolete_chunks(
        embedder,
        canonical_uid,
        {chunk.chunk_id for chunk in chunks},
        preserved_attachment_prefixes=preserved_attachment_prefixes,
    )
    return indexed


def _attachment_projection(record: MailboxMessageRecord) -> list[dict[str, Any]]:
    """Attach stable local identities and optional extracted text to EWS metadata."""
    remaining = list(record.attachment_contents)
    projected: list[dict[str, Any]] = []
    for raw in record.attachments:
        attachment = dict(raw)
        name = str(attachment.get("name") or "attachment")
        content = _take_attachment_content(remaining, name)
        local_identity = {key: value for key, value in attachment.items() if key not in {"attachment_id", "remote_attachment_id"}}
        attachment_id, _metadata_sha = ensure_attachment_identity(local_identity)
        _content_identity, content_sha256 = ensure_attachment_identity(
            local_identity,
            content_bytes=content,
        )
        attachment["attachment_id"] = attachment_id
        attachment["content_sha256"] = content_sha256
        if content is not None:
            text, failure_reason = extract_text_with_reason(
                name,
                content,
                mime_type=str(attachment.get("mime_type") or "") or None,
            )
            if text:
                normalized = normalize_attachment_search_text(text)
                attachment.update(
                    {
                        "extracted_text": text,
                        "normalized_text": normalized,
                        "text_normalization_version": (ATTACHMENT_TEXT_NORMALIZATION_VERSION if normalized else 0),
                        "extraction_state": classify_text_extraction_state(name, text),
                        "evidence_strength": "strong_text",
                        "failure_reason": "",
                        "text_preview": text[:500],
                    }
                )
            else:
                attachment.update(
                    {
                        "extraction_state": "no_text",
                        "evidence_strength": "reference_only",
                        "failure_reason": failure_reason or "no extractable text",
                    }
                )
        projected.append(attachment)
    return projected


_PRESERVED_ATTACHMENT_FIELDS = (
    "attachment_id",
    "content_sha256",
    "extracted_text",
    "normalized_text",
    "text_normalization_version",
    "extraction_state",
    "evidence_strength",
    "failure_reason",
    "text_preview",
    "ocr_used",
    "ocr_engine",
    "ocr_lang",
    "ocr_confidence",
    "locator_version",
    "text_source_path",
    "text_locator",
    "surfaces",
)


def _attachment_reconciliation_key(attachment: dict[str, Any]) -> tuple[str, str, int, bool]:
    """Match an EWS metadata row to an existing canonical attachment."""
    return (
        str(attachment.get("name") or "").casefold(),
        str(attachment.get("mime_type") or "").casefold(),
        int(attachment.get("size") or 0),
        bool(attachment.get("is_inline")),
    )


def _preserve_existing_attachment_metadata(email: ParsedMessage, db: ArchiveDatabase) -> None:
    """Keep richer canonical attachment identities when EWS supplies metadata only."""
    existing_by_key: dict[tuple[str, str, int, bool], list[dict[str, Any]]] = defaultdict(list)
    for existing in db.attachments.attachments_for_email(email.uid):
        existing_by_key[_attachment_reconciliation_key(existing)].append(existing)
    for attachment in email.attachments:
        candidates = existing_by_key.get(_attachment_reconciliation_key(attachment), [])
        if not candidates:
            continue
        _preserve_attachment_metadata(attachment, candidates)


def _preserve_attachment_metadata(attachment: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    content_sha256 = str(attachment.get("content_sha256") or "")
    if content_sha256:
        matching = next(
            (candidate for candidate in candidates if str(candidate.get("content_sha256") or "") == content_sha256),
            None,
        )
        if matching is not None and matching.get("attachment_id"):
            attachment["attachment_id"] = matching["attachment_id"]
        return
    previous = candidates.pop(0)
    for field in _PRESERVED_ATTACHMENT_FIELDS:
        value = previous.get(field)
        if value not in (None, "", [], {}):
            attachment[field] = value


def _take_attachment_content(
    remaining: list[tuple[str, bytes]],
    name: str,
) -> bytes | None:
    for index, (candidate, content) in enumerate(remaining):
        if candidate == name:
            remaining.pop(index)
            return content
    return None


def _project_record_source_folders(
    record: MailboxMessageRecord,
    canonical_uid: str,
    *,
    store: MailboxSourceStore,
    canonical_folder: str,
    canonical_preexisting: bool,
) -> tuple[tuple[str, ...], bool]:
    """Project post-upsert folder membership without committing the retry marker."""
    remote_item_id = record.remote_item_id or record.source_identity
    folders: set[str] = set()
    preexisting = canonical_preexisting
    rows = store.sources_for_canonical_email(canonical_uid)
    for row in rows:
        if _is_current_record_source(row, record, remote_item_id):
            continue
        preexisting = preexisting or bool(row["canonical_preexisting"])
        if not bool(row["is_tombstone"]):
            folder = str(row["folder_id"] or "").strip()
            if folder:
                folders.add(folder)
    if record.folder_id:
        folders.add(record.folder_id)
    if preexisting and canonical_folder:
        folders.add(canonical_folder)
    return tuple(sorted(folders)), preexisting


def _is_current_record_source(row: Any, record: MailboxMessageRecord, remote_item_id: str) -> bool:
    return (
        str(row["account_id"]) == record.account_id
        and str(row["source"]) == record.source
        and str(row["remote_item_id"]) == remote_item_id
    )


def _mailbox_chunks(email: ParsedMessage) -> tuple[list[Any], set[str]]:
    """Create body chunks and any locally extracted attachment chunks."""
    email_dict = email.to_dict()
    email_dict["source_folders"] = list(email.source_folders)
    chunks = list(chunk_email(email_dict))
    chunks.extend(_chunk_forensic_email_surface(email_dict))
    preserved_prefixes: set[str] = set()
    parent_metadata = {
        "uid": email.uid,
        "subject": email.subject,
        "sender_name": email.sender_name,
        "sender_email": email.sender_email,
        "date": email.date,
        "folder": email.folder,
        "source_folders": list(email.source_folders),
    }
    for index, attachment in enumerate(email.attachments):
        name = str(attachment.get("name") or "attachment")
        attachment_id = str(attachment.get("attachment_id") or "")
        text = str(attachment.get("extracted_text") or "")
        token = attachment_chunk_token(
            attachment_id=attachment_id,
            filename=name,
            att_index=index,
        )
        prefix = f"{email.uid}__att_{token}__"
        if not text:
            preserved_prefixes.add(prefix)
            continue
        chunks.extend(
            chunk_attachment(
                email.uid,
                name,
                text,
                parent_metadata,
                att_index=index,
                attachment_id=attachment_id,
                content_sha256=str(attachment.get("content_sha256") or ""),
                normalized_text=str(attachment.get("normalized_text") or ""),
                extraction_state=str(attachment.get("extraction_state") or "text_extracted"),
                evidence_strength=str(attachment.get("evidence_strength") or "strong_text"),
                failure_reason=str(attachment.get("failure_reason") or "") or None,
            )
        )
    return chunks, preserved_prefixes


def _projection_hash(
    record: MailboxMessageRecord,
    content_hash: str | None,
    *,
    source_folders: tuple[str, ...],
) -> str:
    """Hash canonical fields that affect relational or vector retrieval metadata."""
    attachment_content = [(name, hashlib.sha256(content).hexdigest()) for name, content in record.attachment_contents]
    payload = {
        "subject": record.subject,
        "received_at": record.received_at,
        "sender_name": record.sender_name,
        "sender_email": record.sender_email,
        "to": list(record.to),
        "cc": list(record.cc),
        "bcc": list(record.bcc),
        "source_folders": source_folders,
        "content_hash": content_hash,
        "source_body_hash": hashlib.sha256(
            f"{record.body_text}\0{record.body_html}".encode("utf-8", errors="ignore")
        ).hexdigest(),
        "is_read": record.is_read,
        "importance": record.importance,
        "categories": list(record.categories),
        "conversation_id": record.conversation_id,
        "attachments": [
            {key: value for key, value in dict(attachment).items() if key != "remote_attachment_id"}
            for attachment in record.attachments
        ],
        "attachment_content": attachment_content,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _delete_obsolete_chunks(
    embedder: Any,
    uid: str,
    retained_ids: set[str],
    *,
    preserved_attachment_prefixes: set[str] | None = None,
) -> None:
    """Remove stale derived rows after a changed message produces fewer chunks."""
    existing_ids = embedder.get_ids_for_uids([uid])
    prefixes = preserved_attachment_prefixes or set()
    obsolete = sorted(
        chunk_id
        for chunk_id in existing_ids
        if chunk_id.startswith(f"{uid}__")
        and chunk_id not in retained_ids
        and not any(chunk_id.startswith(prefix) for prefix in prefixes)
    )
    if not obsolete:
        return
    embedder.collection.delete(ids=obsolete)
    embedder.image_collection.delete(ids=obsolete)
    embedder.forget_existing_ids(obsolete)
    embedder.checkpoint()
