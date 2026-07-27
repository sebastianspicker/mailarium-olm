"""Structural seam tests for the R6 web_app refactor."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

import mailarium.web_app as web_app
from mailarium.repo_paths import validate_runtime_path


def _set_main_streamlit(monkeypatch, *, page_name, sqlite_path="", errors=None):
    """Install the minimal Streamlit surface consumed by ``main`` routing tests."""
    sidebar_inputs = iter(["", sqlite_path])
    fake_sidebar = SimpleNamespace(
        radio=lambda *args, **kwargs: page_name,
        text_input=lambda *args, **kwargs: next(sidebar_inputs),
    )
    attributes = {
        "sidebar": fake_sidebar,
        "markdown": lambda *args, **kwargs: None,
        "info": lambda *args, **kwargs: None,
    }
    if errors is not None:
        attributes["error"] = lambda message: errors.append(str(message))
    monkeypatch.setattr(web_app, "st", SimpleNamespace(**attributes))


def _stub_search_route(monkeypatch, calls):
    """Prevent routing tests from entering dependent Streamlit page renderers."""
    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "render_search_page", lambda retriever: calls.append(retriever))
    monkeypatch.setattr(web_app, "get_retriever", lambda _vector_index, _sqlite=None: "retriever")


def test_render_sidebar_delegates_to_impl(monkeypatch):
    calls: list[tuple[object, object]] = []

    def fake_impl(*, st_module, retriever):
        calls.append((st_module, retriever))

    retriever = cast(Any, object())
    monkeypatch.setattr(web_app, "render_sidebar_impl", fake_impl)

    web_app.render_sidebar(retriever)

    assert calls == [(web_app.st, retriever)]


def test_render_dashboard_page_delegates_to_impl(monkeypatch, tmp_path):
    calls: list[tuple[object, object]] = []

    def fake_impl(*, st_module, get_email_db_safe_fn):
        calls.append((st_module, get_email_db_safe_fn))

    monkeypatch.setattr(web_app, "render_dashboard_page_impl", fake_impl)

    web_app.render_dashboard_page(str(tmp_path / "email.db"))

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
    _stub_search_route(monkeypatch, calls)
    _set_main_streamlit(monkeypatch, page_name="Search")

    web_app.main()

    assert calls == ["retriever"]


def test_main_routes_dashboard_with_sqlite_path(monkeypatch, tmp_path):
    calls: list[object] = []
    retriever_calls: list[tuple[object, object]] = []
    monkeypatch.setenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", str(tmp_path))

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "render_dashboard_page", lambda sqlite_path=None: calls.append(sqlite_path))
    monkeypatch.setattr(
        web_app, "get_retriever", lambda vector_index, sqlite=None: retriever_calls.append((vector_index, sqlite)) or "retriever"
    )

    _set_main_streamlit(monkeypatch, page_name="Dashboard", sqlite_path=str(tmp_path / "archive.db"))

    web_app.main()

    assert calls == [str(validate_runtime_path(str(tmp_path / "archive.db"), field_name="SQLite path"))]
    assert retriever_calls == []


def test_main_surfaces_runtime_path_errors_instead_of_crashing(monkeypatch, tmp_path):
    errors: list[str] = []

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "render_search_page", lambda retriever: None)

    def fake_get_retriever(_vector_index, _sqlite=None):
        raise RuntimeError("invalid sqlite path")

    monkeypatch.setattr(web_app, "get_retriever", fake_get_retriever)

    _set_main_streamlit(monkeypatch, page_name="Search", sqlite_path=str(tmp_path / "bad-path"), errors=errors)

    web_app.main()

    assert errors
    assert "runtime paths" in errors[0].lower()


def test_main_rejects_web_runtime_paths_outside_allowed_roots(monkeypatch):
    errors: list[str] = []
    calls: list[object] = []
    _stub_search_route(monkeypatch, calls)
    _set_main_streamlit(monkeypatch, page_name="Search", sqlite_path="/etc/archive.db", errors=errors)

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
def test_main_uses_resolved_sqlite_path_for_all_non_search_pages(monkeypatch, tmp_path, page_name, handler_name):
    calls: list[object] = []
    monkeypatch.setenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", str(tmp_path))

    monkeypatch.setattr(web_app, "inject_styles", lambda: None)
    monkeypatch.setattr(web_app, "render_sidebar", lambda retriever: None)
    monkeypatch.setattr(web_app, "get_retriever", lambda _vector_index, _sqlite=None: "retriever")
    monkeypatch.setattr(web_app, handler_name, lambda sqlite_path=None: calls.append(sqlite_path))

    _set_main_streamlit(monkeypatch, page_name=page_name, sqlite_path=str(tmp_path / "archive.db"))

    web_app.main()

    assert calls == [str(validate_runtime_path(str(tmp_path / "archive.db"), field_name="SQLite path"))]
