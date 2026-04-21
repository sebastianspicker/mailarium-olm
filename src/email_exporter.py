"""Export email conversations as styled HTML or PDF.

Renders threads and single emails using a Jinja2 template that mimics
a mail client's print view — with headers, body, and attachment listings.
PDF output requires the optional ``weasyprint`` package.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader

from .formatting import resolve_body_for_render, write_html_or_pdf

if TYPE_CHECKING:
    from .email_db import EmailDatabase

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class EmailExporter:
    """Export email threads and single emails as HTML/PDF."""

    def __init__(self, email_db: EmailDatabase) -> None:
        self._db = email_db
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    # ── Public API ────────────────────────────────────────────

    def export_thread_html(self, conversation_id: str, *, render_mode: str = "retrieval") -> dict[str, Any]:
        """Export a full conversation thread as styled HTML.

        Returns:
            {"html": str, "email_count": int, "subject": str}
            or {"error": str} on failure.
        """
        emails = self._db.get_thread_emails(conversation_id)
        if not emails:
            return {"error": f"No emails found for conversation: {conversation_id}"}
        html = self._render_thread(emails, render_mode=render_mode)
        return {
            "html": html,
            "email_count": len(emails),
            "subject": emails[0].get("subject", "(no subject)"),
            "render_mode": render_mode,
        }

    def export_thread_file(
        self, conversation_id: str, output_path: str, fmt: str = "html", *, render_mode: str = "retrieval"
    ) -> dict[str, Any]:
        """Export a conversation thread to a file.

        Args:
            conversation_id: Thread identifier.
            output_path: Destination file path.
            fmt: 'html' or 'pdf'.

        Returns:
            {"output_path": str, "format": str, "email_count": int, "subject": str}
        """
        result = self.export_thread_html(conversation_id, render_mode=render_mode)
        if "error" in result:
            return result
        return self._write_output(result["html"], output_path, fmt, result)

    def export_single_html(self, uid: str, *, render_mode: str = "retrieval") -> dict[str, Any]:
        """Export a single email as styled HTML."""
        email = self._db.get_email_full(uid)
        if not email:
            return {"error": f"Email not found: {uid}"}
        html = self._render_thread([email], render_mode=render_mode)
        return {
            "html": html,
            "email_count": 1,
            "subject": email.get("subject", "(no subject)"),
            "render_mode": render_mode,
        }

    def export_single_file(
        self, uid: str, output_path: str, fmt: str = "html", *, render_mode: str = "retrieval"
    ) -> dict[str, Any]:
        """Export a single email to a file."""
        result = self.export_single_html(uid, render_mode=render_mode)
        if "error" in result:
            return result
        return self._write_output(result["html"], output_path, fmt, result)

    # ── Internal ──────────────────────────────────────────────

    def _render_thread(self, emails: list[dict], *, render_mode: str = "retrieval") -> str:
        """Render a list of emails using the Jinja2 template."""
        thread_subject = emails[0].get("subject", "(no subject)") if emails else ""
        # Build date range
        dates = [e.get("date", "") for e in emails if e.get("date")]
        date_range = ""
        if dates:
            first = min(dates)[:10]
            last = max(dates)[:10]
            date_range = f"{first} — {last}" if first != last else first

        rendered_emails = []
        for email in emails:
            body_text, _ = resolve_body_for_render(email, render_mode)
            rendered_email = dict(email)
            rendered_email["body_text"] = body_text
            rendered_emails.append(rendered_email)

        template = self._env.get_template("thread_export.html")
        return template.render(
            thread_subject=thread_subject,
            date_range=date_range,
            emails=rendered_emails,
            email_count=len(emails),
        )

    @staticmethod
    def _write_output(html: str, output_path: str, fmt: str, extra: dict[str, Any]) -> dict[str, Any]:
        """Write HTML or PDF to disk."""
        result = write_html_or_pdf(html, output_path, fmt)
        result["email_count"] = extra.get("email_count", 0)
        result["subject"] = extra.get("subject", "")
        return result
