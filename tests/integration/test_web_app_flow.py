"""Integration checks for Streamlit runtime composition and app-body smoke coverage."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import mailarium.web_app as web_app

ROOT = Path(__file__).resolve().parents[2]
STREAMLIT_SMOKE_PATH = ROOT / "scripts" / "smoke" / "streamlit.py"


@pytest.fixture
def isolated_runtime_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep the rendered app's default runtime data outside the checkout."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    monkeypatch.delenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", raising=False)
    return runtime_home


@pytest.fixture
def broken_streamlit_app(tmp_path: Path) -> Path:
    """Provide an app-body failure that AppTest must surface rather than mask."""
    app = tmp_path / "broken_streamlit_app.py"
    app.write_text(
        "import streamlit as st\nst.markdown('fixture started')\nraise RuntimeError('deliberate Streamlit fixture failure')\n",
        encoding="utf-8",
    )
    return app


def _streamlit_smoke_module():
    """Load the executable smoke helper without turning scripts into a package."""
    spec = importlib.util.spec_from_file_location("streamlit_smoke", STREAMLIT_SMOKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_app_body_renders_search_screen_without_app_exception(isolated_runtime_home: Path) -> None:
    """The public Streamlit entrypoint renders a stable initial screen through AppTest."""
    app = AppTest.from_file(str(ROOT / "mailarium" / "web_app.py"), default_timeout=45)
    app.run(timeout=45)

    assert not app.exception
    assert any("Search the archive" in str(element.value) for element in app.markdown)
    assert app.radio[0].value == "Search"


def test_streamlit_smoke_rejects_deliberately_broken_app(broken_streamlit_app: Path) -> None:
    """A broken app body is a smoke failure, not a successful startup banner."""
    smoke = _streamlit_smoke_module()

    with pytest.raises(RuntimeError, match="deliberate Streamlit fixture failure"):
        smoke.run_app_test(broken_streamlit_app)


def test_streamlit_smoke_anchors_the_source_package_root(isolated_runtime_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The direct smoke script resolves the source package even without the checkout on sys.path."""
    smoke = _streamlit_smoke_module()
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if Path(entry or ".").resolve() != ROOT])

    with smoke._app_import_context(ROOT / "mailarium" / "web_app.py"):
        import mailarium

        assert Path(mailarium.__file__).resolve().is_relative_to(ROOT)

    smoke.run_app_test(ROOT / "mailarium" / "web_app.py")


def test_runtime_cache_is_the_single_closable_streamlit_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalidation closes every cached runtime before Streamlit drops its resource cache."""
    created = []

    class RuntimeDouble:
        def __init__(self, *, vector_index_path: str | None, sqlite_path: str | None) -> None:
            self.vector_index_path = vector_index_path
            self.sqlite_path = sqlite_path
            self.closed = False
            created.append(self)

        def close(self) -> None:
            self.closed = True

    web_app.invalidate_runtime_cache()
    monkeypatch.setattr(web_app, "ApplicationRuntime", RuntimeDouble)
    try:
        first = web_app.get_runtime("vectors", "archive.db")
        second = web_app.get_runtime("vectors", "archive.db")

        assert first is second
        assert created == [first]

        web_app.invalidate_runtime_cache()

        assert first.closed is True
    finally:
        web_app.invalidate_runtime_cache()
