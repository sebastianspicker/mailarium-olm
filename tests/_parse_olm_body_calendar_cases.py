# ruff: noqa: F401,I001
from pathlib import Path

from lxml import etree

from src.parse_olm import (
    Email,
    _clean_text,
    _extract_email_from_header,
    _extract_header,
    _extract_name_from_header,
    _html_to_text,
    _parse_address_element,
    _parse_address_list,
    _parse_email_xml,
)
from src.olm_xml_helpers import _extract_folder, _extract_html_body, _parse_references
from src.rfc2822 import _normalize_date


def test_html_to_text_preserves_links():
    html = '<a href="https://example.com">Click here</a>'
    text = _html_to_text(html)
    assert "Click here (https://example.com)" in text


def test_html_to_text_preserves_lists():
    html = "<ul><li>First</li><li>Second</li></ul>"
    text = _html_to_text(html)
    assert "- First" in text
    assert "- Second" in text


def test_html_to_text_preserves_tables():
    html = "<table><tr><td>Name</td><td>Value</td></tr><tr><td>Alice</td><td>100</td></tr></table>"
    text = _html_to_text(html)
    assert "Name" in text
    assert "Alice" in text


def test_html_to_text_preserves_headings():
    html = "<h2>Important Section</h2><p>Content here.</p>"
    text = _html_to_text(html)
    assert "## Important Section" in text


def test_html_to_text_preserves_blockquote():
    html = "<blockquote>Quoted text here</blockquote>"
    text = _html_to_text(html)
    assert "> Quoted text here" in text


def test_clean_text_preserves_leading_indentation():
    text = "if True:\n    do_something()\n    more()"
    result = _clean_text(text)
    assert "    do_something()" in result
    assert "    more()" in result


def test_clean_text_strips_trailing_whitespace():
    text = "hello   \nworld   "
    result = _clean_text(text)
    assert result == "hello\nworld"


def test_clean_text_collapses_blank_lines():
    text = "a\n\n\n\n\nb"
    result = _clean_text(text)
    assert result == "a\n\n\nb"


def test_normalize_date_iso_passthrough():
    assert _normalize_date("2025-06-25T08:52:47") == "2025-06-25T08:52:47"
    # ISO with Z timezone is now normalized to +00:00 (UTC)
    result = _normalize_date("2025-06-25T08:52:47Z")
    assert result.startswith("2025-06-25T08:52:47")
    assert "+00:00" in result


def test_normalize_date_rfc2822_to_iso():
    # RFC 2822 dates are normalized to UTC (10:52:47 +0200 -> 08:52:47 UTC)
    result = _normalize_date("Wed, 25 Jun 2025 10:52:47 +0200")
    assert result.startswith("2025-06-25T08:52:47")
    assert "+00:00" in result  # Should be in UTC


def test_normalize_date_empty():
    assert _normalize_date("") == ""
    assert _normalize_date("   ") == ""


def test_normalize_date_unparseable():
    # Unparseable dates now return empty string to prevent MIN/MAX corruption
    assert _normalize_date("not a date") == ""


def test_extract_html_body_pure_text():
    el = etree.fromstring("<body>Hello world</body>")
    assert _extract_html_body(el) == "Hello world"


def test_extract_html_body_with_child_elements():
    el = etree.fromstring("<body><p>Para 1</p><p>Para 2</p></body>")
    result = _extract_html_body(el)
    assert "<p>" in result
    assert "Para 1" in result
    assert "Para 2" in result


def test_extract_html_body_mixed_content():
    el = etree.fromstring("<body>Before<br/>After</body>")
    result = _extract_html_body(el)
    assert "Before" in result
    assert "<br>" in result or "<br/>" in result
    assert "After" in result


def test_calendar_body_extraction():
    """Calendar-only emails should extract meeting details from ICS content."""
    from src.parse_olm import _calendar_to_text

    ical = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:Team Standup\r\n"
        "DTSTART:20250115T100000Z\r\n"
        "DTEND:20250115T103000Z\r\n"
        "LOCATION:Conference Room A\r\n"
        "ORGANIZER;CN=Alice:mailto:employee@example.test\r\n"
        "DESCRIPTION:Daily standup meeting\\nBring your updates\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    text = _calendar_to_text(ical)
    assert "Team Standup" in text
    assert "Conference Room A" in text
    assert "employee@example.test" in text
    assert "Daily standup meeting" in text


def test_calendar_body_from_source():
    """text/calendar MIME parts should be converted to readable text."""
    from src.parse_olm import _extract_body_from_source

    raw_source = (
        "From: employee@example.test\r\n"
        "Content-Type: text/calendar; method=REQUEST\r\n"
        "\r\n"
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "SUMMARY:Sprint Review\r\n"
        "DTSTART:20250120T140000Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    body_text, _body_html = _extract_body_from_source(raw_source)
    assert "Sprint Review" in body_text


def test_multipart_calendar_fallback():
    """Multipart email with only calendar parts should get placeholder body."""
    from src.parse_olm import _extract_body_from_source

    raw_source = (
        "From: employee@example.test\r\n"
        "Content-Type: multipart/mixed; boundary=boundary123\r\n"
        "\r\n"
        "--boundary123\r\n"
        "Content-Type: application/ics\r\n"
        "\r\n"
        "binary calendar data\r\n"
        "--boundary123--\r\n"
    )
    body_text, body_html = _extract_body_from_source(raw_source)
    # Should get some fallback text, not empty
    assert body_text or body_html


def test_calendar_to_text_empty():
    from src.parse_olm import _calendar_to_text

    assert _calendar_to_text("") == ""
    assert _calendar_to_text("BEGIN:VCALENDAR\nEND:VCALENDAR") == "[Calendar event]"


def test_extract_html_body_no_duplicate_tail():
    """_extract_html_body should not duplicate tail text of child elements."""
    from lxml import etree

    from src.olm_xml_helpers import _extract_html_body

    xml = "<body>Hello <b>bold</b> and <i>italic</i> world</body>"
    el = etree.fromstring(xml)
    result = _extract_html_body(el)
    # "and" should appear exactly once, not twice
    assert result.count(" and ") == 1
    assert result.count(" world") == 1
    assert "bold" in result


def test_html_to_text_strips_comments():
    """HTML comments (especially Outlook conditionals) should be stripped cleanly."""
    from src.html_converter import html_to_text

    # Outlook conditional comment containing '>'
    html = "<!--[if gte mso 9]><xml>stuff</xml><![endif]-->Real content here"
    result = html_to_text(html)
    assert "Real content here" in result
    assert "mso" not in result
    assert "endif" not in result

    # Comment with comparison operator
    html2 = "<!-- value > threshold -->Visible text"
    result2 = html_to_text(html2)
    assert "Visible text" in result2
    assert "threshold" not in result2
