"""Structural seam tests for the R6 web_app refactor."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

import src.web_app as web_app
from src.repo_paths import validate_runtime_path


def test_render_sidebar_delegates_to_impl(monkeypatch):
    calls: list[tuple[object, object]] = []

    def fake_impl(*, st_module, retriever):
        calls.append((st_module, retriever))

    retriever = cast(Any, object())
    monkeypatch.setattr(web_app, "render_sidebar_impl", fake_impl)

    web_app.render_sidebar(retriever)

    assert calls == [(web_app.st, retriever)]


def test_render_dashboard_page_delegates_to_impl(monkeypatch):
    calls: list[tuple[object, object]] = []

    def fake_impl(*, st_module, get_email_db_safe_fn):
        calls.append((st_module, get_email_db_safe_fn))

    monkeypatch.setattr(web_app, "render_dashboard_page_impl", fake_impl)

    web_app.render_dashboard_page("/tmp/email.db")

    assert len(calls) == 1
    assert calls[0][0] is web_app.st
    assert callable(calls[0][1])


def test_render_search_page_delegates_with_callbacks(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_impl(**kwargs):
        calls.append(kwargs)

    retriever = cast(Any, object())
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
    monkeypatch.setattr(web_app, "get_retriever", lambda _chroma, _sqlite=None: "retriever")

    fake_sidebar = SimpleNamespace(
        radio=lambda *args, **kwargs: "Search",
        text_input=lambda *args, **kwargs: "",
    )
    fake_streamlit = SimpleNamespace(
        sidebar=fake_sidebar,
        markdown=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(web_app, "st", fake_streamlit)

    web_app.main()

    assert calls == ["retriever"]


def test_main_routes_dashboard_with_sqlite_path(monkeypatch):
    calls: list[object] = []
    retriever_calls: list[tuple[object, object]] = []
    monkeypatch.setenv("EMAIL_RAG_ALLOWED_RUNTIME_ROOTS", "/tmp")

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "render_dashboard_page", lambda sqlite_path=None: calls.append(sqlite_path))
    monkeypatch.setattr(
        web_app, "get_retriever", lambda chroma, sqlite=None: retriever_calls.append((chroma, sqlite)) or "retriever"
    )

    sidebar_inputs = iter(["", "/tmp/archive.db"])
    fake_sidebar = SimpleNamespace(
        radio=lambda *args, **kwargs: "Dashboard",
        text_input=lambda *args, **kwargs: next(sidebar_inputs),
    )
    fake_streamlit = SimpleNamespace(
        sidebar=fake_sidebar,
        markdown=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(web_app, "st", fake_streamlit)

    web_app.main()

    assert calls == [str(validate_runtime_path("/tmp/archive.db", field_name="SQLite path"))]
    assert retriever_calls == []


def test_main_surfaces_runtime_path_errors_instead_of_crashing(monkeypatch):
    errors: list[str] = []

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "render_search_page", lambda retriever: None)

    def fake_get_retriever(_chroma, _sqlite=None):
        raise RuntimeError("invalid sqlite path")

    monkeypatch.setattr(web_app, "get_retriever", fake_get_retriever)

    fake_sidebar = SimpleNamespace(
        radio=lambda *args, **kwargs: "Search",
        text_input=lambda *args, **kwargs: "/tmp/bad-path",
    )
    fake_streamlit = SimpleNamespace(
        sidebar=fake_sidebar,
        markdown=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        error=lambda message: errors.append(str(message)),
    )
    monkeypatch.setattr(web_app, "st", fake_streamlit)

    web_app.main()

    assert errors
    assert "runtime paths" in errors[0].lower()


def test_main_rejects_web_runtime_paths_outside_allowed_roots(monkeypatch):
    errors: list[str] = []
    calls: list[object] = []

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "render_search_page", lambda retriever: calls.append(retriever))
    monkeypatch.setattr(web_app, "get_retriever", lambda _chroma, _sqlite=None: "retriever")

    sidebar_inputs = iter(["", "/etc/archive.db"])
    fake_sidebar = SimpleNamespace(
        radio=lambda *args, **kwargs: "Search",
        text_input=lambda *args, **kwargs: next(sidebar_inputs),
    )
    fake_streamlit = SimpleNamespace(
        sidebar=fake_sidebar,
        markdown=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        error=lambda message: errors.append(str(message)),
    )
    monkeypatch.setattr(web_app, "st", fake_streamlit)

    web_app.main()

    assert calls == []
    assert errors
    assert "allowed runtime roots" in errors[0]


@pytest.mark.parametrize(
    ("page_name", "handler_name"),
    [
        ("Dashboard", "render_dashboard_page"),
        ("Entities", "render_entity_page"),
        ("Network", "render_network_page"),
        ("Evidence", "render_evidence_page"),
    ],
)
def test_main_uses_resolved_sqlite_path_for_all_non_search_pages(monkeypatch, page_name, handler_name):
    calls: list[object] = []
    monkeypatch.setenv("EMAIL_RAG_ALLOWED_RUNTIME_ROOTS", "/tmp")

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "get_retriever", lambda _chroma, _sqlite=None: "retriever")
    monkeypatch.setattr(web_app, handler_name, lambda sqlite_path=None: calls.append(sqlite_path))

    sidebar_inputs = iter(["", "/tmp/archive.db"])
    fake_sidebar = SimpleNamespace(
        radio=lambda *args, **kwargs: page_name,
        text_input=lambda *args, **kwargs: next(sidebar_inputs),
    )
    fake_streamlit = SimpleNamespace(
        sidebar=fake_sidebar,
        markdown=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(web_app, "st", fake_streamlit)

    web_app.main()

    assert calls == [str(validate_runtime_path("/tmp/archive.db", field_name="SQLite path"))]
