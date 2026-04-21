"""Structural seam tests for the R6 web_app refactor."""

from __future__ import annotations

from types import SimpleNamespace

import src.web_app as web_app


def test_render_sidebar_delegates_to_impl(monkeypatch):
    calls: list[tuple[object, object]] = []

    def fake_impl(*, st_module, retriever):
        calls.append((st_module, retriever))

    retriever = object()
    monkeypatch.setattr(web_app, "render_sidebar_impl", fake_impl)

    web_app.render_sidebar(retriever)

    assert calls == [(web_app.st, retriever)]


def test_render_dashboard_page_delegates_to_impl(monkeypatch):
    calls: list[tuple[object, object]] = []

    def fake_impl(*, st_module, get_email_db_safe_fn):
        calls.append((st_module, get_email_db_safe_fn))

    monkeypatch.setattr(web_app, "render_dashboard_page_impl", fake_impl)

    web_app.render_dashboard_page()

    assert calls == [(web_app.st, web_app._get_email_db_safe)]


def test_render_search_page_delegates_with_callbacks(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_impl(**kwargs):
        calls.append(kwargs)

    retriever = object()
    monkeypatch.setattr(web_app, "render_search_page_impl", fake_impl)

    web_app.render_search_page(retriever)

    assert len(calls) == 1
    assert calls[0]["st_module"] is web_app.st
    assert calls[0]["retriever"] is retriever
    assert calls[0]["render_results_fn"] is web_app.render_results
    assert calls[0]["render_results_summary_fn"] is web_app.render_results_summary
    assert calls[0]["build_csv_export_fn"] is web_app._build_csv_export


def test_main_routes_search_to_render_search_page(monkeypatch):
    calls: list[object] = []

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "render_search_page", lambda retriever: calls.append(retriever))
    monkeypatch.setattr(web_app, "get_retriever", lambda _path: "retriever")

    fake_sidebar = SimpleNamespace(
        radio=lambda *args, **kwargs: "Search",
        text_input=lambda *args, **kwargs: "",
    )
    fake_streamlit = SimpleNamespace(
        sidebar=fake_sidebar,
        markdown=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(web_app, "st", fake_streamlit)

    web_app.main()

    assert calls == ["retriever"]
