"""Tests for src/evidence_exporter.py — evidence report HTML/CSV export."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.email_db import EmailDatabase
from src.evidence_exporter import EvidenceExporter
from src.parse_olm import Email


def _make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Team Meeting",
        "sender_name": "Boss",
        "sender_email": "boss@company.com",
        "to": ["Worker <worker@company.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-06-15T10:30:00",
        "body_text": "You are not qualified for this role. You should consider leaving.",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def _seed_db() -> EmailDatabase:
    db = EmailDatabase(":memory:")
    e1 = _make_email()
    e2 = _make_email(
        message_id="<msg2@example.com>",
        body_text="This is your final warning.",
        date="2024-07-01T09:00:00",
        subject="Performance Review",
    )
    db.insert_email(e1)
    db.insert_email(e2)

    db.add_evidence(
        e1.uid,
        "discrimination",
        "You are not qualified for this role",
        "Questioning competence related to disability.",
        relevance=5,
    )
    db.add_evidence(
        e1.uid,
        "bossing",
        "You should consider leaving",
        "Pushing employee out.",
        relevance=4,
    )
    db.add_evidence(
        e2.uid,
        "harassment",
        "This is your final warning",
        "Threatening language.",
        relevance=3,
    )
    return db


# ── HTML Export ───────────────────────────────────────────────


def test_html_export_contains_items():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_html()
    assert result["item_count"] == 3
    html = result["html"]
    assert "Evidence Report" in html
    assert "discrimination" in html.lower()
    assert "bossing" in html.lower()
    assert "harassment" in html.lower()
    db.close()


def test_html_export_contains_quotes():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_html()
    html = result["html"]
    assert "not qualified" in html
    assert "should consider leaving" in html
    assert "final warning" in html
    db.close()


def test_html_export_respects_min_relevance():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_html(min_relevance=5)
    assert result["item_count"] == 1
    db.close()


def test_html_export_respects_category():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_html(category="bossing")
    assert result["item_count"] == 1
    db.close()


def test_html_export_verification_banner():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_html()
    html = result["html"]
    # All quotes should be verified since they exist in body text
    assert "verified" in html.lower()
    db.close()


def test_html_export_appendix_contains_body():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_html()
    html = result["html"]
    # Appendix should contain full email body text
    assert "You are not qualified for this role" in html
    assert "This is your final warning" in html
    db.close()


def test_html_export_empty():
    db = EmailDatabase(":memory:")
    exporter = EvidenceExporter(db)

    result = exporter.export_html()
    assert result["item_count"] == 0
    db.close()


# ── CSV Export ────────────────────────────────────────────────


def test_csv_export_headers():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_csv()
    csv_text = result["csv"]
    header_line = csv_text.split("\n")[0]
    assert "id" in header_line
    assert "category" in header_line
    assert "key_quote" in header_line
    assert "relevance" in header_line
    assert "verified" in header_line
    assert "email_uid" in header_line
    db.close()


def test_csv_export_data_rows():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_csv()
    assert result["item_count"] == 3
    lines = [line for line in result["csv"].strip().split("\n") if line]
    assert len(lines) == 4  # header + 3 data rows
    db.close()


def test_csv_export_respects_filters():
    db = _seed_db()
    exporter = EvidenceExporter(db)

    result = exporter.export_csv(min_relevance=4)
    assert result["item_count"] == 2
    db.close()


# ── File Export ───────────────────────────────────────────────


def test_export_file_html(tmp_path):
    db = _seed_db()
    exporter = EvidenceExporter(db)

    out = str(tmp_path / "evidence.html")
    result = exporter.export_file(out, fmt="html")

    assert result["format"] == "html"
    assert result["output_path"] == out
    assert Path(out).exists()
    content = Path(out).read_text()
    assert "Evidence Report" in content
    db.close()


def test_export_file_csv(tmp_path):
    db = _seed_db()
    exporter = EvidenceExporter(db)

    out = str(tmp_path / "evidence.csv")
    result = exporter.export_file(out, fmt="csv")

    assert result["format"] == "csv"
    assert Path(out).exists()
    content = Path(out).read_text()
    assert "category" in content
    db.close()


def test_export_file_pdf_fallback(tmp_path):
    db = _seed_db()
    exporter = EvidenceExporter(db)

    out = str(tmp_path / "evidence.pdf")
    with patch.dict("sys.modules", {"weasyprint": None}):
        result = exporter.export_file(out, fmt="pdf")

    assert result["format"] == "html"
    assert result["output_path"].endswith(".html")
    assert "note" in result
    assert "weasyprint" in result["note"].lower()
    db.close()


def test_export_file_creates_parent_dirs(tmp_path):
    db = _seed_db()
    exporter = EvidenceExporter(db)

    out = str(tmp_path / "nested" / "deep" / "evidence.html")
    result = exporter.export_file(out, fmt="html")

    assert Path(out).exists()
    assert result["format"] == "html"
    db.close()


# ── Evidence stats filtering ──────────────────────────────────


def test_evidence_stats_unfiltered():
    db = _seed_db()
    stats = db.evidence_stats()
    assert stats["total"] == 3
    db.close()


def test_evidence_stats_with_category_filter():
    db = _seed_db()
    stats = db.evidence_stats(category="discrimination")
    assert stats["total"] == 1
    assert stats["by_category"][0]["category"] == "discrimination"
    db.close()


def test_evidence_stats_with_min_relevance_filter():
    db = _seed_db()
    stats = db.evidence_stats(min_relevance=4)
    assert stats["total"] == 2  # relevance 5 + relevance 4
    db.close()


def test_evidence_stats_with_both_filters():
    db = _seed_db()
    stats = db.evidence_stats(category="discrimination", min_relevance=5)
    assert stats["total"] == 1
    stats2 = db.evidence_stats(category="harassment", min_relevance=5)
    assert stats2["total"] == 0
    db.close()
