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
            if params.check == "duplicates":
                from ..dedup_detector import DuplicateDetector

                duplicates = DuplicateDetector(db, threshold=params.threshold).find_duplicates(
                    limit=params.limit,
                )
                return json_response({"count": len(duplicates), "duplicates": duplicates})

            if params.check == "languages":
                try:
                    total_row = db.conn.execute("SELECT COUNT(*) AS cnt FROM emails").fetchone()
                    rows = db.conn.execute(
                        """
                        SELECT detected_language, COUNT(*) as cnt
                        FROM emails
                        WHERE detected_language IS NOT NULL AND detected_language != ''
                        GROUP BY detected_language
                        ORDER BY cnt DESC
                        """
                    ).fetchall()
                    confidence_rows = db.conn.execute(
                        """
                        SELECT detected_language_confidence AS confidence, COUNT(*) AS cnt
                        FROM emails
                        WHERE detected_language_confidence IS NOT NULL AND detected_language_confidence != ''
                        GROUP BY detected_language_confidence
                        ORDER BY cnt DESC
                        """
                    ).fetchall()
                    reason_rows = db.conn.execute(
                        """
                        SELECT detected_language_reason AS reason, COUNT(*) AS cnt
                        FROM emails
                        WHERE detected_language_reason IS NOT NULL AND detected_language_reason != ''
                        GROUP BY detected_language_reason
                        ORDER BY cnt DESC
                        """
                    ).fetchall()
                    source_rows = db.conn.execute(
                        """
                        SELECT detected_language_source AS source, COUNT(*) AS cnt
                        FROM emails
                        WHERE detected_language_source IS NOT NULL AND detected_language_source != ''
                        GROUP BY detected_language_source
                        ORDER BY cnt DESC
                        """
                    ).fetchall()
                    metadata_row = db.conn.execute(
                        """
                        SELECT
                            SUM(
                                CASE
                                    WHEN COALESCE(detected_language_confidence, '') != ''
                                      OR COALESCE(detected_language_reason, '') != ''
                                      OR COALESCE(detected_language_source, '') != ''
                                    THEN 1 ELSE 0
                                END
                            ) AS metadata_rows,
                            SUM(
                                CASE
                                    WHEN detected_language IS NOT NULL AND detected_language != ''
                                     AND detected_language_confidence = 'low'
                                    THEN 1 ELSE 0
                                END
                            ) AS low_confidence_labeled_rows,
                            SUM(
                                CASE
                                    WHEN COALESCE(detected_language_reason, '') LIKE 'short_text_%'
                                    THEN 1 ELSE 0
                                END
                            ) AS short_text_rows
                        FROM emails
                        """
                    ).fetchone()
                except sqlite3.OperationalError:
                    return json_error("Language columns not found. Run email_admin(action='reingest_analytics').")
                total_count = int(total_row["cnt"] or 0)
                labeled_count = sum(int(row["cnt"] or 0) for row in rows)
                unlabeled_count = max(0, total_count - labeled_count)
                if not rows and unlabeled_count <= 0:
                    return json_error("No language data available. Run email_admin(action='reingest_analytics').")
                stats = [{"language": row["detected_language"], "count": row["cnt"]} for row in rows]
                confidence_breakdown = [{"confidence": row["confidence"], "count": row["cnt"]} for row in confidence_rows]
                reason_breakdown = [{"reason": row["reason"], "count": row["cnt"]} for row in reason_rows]
                source_breakdown = [{"source": row["source"], "count": row["cnt"]} for row in source_rows]
                dominant_language = str(stats[0]["language"] or "") if stats else ""
                metadata_rows = int(metadata_row["metadata_rows"] or 0) if metadata_row else 0
                low_confidence_labeled_rows = int(metadata_row["low_confidence_labeled_rows"] or 0) if metadata_row else 0
                short_text_rows = int(metadata_row["short_text_rows"] or 0) if metadata_row else 0
                caveats: list[str] = []
                if unlabeled_count:
                    caveats.append("Some emails remain unlabeled for language.")
                if low_confidence_labeled_rows:
                    caveats.append("Some language labels are low-confidence, often due to short texts.")
                if short_text_rows:
                    caveats.append("Short-message analytics include signal-limited rows.")
                if metadata_rows < total_count:
                    caveats.append("Language-confidence metadata is incomplete for part of the archive.")
                return json_response(
                    {
                        "languages": stats,
                        "confidence_breakdown": confidence_breakdown,
                        "reason_breakdown": reason_breakdown,
                        "source_breakdown": source_breakdown,
                        "coverage": {
                            "total_emails": total_count,
                            "labeled_emails": labeled_count,
                            "unlabeled_emails": unlabeled_count,
                            "language_metadata_emails": metadata_rows,
                            "language_metadata_share": round((metadata_rows / total_count), 4) if total_count else 0.0,
                            "labeled_share": round((labeled_count / total_count), 4) if total_count else 0.0,
                            "dominant_language": dominant_language,
                            "dominant_language_total_share": (
                                round((int(stats[0]["count"]) / total_count), 4) if stats and total_count else 0.0
                            ),
                            "dominant_language_labeled_share": (
                                round((int(stats[0]["count"]) / labeled_count), 4) if stats and labeled_count else 0.0
                            ),
                            "low_confidence_labeled_emails": low_confidence_labeled_rows,
                            "short_text_signal_limited_emails": short_text_rows,
                        },
                        "caveats": caveats,
                    }
                )

            if params.check == "sentiment":
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
                stats = [
                    {"sentiment": row["sentiment_label"], "count": row["cnt"], "avg_score": row["avg_score"]} for row in rows
                ]
                return json_response({"sentiments": stats})

            return json_error(f"Invalid check: {params.check}. Use 'duplicates', 'languages', or 'sentiment'.")

        return await run_with_db(deps, _work)
