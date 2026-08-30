"""Data quality MCP tools."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..mcp_models import EmailQualityInput
from .utils import ToolDepsProto, json_error, json_response, run_with_db


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register data quality tools."""

    @mcp.tool(name="email_quality", annotations=deps.tool_annotations("Email Quality Checks"))
    async def email_quality(params: EmailQualityInput) -> str:
        """Data quality checks: duplicates, language distribution, or sentiment overview.

        check='duplicates': find near-duplicate emails by character n-gram similarity.
        check='languages': language distribution across all indexed emails.
        check='sentiment': sentiment distribution across indexed emails.
        """

        def _work(db: Any) -> str:
            return _email_quality_work(db, params)

        return await run_with_db(deps, _work)


def _email_quality_work(db: Any, params: EmailQualityInput) -> str:
    """Dispatch the requested quality check and reject unsupported check names explicitly."""
    handlers = {"duplicates": _duplicates_quality, "languages": _languages_quality, "sentiment": _sentiment_quality}
    handler = handlers.get(params.check)
    if handler is None:
        return json_error(f"Invalid check: {params.check}. Use 'duplicates', 'languages', or 'sentiment'.")
    return handler(db, params)


def _duplicates_quality(db: Any, params: EmailQualityInput) -> str:
    """Run thresholded duplicate detection and serialize the bounded match set."""
    from mailarium.investigation.dedup_detector import DuplicateDetector

    duplicates = DuplicateDetector(db, threshold=params.threshold).find_duplicates(limit=params.limit)
    return json_response({"count": len(duplicates), "duplicates": duplicates})


def _languages_quality(db: Any, _params: EmailQualityInput) -> str:
    """Summarize language labels, confidence coverage, metadata completeness, and caveats from SQLite."""
    try:
        total_row, rows, confidence_rows, reason_rows, source_rows, metadata_row = _load_language_rows(db)
    except sqlite3.OperationalError:
        return json_error("Language columns not found. Run email_admin(action='reingest_analytics').")
    total_count = int(total_row["cnt"] or 0)
    labeled_count = sum(int(row["cnt"] or 0) for row in rows)
    unlabeled_count = max(0, total_count - labeled_count)
    if not rows and unlabeled_count <= 0:
        return json_error("No language data available. Run email_admin(action='reingest_analytics').")
    stats = [{"language": row["detected_language"], "count": row["cnt"]} for row in rows]
    metadata = _language_metadata(metadata_row)
    return json_response(
        {
            "languages": stats,
            "confidence_breakdown": [{"confidence": row["confidence"], "count": row["cnt"]} for row in confidence_rows],
            "reason_breakdown": [{"reason": row["reason"], "count": row["cnt"]} for row in reason_rows],
            "source_breakdown": [{"source": row["source"], "count": row["cnt"]} for row in source_rows],
            "coverage": _language_coverage(stats, total_count, labeled_count, unlabeled_count, metadata),
            "caveats": _language_caveats(total_count, unlabeled_count, metadata),
        }
    )


_LANGUAGE_GROUP_QUERIES = (
    """SELECT detected_language, COUNT(*) as cnt FROM emails
       WHERE detected_language IS NOT NULL AND detected_language != ''
       GROUP BY detected_language ORDER BY cnt DESC""",
    """SELECT detected_language_confidence AS confidence, COUNT(*) AS cnt FROM emails
       WHERE detected_language_confidence IS NOT NULL AND detected_language_confidence != ''
       GROUP BY detected_language_confidence ORDER BY cnt DESC""",
    """SELECT detected_language_reason AS reason, COUNT(*) AS cnt FROM emails
       WHERE detected_language_reason IS NOT NULL AND detected_language_reason != ''
       GROUP BY detected_language_reason ORDER BY cnt DESC""",
    """SELECT detected_language_source AS source, COUNT(*) AS cnt FROM emails
       WHERE detected_language_source IS NOT NULL AND detected_language_source != ''
       GROUP BY detected_language_source ORDER BY cnt DESC""",
)
_LANGUAGE_METADATA_QUERY = """SELECT
    SUM(CASE WHEN COALESCE(detected_language_confidence, '') != ''
        OR COALESCE(detected_language_reason, '') != ''
        OR COALESCE(detected_language_source, '') != '' THEN 1 ELSE 0 END) AS metadata_rows,
    SUM(CASE WHEN detected_language IS NOT NULL AND detected_language != ''
        AND detected_language_confidence = 'low' THEN 1 ELSE 0 END) AS low_confidence_labeled_rows,
    SUM(CASE WHEN COALESCE(detected_language_reason, '') LIKE 'short_text_%' THEN 1 ELSE 0 END) AS short_text_rows
    FROM emails"""


def _load_language_rows(db: Any) -> tuple[Any, ...]:
    """Load language rows while preserving the caller's fallback behavior."""
    total = db.conn.execute("SELECT COUNT(*) AS cnt FROM emails").fetchone()
    grouped = [db.conn.execute(query).fetchall() for query in _LANGUAGE_GROUP_QUERIES]
    metadata = db.conn.execute(_LANGUAGE_METADATA_QUERY).fetchone()
    return total, *grouped, metadata


def _language_coverage(stats, total: int, labeled: int, unlabeled: int, metadata: dict[str, int]) -> dict[str, Any]:
    """Calculate labeled, dominant-language, confidence, and short-text coverage shares."""
    dominant_count = int(stats[0]["count"]) if stats else 0
    return {
        "total_emails": total,
        "labeled_emails": labeled,
        "unlabeled_emails": unlabeled,
        "language_metadata_emails": metadata["rows"],
        "language_metadata_share": round(metadata["rows"] / total, 4) if total else 0.0,
        "labeled_share": round(labeled / total, 4) if total else 0.0,
        "dominant_language": str(stats[0]["language"] or "") if stats else "",
        "dominant_language_total_share": round(dominant_count / total, 4) if total else 0.0,
        "dominant_language_labeled_share": round(dominant_count / labeled, 4) if labeled else 0.0,
        "low_confidence_labeled_emails": metadata["low_confidence"],
        "short_text_signal_limited_emails": metadata["short_text"],
    }


def _language_metadata(row: Any) -> dict[str, int]:
    """Convert the aggregate language-metadata row into stable integer counters."""
    return {
        "rows": int(row["metadata_rows"] or 0) if row else 0,
        "low_confidence": int(row["low_confidence_labeled_rows"] or 0) if row else 0,
        "short_text": int(row["short_text_rows"] or 0) if row else 0,
    }


def _language_caveats(total: int, unlabeled: int, metadata: dict[str, int]) -> list[str]:
    """Report only the language-quality limitations present in the measured archive."""
    candidates = (
        (unlabeled, "Some emails remain unlabeled for language."),
        (metadata["low_confidence"], "Some language labels are low-confidence, often due to short texts."),
        (metadata["short_text"], "Short-message analytics include signal-limited rows."),
        (metadata["rows"] < total, "Language-confidence metadata is incomplete for part of the archive."),
    )
    return [message for condition, message in candidates if condition]


def _sentiment_quality(db: Any, _params: EmailQualityInput) -> str:
    """Aggregate sentiment counts and mean scores, failing clearly when analytics data is absent."""
    try:
        rows = db.conn.execute(
            """
                        SELECT sentiment_label, COUNT(*) as cnt,
                               ROUND(AVG(sentiment_score), 4) as avg_score
                        FROM emails
                        WHERE sentiment_label IS NOT NULL AND sentiment_label != ''
                        GROUP BY sentiment_label
                        ORDER BY cnt DESC
                        """
        ).fetchall()
    except sqlite3.OperationalError:
        return json_error("Sentiment columns not found. Run email_admin(action='reingest_analytics').")
    if not rows:
        return json_error("No sentiment data available. Run email_admin(action='reingest_analytics').")
    stats = [{"sentiment": row["sentiment_label"], "count": row["cnt"], "avg_score": row["avg_score"]} for row in rows]
    return json_response({"sentiments": stats})
