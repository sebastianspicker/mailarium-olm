"""Read-only archive diagnostics and question-answering readiness counters."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from ..locking import ArchiveRepository, archive_repository
from ..sql import validate_sql_identifier as _validate_sql_identifier

logger = logging.getLogger(__name__)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return known column names for *table*, or an empty set on failure."""
    try:
        safe_table = _validate_sql_identifier(table)
        rows = conn.execute("SELECT * FROM pragma_table_info(?)", (safe_table,)).fetchall()
    except sqlite3.Error:
        logger.debug("Diagnostics PRAGMA failed for table %s", table, exc_info=True)
        return set()
    return {str(row["name"] if not isinstance(row, tuple) else row[1]) for row in rows}


def _count_rows(conn: sqlite3.Connection, query: str) -> dict[str, int]:
    """Return label counters, degrading database errors to an empty mapping."""
    try:
        rows = conn.execute(query).fetchall()
    except sqlite3.Error:
        logger.debug("Diagnostics counter query failed: %s", query, exc_info=True)
        return {}
    return {str(row["label"]): int(row["count"]) for row in rows if row["label"]}


def _scalar_count(conn: sqlite3.Connection, query: str) -> int:
    """Execute a scalar diagnostics query and degrade database errors or empty rows to zero."""
    try:
        row = conn.execute(query).fetchone()
    except sqlite3.Error:
        logger.debug("Diagnostics scalar query failed: %s", query, exc_info=True)
        return 0
    if not row:
        return 0
    return int(row[0] or 0)


def _rate(count: int, total: int) -> float:
    """Return a stable float rate, guarding zero denominators."""
    if total <= 0:
        return 0.0
    return count / total


def _content_diagnostics(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return body, recipient, reply-context, segment, and inferred-thread counters."""
    return {
        "body_kind_counts": _count_rows(
            conn,
            """SELECT body_kind AS label, COUNT(*) AS count
                       FROM emails
                       WHERE body_kind IS NOT NULL AND body_kind != ''
                       GROUP BY body_kind
                       ORDER BY count DESC""",
        ),
        "body_empty_reason_counts": _count_rows(
            conn,
            """SELECT body_empty_reason AS label, COUNT(*) AS count
                       FROM emails
                       WHERE body_empty_reason IS NOT NULL AND body_empty_reason != ''
                       GROUP BY body_empty_reason
                       ORDER BY count DESC""",
        ),
        "recipient_identity_source_counts": _count_rows(
            conn,
            """SELECT recipient_identity_source AS label, COUNT(*) AS count
                       FROM emails
                       WHERE recipient_identity_source IS NOT NULL AND recipient_identity_source != ''
                       GROUP BY recipient_identity_source
                       ORDER BY count DESC""",
        ),
        "reply_context_recovered_count": _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
                       WHERE reply_context_from IS NOT NULL AND reply_context_from != ''""",
        ),
        "message_segment_count": _scalar_count(conn, "SELECT COUNT(*) FROM message_segments"),
        "emails_with_segments_count": _scalar_count(
            conn,
            "SELECT COUNT(DISTINCT email_uid) FROM message_segments",
        ),
        "emails_with_inferred_thread_count": _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
                       WHERE inferred_parent_uid IS NOT NULL AND inferred_parent_uid != ''""",
        ),
    }


def _qa_readiness_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return corpus-level Q&A readiness metrics from stored archive data."""
    columns = _table_columns(conn, "emails")
    if not columns:
        return {}

    total_emails = _scalar_count(conn, "SELECT COUNT(*) FROM emails")
    content_email_count = (
        _scalar_count(conn, "SELECT COUNT(*) FROM emails WHERE body_kind = 'content'") if "body_kind" in columns else 0
    )
    attachment_email_count = (
        _scalar_count(conn, "SELECT COUNT(*) FROM emails WHERE COALESCE(has_attachments, 0) != 0")
        if "has_attachments" in columns
        else 0
    )
    forensic_body_count = (
        _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
               WHERE forensic_body_text IS NOT NULL AND forensic_body_text != ''""",
        )
        if "forensic_body_text" in columns
        else 0
    )
    raw_source_count = (
        _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
               WHERE raw_source IS NOT NULL AND raw_source != ''""",
        )
        if "raw_source" in columns
        else 0
    )
    emails_with_segments_count = _scalar_count(conn, "SELECT COUNT(DISTINCT email_uid) FROM message_segments")
    reply_or_forward_count = (
        _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
               WHERE email_type IN ('reply', 'forward')""",
        )
        if "email_type" in columns
        else 0
    )
    reply_context_recovered_count = (
        _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
               WHERE reply_context_from IS NOT NULL AND reply_context_from != ''""",
        )
        if "reply_context_from" in columns
        else 0
    )
    canonical_thread_linked_count = (
        _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
               WHERE
                   (in_reply_to IS NOT NULL AND in_reply_to != '')
                   OR (references_json IS NOT NULL AND references_json != '' AND references_json != '[]')""",
        )
        if {"in_reply_to", "references_json"}.issubset(columns)
        else 0
    )
    inferred_thread_linked_count = (
        _scalar_count(
            conn,
            """SELECT COUNT(*) FROM emails
               WHERE inferred_parent_uid IS NOT NULL AND inferred_parent_uid != ''""",
        )
        if "inferred_parent_uid" in columns
        else 0
    )

    return {
        "total_emails": total_emails,
        "content_email_count": content_email_count,
        "content_email_rate": _rate(content_email_count, total_emails),
        "attachment_email_count": attachment_email_count,
        "attachment_email_rate": _rate(attachment_email_count, total_emails),
        "forensic_body_count": forensic_body_count,
        "forensic_body_rate": _rate(forensic_body_count, total_emails),
        "raw_source_count": raw_source_count,
        "raw_source_rate": _rate(raw_source_count, total_emails),
        "emails_with_segments_count": emails_with_segments_count,
        "segment_provenance_rate": _rate(emails_with_segments_count, total_emails),
        "reply_or_forward_count": reply_or_forward_count,
        "reply_context_recovered_count": reply_context_recovered_count,
        "reply_context_recovery_rate": _rate(reply_context_recovered_count, reply_or_forward_count),
        "canonical_thread_linked_count": canonical_thread_linked_count,
        "canonical_thread_link_rate": _rate(canonical_thread_linked_count, total_emails),
        "inferred_thread_linked_count": inferred_thread_linked_count,
        "inferred_thread_link_rate": _rate(inferred_thread_linked_count, total_emails),
        "top_body_empty_reasons": _top_body_empty_reasons(conn),
    }


def _top_body_empty_reasons(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return the five most frequent non-empty body-loss reasons."""
    rows = _count_rows(
        conn,
        """SELECT body_empty_reason AS label, COUNT(*) AS count
           FROM emails WHERE body_empty_reason IS NOT NULL AND body_empty_reason != ''
           GROUP BY body_empty_reason ORDER BY count DESC, label ASC LIMIT 5""",
    )
    return [{"label": label, "count": count} for label, count in rows.items()]


@archive_repository
class DiagnosticsRepository(ArchiveRepository):
    """Read-only corpus diagnostics that degrade database errors to empty counters."""

    def content_diagnostics(self) -> dict[str, Any]:
        """Return body-kind, recipient, reply-context, segment, and inferred-thread counters."""
        return _content_diagnostics(self.conn)

    def qa_readiness_summary(self) -> dict[str, Any]:
        """Return corpus-level question-answering readiness metrics from stored archive data."""
        return _qa_readiness_summary(self.conn)
