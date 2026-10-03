"""Read queries over canonical messages: counts, browsing, threads, segments, and corpus reads."""

from __future__ import annotations

import re
import sqlite3

from ..locking import ArchiveRepository, archive_repository
from ..session import ArchiveSession
from ..sql import escape_like as _escape_like
from ..sql import sql_in_placeholders as _sql_in_placeholders
from .attachments import AttachmentRepository
from .browse import (
    BrowsePageRequest,
    emails_full_batch,
    hydrate_email,
    list_emails_page,
    recipients_for_uid,
    reembed_email_payload,
    related_thread_emails,
)


def _ranked_segment_rows(rows: list[sqlite3.Row], tokens: list[str], normalized_phrase: str, limit: int) -> list[dict]:
    """Sort segment rows by retrieval score and retain positive matches."""
    ranked: list[dict] = []
    for row in rows:
        item = _ranked_segment_row(dict(row), tokens, normalized_phrase)
        if item is not None:
            ranked.append(item)
    ranked.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(item.get("date") or ""),
            int(item.get("ordinal") or 0),
        )
    )
    return ranked[:limit]


def _ranked_segment_row(item: dict, tokens: list[str], normalized_phrase: str) -> dict | None:
    """Return the highest-ranked segment row or no result."""
    haystack = " ".join(str(item.get("segment_text") or "").split()).casefold()
    if not haystack:
        return None
    matched_tokens = [token for token in tokens if token in haystack]
    phrase_match = normalized_phrase in haystack
    if not phrase_match and not matched_tokens:
        return None
    score = 0.35 + (0.4 if phrase_match else 0.0)
    if tokens:
        score += min(0.2, (len(matched_tokens) / len(tokens)) * 0.2)
    if str(item.get("segment_type") or "") == "quoted_reply":
        score += 0.05
    item["score"] = round(min(score, 0.99), 4)
    item["matched_tokens"] = matched_tokens
    return item


@archive_repository
class MessageQueryRepository(ArchiveRepository):
    """Read queries, full-body retrieval, browsing, and grouping over canonical messages."""

    def __init__(self, session: ArchiveSession, *, attachments: AttachmentRepository) -> None:
        super().__init__(session)
        self._attachments = attachments

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def email_count(self) -> int:
        """Return total number of emails in the database."""
        row = self.conn.execute("SELECT COUNT(*) AS c FROM emails").fetchone()
        return row["c"]

    def unique_sender_count(self) -> int:
        """Return count of distinct sender email addresses."""
        row = self.conn.execute("SELECT COUNT(DISTINCT sender_email) AS c FROM emails").fetchone()
        return row["c"]

    def date_range(self) -> tuple[str, str]:
        """Return (earliest_date, latest_date) across all emails."""
        row = self.conn.execute("SELECT MIN(NULLIF(date, '')) AS min_d, MAX(NULLIF(date, '')) AS max_d FROM emails").fetchone()
        return (row["min_d"] or "", row["max_d"] or "")

    def folder_counts(self) -> dict[str, int]:
        """Return effective-folder counts without duplicating canonical emails."""
        rows = self.conn.execute(
            "SELECT effective_folders.folder,COUNT(DISTINCT effective_folders.uid) AS c "
            "FROM ("
            "SELECT emails.uid,active_source.folder_id AS folder "
            "FROM emails JOIN email_sources active_source "
            "ON active_source.canonical_email_uid=emails.uid "
            "WHERE active_source.is_tombstone=0 "
            "UNION "
            "SELECT emails.uid,emails.folder AS folder FROM emails "
            "WHERE NOT EXISTS (SELECT 1 FROM email_sources mailbox_source "
            "WHERE mailbox_source.canonical_email_uid=emails.uid) "
            "OR EXISTS (SELECT 1 FROM email_sources mailbox_source "
            "WHERE mailbox_source.canonical_email_uid=emails.uid "
            "AND mailbox_source.canonical_preexisting=1)"
            ") AS effective_folders "
            "WHERE effective_folders.folder IS NOT NULL AND effective_folders.folder != '' "
            "GROUP BY effective_folders.folder ORDER BY c DESC,effective_folders.folder ASC"
        ).fetchall()
        return {r["folder"]: r["c"] for r in rows}

    def top_senders(self, limit: int = 30) -> list[dict]:
        """Return senders ranked by message count."""
        rows = self.conn.execute(
            """SELECT sender_email, sender_name, COUNT(*) AS message_count
               FROM emails
               GROUP BY sender_email
               ORDER BY message_count DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_message_segments(
        self,
        query: str,
        *,
        segment_types: tuple[str, ...] = ("quoted_reply", "forwarded_message"),
        limit: int = 20,
    ) -> list[dict]:
        """Search persisted quoted/forwarded message segments with lexical matching.

        This is an additive retrieval lane for historical quoted context that is
        intentionally conservative and SQLite-backed. Results are scored
        synthetically from phrase and token overlap and are not meant to replace
        semantic retrieval.
        """
        compact_query = " ".join(str(query or "").split()).strip()
        if not compact_query or not segment_types:
            return []

        tokens = [token for token in re.findall(r"[\w@.-]{4,}", compact_query.casefold()) if token]
        like_patterns = [compact_query.casefold(), *tokens]
        if not like_patterns:
            return []

        segment_placeholders = _sql_in_placeholders(segment_types)
        conditions = ["LOWER(ms.text) LIKE ? ESCAPE '\\'" for _ in like_patterns]
        params: list[object] = [*segment_types, *[f"%{_escape_like(pattern)}%" for pattern in like_patterns], limit * 8]
        where_clause = f"WHERE ms.segment_type IN ({segment_placeholders}) AND ({' OR '.join(conditions)})"  # nosec B608
        rows = self.conn.execute(
            "SELECT ms.email_uid AS uid, "
            "ms.ordinal, ms.segment_type, ms.depth, ms.text AS segment_text, "
            "ms.source_surface, e.subject, e.sender_email, e.sender_name, "
            "e.date, e.conversation_id, e.folder, e.has_attachments, "
            "e.attachment_count, e.detected_language, e.detected_language_confidence "
            "FROM message_segments ms "
            "JOIN emails e ON e.uid = ms.email_uid "
            f"{where_clause} "  # nosec B608
            "ORDER BY e.date DESC, ms.ordinal ASC "
            "LIMIT ?",
            params,
        ).fetchall()
        return _ranked_segment_rows(rows, tokens, compact_query.casefold(), limit)

    # ------------------------------------------------------------------
    # Category / Calendar / Attachment queries (schema v7)
    # ------------------------------------------------------------------

    def category_counts(self) -> list[dict]:
        """Get category names with email counts."""
        rows = self.conn.execute(
            """SELECT category, COUNT(*) AS count
               FROM email_categories
               GROUP BY category
               ORDER BY count DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def calendar_emails(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get calendar/meeting emails, optionally filtered by date."""
        query = "SELECT uid, subject, sender_email, date, folder FROM emails WHERE is_calendar_message = 1"
        params: list = []
        if date_from:
            query += " AND SUBSTR(date, 1, 10) >= ?"
            params.append(date_from[:10])
        if date_to:
            query += " AND SUBSTR(date, 1, 10) <= ?"
            params.append(date_to[:10])
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def thread_by_topic(self, thread_topic: str, limit: int = 50) -> list[dict]:
        """Find all emails sharing a thread topic."""
        rows = self.conn.execute(
            """SELECT uid, subject, sender_email, date, folder
               FROM emails
               WHERE thread_topic = ?
               ORDER BY date ASC LIMIT ?""",
            (thread_topic, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Full-body retrieval (Phase: export & browse)
    # ------------------------------------------------------------------

    def get_email_full(self, uid: str) -> dict | None:
        """Return one complete email record, including body and attachment metadata."""
        row = self.conn.execute("SELECT * FROM emails WHERE uid = ?", (uid,)).fetchone()
        if not row:
            return None
        recipients = recipients_for_uid(self.conn, uid)
        return hydrate_email(dict(row), recipients, self._attachments.attachments_for_email(uid))

    def get_emails_full_batch(self, uids: list[str]) -> dict[str, dict]:
        """Return complete email records keyed by UID for batch export."""
        return emails_full_batch(self.conn, uids)

    def get_thread_emails(self, conversation_id: str) -> list[dict]:
        """Return messages that share an explicit conversation identifier, sorted by date."""
        return related_thread_emails(self.conn, conversation_id, inferred=False)

    def get_inferred_thread_emails(self, inferred_thread_id: str) -> list[dict]:
        """Return messages grouped by the inferred thread identifier, sorted by date."""
        return related_thread_emails(self.conn, inferred_thread_id, inferred=True)

    def list_emails_paginated(
        self,
        offset: int = 0,
        limit: int = 20,
        sort_by: str = "date",
        sort_order: str = "DESC",
        folder: str | None = None,
        sender: str | None = None,
        category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """List filtered email summaries with stable pagination and ordering."""
        return list_emails_page(
            self.conn,
            BrowsePageRequest(
                offset=offset,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order,
                folder=folder,
                sender=sender,
                category=category,
                date_from=date_from,
                date_to=date_to,
            ),
        )

    # ------------------------------------------------------------------
    # Re-embed helper
    # ------------------------------------------------------------------

    def get_email_for_reembed(self, uid: str) -> dict | None:
        """Return the stored email fields required to regenerate its embeddings."""
        full = self.get_email_full(uid)
        if not full:
            return None
        body = full.get("body_text") or ""
        if not body.strip():
            return None
        return reembed_email_payload(full, body)

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    def emails_by_base_subject(self, min_group_size: int = 2) -> list[tuple[str, list[tuple[str, str]]]]:
        """Group emails by base_subject for dedup comparison.

        Returns:
            List of (base_subject, [(uid, body_text), ...]) tuples,
            only groups with >= min_group_size emails.
        """
        # Single query: fetch all emails whose base_subject appears >= min_group_size times
        rows = self.conn.execute(
            """
            SELECT e.base_subject, e.uid, e.body_text
            FROM emails e
            JOIN (
                SELECT base_subject
                FROM emails
                WHERE base_subject IS NOT NULL AND base_subject != ''
                GROUP BY base_subject
                HAVING COUNT(*) >= ?
                ORDER BY COUNT(*) DESC
                LIMIT 500
            ) g ON e.base_subject = g.base_subject
            ORDER BY e.base_subject, e.date
            """,
            (min_group_size,),
        ).fetchall()

        # Group results in Python
        groups: dict[str, list[tuple[str, str]]] = {}
        for row in rows:
            groups.setdefault(row["base_subject"], []).append((row["uid"], row["body_text"] or ""))

        return list(groups.items())

    # ------------------------------------------------------------------
    # Projection, segment, and corpus reads for feature services
    # ------------------------------------------------------------------

    def email_identity_fingerprint(self, uid: str) -> sqlite3.Row | None:
        """Return the sender, date, and content hash used to confirm cross-source identity."""
        return self.conn.execute(
            "SELECT sender_email,date,content_sha256 FROM emails WHERE uid=?",
            (uid,),
        ).fetchone()

    def email_projection_state(self, uid: str) -> sqlite3.Row | None:
        """Return the stored content hash, source, folder, and body surfaces compared by mailbox projection."""
        return self.conn.execute(
            "SELECT content_sha256,raw_source,folder,raw_body_text,raw_body_html,forensic_body_text FROM emails WHERE uid=?",
            (uid,),
        ).fetchone()

    def sender_email_count(self, sender_email: str) -> int:
        """Return how many stored messages were sent from one address."""
        row = self.conn.execute("SELECT COUNT(*) AS c FROM emails WHERE sender_email = ?", (sender_email,)).fetchone()
        return row["c"]

    def message_segments_for_email(self, uid: str, *, include_provenance: bool = False) -> list[dict]:
        """Return one message's persisted conversation segments in ordinal order."""
        if include_provenance:
            rows = self.conn.execute(
                """SELECT ordinal, segment_type, depth, text, source_surface, provenance_json
               FROM message_segments WHERE email_uid = ? ORDER BY ordinal ASC""",
                (uid,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT ordinal, segment_type, depth, text, source_surface
           FROM message_segments
           WHERE email_uid = ?
           ORDER BY ordinal ASC""",
                (uid,),
            ).fetchall()
        return [dict(row) for row in rows]

    def message_segments_for_emails(self, uids: list[str]) -> dict[str, list[dict]]:
        """Return ordered conversation segments for several messages, keyed by message UID."""
        if not uids:
            return {}
        placeholders = _sql_in_placeholders(uids)
        rows = self.conn.execute(
            "SELECT email_uid, ordinal, segment_type, depth, text, source_surface "
            f"FROM message_segments WHERE email_uid IN ({placeholders}) "  # nosec B608
            "ORDER BY email_uid ASC, ordinal ASC",
            uids,
        ).fetchall()
        by_uid: dict[str, list[dict]] = {}
        for row in rows:
            item = dict(row)
            by_uid.setdefault(str(item.pop("email_uid")), []).append(item)
        return by_uid

    def thread_topics_for_uids(self, uids: list[str]) -> dict[str, str]:
        """Return each listed message's thread topic, empty when unset."""
        if not uids:
            return {}
        placeholders = _sql_in_placeholders(uids)
        rows = self.conn.execute(
            f"SELECT uid, thread_topic FROM emails WHERE uid IN ({placeholders})",  # nosec B608
            uids,
        ).fetchall()
        return {row["uid"]: row["thread_topic"] or "" for row in rows}

    def archive_totals(self) -> sqlite3.Row | None:
        """Return the message count and raw earliest and latest dates across the archive."""
        return self.conn.execute("SELECT COUNT(*) as total, MIN(date) as earliest, MAX(date) as latest FROM emails").fetchone()

    def nonempty_body_texts(self) -> tuple[list[str], list[str]]:
        """Return parallel UID and body-text lists for messages with non-blank body text."""
        rows = self.conn.execute(
            "SELECT uid, COALESCE(body_text, '') FROM emails WHERE TRIM(COALESCE(body_text, '')) != ''"
        ).fetchall()
        return [str(r[0]) for r in rows], [str(r[1]) for r in rows]

    def training_email_rows(self) -> list[dict]:
        """Return the chronological thread, sender, subject, and body fields used for training triplets."""
        rows = self.conn.execute(
            "SELECT uid, conversation_id, sender_email, subject, body_text FROM emails ORDER BY date"
        ).fetchall()
        return [dict(row) for row in rows]

    def all_uids(self) -> set[str]:
        """Return all UIDs in the database."""
        rows = self.conn.execute("SELECT uid FROM emails").fetchall()
        return {r["uid"] for r in rows}

    def uids_missing_body(self) -> set[str]:
        """Return UIDs of emails where body_text is NULL, empty, or whitespace-only."""
        rows = self.conn.execute("SELECT uid FROM emails WHERE body_text IS NULL OR TRIM(body_text) = ''").fetchall()
        return {r["uid"] for r in rows}
