"""Focused contracts for the mockup-matching search workspace."""

from __future__ import annotations

from unittest.mock import MagicMock

from mailarium.web_app_workspace import (
    _attachment_names,
    _document_body_html,
    _quoted_proof,
    render_search_workspace_impl,
)

from .helpers.web_app_fixtures import _result


def _workspace_streamlit() -> MagicMock:
    st_module = MagicMock()
    st_module.session_state = {"web_query": "handoff"}
    st_module.columns.side_effect = lambda widths, **_kwargs: [MagicMock() for _ in widths]
    st_module.button.return_value = False
    st_module.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
    st_module.expander.return_value.__exit__ = MagicMock(return_value=False)
    return st_module


def _render(st_module: MagicMock, results: list) -> None:
    render_search_workspace_impl(
        st_module=st_module,
        retriever=MagicMock(),
        results=results,
        page_results=results,
        page=0,
        page_size=20,
        total_pages=1,
        filters={"hybrid": True, "rerank": True},
        sort_value="relevance",
        build_export_payload_fn=lambda **values: values,
        build_csv_export_fn=lambda _results: "header\n",
    )


def test_workspace_defaults_to_first_result_and_renders_all_three_panes():
    st_module = _workspace_streamlit()
    results = [_result(chunk_id="first"), _result(chunk_id="second")]

    _render(st_module, results)

    assert st_module.session_state["web_selected_chunk_id"] == "first"
    rendered = "\n".join(str(call) for call in st_module.markdown.call_args_list)
    assert "mailarium-results-marker" in rendered
    assert "mailarium-document-marker" in rendered
    assert "mailarium-inspector-marker" in rendered
    assert "<span>Source</span>" in rendered


def test_workspace_escapes_message_metadata_and_body():
    st_module = _workspace_streamlit()
    result = _result(subject="<script>alert(1)</script>", text="<img src=x onerror=alert(1)>")

    _render(st_module, [result])

    rendered = "\n".join(str(call) for call in st_module.markdown.call_args_list)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered


def test_workspace_normalizes_quote_and_attachment_display_values():
    assert _quoted_proof("Short. This is the first meaningful sentence with enough source context. Later.") == (
        "This is the first meaningful sentence with enough source context."
    )
    assert _attachment_names({"attachment_names": "brief.pdf; owners.xlsx, notes.txt"}) == [
        "brief.pdf",
        "owners.xlsx",
        "notes.txt",
    ]


def test_document_body_marks_escaped_quoted_proof_as_provenance_anchor():
    rendered = _document_body_html("<unsafe>. This sentence is long enough to become quoted proof. Later.")

    assert "&lt;unsafe&gt;" in rendered
    assert "<unsafe>" not in rendered
    assert "<mark class='provenance-highlight'>" in rendered
