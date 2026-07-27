"""Export evidence collection as HTML report or CSV for legal review.

Renders the evidence table with verification status, category breakdown,
and an appendix containing the full source email text for each finding.
"""

from __future__ import annotations

# pylint: disable=too-many-locals
import csv
import io
import logging
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader

from .formatting import strip_html_tags, write_html_or_pdf
from .repo_paths import validate_new_output_path
from .sanitization import csv_safe_cell

if TYPE_CHECKING:
    from .email_db import EmailDatabase

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class EvidenceExporter:
    """Export evidence items as HTML reports or CSV files."""

    def __init__(self, email_db: EmailDatabase) -> None:
        """Bind the database supplying evidence records and source metadata."""
        self._db = email_db
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

        def _strip_html_safe(value: str | None) -> str:
            """Strip HTML tags; Jinja autoescape escapes the returned text."""
            return strip_html_tags(value)

        self._env.filters["strip_html"] = _strip_html_safe

    # ── Public API ────────────────────────────────────────────

    def export_html(
        self,
        min_relevance: int | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Export evidence as a styled HTML report.

        Returns:
            {"html": str, "item_count": int}
            or {"error": str} on failure.
        """
        items = self._get_filtered_items(min_relevance, category)
        if not items:
            return {"html": "<html><body><p>No evidence items match the specified filters.</p></body></html>", "item_count": 0}

        # Gather full email bodies for the appendix (batch)
        all_uids = list({item["email_uid"] for item in items if item.get("email_uid")})
        batch = self._db.get_emails_full_batch(all_uids)
        appendix_emails = []
        for item in items:
            full = batch.get(item.get("email_uid", ""))
            if full:
                appendix_emails.append(
                    {
                        "evidence_id": item["id"],
                        "email": full,
                        "key_quote": item.get("key_quote", ""),
                        "category": item.get("category", ""),
                    }
                )

        stats = self._db.evidence_stats(category=category, min_relevance=min_relevance)
        verified_count = sum(1 for i in items if i.get("verified"))
        total_count = len(items)

        # Date range from evidence items
        dates = [i["date"] for i in items if i.get("date")]
        date_range = {}
        if dates:
            date_range = {"earliest": min(dates)[:10], "latest": max(dates)[:10]}

        from datetime import datetime

        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        template = self._env.get_template("evidence_report.html")
        html = template.render(
            items=items,
            stats=stats,
            appendix_emails=appendix_emails,
            verified_count=verified_count,
            total_count=total_count,
            date_range=date_range,
            generated_at=generated_at,
        )
        return {"html": html, "item_count": total_count}

    def export_csv(
        self,
        min_relevance: int | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Export evidence as CSV text.

        Returns:
            {"csv": str, "item_count": int}
        """
        items = self._get_filtered_items(min_relevance, category)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "date",
                "sender_name",
                "sender_email",
                "recipients",
                "subject",
                "category",
                "key_quote",
                "summary",
                "relevance",
                "verified",
                "notes",
                "email_uid",
                "created_at",
                "updated_at",
            ]
        )
        for item in items:
            writer.writerow(
                [
                    csv_safe_cell(item.get("id", "")),
                    csv_safe_cell(item.get("date", "")),
                    csv_safe_cell(item.get("sender_name", "")),
                    csv_safe_cell(item.get("sender_email", "")),
                    csv_safe_cell(item.get("recipients", "")),
                    csv_safe_cell(item.get("subject", "")),
                    csv_safe_cell(item.get("category", "")),
                    csv_safe_cell(item.get("key_quote", "")),
                    csv_safe_cell(item.get("summary", "")),
                    csv_safe_cell(item.get("relevance", "")),
                    csv_safe_cell("yes" if item.get("verified") else "no"),
                    csv_safe_cell(item.get("notes", "")),
                    csv_safe_cell(item.get("email_uid", "")),
                    csv_safe_cell(item.get("created_at", "")),
                    csv_safe_cell(item.get("updated_at", "")),
                ]
            )

        return {"csv": output.getvalue(), "item_count": len(items)}

    def export_file(
        self,
        output_path: str,
        fmt: str = "html",
        min_relevance: int | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Write evidence report to a file.

        Args:
            output_path: Destination file path.
            fmt: 'html', 'csv', or 'pdf'.
            min_relevance: Optional minimum relevance filter.
            category: Optional category filter.

        Returns:
            {"output_path": str, "format": str, "item_count": int}
        """
        if fmt.lower() == "csv":
            result = self.export_csv(min_relevance=min_relevance, category=category)
            output = validate_new_output_path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result["csv"], encoding="utf-8")
            return {
                "output_path": output_path,
                "format": "csv",
                "item_count": result["item_count"],
            }

        # HTML or PDF
        result = self.export_html(min_relevance=min_relevance, category=category)
        result_meta = write_html_or_pdf(result["html"], output_path, fmt)
        result_meta["item_count"] = result["item_count"]
        return result_meta

    # ── Internal ──────────────────────────────────────────────

    def _get_filtered_items(
        self,
        min_relevance: int | None = None,
        category: str | None = None,
    ) -> list[dict]:
        """Fetch evidence items with optional filters."""
        result = self._db.list_evidence(
            min_relevance=min_relevance,
            category=category,
            limit=10000,
        )
        return result["items"]
