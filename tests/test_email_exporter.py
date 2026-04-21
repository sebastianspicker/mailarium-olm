"""Tests for src/email_exporter.py — thread and single email HTML/PDF export."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.email_exporter import EmailExporter

# ── Helpers ──────────────────────────────────────────────────────────


def _fake_email(**overrides) -> dict:
    """Build a minimal email dict as returned by EmailDatabase.get_email_full()."""
    defaults = {
        "uid": "abc123",
        "subject": "Hello World",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "date": "2024-06-15T10:30:00",
        "folder": "Inbox",
        "email_type": "original",
        "has_attachments": 0,
        "attachment_count": 0,
        "body_text": "This is the email body.",
        "body_html": "",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "conversation_id": "conv_001",
    }
    defaults.update(overrides)
    return defaults


def _mock_db(thread_emails=None, single_email=None) -> MagicMock:
    """Create a mock EmailDatabase with configurable returns."""
    db = MagicMock()
    db.get_thread_emails.return_value = thread_emails or []
    db.get_email_full.return_value = single_email
    return db


# ── export_thread_html ───────────────────────────────────────────────


def test_export_thread_html_returns_html():
    emails = [_fake_email(), _fake_email(uid="def456", date="2024-06-16T09:00:00")]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    assert "html" in result
    assert result["email_count"] == 2
    assert result["subject"] == "Hello World"
    assert "<html" in result["html"].lower()


def test_export_thread_html_contains_headers():
    emails = [
        _fake_email(
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
            bcc=["Dave <dave@example.com>"],
        )
    ]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    html = result["html"]
    assert "alice@example.com" in html
    assert "bob@example.com" in html
    assert "carol@example.com" in html
    assert "dave@example.com" in html


def test_export_thread_html_contains_body():
    emails = [_fake_email(body_text="Important meeting notes here.")]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    assert "Important meeting notes here." in result["html"]


def test_export_thread_html_forensic_mode_uses_forensic_body():
    emails = [
        _fake_email(
            body_text="Normalized retrieval body.",
            forensic_body_text="Forensic body with preserved quoted history.",
        )
    ]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001", render_mode="forensic")
    assert "Forensic body with preserved quoted history." in result["html"]
    assert "Normalized retrieval body." not in result["html"]
    assert result["render_mode"] == "forensic"


def test_export_thread_html_empty_thread():
    db = _mock_db(thread_emails=[])
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("nonexistent_conv")
    assert "error" in result
    assert "No emails found" in result["error"]


def test_export_thread_html_date_range():
    emails = [
        _fake_email(date="2024-01-10T08:00:00"),
        _fake_email(uid="def456", date="2024-03-20T14:00:00"),
    ]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    # The template should render the date range
    assert "2024-01-10" in result["html"]
    assert "2024-03-20" in result["html"]


# ── export_single_html ───────────────────────────────────────────────


def test_export_single_html_valid_uid():
    email = _fake_email()
    db = _mock_db(single_email=email)
    exporter = EmailExporter(db)

    result = exporter.export_single_html("abc123")
    assert "html" in result
    assert result["email_count"] == 1
    assert result["subject"] == "Hello World"


def test_export_single_html_missing_uid():
    db = _mock_db(single_email=None)
    exporter = EmailExporter(db)

    result = exporter.export_single_html("missing_uid")
    assert "error" in result
    assert "Email not found" in result["error"]


# ── export_thread_file ───────────────────────────────────────────────


def test_export_thread_file_html(tmp_path):
    emails = [_fake_email()]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    out = str(tmp_path / "thread.html")
    result = exporter.export_thread_file("conv_001", out, fmt="html")

    assert result["format"] == "html"
    assert result["output_path"] == out
    assert Path(out).exists()
    content = Path(out).read_text()
    assert "<html" in content.lower()


def test_export_thread_file_error_propagated(tmp_path):
    db = _mock_db(thread_emails=[])
    exporter = EmailExporter(db)

    result = exporter.export_thread_file("bad_conv", str(tmp_path / "out.html"))
    assert "error" in result


def test_export_thread_file_pdf_fallback_to_html(tmp_path):
    """Without weasyprint, PDF export should fall back to HTML."""
    emails = [_fake_email()]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    out = str(tmp_path / "thread.pdf")
    with patch.dict("sys.modules", {"weasyprint": None}):
        result = exporter.export_thread_file("conv_001", out, fmt="pdf")

    # Should have fallen back to HTML
    assert result["format"] == "html"
    assert result["output_path"].endswith(".html")
    assert "note" in result
    assert "weasyprint" in result["note"].lower()


# ── export_single_file ──────────────────────────────────────────────


def test_export_single_file_html(tmp_path):
    email = _fake_email()
    db = _mock_db(single_email=email)
    exporter = EmailExporter(db)

    out = str(tmp_path / "email.html")
    result = exporter.export_single_file("abc123", out, fmt="html")

    assert result["format"] == "html"
    assert Path(out).exists()
    assert result["email_count"] == 1


def test_export_single_file_error_propagated(tmp_path):
    db = _mock_db(single_email=None)
    exporter = EmailExporter(db)

    result = exporter.export_single_file("missing", str(tmp_path / "out.html"))
    assert "error" in result


# ── Template rendering details ───────────────────────────────────────


def test_template_renders_attachment_info():
    email = _fake_email(has_attachments=1, attachment_count=3)
    db = _mock_db(thread_emails=[email])
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    # Should mention attachments somewhere in the HTML
    assert "3" in result["html"]


def test_template_renders_email_type_badge():
    email = _fake_email(email_type="reply")
    db = _mock_db(thread_emails=[email])
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    html_lower = result["html"].lower()
    assert "reply" in html_lower


def test_template_renders_no_subject():
    email = _fake_email(subject="")
    db = _mock_db(thread_emails=[email])
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    # The template falls back to "(no subject)" in the rendered HTML
    assert "(no subject)" in result["html"]


def test_template_multiple_emails_in_thread():
    emails = [
        _fake_email(uid="e1", subject="Project Update", date="2024-01-01T10:00:00", body_text="Initial update."),
        _fake_email(
            uid="e2",
            subject="RE: Project Update",
            date="2024-01-02T11:00:00",
            sender_name="Bob",
            sender_email="bob@example.com",
            body_text="Thanks for the update.",
        ),
        _fake_email(uid="e3", subject="RE: Project Update", date="2024-01-03T09:00:00", body_text="Final reply."),
    ]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    result = exporter.export_thread_html("conv_001")
    html = result["html"]
    assert result["email_count"] == 3
    assert "Initial update." in html
    assert "Thanks for the update." in html
    assert "Final reply." in html


# ── _write_output edge cases ────────────────────────────────────────


def test_write_output_creates_parent_dirs(tmp_path):
    emails = [_fake_email()]
    db = _mock_db(thread_emails=emails)
    exporter = EmailExporter(db)

    out = str(tmp_path / "nested" / "deep" / "thread.html")
    result = exporter.export_thread_file("conv_001", out, fmt="html")

    assert result["format"] == "html"
    assert Path(out).exists()
