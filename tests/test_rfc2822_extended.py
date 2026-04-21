"""Extended tests for src/rfc2822.py — targets lines missed by existing tests."""

from __future__ import annotations

from src.rfc2822 import (
    _calendar_to_text,
    _decode_mime_words,
    _extract_body_from_source,
    _extract_email_from_header,
    _extract_header,
    _extract_name_from_header,
    _normalize_date,
    _parse_address_list,
    _parse_int,
)

# ── _parse_int ────────────────────────────────────────────────────


class TestParseInt:
    def test_empty_string(self):
        assert _parse_int("") == 0

    def test_none_value(self):
        assert _parse_int(None) == 0  # type: ignore[arg-type]

    def test_whitespace_only(self):
        assert _parse_int("   ") == 0

    def test_valid_integer(self):
        assert _parse_int("42") == 42

    def test_integer_with_whitespace(self):
        assert _parse_int("  7  ") == 7

    def test_invalid_value(self):
        assert _parse_int("abc") == 0

    def test_custom_default(self):
        assert _parse_int("", 5) == 5
        assert _parse_int("not_a_number", 99) == 99

    def test_negative_integer(self):
        assert _parse_int("-3") == -3

    def test_empty_with_custom_default(self):
        assert _parse_int(None, 10) == 10  # type: ignore[arg-type]


# ── _extract_body_from_source ─────────────────────────────────────


class TestExtractBodyFromSource:
    def test_simple_plain_text_email(self):
        raw = (
            "From: alice@example.com\r\n"
            "To: bob@example.com\r\n"
            "Subject: Test\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Hello, this is a test email."
        )
        body, html = _extract_body_from_source(raw)
        assert "Hello, this is a test email." in body
        assert html == ""

    def test_simple_html_email(self):
        raw = (
            "From: alice@example.com\r\n"
            "To: bob@example.com\r\n"
            "Subject: Test\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "\r\n"
            "<html><body><p>Hello HTML</p></body></html>"
        )
        body, html = _extract_body_from_source(raw)
        assert body == ""
        assert "Hello HTML" in html

    def test_multipart_email_with_text_and_html(self):
        raw = (
            "From: alice@example.com\r\n"
            "To: bob@example.com\r\n"
            "Subject: Test\r\n"
            "MIME-Version: 1.0\r\n"
            'Content-Type: multipart/alternative; boundary="boundary123"\r\n'
            "\r\n"
            "--boundary123\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Plain text body\r\n"
            "--boundary123\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "\r\n"
            "<html><body><p>HTML body</p></body></html>\r\n"
            "--boundary123--\r\n"
        )
        body, html = _extract_body_from_source(raw)
        assert "Plain text body" in body
        assert "HTML body" in html

    def test_multipart_email_with_calendar(self):
        raw = (
            "From: alice@example.com\r\n"
            "To: bob@example.com\r\n"
            "Subject: Meeting\r\n"
            "MIME-Version: 1.0\r\n"
            'Content-Type: multipart/alternative; boundary="cal_boundary"\r\n'
            "\r\n"
            "--cal_boundary\r\n"
            "Content-Type: text/calendar; charset=utf-8\r\n"
            "\r\n"
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Team standup\r\n"
            "DTSTART:20240101T090000Z\r\n"
            "DTEND:20240101T093000Z\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
            "--cal_boundary--\r\n"
        )
        body, html = _extract_body_from_source(raw)
        assert "Team standup" in body
        assert html == ""

    def test_non_multipart_calendar(self):
        raw = (
            "From: alice@example.com\r\n"
            "To: bob@example.com\r\n"
            "Subject: Meeting\r\n"
            "Content-Type: text/calendar; charset=utf-8\r\n"
            "\r\n"
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Standup\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        body, _html = _extract_body_from_source(raw)
        assert "Standup" in body

    def test_fallback_on_malformed_source(self):
        # Extremely malformed input — not valid RFC 2822 at all.
        # The email parser may still parse it, but we test the simple
        # header/body split fallback behavior when we have a blank line.
        raw = "Some garbage header\n\nBody content here"
        body, html = _extract_body_from_source(raw)
        # Should at least extract something
        assert isinstance(body, str)
        assert isinstance(html, str)

    def test_empty_source(self):
        body, html = _extract_body_from_source("")
        assert body == ""
        assert html == ""

    def test_multipart_attachment_only(self):
        """Multipart email with only an attachment (no text/html)."""
        raw = (
            "From: alice@example.com\r\n"
            "To: bob@example.com\r\n"
            "Subject: File\r\n"
            "MIME-Version: 1.0\r\n"
            'Content-Type: multipart/mixed; boundary="att_boundary"\r\n'
            "\r\n"
            "--att_boundary\r\n"
            "Content-Type: application/pdf\r\n"
            "Content-Disposition: attachment; filename=report.pdf\r\n"
            "Content-Transfer-Encoding: base64\r\n"
            "\r\n"
            "SGVsbG8=\r\n"
            "--att_boundary--\r\n"
        )
        body, _html = _extract_body_from_source(raw)
        assert "Attachment-only" in body or body == ""

    def test_multipart_calendar_only(self):
        """Multipart with only calendar part, no text or html parts."""
        raw = (
            "From: alice@example.com\r\n"
            "To: bob@example.com\r\n"
            "Subject: Meeting invite\r\n"
            "MIME-Version: 1.0\r\n"
            'Content-Type: multipart/mixed; boundary="calonly"\r\n'
            "\r\n"
            "--calonly\r\n"
            "Content-Type: text/calendar; method=REQUEST\r\n"
            "\r\n"
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Board meeting\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
            "--calonly\r\n"
            "Content-Type: application/ics\r\n"
            "Content-Disposition: attachment; filename=invite.ics\r\n"
            "\r\n"
            "BEGIN:VCALENDAR\r\n"
            "END:VCALENDAR\r\n"
            "--calonly--\r\n"
        )
        body, _html = _extract_body_from_source(raw)
        # Should extract calendar content from text/calendar part
        assert "Board meeting" in body


# ── _decode_mime_words ───────────────────────────────────────────


class TestDecodeMimeWords:
    def test_plain_text_no_encoding(self):
        assert _decode_mime_words("Hello World") == "Hello World"

    def test_utf8_encoded_word(self):
        result = _decode_mime_words("=?utf-8?Q?Hello_World?=")
        assert "Hello" in result
        assert "World" in result

    def test_iso_8859_1_encoded_word(self):
        result = _decode_mime_words("=?iso-8859-1?Q?Gr=FC=DFe?=")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_base64_encoded_word(self):
        result = _decode_mime_words("=?utf-8?B?SGVsbG8gV29ybGQ=?=")
        assert result == "Hello World"

    def test_multiple_encoded_words(self):
        result = _decode_mime_words("=?utf-8?Q?Part_1?= =?utf-8?Q?_Part_2?=")
        assert "Part" in result

    def test_mixed_plain_and_encoded(self):
        result = _decode_mime_words("Re: =?utf-8?Q?Hello?=")
        assert "Re:" in result
        assert "Hello" in result

    def test_no_encoded_word_marker(self):
        # Should return as-is when no =? marker present
        plain = "Just a regular subject line"
        assert _decode_mime_words(plain) == plain

    def test_empty_string(self):
        assert _decode_mime_words("") == ""

    def test_bytes_decoded_with_charset(self):
        # Encoded word with non-utf8 charset
        result = _decode_mime_words("=?windows-1252?Q?Re=3A_Meeting?=")
        assert "Re:" in result
        assert "Meeting" in result


# ── _extract_email_from_header ────────────────────────────────────


class TestExtractEmailFromHeader:
    def test_angle_bracket_email(self):
        source = "From: Alice Smith <alice@example.com>\n\nBody"
        assert _extract_email_from_header(source, "From") == "alice@example.com"

    def test_bare_email(self):
        source = "From: alice@example.com\n\nBody"
        assert _extract_email_from_header(source, "From") == "alice@example.com"

    def test_html_encoded_brackets(self):
        source = "From: Alice &lt;alice@example.com&gt;\n\nBody"
        assert _extract_email_from_header(source, "From") == "alice@example.com"

    def test_missing_header(self):
        source = "Subject: Test\n\nBody"
        assert _extract_email_from_header(source, "From") == ""

    def test_no_email_in_header(self):
        source = "From: Just A Name\n\nBody"
        result = _extract_email_from_header(source, "From")
        # Should return the raw value when no email pattern found
        assert result == "Just A Name"

    def test_quoted_name_with_email(self):
        source = 'From: "Smith, Alice" <alice@example.com>\n\nBody'
        assert _extract_email_from_header(source, "From") == "alice@example.com"


# ── _extract_name_from_header ────────────────────────────────────


class TestExtractNameFromHeader:
    def test_quoted_name(self):
        source = 'From: "Alice Smith" <alice@example.com>\n\nBody'
        assert _extract_name_from_header(source, "From") == "Alice Smith"

    def test_unquoted_name(self):
        source = "From: Alice Smith <alice@example.com>\n\nBody"
        assert _extract_name_from_header(source, "From") == "Alice Smith"

    def test_missing_header(self):
        source = "Subject: Test\n\nBody"
        assert _extract_name_from_header(source, "From") == ""

    def test_email_only_no_name(self):
        source = "From: alice@example.com\n\nBody"
        result = _extract_name_from_header(source, "From")
        # parseaddr should return empty name for bare email
        assert result == ""

    def test_html_encoded_brackets(self):
        source = "From: Alice &lt;alice@example.com&gt;\n\nBody"
        name = _extract_name_from_header(source, "From")
        assert name == "Alice"

    def test_name_with_comma_quoted(self):
        source = 'From: "Smith, Alice" <alice@example.com>\n\nBody'
        name = _extract_name_from_header(source, "From")
        assert "Smith" in name
        assert "Alice" in name


# ── _extract_header ──────────────────────────────────────────────


class TestExtractHeader:
    def test_simple_header(self):
        source = "Subject: Test Email\nFrom: alice@example.com\n\nBody"
        assert _extract_header(source, "Subject") == "Test Email"

    def test_continuation_line(self):
        source = "Subject: Very Long\n Subject Line\nFrom: alice@example.com\n\nBody"
        result = _extract_header(source, "Subject")
        assert "Very Long" in result
        assert "Subject Line" in result

    def test_missing_header(self):
        source = "Subject: Test\n\nBody"
        assert _extract_header(source, "X-Custom") == ""

    def test_case_insensitive(self):
        source = "SUBJECT: Upper Case\n\nBody"
        assert _extract_header(source, "Subject") == "Upper Case"


# ── _parse_address_list ──────────────────────────────────────────


class TestParseAddressList:
    def test_single_address(self):
        result = _parse_address_list("alice@example.com")
        assert result == ["alice@example.com"]

    def test_multiple_comma_separated(self):
        result = _parse_address_list("alice@example.com, bob@example.com")
        assert result == ["alice@example.com", "bob@example.com"]

    def test_semicolon_separated(self):
        result = _parse_address_list("alice@example.com; bob@example.com")
        assert result == ["alice@example.com", "bob@example.com"]

    def test_with_display_names(self):
        result = _parse_address_list("Alice <alice@example.com>, Bob <bob@example.com>")
        assert result == ["alice@example.com", "bob@example.com"]

    def test_html_encoded_brackets(self):
        result = _parse_address_list("Alice &lt;alice@example.com&gt;")
        assert result == ["alice@example.com"]

    def test_empty_string(self):
        result = _parse_address_list("")
        assert result == []

    def test_mixed_separators(self):
        result = _parse_address_list("a@x.com; b@x.com, c@x.com")
        assert len(result) == 3


# ── _normalize_date ──────────────────────────────────────────────


class TestNormalizeDate:
    def test_iso_format_unchanged(self):
        assert _normalize_date("2024-01-15T10:30:00") == "2024-01-15T10:30:00"

    def test_rfc2822_format(self):
        result = _normalize_date("Wed, 25 Jun 2025 10:52:47 +0200")
        assert result.startswith("2025-06-25")

    def test_empty_string(self):
        assert _normalize_date("") == ""

    def test_whitespace_only(self):
        assert _normalize_date("   ") == ""

    def test_none_value(self):
        assert _normalize_date(None) == ""  # type: ignore[arg-type]

    def test_unparseable_date(self):
        result = _normalize_date("not-a-date")
        assert result == ""


# ── _calendar_to_text ────────────────────────────────────────────


class TestCalendarToText:
    def test_empty_input(self):
        assert _calendar_to_text("") == ""

    def test_none_input(self):
        assert _calendar_to_text(None) == ""  # type: ignore[arg-type]

    def test_full_event(self):
        ical = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Team Standup\r\n"
            "ORGANIZER;CN=Alice:mailto:alice@example.com\r\n"
            "LOCATION:Room 101\r\n"
            "DTSTART:20240101T090000Z\r\n"
            "DTEND:20240101T093000Z\r\n"
            "DESCRIPTION:Daily standup meeting\\nBring your updates\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        result = _calendar_to_text(ical)
        assert "Team Standup" in result
        assert "alice@example.com" in result
        assert "Room 101" in result
        assert "Daily standup meeting" in result

    def test_no_fields_returns_bracket_text(self):
        ical = "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        result = _calendar_to_text(ical)
        assert result == "[Calendar event]"
