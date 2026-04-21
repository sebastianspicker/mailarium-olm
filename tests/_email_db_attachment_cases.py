# ruff: noqa: F401
"""Tests for the SQLite EmailDatabase."""

from src.email_db import EmailDatabase, _parse_address
from src.parse_olm import Email

from .helpers.email_db_builders import _make_email


class TestAttachmentQueries:
    def _make_db_with_attachments(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(
            message_id="<a1@example.test>",
            has_attachments=True,
            attachments=[
                {"name": "report.pdf", "mime_type": "application/pdf", "size": 5000, "content_id": "", "is_inline": False},
                {
                    "name": "budget.xlsx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size": 12000,
                    "content_id": "",
                    "is_inline": False,
                },
            ],
        )
        e2 = _make_email(
            message_id="<a2@example.test>",
            sender_email="bob@example.com",
            sender_name="Bob",
            has_attachments=True,
            attachments=[
                {"name": "slides.pdf", "mime_type": "application/pdf", "size": 8000, "content_id": "", "is_inline": False},
            ],
        )
        e3 = _make_email(message_id="<a3@example.test>", has_attachments=False)
        db.insert_email(e1)
        db.insert_email(e2)
        db.insert_email(e3)
        return db

    def test_attachment_stats_empty(self):
        db = EmailDatabase(":memory:")
        stats = db.attachment_stats()
        assert stats["total_attachments"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["emails_with_attachments"] == 0
        db.close()

    def test_attachment_stats_with_data(self):
        db = self._make_db_with_attachments()
        stats = db.attachment_stats()
        assert stats["total_attachments"] == 3
        assert stats["total_size_bytes"] == 25000
        assert stats["emails_with_attachments"] == 2
        assert len(stats["by_extension"]) > 0
        assert len(stats["top_filenames"]) > 0
        db.close()

    def test_attachment_stats_extension_includes_dot(self):
        """Extension extraction SQL should include the leading dot."""
        db = self._make_db_with_attachments()
        stats = db.attachment_stats()
        extensions = {e["extension"] for e in stats["by_extension"]}
        # All non-empty extensions should start with '.'
        for ext in extensions:
            if ext:
                assert ext.startswith("."), f"Extension '{ext}' missing leading dot"
        assert ".pdf" in extensions
        assert ".xlsx" in extensions
        db.close()

    def test_list_attachments_no_filter(self):
        db = self._make_db_with_attachments()
        result = db.list_attachments()
        assert result["total"] == 3
        assert len(result["attachments"]) == 3
        db.close()

    def test_list_attachments_filter_extension(self):
        db = self._make_db_with_attachments()
        result = db.list_attachments(extension="pdf")
        assert result["total"] == 2
        assert all("pdf" in a["name"].lower() for a in result["attachments"])
        db.close()

    def test_list_attachments_filter_sender(self):
        db = self._make_db_with_attachments()
        result = db.list_attachments(sender="bob")
        assert result["total"] == 1
        assert result["attachments"][0]["name"] == "slides.pdf"
        db.close()

    def test_search_emails_by_attachment_filename(self):
        db = self._make_db_with_attachments()
        results = db.search_emails_by_attachment(filename="report")
        assert len(results) == 1
        assert "report.pdf" in results[0]["matching_attachments"]
        db.close()

    def test_search_emails_by_attachment_extension(self):
        db = self._make_db_with_attachments()
        results = db.search_emails_by_attachment(extension="pdf")
        assert len(results) == 2
        db.close()


class TestAttachmentStatsMultiDotExtension:
    def test_multi_dot_filename_extracts_last_extension(self):
        """Filenames like 'report.v2.pdf' should extract '.pdf', not '.v2.pdf'."""
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachments=[
                {"name": "my.report.v2.pdf", "mime_type": "application/pdf", "size": 1000, "content_id": "", "is_inline": False},
                {"name": "backup.tar.gz", "mime_type": "application/gzip", "size": 2000, "content_id": "", "is_inline": False},
            ],
        )
        db.insert_email(email)
        stats = db.attachment_stats()
        extensions = {e["extension"] for e in stats["by_extension"]}
        assert ".pdf" in extensions
        assert ".gz" in extensions
        # Should NOT contain the wrong multi-dot extractions
        assert ".v2.pdf" not in extensions
        assert ".tar.gz" not in extensions
        db.close()
