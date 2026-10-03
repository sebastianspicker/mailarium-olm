"""Rendering contracts for the Marginalia web helpers: escaping, quoted history, and quote marks."""

from __future__ import annotations

from mailarium.interfaces.web.presentation import build_register_table_html, relevance_label
from mailarium.interfaces.web.workspace import _document_body_html


def test_body_escapes_untrusted_text_and_marks_quote_without_splitting_entities() -> None:
    body = "Tom & Jerry <script>x()</script>\nThe launch moved to 9 June."

    rendered = _document_body_html(body, highlight="amp")
    assert "<script>" not in rendered
    assert "Tom &amp; Jerry &lt;script&gt;" in rendered
    assert "pencil-mark" not in rendered

    rendered = _document_body_html(body, highlight="launch MOVED")
    assert "<mark class='pencil-mark'>launch moved</mark>" in rendered
    assert rendered.count("pencil-mark") == 1


def test_body_sets_quoted_history_apart_and_keeps_literal_markers() -> None:
    rendered = _document_body_html("Agreed.\n> On Monday, Omar wrote:\n> Can we hold the date?", highlight="hold the date")

    assert "<span class='quoted-history'>" in rendered
    assert "&gt; Can we <mark class='pencil-mark'>hold the date</mark>?" in rendered
    assert rendered.index("Agreed.") < rendered.index("quoted-history")


def test_body_ignores_short_highlights_and_reports_empty_bodies() -> None:
    assert "pencil-mark" not in _document_body_html("a b c", highlight="a")
    assert _document_body_html(" \n ") == ""


def test_register_table_escapes_cells_and_headings() -> None:
    html = build_register_table_html(
        [{"name": "<b>Acme</b>", "count": 1200, "score": 0.0042}],
        {"name": "Name & role", "count": "Messages", "score": "Centrality"},
        numeric=("count", "score"),
    )
    assert "&lt;b&gt;Acme&lt;/b&gt;" in html and "<b>" not in html
    assert "Name &amp; role" in html
    assert "1,200" in html and "0.0042" in html


def test_relevance_label_names_and_clamps() -> None:
    assert relevance_label(5) == "5 · Critical"
    assert relevance_label(9) == "5 · Critical"
    assert relevance_label(None) == "1 · Tangential"
