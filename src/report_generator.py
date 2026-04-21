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

from .repo_paths import validate_new_output_path
from .sanitization import apply_privacy_guardrails

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class ReportGenerationError(RuntimeError):
    """Archive report rendering could not complete truthfully."""


class ReportGenerator:
    """Generate self-contained HTML reports from the email archive."""

    def __init__(self, email_db: EmailDatabase) -> None:
        self._db = email_db
        self.last_warnings: list[str] = []

    def _record_warning(self, message: str, *, exc: Exception | None = None) -> None:
        self.last_warnings.append(message)
        logger.warning(message, exc_info=exc)

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
        except Exception as exc:
            self._record_warning(f"monthly_volume unavailable: {type(exc).__name__}", exc=exc)
            return []

    def _gather_top_entities(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            return self._db.top_entities(limit=limit)
        except Exception as exc:
            self._record_warning(f"top_entities unavailable: {type(exc).__name__}", exc=exc)
            return []

    def _gather_response_times(self, limit: int = 15) -> list[dict[str, Any]]:
        try:
            from .temporal_analysis import TemporalAnalyzer

            analyzer = TemporalAnalyzer(self._db)
            return analyzer.response_times(limit=limit)
        except Exception as exc:
            self._record_warning(f"response_times unavailable: {type(exc).__name__}", exc=exc)
            return []

    def generate(
        self,
        title: str = "Email Archive Report",
        output_path: str | None = None,
        privacy_mode: str = "full_access",
    ) -> str:
        """Generate the HTML report.

        Args:
            title: Title for the report header.
            output_path: If provided, write the HTML to this file path.
            privacy_mode: Output privacy mode for archive rendering.

        Returns:
            The rendered HTML string.
        """
        self.last_warnings = []

        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError as exc:
            raise ReportGenerationError("Jinja2 is required for report generation. Run: pip install jinja2") from exc

        overview = self._gather_overview()
        top_senders = self._gather_top_senders()
        folders = self._gather_folders()
        monthly_volume = self._gather_monthly_volume()
        top_entities = self._gather_top_entities()
        response_times = self._gather_response_times()
        render_payload, privacy_guardrails = apply_privacy_guardrails(
            {
                "title": title,
                "overview": overview,
                "top_senders": top_senders,
                "folders": folders,
                "monthly_volume": monthly_volume,
                "top_entities": top_entities,
                "response_times": response_times,
            },
            privacy_mode=privacy_mode,
        )
        render_payload = render_payload if isinstance(render_payload, dict) else {}

        # Template uses these as denominators for CSS width percentages
        top_senders_render = [item for item in render_payload.get("top_senders", []) if isinstance(item, dict)]
        folders_render = [
            (str(item[0]), item[1])
            for item in render_payload.get("folders", [])
            if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[1], int)
        ]
        monthly_volume_render = [item for item in render_payload.get("monthly_volume", []) if isinstance(item, dict)]
        top_entities_render = render_payload.get("top_entities") if isinstance(render_payload.get("top_entities"), list) else []
        response_times_render = (
            render_payload.get("response_times") if isinstance(render_payload.get("response_times"), list) else []
        )
        top_senders_max = max((s["message_count"] for s in top_senders_render if isinstance(s, dict)), default=1)
        folders_max = max((c for _, c in folders_render if isinstance(c, int)), default=1)
        monthly_volume_max = max(
            (r["count"] for r in monthly_volume_render if isinstance(r, dict) and isinstance(r.get("count"), int)),
            default=1,
        )

        try:
            env = Environment(
                loader=FileSystemLoader(str(_TEMPLATE_DIR)),
                autoescape=True,
            )
            template = env.get_template("report.html")
            html = template.render(
                title=render_payload.get("title") or title,
                generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                overview=render_payload.get("overview") or overview,
                top_senders=top_senders_render,
                top_senders_max=top_senders_max,
                folders=folders_render,
                folders_max=folders_max,
                monthly_volume=monthly_volume_render,
                monthly_volume_max=monthly_volume_max,
                top_entities=top_entities_render,
                response_times=response_times_render,
                privacy_guardrails=privacy_guardrails,
            )
        except Exception as exc:
            raise ReportGenerationError(f"Archive report rendering failed: {type(exc).__name__}: {exc}") from exc

        if output_path:
            try:
                output = validate_new_output_path(output_path)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(html, encoding="utf-8")
                logger.info("Report written to %s", output)
            except (OSError, ValueError) as exc:
                raise ReportGenerationError(f"Could not write archive report to {output_path}: {exc}") from exc

        return html
