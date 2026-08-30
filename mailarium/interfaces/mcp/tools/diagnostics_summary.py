"""Database-derived readiness summaries for diagnostics tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def qa_readiness_summary_impl(
    db,
    *,
    table_columns: Callable[[Any, str], set[str]],
    scalar_count: Callable[[Any, str], int],
    count_rows: Callable[[Any, str], dict[str, int]],
    rate: Callable[[int, int], float],
) -> dict[str, Any]:
    """Return corpus-level Q&A readiness metrics from stored archive data."""
    columns = table_columns(db, "emails")
    if not columns:
        return {}

    total_emails = scalar_count(db, "SELECT COUNT(*) FROM emails")
    content_email_count = (
        scalar_count(db, "SELECT COUNT(*) FROM emails WHERE body_kind = 'content'") if "body_kind" in columns else 0
    )
    attachment_email_count = (
        scalar_count(db, "SELECT COUNT(*) FROM emails WHERE COALESCE(has_attachments, 0) != 0")
        if "has_attachments" in columns
        else 0
    )
    forensic_body_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE forensic_body_text IS NOT NULL AND forensic_body_text != ''""",
        )
        if "forensic_body_text" in columns
        else 0
    )
    raw_source_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE raw_source IS NOT NULL AND raw_source != ''""",
        )
        if "raw_source" in columns
        else 0
    )
    emails_with_segments_count = scalar_count(db, "SELECT COUNT(DISTINCT email_uid) FROM message_segments")
    reply_or_forward_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE email_type IN ('reply', 'forward')""",
        )
        if "email_type" in columns
        else 0
    )
    reply_context_recovered_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE reply_context_from IS NOT NULL AND reply_context_from != ''""",
        )
        if "reply_context_from" in columns
        else 0
    )
    canonical_thread_linked_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE
                   (in_reply_to IS NOT NULL AND in_reply_to != '')
                   OR (references_json IS NOT NULL AND references_json != '' AND references_json != '[]')""",
        )
        if {"in_reply_to", "references_json"}.issubset(columns)
        else 0
    )
    inferred_thread_linked_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE inferred_parent_uid IS NOT NULL AND inferred_parent_uid != ''""",
        )
        if "inferred_parent_uid" in columns
        else 0
    )

    return {
        "total_emails": total_emails,
        "content_email_count": content_email_count,
        "content_email_rate": rate(content_email_count, total_emails),
        "attachment_email_count": attachment_email_count,
        "attachment_email_rate": rate(attachment_email_count, total_emails),
        "forensic_body_count": forensic_body_count,
        "forensic_body_rate": rate(forensic_body_count, total_emails),
        "raw_source_count": raw_source_count,
        "raw_source_rate": rate(raw_source_count, total_emails),
        "emails_with_segments_count": emails_with_segments_count,
        "segment_provenance_rate": rate(emails_with_segments_count, total_emails),
        "reply_or_forward_count": reply_or_forward_count,
        "reply_context_recovered_count": reply_context_recovered_count,
        "reply_context_recovery_rate": rate(reply_context_recovered_count, reply_or_forward_count),
        "canonical_thread_linked_count": canonical_thread_linked_count,
        "canonical_thread_link_rate": rate(canonical_thread_linked_count, total_emails),
        "inferred_thread_linked_count": inferred_thread_linked_count,
        "inferred_thread_link_rate": rate(inferred_thread_linked_count, total_emails),
        "top_body_empty_reasons": _top_body_empty_reasons(db, count_rows),
    }


def _top_body_empty_reasons(db, count_rows) -> list[dict[str, Any]]:
    """Return the five most frequent non-empty body-loss reasons."""
    rows = count_rows(
        db,
        """SELECT body_empty_reason AS label, COUNT(*) AS count
           FROM emails WHERE body_empty_reason IS NOT NULL AND body_empty_reason != ''
           GROUP BY body_empty_reason ORDER BY count DESC, label ASC LIMIT 5""",
    )
    return [{"label": label, "count": count} for label, count in rows.items()]
