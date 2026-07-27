"""Adapt source-neutral mailbox records into the canonical email archive."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .attachment_extractor import classify_text_extraction_state, extract_text_with_reason
from .attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    attachment_chunk_token,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from .chunker import chunk_attachment, chunk_email
from .mailbox_models import MailboxMessageRecord
from .mailbox_store import MailboxStore
from .parse_olm import Email


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


def canonical_uid_for_record(record: MailboxMessageRecord, *, db: Any, store: MailboxStore) -> tuple[str, bool]:
    """Resolve stable identity without binding canonical IDs to mutable EWS IDs."""
    remote_item_id = record.remote_item_id or record.source_identity
    source_row = store.conn.execute(
        "SELECT canonical_email_uid FROM email_sources WHERE account_id=? AND source=? AND remote_item_id=?",
        (record.account_id, record.source, remote_item_id),
    ).fetchone()
    if source_row is not None and source_row[0]:
        return str(source_row[0]), False

    if record.canonical_email_uid:
        return record.canonical_email_uid, False

    if record.internet_message_id:
        candidate = hashlib.sha256(record.internet_message_id.encode()).hexdigest()
        existing = db.conn.execute(
            "SELECT sender_email,date,content_sha256 FROM emails WHERE uid=?",
            (candidate,),
        ).fetchone()
        if existing is None or _fingerprint_matches(record, existing, db):
            return candidate, False

    source_key = f"{record.source}:{record.account_id}:{remote_item_id}"
    return hashlib.sha256(source_key.encode()).hexdigest(), bool(record.internet_message_id)


def _fingerprint_matches(record: MailboxMessageRecord, existing: Any, db: Any) -> bool:
    """Require consistent envelope and content before cross-source identity reuse."""
    sender_matches = not record.sender_email or not existing["sender_email"] or record.sender_email == existing["sender_email"]
    date_matches = not record.received_at or not existing["date"] or record.received_at == existing["date"]
    body_hash = db.compute_content_hash(record.body_text) if record.body_text else None
    content_matches = not body_hash or not existing["content_sha256"] or body_hash == existing["content_sha256"]
    return bool(sender_matches and date_matches and content_matches)


def mailbox_record_to_email(record: MailboxMessageRecord, canonical_uid: str) -> Email:
    """Project an EWS record into the archive's exercised email model."""
    attachments = _attachment_projection(record)
    return Email(
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


def persist_mailbox_record(
    record: MailboxMessageRecord,
    *,
    db: Any,
    store: MailboxStore,
    embedder: Any | None = None,
) -> MailboxIngestResult:
    """Upsert one mailbox record and refresh affected body/attachment vectors."""
    canonical_uid, possible_duplicate = canonical_uid_for_record(record, db=db, store=store)
    if record.is_tombstone:
        _persist_tombstone(record, store)
        return MailboxIngestResult(
            canonical_uid,
            tombstoned=True,
            possible_duplicate=possible_duplicate,
        )

    email, existing, source_row, content_hash, source_folders, canonical_preexisting = _prepare_mailbox_projection(
        record, canonical_uid, db=db, store=store
    )
    inserted = existing is None and bool(db.insert_email(email))
    content_changed = existing is not None and content_hash != existing["content_sha256"]
    projection_hash = _projection_hash(
        record,
        content_hash,
        source_folders=source_folders,
    )
    previous_metadata = json.loads(source_row["metadata_json"]) if source_row is not None else {}
    metadata_changed = existing is not None and previous_metadata.get("projection_hash") != projection_hash
    if content_changed or metadata_changed:
        _update_existing_email(db, email, content_hash)

    metadata = dict(record.metadata)
    metadata["possible_duplicate"] = possible_duplicate
    metadata["projection_hash"] = projection_hash
    metadata["canonical_preexisting"] = canonical_preexisting
    indexed = _index_mailbox_projection(
        embedder, email, canonical_uid, inserted=inserted, changed=content_changed or metadata_changed
    )
    # The projection hash is the durable retry marker. Record it only after
    # vector work succeeds so a transient indexing failure is repaired by the
    # next sync replay instead of being mistaken for a completed projection.
    store.upsert_source(
        MailboxMessageRecord(
            **{
                **record.__dict__,
                "canonical_email_uid": canonical_uid,
                "remote_item_id": record.remote_item_id or record.source_identity,
                "metadata": metadata,
            }
        )
    )
    return MailboxIngestResult(
        canonical_uid,
        inserted=inserted,
        content_changed=content_changed,
        metadata_changed=metadata_changed,
        indexed_chunks=indexed,
        possible_duplicate=possible_duplicate,
    )


def _persist_tombstone(record: MailboxMessageRecord, store: MailboxStore) -> None:
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
    db: Any,
    store: MailboxStore,
) -> tuple[Email, Any, Any, str | None, tuple[str, ...], bool]:
    email = mailbox_record_to_email(record, canonical_uid)
    content_hash = db.compute_content_hash(email.clean_body) if email.clean_body else None
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


def _existing_canonical_email(db: Any, canonical_uid: str, email: Email) -> Any:
    existing = db.conn.execute("SELECT content_sha256,raw_source,folder FROM emails WHERE uid=?", (canonical_uid,)).fetchone()
    if existing is not None:
        _preserve_existing_attachment_metadata(email, db)
    return existing


def _existing_mailbox_source(store: MailboxStore, record: MailboxMessageRecord) -> Any:
    return store.conn.execute(
        "SELECT canonical_preexisting,metadata_json FROM email_sources WHERE account_id=? AND source=? AND remote_item_id=?",
        (record.account_id, record.source, record.remote_item_id or record.source_identity),
    ).fetchone()


def _canonical_preexisting(existing: Any, source_row: Any) -> bool:
    if source_row is not None:
        return bool(source_row["canonical_preexisting"])
    return bool(existing is not None and str(existing["raw_source"] or "") != "ews")


def _index_mailbox_projection(
    embedder: Any | None,
    email: Email,
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


def _preserve_existing_attachment_metadata(email: Email, db: Any) -> None:
    """Keep richer canonical attachment identities when EWS supplies metadata only."""
    existing_by_key: dict[tuple[str, str, int, bool], list[dict[str, Any]]] = defaultdict(list)
    for existing in db.attachments_for_email(email.uid):
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
    store: MailboxStore,
    canonical_folder: str,
    canonical_preexisting: bool,
) -> tuple[tuple[str, ...], bool]:
    """Project post-upsert folder membership without committing the retry marker."""
    remote_item_id = record.remote_item_id or record.source_identity
    folders: set[str] = set()
    preexisting = canonical_preexisting
    rows = store.conn.execute(
        "SELECT account_id,source,remote_item_id,folder_id,is_tombstone,"
        "canonical_preexisting FROM email_sources WHERE canonical_email_uid=?",
        (canonical_uid,),
    ).fetchall()
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


def _mailbox_chunks(email: Email) -> tuple[list[Any], set[str]]:
    """Create body chunks and any locally extracted attachment chunks."""
    email_dict = email.to_dict()
    email_dict["source_folders"] = list(email.source_folders)
    chunks = list(chunk_email(email_dict))
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


def _update_existing_email(db: Any, email: Email, content_hash: str | None) -> None:
    """Refresh mutable EWS content while preserving canonical evidence rows."""
    with db.operation():
        db.conn.execute("BEGIN IMMEDIATE")
        try:
            db.update_body_text(
                email.uid,
                email.clean_body,
                email.body_html,
                normalized_body_source=email.clean_body_source,
                body_normalization_version=email.body_normalization_version,
                body_kind=email.body_kind,
                body_empty_reason=email.body_empty_reason,
                recovery_strategy=email.recovery_strategy,
                recovery_confidence=email.recovery_confidence,
                commit=False,
            )
            db.update_headers(
                email.uid,
                email.subject,
                email.sender_name,
                email.sender_email,
                email.base_subject,
                email.email_type,
                commit=False,
            )
            db.conn.execute(
                "UPDATE emails SET date=?,folder=?,priority=?,is_read=?,body_length=?,content_sha256=? WHERE uid=?",
                (email.date, email.folder, email.priority, int(email.is_read), len(email.clean_body), content_hash, email.uid),
            )
            db.update_v7_metadata(email, commit=False)
            _replace_recipients(db.conn, email)
            db.conn.commit()
        except Exception:
            db.conn.rollback()
            raise


def _replace_recipients(conn: Any, email: Email) -> None:
    """Replace envelope recipients for a changed mailbox item."""
    conn.execute("DELETE FROM recipients WHERE email_uid=?", (email.uid,))
    rows = [
        (email.uid, address, "", kind)
        for kind, values in (("to", email.to), ("cc", email.cc), ("bcc", email.bcc))
        for address in values
        if address
    ]
    if rows:
        conn.executemany(
            "INSERT OR IGNORE INTO recipients(email_uid,address,display_name,type) VALUES(?,?,?,?)",
            rows,
        )


def _delete_obsolete_chunks(
    embedder: Any,
    uid: str,
    retained_ids: set[str],
    *,
    preserved_attachment_prefixes: set[str] | None = None,
) -> None:
    """Remove stale derived rows after a changed message produces fewer chunks."""
    existing_ids = embedder.get_existing_ids(refresh=True)
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
    existing_ids.difference_update(obsolete)
    embedder.checkpoint()
