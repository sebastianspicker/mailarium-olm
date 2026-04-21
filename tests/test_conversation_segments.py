"""Tests for conversation segmentation."""

from src.conversation_segments import extract_segments
from src.parse_olm import _parse_email_xml


def _segment_summary(segments):
    return [(segment.segment_type, segment.depth, segment.text) for segment in segments]


def test_extract_segments_from_plain_reply_with_quoted_tail():
    body = "Latest answer.\n\nOn Mon, Jan 1, 2025 at 10:00 AM Alice wrote:\n> Older line 1\n> Older line 2"
    segments = extract_segments(body, "", "", "reply")

    assert _segment_summary(segments) == [
        ("authored_body", 0, "Latest answer."),
        ("header_block", 0, "On Mon, Jan 1, 2025 at 10:00 AM Alice wrote:"),
        ("quoted_reply", 1, "Older line 1\nOlder line 2"),
    ]
    assert all(segment.source_surface == "body_text" for segment in segments)


def test_extract_segments_from_html_nested_blockquotes():
    html = "<div><p>Latest answer.</p><blockquote><p>Older line</p><blockquote><p>Oldest line</p></blockquote></blockquote></div>"

    segments = extract_segments("", html, "", "reply")

    assert _segment_summary(segments) == [
        ("authored_body", 0, "Latest answer."),
        ("quoted_reply", 1, "Older line"),
        ("quoted_reply", 2, "Oldest line"),
    ]
    assert all(segment.source_surface == "body_html" for segment in segments)


def test_extract_segments_from_html_blockquote_with_comment_does_not_crash():
    html = (
        "<div><p>Latest answer.</p>"
        "<blockquote><!-- outlook-comment --><p>Older line</p><?pi test?>"
        "<blockquote><p>Oldest line</p></blockquote></blockquote></div>"
    )

    segments = extract_segments("", html, "", "reply")

    assert _segment_summary(segments) == [
        ("authored_body", 0, "Latest answer."),
        ("quoted_reply", 1, "Older line"),
        ("quoted_reply", 2, "Oldest line"),
    ]


def test_extract_segments_from_forwarded_header_block():
    body = (
        "FYI.\n\n"
        "-----Original Message-----\n"
        "From: Alice <alice@example.com>\n"
        "Sent: Monday, January 1, 2025 10:00 AM\n"
        "To: Bob <bob@example.com>\n"
        "Subject: Original topic\n\n"
        "Forwarded body text."
    )

    segments = extract_segments(body, "", "", "forward")

    assert _segment_summary(segments) == [
        ("authored_body", 0, "FYI."),
        ("system_separator", 0, "-----Original Message-----"),
        (
            "header_block",
            0,
            "From: Alice <alice@example.com>\n"
            "Sent: Monday, January 1, 2025 10:00 AM\n"
            "To: Bob <bob@example.com>\n"
            "Subject: Original topic",
        ),
        ("forwarded_message", 0, "Forwarded body text."),
    ]


def test_extract_segments_marks_signature_and_legal_footer():
    body = (
        "Latest answer.\n\n"
        "-- \n"
        "Alice Example\n"
        "IT Services\n\n"
        "This email is confidential.\n"
        "It is intended only for the named recipient.\n"
        "If you received it in error, notify the sender and delete this email.\n"
        "Unauthorized review, use, disclosure, or distribution is prohibited."
    )

    segments = extract_segments(body, "", "", "original")

    assert _segment_summary(segments) == [
        ("authored_body", 0, "Latest answer."),
        ("signature", 0, "Alice Example\nIT Services"),
        (
            "legal_footer",
            0,
            "This email is confidential.\n"
            "It is intended only for the named recipient.\n"
            "If you received it in error, notify the sender and delete this email.\n"
            "Unauthorized review, use, disclosure, or distribution is prohibited.",
        ),
    ]


def test_parse_email_xml_attaches_segments():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>RE: Follow-up</OPFMessageCopySubject>
  <OPFMessageCopyBody>Current answer.

On Mon, Jan 1, 2025 at 10:00 AM Alice wrote:
&gt; Older line 1
&gt; Older line 2</OPFMessageCopyBody>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")
    assert parsed is not None
    assert _segment_summary(parsed.segments) == [
        ("authored_body", 0, "Current answer."),
        ("header_block", 0, "On Mon, Jan 1, 2025 at 10:00 AM Alice wrote:"),
        ("quoted_reply", 1, "Older line 1\nOlder line 2"),
    ]


def test_parse_email_xml_handles_html_comment_inside_blockquote():
    xml = b"""<?xml version="1.0"?>
<emails><email>
  <OPFMessageCopySentTime>2025-01-01T00:00:00</OPFMessageCopySentTime>
  <OPFMessageCopySubject>RE: Follow-up</OPFMessageCopySubject>
  <OPFMessageCopyHTMLBody><![CDATA[
    <div><p>Latest answer.</p><blockquote><!-- outlook-comment --><p>Older line</p><?pi test?>
    <blockquote><p>Oldest line</p></blockquote></blockquote></div>
  ]]></OPFMessageCopyHTMLBody>
</email></emails>"""
    parsed = _parse_email_xml(xml, "Accounts/a/com.microsoft.__Messages/Inbox/msg.xml")

    assert parsed is not None
    assert _segment_summary(parsed.segments) == [
        ("authored_body", 0, "Latest answer."),
        ("quoted_reply", 1, "Older line"),
        ("quoted_reply", 2, "Oldest line"),
    ]
