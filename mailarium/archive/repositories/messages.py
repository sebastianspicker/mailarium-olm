"""Canonical message writes: inserts, body and header refreshes, and mailbox content updates."""

from __future__ import annotations

import sqlite3

from mailarium.model import Message
from mailarium.model.body_normalization import BODY_NORMALIZATION_VERSION

from ..locking import ArchiveRepository, archive_repository
from ..session import ArchiveSession
from .attachments import AttachmentRepository
from .message_rows import (
    EMAIL_INSERT_OR_IGNORE_SQL,
    EMAIL_INSERT_SQL,
    BatchRows,
    build_email_insert_row,
    collect_batch_related_rows,
    persist_batch_rows,
    persist_single_related_rows,
    replace_mailbox_body_evidence,
    replace_mailbox_recipients,
    replace_v7_attachments,
    replace_v7_categories,
    update_v7_email_row,
)


@archive_repository
class MessageRepository(ArchiveRepository):
    """Insert canonical messages with their related rows and refresh mutable message fields."""

    def __init__(self, session: ArchiveSession, *, attachments: AttachmentRepository) -> None:
        super().__init__(session)
        self._attachments = attachments

    def insert_email(self, email: Message, *, ingestion_run_id: int | None = None) -> bool:
        """Insert a single email and update contacts/edges.

        Returns False if uid already exists (duplicate).
        All writes happen in a single transaction - either the email and all
        its related rows (recipients, contacts, edges) are committed together,
        or nothing is written.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            cur.execute(EMAIL_INSERT_SQL, build_email_insert_row(email, ingestion_run_id))
            persist_single_related_rows(cur, email)
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False
        except Exception:
            self.conn.rollback()
            raise
        return True

    def insert_emails_batch(
        self,
        emails: list[Message],
        ingestion_run_id: int | None = None,
        *,
        commit: bool = True,
    ) -> set[str]:
        """Insert a batch of emails in a single transaction.

        Returns the set of UIDs that were actually inserted (new emails).
        The set is truthy/has ``len()`` so callers that only need the count
        still work via ``len(result)`` or ``bool(result)``.

        Uses batched parameter collection for recipients, categories,
        attachments, contacts, and communication edges to reduce per-row
        execute() overhead.  With ``commit=False`` the caller owns the
        surrounding transaction.
        """
        inserted_uids: set[str] = set()
        cur = self.conn.cursor()
        rows = BatchRows()
        try:
            if commit:
                cur.execute("BEGIN IMMEDIATE")
            for email in emails:
                cur.execute(EMAIL_INSERT_OR_IGNORE_SQL, build_email_insert_row(email, ingestion_run_id))
                if cur.rowcount == 0:
                    continue
                collect_batch_related_rows(cur, email, rows)
                inserted_uids.add(email.uid)
            persist_batch_rows(cur, rows)
            if commit:
                self.conn.commit()
        except Exception:
            if commit:
                self.conn.rollback()
            raise
        return inserted_uids

    def update_body_text(
        self,
        uid: str,
        body_text: str,
        body_html: str,
        *,
        normalized_body_source: str | None = None,
        body_normalization_version: int | None = None,
        body_kind: str | None = None,
        body_empty_reason: str | None = None,
        recovery_strategy: str | None = None,
        recovery_confidence: float | None = None,
        commit: bool = True,
    ) -> bool:
        """Update body_text and body_html for an existing email.

        Only overwrites body_html if the new value is non-empty, to avoid
        losing good HTML content when the re-parsed email lacks an HTML body.
        Returns True if updated.  Pass ``commit=False`` to defer the commit
        (caller is responsible for calling ``self.conn.commit()``).
        """
        if normalized_body_source is None:
            normalized_body_source = "body_text"
        if body_normalization_version is None:
            body_normalization_version = BODY_NORMALIZATION_VERSION
        if body_kind is None:
            body_kind = "content"
        if body_empty_reason is None:
            body_empty_reason = ""
        if recovery_strategy is None:
            recovery_strategy = ""
        if recovery_confidence is None:
            recovery_confidence = 0.0

        if body_html:
            cur = self.conn.execute(
                """UPDATE emails
                   SET body_text = ?, body_html = ?, normalized_body_source = ?,
                       body_normalization_version = ?, body_kind = ?, body_empty_reason = ?,
                       recovery_strategy = ?, recovery_confidence = ?
                 WHERE uid = ?""",
                (
                    body_text,
                    body_html,
                    normalized_body_source,
                    body_normalization_version,
                    body_kind,
                    body_empty_reason,
                    recovery_strategy,
                    recovery_confidence,
                    uid,
                ),
            )
        else:
            cur = self.conn.execute(
                """UPDATE emails
                   SET body_text = ?, normalized_body_source = ?,
                       body_normalization_version = ?, body_kind = ?, body_empty_reason = ?,
                       recovery_strategy = ?, recovery_confidence = ?
                 WHERE uid = ?""",
                (
                    body_text,
                    normalized_body_source,
                    body_normalization_version,
                    body_kind,
                    body_empty_reason,
                    recovery_strategy,
                    recovery_confidence,
                    uid,
                ),
            )
        if commit:
            self.conn.commit()
        return cur.rowcount > 0

    def update_headers(
        self,
        uid: str,
        subject: str,
        sender_name: str,
        sender_email: str,
        base_subject: str,
        email_type: str,
        *,
        commit: bool = True,
    ) -> bool:
        """Update decoded header fields for an existing email.

        Fixes MIME encoded-word subjects and sender names that were stored
        without decoding during earlier ingestions.  Returns True if updated.
        Pass ``commit=False`` to defer the commit.
        """
        cur = self.conn.execute(
            """UPDATE emails
               SET subject = ?, sender_name = ?, sender_email = ?,
                   base_subject = ?, email_type = ?
             WHERE uid = ?""",
            (subject, sender_name, sender_email, base_subject, email_type, uid),
        )
        if commit:
            self.conn.commit()
        return cur.rowcount > 0

    def update_v7_metadata(self, email: Message, *, commit: bool = True) -> bool:
        """Update schema-v7 metadata fields for an existing email.

        Populates categories, thread_topic, inference_classification,
        is_calendar_message, references_json, and related tables
        (email_categories, attachments). Returns True if updated.
        Pass ``commit=False`` to defer the commit.
        """
        cur = self.conn.cursor()
        if not update_v7_email_row(cur, email):
            return False
        replace_v7_categories(cur, email)
        replace_v7_attachments(cur, email, self._attachments.attachments_for_email(email.uid))
        if commit:
            self.conn.commit()
        return True

    def refresh_mailbox_message(self, email: Message, content_hash: str | None, *, commit: bool = True) -> None:
        """Refresh mutable mailbox content, envelope, segments, and recipients as one unit of work.

        Canonical evidence rows are preserved.  With ``commit=True`` the
        refresh runs in its own ``BEGIN IMMEDIATE`` transaction and rolls back
        on failure. Pass ``commit=False`` when the caller already owns the
        surrounding transaction.
        """
        if commit:
            self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.update_body_text(
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
            self.update_headers(
                email.uid,
                email.subject,
                email.sender_name,
                email.sender_email,
                email.base_subject,
                email.email_type,
                commit=False,
            )
            replace_mailbox_body_evidence(self.conn, email)
            self.conn.execute(
                "UPDATE emails SET date=?,folder=?,priority=?,is_read=?,body_length=?,content_sha256=? WHERE uid=?",
                (email.date, email.folder, email.priority, int(email.is_read), len(email.clean_body), content_hash, email.uid),
            )
            self.update_v7_metadata(email, commit=False)
            replace_mailbox_recipients(self.conn, email)
            if commit:
                self.conn.commit()
        except Exception:
            if commit:
                self.conn.rollback()
            raise
