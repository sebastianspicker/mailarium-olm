"""Query mixin for EmailDatabase: read operations, full-body retrieval, browsing."""

from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING

from .db_queries_browse import (
    get_email_for_reembed_impl,
    get_email_full_impl,
    get_emails_full_batch_impl,
    get_inferred_thread_emails_impl,
    get_thread_emails_impl,
    list_emails_paginated_impl,
    recipients_for_uid_impl,
    recipients_for_uids_impl,
)
from .db_schema import _escape_like

if TYPE_CHECKING:
    pass  # conn declared below for mypy


class QueryMixin:
    """Read queries, full-body retrieval, browsing, and consistency checks."""

    if TYPE_CHECKING:
        conn: sqlite3.Connection

        def attachments_for_email(self, uid: str) -> list[dict]: ...
        def all_uids(self) -> set[str]: ...

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
        """Return {folder_name: email_count} for all folders."""
        rows = self.conn.execute("SELECT folder, COUNT(*) AS c FROM emails GROUP BY folder ORDER BY c DESC").fetchall()
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

    def email_exists(self, uid: str) -> bool:
        """Check whether an email with the given UID exists."""
        row = self.conn.execute("SELECT 1 FROM emails WHERE uid = ?", (uid,)).fetchone()
        return row is not None

    def completed_ingest_uids(
        self,
        *,
        attachment_required: bool = False,
    ) -> set[str]:
        """Return UIDs whose relational and vector ingest state is complete enough to skip."""
        manageres = ["state.vector_status = 'completed'"]
        if attachment_required:
            manageres.append("(state.attachment_status = 'completed' OR emails.has_attachments = 0)")
        rows = self.conn.execute(
            "SELECT state.email_uid "
            "FROM email_ingest_state AS state "
            "JOIN emails ON emails.uid = state.email_uid "
            f"WHERE {' AND '.join(manageres)}",  # nosec
        ).fetchall()
        return {str(row["email_uid"]) for row in rows if str(row["email_uid"] or "")}

    def emails_by_sender(self, sender_email: str, limit: int = 100) -> list[dict]:
        """Get emails from a specific sender.

        Args:
            sender_email: Sender's email address (partial match).
            limit: Maximum emails to return.

        Returns:
            List of email dicts with uid, subject, body_text, date.
        """
        rows = self.conn.execute(
            """SELECT uid, subject, body_text, date, sender_name, sender_email
               FROM emails
               WHERE sender_email LIKE ? ESCAPE '\\'
               ORDER BY date DESC LIMIT ?""",
            (f"%{_escape_like(sender_email)}%", limit),
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

        segment_placeholders = ",".join("?" for _ in segment_types)
        conditions = ["LOWER(ms.text) LIKE ? ESCAPE '\\'" for _ in like_patterns]
        params: list[object] = [*segment_types, *[f"%{_escape_like(pattern)}%" for pattern in like_patterns], limit * 8]
        rows = self.conn.execute(
            "SELECT ms.email_uid AS uid, "
            "ms.ordinal, ms.segment_type, ms.depth, ms.text AS segment_text, "
            "ms.source_surface, e.subject, e.sender_email, e.sender_name, "
            "e.date, e.conversation_id, e.folder, e.has_attachments, "
            "e.attachment_count, e.detected_language, e.detected_language_confidence "
            "FROM message_segments ms "
            "JOIN emails e ON e.uid = ms.email_uid "
            f"WHERE ms.segment_type IN ({segment_placeholders}) "  # nosec
            f"AND ({' OR '.join(conditions)}) "
            "ORDER BY e.date DESC, ms.ordinal ASC "
            "LIMIT ?",
            params,
        ).fetchall()

        ranked: list[dict] = []
        normalized_phrase = compact_query.casefold()
        for row in rows:
            item = dict(row)
            haystack = " ".join(str(item.get("segment_text") or "").split()).casefold()
            if not haystack:
                continue
            matched_tokens = [token for token in tokens if token in haystack]
            phrase_match = normalized_phrase in haystack
            if not phrase_match and not matched_tokens:
                continue
            score = 0.35 + (0.4 if phrase_match else 0.0)
            if tokens:
                score += min(0.2, (len(matched_tokens) / len(tokens)) * 0.2)
            if str(item.get("segment_type") or "") == "quoted_reply":
                score += 0.05
            item["score"] = round(min(score, 0.99), 4)
            item["matched_tokens"] = matched_tokens
            ranked.append(item)

        ranked.sort(
            key=lambda item: (
                -float(item.get("score") or 0.0),
                str(item.get("date") or ""),
                int(item.get("ordinal") or 0),
            )
        )
        return ranked[:limit]

    # ------------------------------------------------------------------
    # Category / Calendar / Attachment queries (schema v7)
    # ------------------------------------------------------------------

    def emails_by_category(self, category: str, limit: int = 50) -> list[dict]:
        """Get emails with a specific category."""
        rows = self.conn.execute(
            """SELECT e.uid, e.subject, e.sender_email, e.date, e.folder
               FROM email_categories ec
               JOIN emails e ON ec.email_uid = e.uid
               WHERE ec.category = ?
               ORDER BY e.date DESC LIMIT ?""",
            (category, limit),
        ).fetchall()
        return [dict(r) for r in rows]

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

    def thread_by_references(self, message_id: str, limit: int = 50) -> list[dict]:
        """Find emails whose references_json contains a given message-id."""
        rows = self.conn.execute(
            """SELECT uid, subject, sender_email, date, folder
               FROM emails
               WHERE references_json LIKE ? ESCAPE '\\'
               ORDER BY date ASC LIMIT ?""",
            (f"%{_escape_like(message_id)}%", limit),
        ).fetchall()
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

    def _recipients_for_uid(self, uid: str) -> dict[str, list[str]]:
        return recipients_for_uid_impl(self, uid)

    def _recipients_for_uids(self, uids: list[str]) -> dict[str, dict[str, list[str]]]:
        return recipients_for_uids_impl(self, uids)

    def get_email_full(self, uid: str) -> dict | None:
        return get_email_full_impl(self, uid)

    def get_emails_full_batch(self, uids: list[str]) -> dict[str, dict]:
        return get_emails_full_batch_impl(self, uids)

    def get_thread_emails(self, conversation_id: str) -> list[dict]:
        return get_thread_emails_impl(self, conversation_id)

    def get_inferred_thread_emails(self, inferred_thread_id: str) -> list[dict]:
        return get_inferred_thread_emails_impl(self, inferred_thread_id)

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
        return list_emails_paginated_impl(
            self,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            folder=folder,
            sender=sender,
            category=category,
            date_from=date_from,
            date_to=date_to,
        )

    # ------------------------------------------------------------------
    # Re-embed helper
    # ------------------------------------------------------------------

    def get_email_for_reembed(self, uid: str) -> dict | None:
        return get_email_for_reembed_impl(self, uid)

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
    # Consistency checks
    # ------------------------------------------------------------------

    def consistency_check(self, chromadb_uids: set[str]) -> dict:
        """Compare SQLite email UIDs against ChromaDB chunk UIDs.

        ChromaDB chunk IDs follow the pattern ``{uid}__{chunk_index}``, so
        the email UID is the prefix before ``__``.

        Args:
            chromadb_uids: Set of chunk IDs from ChromaDB (e.g. via
                ``iter_collection_ids()``).

        Returns:
            Dict with ``sqlite_only`` (UIDs in SQLite but no chunks in
            ChromaDB), ``chromadb_only`` (UIDs with chunks in ChromaDB but
            missing from SQLite), and counts.
        """
        sqlite_uids = self.all_uids()

        # Extract email UIDs from chunk IDs: "uid__0" -> "uid"
        chromadb_email_uids: set[str] = set()
        for chunk_id in chromadb_uids:
            parts = chunk_id.split("__", 1)
            if parts:
                chromadb_email_uids.add(parts[0])

        sqlite_only = sqlite_uids - chromadb_email_uids
        chromadb_only = chromadb_email_uids - sqlite_uids

        return {
            "sqlite_count": len(sqlite_uids),
            "chromadb_uid_count": len(chromadb_email_uids),
            "sqlite_only": sorted(sqlite_only),
            "chromadb_only": sorted(chromadb_only),
            "sqlite_only_count": len(sqlite_only),
            "chromadb_only_count": len(chromadb_only),
            "is_consistent": len(sqlite_only) == 0 and len(chromadb_only) == 0,
        }
