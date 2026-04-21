from src.body_forensics import extract_source_headers, render_forensic_text


def test_extract_source_headers_returns_common_headers():
    raw_source = (
        "From: Alice <alice@example.com>\n"
        "To: Bob <bob@example.com>\n"
        "Subject: Test subject\n"
        "Date: Wed, 25 Jun 2025 10:52:47 +0200\n"
        "\n"
        "Body text."
    )

    headers = extract_source_headers(raw_source)

    assert headers["From"] == "Alice <alice@example.com>"
    assert headers["To"] == "Bob <bob@example.com>"
    assert headers["Subject"] == "Test subject"
    assert headers["Date"] == "Wed, 25 Jun 2025 10:52:47 +0200"


def test_render_forensic_text_prefers_raw_plain_text_without_retrieval_stripping():
    forensic = render_forensic_text(
        raw_body_text=(
            "Latest answer.\n\n"
            "From: Alice <alice@example.com>\n"
            "Sent: Monday, January 1, 2025 10:00 AM\n"
            "To: Bob <bob@example.com>\n"
            "Subject: Status"
        ),
        raw_body_html="",
        raw_source="",
    )

    assert forensic.source == "raw_body_text"
    assert "From: Alice <alice@example.com>" in forensic.text
    assert forensic.content_hash


def test_render_forensic_text_is_deterministic():
    kwargs = {
        "raw_body_text": "",
        "raw_body_html": "<html><body><p>Hello<br>World</p></body></html>",
        "raw_source": "Subject: Test\n\nFallback body.",
    }

    first = render_forensic_text(**kwargs)
    second = render_forensic_text(**kwargs)

    assert first == second
    assert first.source == "raw_body_html"
    assert first.text == "Hello\nWorld"
