"""Dossier export and formatting tests."""

from __future__ import annotations

import os
import tempfile

from src.formatting import format_file_size, strip_html_tags

pytest_plugins = ["tests._dossier_cases"]


def test_generate_file_writes_html(gen):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "dossier.html")
        result = gen.generate_file(path, title="File Test")

        assert result["output_path"] == path
        assert result["format"] == "html"
        assert os.path.exists(path)

        content = open(path, encoding="utf-8").read()
        assert "File Test" in content


def test_generate_file_creates_parent_dirs(gen):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "subdir", "deep", "dossier.html")
        result = gen.generate_file(path, title="Deep Test")

        assert os.path.exists(path)
        assert result["evidence_count"] == 3


def test_date_formatting(gen):
    result = gen.generate()
    html = result["html"]

    assert "January" in html


def test_created_at_shown(gen):
    result = gen.generate()
    html = result["html"]

    assert "Collected:" in html


def test_content_sha256_fallback(db, gen):
    db.conn.execute(
        """INSERT INTO emails (uid, sender_email, sender_name, date, subject,
           body_text, body_html, has_attachments, attachment_count,
           priority, is_read, body_length, content_sha256)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 1, 10, ?)""",
        ("uid-nohash", "test@test.com", "Test", "2024-01-20", "No Hash", "Body", "<p>Body</p>", ""),
    )
    db.conn.execute(
        "INSERT INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)",
        ("uid-nohash", "r@test.com", "R", "to"),
    )
    db.conn.commit()
    db.add_evidence("uid-nohash", "general", "test quote", "Test", 1)

    result = gen.generate()
    html = result["html"]

    assert "(not available)" in html


def test_print_css_avoids_breaks(gen):
    result = gen.generate()
    html = result["html"]

    assert "break-inside: avoid" in html


def test_print_css_removes_scroll(gen):
    result = gen.generate()
    html = result["html"]

    assert "max-height: none" in html


def test_verified_badge_text(gen):
    result = gen.generate()
    html = result["html"]

    assert "Verified" in html
    assert "data-verified" not in html


def test_no_javascript_in_output(gen):
    result = gen.generate()
    html = result["html"]

    assert "<script>" not in html
    assert "<script " not in html


def test_strip_html_tags_removes_style_content():
    text = "<style>.foo { color: red; }</style><p>Hello</p>"
    result = strip_html_tags(text)
    assert "color: red" not in result
    assert "Hello" in result


def test_strip_html_tags_removes_script_content():
    text = '<script>var x = 1; alert("hi");</script><p>Content</p>'
    result = strip_html_tags(text)
    assert "alert" not in result
    assert "Content" in result


def test_strip_html_tags_removes_html_comments():
    text = "<!--[if gte mso 9]><xml><o:OfficeDocumentSettings></o:OfficeDocumentSettings></xml><![endif]-->Hello world"
    result = strip_html_tags(text)
    assert "<!--" not in result
    assert "mso" not in result
    assert "Hello world" in result


def test_relevance_stars(gen):
    result = gen.generate()
    html = result["html"]

    assert "\u2605\u2605\u2605\u2605\u2605" in html
    assert "relevance-stars" in html


def test_relevance_stars_mixed(gen):
    result = gen.generate()
    html = result["html"]

    assert "\u2605\u2605\u2605\u2606\u2606" in html


def test_print_css_bw_badges(gen):
    result = gen.generate()
    html = result["html"]

    assert "border: 1px solid #666" in html


def test_format_file_size():
    assert format_file_size(None) == ""
    assert format_file_size(0) == "0 B"
    assert format_file_size(500) == "500 B"
    assert format_file_size(1536) == "1.5 KB"
    assert format_file_size(2097152) == "2.0 MB"
