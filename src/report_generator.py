"""HTML report generation for the email archive.

Renders a self-contained HTML report with archive overview, top senders,
folder distribution, monthly volume, top entities, and response times.
Uses Jinja2 for template rendering.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_db import EmailDatabase

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class ReportGenerator:
    """Generate self-contained HTML reports from the email archive."""

    def __init__(self, email_db: EmailDatabase) -> None:
        self._db = email_db

    def _gather_overview(self) -> dict[str, Any]:
        """Collect high-level archive statistics."""
        total = self._db.email_count()
        senders = self._db.unique_sender_count()
        folders = self._db.folder_counts()
        date_start, date_end = self._db.date_range()
        return {
            "total_emails": total,
            "unique_senders": senders,
            "unique_folders": len(folders),
            "date_range_start": date_start[:10] if date_start else "—",
            "date_range_end": date_end[:10] if date_end else "—",
        }

    def _gather_top_senders(self, limit: int = 15) -> list[dict[str, Any]]:
        return self._db.top_senders(limit=limit)

    def _gather_folders(self) -> list[tuple[str, int]]:
        folder_counts = self._db.folder_counts()
        return sorted(folder_counts.items(), key=lambda x: x[1], reverse=True)

    def _gather_monthly_volume(self) -> list[dict[str, Any]]:
        try:
            from .temporal_analysis import TemporalAnalyzer

            analyzer = TemporalAnalyzer(self._db)
            return analyzer.volume_over_time(period="month")
        except Exception:
            logger.debug("Monthly volume unavailable", exc_info=True)
            return []

    def _gather_top_entities(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return self._db.top_entities(limit=limit)
        except Exception:
            logger.debug("Entities unavailable", exc_info=True)
            return []

    def _gather_response_times(self, limit: int = 15) -> list[dict[str, Any]]:
        try:
            from .temporal_analysis import TemporalAnalyzer

            analyzer = TemporalAnalyzer(self._db)
            return analyzer.response_times(limit=limit)
        except Exception:
            logger.debug("Response times unavailable", exc_info=True)
            return []

    def generate(
        self,
        title: str = "Email Archive Report",
        output_path: str | None = None,
    ) -> str:
        """Generate the HTML report.

        Args:
            title: Title for the report header.
            output_path: If provided, write the HTML to this file path.

        Returns:
            The rendered HTML string.
        """
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            return (
                "<html><body><h1>Error</h1><p>Jinja2 is required for report generation. Run: pip install jinja2</p></body></html>"
            )

        overview = self._gather_overview()
        top_senders = self._gather_top_senders()
        folders = self._gather_folders()
        monthly_volume = self._gather_monthly_volume()
        top_entities = self._gather_top_entities()
        response_times = self._gather_response_times()

        # Template uses these as denominators for CSS width percentages
        top_senders_max = max((s["message_count"] for s in top_senders), default=1)
        folders_max = max((c for _, c in folders), default=1)
        monthly_volume_max = max((r["count"] for r in monthly_volume), default=1)

        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )
        template = env.get_template("report.html")
        html = template.render(
            title=title,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            overview=overview,
            top_senders=top_senders,
            top_senders_max=top_senders_max,
            folders=folders,
            folders_max=folders_max,
            monthly_volume=monthly_volume,
            monthly_volume_max=monthly_volume_max,
            top_entities=top_entities,
            response_times=response_times,
        )

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(html, encoding="utf-8")
            logger.info("Report written to %s", output_path)

        return html
