"""Tests for formatting module (Phase 4)."""

from src.formatting import build_result_header, estimate_tokens


def test_result_header_truncates_date_to_date_only():
    header = build_result_header({"date": "2025-01-15T10:30:00Z", "subject": "Test"})
    assert "Date: 2025-01-15" in header
    assert "T10:30:00Z" not in header


def test_result_header_omits_inbox_folder():
    header = build_result_header({"folder": "Inbox", "subject": "Test"})
    assert "Folder" not in header


def test_result_header_shows_non_inbox_folder():
    header = build_result_header({"folder": "Sent Items", "subject": "Test"})
    assert "Folder: Sent Items" in header


def test_result_header_shows_email_type_for_replies():
    header = build_result_header({"email_type": "reply", "subject": "RE: Test"})
    assert "Type: reply" in header


def test_result_header_omits_email_type_for_originals():
    header = build_result_header({"email_type": "original", "subject": "Test"})
    assert "Type" not in header


def test_result_header_shows_priority():
    header = build_result_header({"priority": "2", "subject": "Test"})
    assert "Priority: 2" in header


def test_result_header_omits_zero_priority():
    header = build_result_header({"priority": "0", "subject": "Test"})
    assert "Priority" not in header


def test_result_header_shows_attachment_names():
    header = build_result_header({"attachment_names": "report.pdf, image.png", "subject": "Test"})
    assert "Attachments: report.pdf, image.png" in header


def test_estimate_tokens():
    assert estimate_tokens("") == 1  # minimum 1
    assert estimate_tokens("a" * 100) == 25
    assert estimate_tokens("hello world") >= 1


# ── Categories and calendar in headers ──────────────────────


def test_email_header_shows_categories():
    from src.formatting import build_email_header

    header = build_email_header(
        {
            "subject": "Test",
            "categories": ["Meeting", "Finance"],
        }
    )
    assert "Categories: Meeting, Finance" in header


def test_email_header_shows_calendar_tag():
    from src.formatting import build_email_header

    header = build_email_header(
        {
            "subject": "Test",
            "is_calendar_message": True,
        }
    )
    assert "[Calendar/Meeting]" in header


def test_result_header_shows_categories():
    header = build_result_header({"subject": "Test", "categories": "Finance, HR"})
    assert "Categories: Finance, HR" in header


def test_result_header_shows_calendar_tag():
    header = build_result_header({"subject": "Test", "is_calendar_message": "True"})
    assert "[Calendar/Meeting]" in header


# ── truncate_body None handling ────────────────────────────────────


class TestTruncateBodyNone:
    """Regression: truncate_body must handle None from SQLite NULL columns.

    dict.get("body_text", "") returns None (not "") when the key exists
    with a None value, which is exactly what happens with dict(sqlite_row)
    for NULL columns.
    """

    def test_truncate_body_none_returns_empty(self):
        from src.formatting import truncate_body

        assert truncate_body(None, 500) == ""

    def test_truncate_body_none_unlimited(self):
        from src.formatting import truncate_body

        assert truncate_body(None, 0) == ""

    def test_truncate_body_normal_string(self):
        from src.formatting import truncate_body

        assert truncate_body("hello", 500) == "hello"

    def test_truncate_body_truncates(self):
        from src.formatting import truncate_body

        result = truncate_body("x" * 1000, 100)
        assert len(result) < 300  # body (100) + truncation notice with char counts
        assert result.startswith("x" * 100)
        assert "truncated" in result

    def test_dict_get_returns_none_not_default(self):
        """Verify the root cause: dict.get returns None, not the default."""
        d = {"body_text": None}
        assert d.get("body_text", "") is None  # This IS the bug's root cause
