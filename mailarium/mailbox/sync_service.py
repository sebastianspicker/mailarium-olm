"""Bounded EWS synchronization and canonical record projection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from mailarium.model.mailbox_models import MailboxMessageRecord

from .mailbox_runtime import MailboxRuntimePolicy
from .mailbox_store import MailboxStore
from .service_context import MailboxServiceContext

_GET_ITEM_BATCH_SIZE = 20


@dataclass
class _AttachmentContentBudget:
    remaining_bytes: int

    def consume(self, size: int) -> None:
        if size < 0 or size > self.remaining_bytes:
            raise ValueError("EWS attachment content exceeds the per-sync byte limit.")
        self.remaining_bytes -= size


class MailboxSynchronizationService(MailboxServiceContext):
    def sync(
        self,
        account_id: str,
        *,
        folders: Iterable[str] = (),
        include_attachment_content: bool = False,
        until_complete: bool = False,
        defer_indexing: bool = False,
    ) -> dict[str, Any]:
        """Synchronize selected folders in one bounded pass or until complete when explicitly requested."""
        account = self._remote_account(account_id, require_write=False)
        selected = self._selected_folders(account_id, folders)
        if include_attachment_content and not self.policy.attachment_content_enabled:
            raise PermissionError("Attachment content is disabled; set EWS_ATTACHMENT_CONTENT_ENABLED=true to opt in.")
        if self.db is None:
            raise RuntimeError("Mailbox synchronization requires the canonical ArchiveDatabase.")

        gateway = self.gateway_factory(account, self.policy)
        embedder = self.embedder_factory() if not defer_indexing and self.embedder_factory is not None else None
        attachment_budget = (
            _AttachmentContentBudget(self.policy.max_attachment_total_bytes_per_sync) if include_attachment_content else None
        )
        totals = {"created": 0, "updated": 0, "deleted": 0, "indexed_chunks": 0}
        folder_totals: dict[str, dict[str, Any]] = {}
        pending = selected
        passes = 0
        try:
            while pending:
                passes += 1
                next_pending, cursor_before = self._sync_pass(
                    account_id,
                    pending,
                    gateway,
                    embedder,
                    include_attachment_content=include_attachment_content,
                    attachment_budget=attachment_budget,
                    folder_totals=folder_totals,
                    totals=totals,
                )
                if not until_complete or not next_pending:
                    pending = tuple(next_pending)
                    break
                if not any(
                    cursor_before[folder_id] != _cursor_progress_state(self.store, account_id, folder_id)
                    for folder_id in next_pending
                ):
                    raise RuntimeError("EWS sync made no cursor progress while incomplete folders remain.")
                pending = tuple(next_pending)
        finally:
            close = getattr(embedder, "close", None)
            if callable(close):
                close()
        result = {"account_id": account_id, **totals, "folders": folder_totals}
        if until_complete:
            result.update({"passes": passes, "complete": not pending})
        return result

    def _sync_pass(
        self,
        account_id: str,
        pending: Iterable[str],
        gateway: Any,
        embedder: Any | None,
        *,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
        folder_totals: dict[str, dict[str, Any]],
        totals: dict[str, int],
    ) -> tuple[list[str], dict[str, tuple[int, str, str]]]:
        cursor_before = {folder_id: _cursor_progress_state(self.store, account_id, folder_id) for folder_id in pending}
        next_pending: list[str] = []
        for folder_id in pending:
            pass_totals = self._sync_folder(
                account_id,
                folder_id,
                gateway,
                embedder,
                include_attachment_content=include_attachment_content,
                attachment_budget=attachment_budget,
            )
            aggregate = folder_totals.setdefault(
                folder_id,
                {"created": 0, "updated": 0, "deleted": 0, "indexed_chunks": 0, "complete": False},
            )
            for name in ("created", "updated", "deleted", "indexed_chunks"):
                aggregate[name] += int(pass_totals[name])
                totals[name] += int(pass_totals[name])
            aggregate["complete"] = bool(pass_totals["complete"])
            if not aggregate["complete"]:
                next_pending.append(folder_id)
        return next_pending, cursor_before

    def _sync_folder(
        self,
        account_id: str,
        folder_id: str,
        gateway: Any,
        embedder: Any | None,
        *,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> dict[str, Any]:
        generation, watermark, full_refresh = self._sync_cursor_state(account_id, folder_id)
        result = {"created": 0, "updated": 0, "deleted": 0, "indexed_chunks": 0, "complete": False}
        reset_attempted = False
        while True:
            remaining = self.policy.max_sync_items - _sync_processed_count(result)
            if remaining <= 0:
                return result
            request_watermark = watermark
            delta, generation, watermark, full_refresh, reset_attempted = self._request_sync_delta(
                account_id, folder_id, gateway, generation, watermark, full_refresh, reset_attempted, remaining
            )
            if delta is None:
                continue
            next_watermark = _validate_sync_delta(delta, watermark, remaining)
            items = _synchronized_items(gateway, delta)
            self._persist_sync_items(
                result,
                account_id,
                folder_id,
                items,
                delta,
                gateway,
                embedder,
                generation,
                include_attachment_content,
                attachment_budget,
            )
            self._tombstone_sync_items(result, account_id, folder_id, delta.deleted)
            watermark = next_watermark
            self._commit_sync_page(result, account_id, folder_id, delta, watermark, generation, request_watermark, full_refresh)
            if not delta.has_more:
                result["complete"] = True
                return result
            if _sync_processed_count(result) >= self.policy.max_sync_items:
                return result

    def _sync_cursor_state(self, account_id: str, folder_id: str) -> tuple[int, str, bool]:
        generation, watermark = self.store.get_cursor(account_id, folder_id, scope="items")
        full_refresh = generation == 0 or self.store.cursor_state(account_id, folder_id) == "full_refresh"
        if full_refresh and generation == 0:
            generation = self.store.start_cursor_generation(account_id, folder_id, scope="items", expected_generation=generation)
        return generation, watermark, full_refresh

    def _request_sync_delta(
        self,
        account_id: str,
        folder_id: str,
        gateway: Any,
        generation: int,
        watermark: str,
        full_refresh: bool,
        reset_attempted: bool,
        remaining: int,
    ) -> tuple[Any | None, int, str, bool, bool]:
        try:
            delta = gateway.sync_folder_items(folder_id, watermark=watermark or None, max_changes=min(100, remaining))
        except Exception as exc:
            if reset_attempted or not _is_expired_watermark(exc):
                raise
            generation = self.store.start_cursor_generation(account_id, folder_id, scope="items", expected_generation=generation)
            return None, generation, "", True, True
        return delta, generation, watermark, full_refresh, reset_attempted

    def _persist_sync_items(
        self,
        result: dict[str, Any],
        account_id: str,
        folder_id: str,
        items: tuple[Any, ...],
        delta: Any,
        gateway: Any,
        embedder: Any | None,
        generation: int,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> None:
        created_ids = {value.item_id for value in delta.created}
        for item in items:
            record = self._record_from_ews_item(
                account_id,
                folder_id,
                item,
                gateway,
                generation=generation,
                include_attachment_content=include_attachment_content,
                attachment_budget=attachment_budget,
            )
            persisted = self._persist_record(record, db=self.db, store=self.store, embedder=embedder)
            result["created" if item.item_id in created_ids else "updated"] += 1
            result["indexed_chunks"] += int(getattr(persisted, "indexed_chunks", 0))

    def _tombstone_sync_items(self, result: dict[str, Any], account_id: str, folder_id: str, deleted: Any) -> None:
        for item in deleted:
            self._tombstone_remote(account_id, folder_id, item.item_id, item.change_key or "")
            result["deleted"] += 1

    def _commit_sync_page(
        self,
        result: dict[str, Any],
        account_id: str,
        folder_id: str,
        delta: Any,
        watermark: str,
        generation: int,
        request_watermark: str,
        full_refresh: bool,
    ) -> None:
        if not delta.has_more and full_refresh:
            result["deleted"] += self.store.complete_full_refresh(
                account_id,
                folder_id,
                watermark,
                generation=generation,
                expected_cursor_value=request_watermark,
                scope="items",
            )
            return
        self.store.commit_cursor(
            account_id,
            folder_id,
            watermark,
            scope="items",
            expected_generation=generation,
            expected_cursor_value=request_watermark,
            completed=not delta.has_more,
        )

    def _record_from_ews_item(
        self,
        account_id: str,
        folder_id: str,
        item: Any,
        gateway: Any,
        *,
        generation: int,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> MailboxMessageRecord:
        attachments, contents = self._item_attachments(item, gateway, include_attachment_content, attachment_budget)
        return MailboxMessageRecord(
            account_id=account_id,
            folder_id=folder_id,
            source="ews",
            source_identity=item.item_id,
            remote_item_id=item.item_id,
            change_key=item.change_key or "",
            subject=item.subject,
            received_at=item.received_at or "",
            internet_message_id=item.internet_message_id or "",
            sender_email=item.sender or "",
            to=tuple(item.recipients),
            cc=tuple(item.cc_recipients),
            bcc=tuple(item.bcc_recipients),
            body_text=item.body_text or "",
            is_read=bool(item.is_read),
            importance=item.importance or "Normal",
            categories=tuple(item.categories),
            conversation_id=item.conversation_id or "",
            attachments=tuple(attachments),
            attachment_contents=tuple(contents),
            metadata={
                "sync_generation": generation,
                "is_read": bool(item.is_read),
                "importance": item.importance or "Normal",
                "subject": item.subject,
            },
        )

    def _item_attachments(
        self,
        item: Any,
        gateway: Any,
        include_attachment_content: bool,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> tuple[list[dict[str, Any]], list[tuple[str, bytes]]]:
        attachments = [_attachment_metadata(attachment) for attachment in item.attachments]
        file_attachments = tuple(attachment for attachment in item.attachments if attachment.attachment_type == "file")
        if include_attachment_content and len(file_attachments) > self.policy.max_attachments_per_item:
            raise ValueError("EWS item exceeds the configured attachment-count limit.")
        if not include_attachment_content:
            return attachments, []
        return attachments, self._load_attachment_contents(file_attachments, gateway, attachment_budget)

    def _load_attachment_contents(
        self,
        attachments: tuple[Any, ...],
        gateway: Any,
        attachment_budget: _AttachmentContentBudget | None,
    ) -> list[tuple[str, bytes]]:
        if attachment_budget is None:
            raise RuntimeError("Attachment content budget is unavailable.")
        contents: list[tuple[str, bytes]] = []
        item_remaining_bytes = self.policy.max_attachment_total_bytes_per_item
        for attachment in attachments:
            allowed_bytes = _allowed_attachment_bytes(self.policy, attachment, item_remaining_bytes, attachment_budget)
            loaded = gateway.get_attachment(attachment.attachment_id, max_content_bytes=allowed_bytes)
            if loaded.content is not None:
                loaded_size = len(loaded.content)
                if loaded_size > allowed_bytes:
                    raise ValueError("EWS attachment content exceeds an aggregate byte limit.")
                item_remaining_bytes -= loaded_size
                attachment_budget.consume(loaded_size)
                contents.append((loaded.name or attachment.name or "attachment", loaded.content))
        return contents

    def _tombstone_remote(self, account_id: str, folder_id: str, remote_item_id: str, change_key: str) -> None:
        self.store.tombstone_source(
            account_id=account_id,
            folder_id=folder_id,
            source="ews",
            source_identity=remote_item_id,
            change_key=change_key,
        )


def _sync_processed_count(result: Mapping[str, Any]) -> int:
    return sum(int(result[name]) for name in ("created", "updated", "deleted"))


def _cursor_progress_state(store: MailboxStore, account_id: str, folder_id: str) -> tuple[int, str, str]:
    generation, watermark = store.get_cursor(account_id, folder_id, scope="items")
    return generation, watermark, store.cursor_state(account_id, folder_id)


def _validate_sync_delta(delta: Any, watermark: str, remaining: int) -> str:
    returned_changes = len(delta.created) + len(delta.updated) + len(delta.deleted)
    raw_change_count = getattr(delta, "raw_change_count", None)
    if raw_change_count is not None and returned_changes != int(raw_change_count):
        raise RuntimeError("EWS sync response contained unsupported or unparsed changes.")
    if returned_changes > min(100, remaining):
        raise RuntimeError("EWS sync response exceeded the requested change limit.")
    next_watermark = delta.watermark or watermark
    if delta.has_more and next_watermark == watermark:
        raise RuntimeError("EWS sync watermark did not advance for a partial page.")
    return next_watermark


def _synchronized_items(gateway: Any, delta: Any) -> tuple[Any, ...]:
    changed_refs = (*delta.created, *delta.updated)
    items = tuple(
        item
        for start in range(0, len(changed_refs), _GET_ITEM_BATCH_SIZE)
        for item in gateway.get_items(changed_refs[start : start + _GET_ITEM_BATCH_SIZE])
    )
    if len(items) != len(changed_refs):
        raise RuntimeError("EWS GetItem did not return every synchronized item.")
    return items


def _attachment_metadata(attachment: Any) -> dict[str, Any]:
    return {
        "remote_attachment_id": attachment.attachment_id,
        "name": attachment.name or "",
        "mime_type": attachment.content_type or "",
        "size": int(attachment.size or 0),
        "is_inline": bool(attachment.is_inline),
        "attachment_type": attachment.attachment_type,
    }


def _allowed_attachment_bytes(
    policy: MailboxRuntimePolicy,
    attachment: Any,
    item_remaining_bytes: int,
    attachment_budget: _AttachmentContentBudget,
) -> int:
    declared_size = max(0, int(attachment.size or 0))
    if declared_size > policy.max_attachment_bytes:
        raise ValueError("EWS attachment exceeds the configured content limit.")
    allowed_bytes = min(policy.max_attachment_bytes, item_remaining_bytes, attachment_budget.remaining_bytes)
    if allowed_bytes < 1 or declared_size > allowed_bytes:
        raise ValueError("EWS attachment content exceeds an aggregate byte limit.")
    return allowed_bytes


def _is_expired_watermark(exc: Exception) -> bool:
    return getattr(exc, "code", "") in {"ErrorInvalidSyncStateData", "ErrorSyncStateNotFound"}
