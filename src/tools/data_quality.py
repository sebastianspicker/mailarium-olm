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
                    rows = db.conn.execute(
                        """
                        SELECT detected_language, COUNT(*) as cnt
                        FROM emails
                        WHERE detected_language IS NOT NULL AND detected_language != ''
                        GROUP BY detected_language
                        ORDER BY cnt DESC
                        """
                    ).fetchall()
                except sqlite3.OperationalError:
                    return json_error("Language columns not found. Run email_admin(action='reingest_analytics').")
                if not rows:
                    return json_error("No language data available. Run email_admin(action='reingest_analytics').")
                stats = [{"language": row["detected_language"], "count": row["cnt"]} for row in rows]
                return json_response({"languages": stats})

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
