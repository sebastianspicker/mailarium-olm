"""Tests for web_app.py helper functions."""

import io

from src.retriever import SearchResult


def _result(
    chunk_id: str = "c1",
    score_distance: float = 0.2,
    date: str = "2024-01-15",
    sender_email: str = "a@example.com",
    sender_name: str = "Alice",
    subject: str = "Test Subject",
    folder: str = "Inbox",
    text: str = "Hello world body text",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        text=text,
        metadata={
            "subject": subject,
            "sender_email": sender_email,
            "sender_name": sender_name,
            "date": date,
            "folder": folder,
        },
        distance=score_distance,
    )


def test_web_app_imports():
    """Verify the module imports without error."""
    from src import web_app  # noqa: F401


def test_build_csv_export_header_and_rows():
    from src.web_app import _build_csv_export

    results = [_result("c1", 0.2, "2024-01-01"), _result("c2", 0.3, "2024-06-01")]
    csv_text = _build_csv_export(results)
    lines = [ln.rstrip("\r") for ln in csv_text.strip().split("\n")]
    assert lines[0] == "date,sender,subject,folder,score,text_preview"
    assert len(lines) == 3  # header + 2 rows


def test_build_csv_export_empty():
    from src.web_app import _build_csv_export

    csv_text = _build_csv_export([])
    lines = csv_text.strip().split("\n")
    assert len(lines) == 1  # header only


def test_build_csv_export_truncates_preview():
    from src.web_app import _build_csv_export

    long_text = "x" * 500
    results = [_result(text=long_text)]
    csv_text = _build_csv_export(results)
    # Preview should be truncated to 300 chars
    import csv

    reader = csv.DictReader(io.StringIO(csv_text))
    row = next(reader)
    assert len(row["text_preview"]) == 300


def test_as_optional_str():
    from src.web_app import _as_optional_str

    assert _as_optional_str("hello") == "hello"
    assert _as_optional_str("") == ""
    assert _as_optional_str(None) is None
    assert _as_optional_str(42) is None
    assert _as_optional_str([]) is None


def test_as_optional_float():
    from src.web_app import _as_optional_float

    assert _as_optional_float(3.14) == 3.14
    assert _as_optional_float(42) == 42.0
    assert _as_optional_float(0) == 0.0
    assert _as_optional_float(None) is None
    assert _as_optional_float("nope") is None
    assert _as_optional_float([]) is None


def test_build_csv_export_handles_missing_metadata():
    from src.web_app import _build_csv_export

    result = SearchResult(
        chunk_id="bare",
        text="minimal body",
        metadata={},
        distance=0.5,
    )
    csv_text = _build_csv_export([result])
    import csv

    reader = csv.DictReader(io.StringIO(csv_text))
    row = next(reader)
    assert row["sender"] == ""
    assert row["subject"] == ""


def test_build_csv_export_score_formatting():
    from src.web_app import _build_csv_export

    results = [_result(score_distance=0.15)]  # score = 0.85
    csv_text = _build_csv_export(results)
    import csv

    reader = csv.DictReader(io.StringIO(csv_text))
    row = next(reader)
    assert row["score"] == "0.85"
