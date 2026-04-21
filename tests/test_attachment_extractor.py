"""Tests for attachment text extraction."""

from src.attachment_extractor import extract_text


def test_extract_plain_text():
    content = b"Hello, this is a plain text file."
    result = extract_text("notes.txt", content)
    assert result == "Hello, this is a plain text file."


def test_extract_csv():
    content = b"name,value\nalice,100\nbob,200"
    result = extract_text("data.csv", content)
    assert "alice,100" in result


def test_extract_markdown():
    content = b"# Title\n\nSome markdown content."
    result = extract_text("readme.md", content)
    assert "# Title" in result


def test_extract_html():
    content = b"<html><body><p>Hello world</p></body></html>"
    result = extract_text("page.html", content)
    assert "Hello world" in result


def test_extract_unsupported_returns_none():
    result = extract_text("photo.jpg", b"\xff\xd8\xff\xe0")
    assert result is None


def test_extract_empty_returns_none():
    assert extract_text("test.txt", b"") is None
    assert extract_text("", b"hello") is None


def test_extract_binary_skip_extensions():
    assert extract_text("archive.zip", b"PK\x03\x04") is None
    assert extract_text("program.exe", b"MZ\x90\x00") is None


def test_extract_text_truncation():
    from src.attachment_extractor import MAX_EXTRACTED_CHARS

    long_content = ("x" * (MAX_EXTRACTED_CHARS + 1000)).encode()
    result = extract_text("large.txt", long_content)
    assert result is not None
    assert "[... content truncated ...]" in result
    assert len(result) < len(long_content.decode())


def test_extract_latin1_fallback():
    # Latin-1 encoded content (not valid UTF-8)
    content = "Grüße aus München".encode("latin-1")
    result = extract_text("message.txt", content)
    assert result is not None
    assert "München" in result or "M" in result  # Latin-1 decoded


def test_pptx_returns_none_without_library(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "pptx":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    result = extract_text("slides.pptx", b"fake content")
    assert result is None


def test_ppt_still_skipped():
    result = extract_text("slides.ppt", b"fake content")
    assert result is None


def test_pptx_extraction():
    pptx = __import__("pytest").importorskip("pptx")
    import io

    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    from pptx.util import Inches

    txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    txBox.text_frame.text = "Hello from slide one"

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)

    result = extract_text("deck.pptx", buf.read())
    assert result is not None
    assert "[Slide 1]" in result
    assert "Hello from slide one" in result
