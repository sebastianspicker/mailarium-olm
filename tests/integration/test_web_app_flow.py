"""Integration checks for Streamlit runtime composition and app-body smoke coverage."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import mailarium.interfaces.web.app as web_app
from mailarium.interfaces.web.styles import build_style_css
from mailarium.model.message import Message
from mailarium.platform.settings import clear_settings_cache
from mailarium.retrieval.multi_vector_embedder import MultiVectorEmbedder

ROOT = Path(__file__).resolve().parents[2]
STREAMLIT_SMOKE_PATH = ROOT / "scripts" / "smoke" / "streamlit.py"


@pytest.fixture
def isolated_runtime_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Keep the rendered app's default runtime data outside the checkout."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    monkeypatch.delenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", raising=False)
    monkeypatch.setenv("VECTOR_INDEX_PATH", str(runtime_home / "vectors"))
    monkeypatch.setenv("SQLITE_PATH", str(runtime_home / "archive.db"))
    monkeypatch.setenv("RUNTIME_PROFILE", "offline-test")
    clear_settings_cache()
    web_app.invalidate_runtime_cache()
    yield runtime_home
    web_app.invalidate_runtime_cache()
    clear_settings_cache()


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
    assert any("What are you trying to establish?" in str(element.value) for element in app.markdown)
    assert any("Mailarium" in str(element.value) for element in app.markdown)
    assert app.radio[0].value == "Search"


def test_refined_styles_keep_accessible_theme_and_mobile_contracts() -> None:
    """The rendered design exposes both lights, three type voices, and source-first mobile review."""
    day_css = build_style_css("day")
    night_css = build_style_css("night")

    assert "--paper:#f5f2ea" in day_css
    assert "--paper:#141311" in night_css
    assert all(voice in day_css for voice in ("--font-text", "--font-ui", "--font-mono"))
    assert "https://" not in day_css and "@import" not in day_css
    assert "@media (prefers-reduced-motion:reduce)" in day_css
    assert "@media (max-width:860px)" in day_css
    assert "mailarium-results-marker) { display:none" not in day_css


def test_web_app_theme_toggle_rerenders_the_light_theme(isolated_runtime_home: Path) -> None:
    """The selected light is stored in Streamlit state and changes the generated token set."""
    app = AppTest.from_file(str(ROOT / "mailarium" / "web_app.py"), default_timeout=45)
    app.run(timeout=45)

    assert app.button(key="web-theme-toggle").label == "Use light theme"
    app.button(key="web-theme-toggle").click().run(timeout=45)

    assert app.button(key="web-theme-toggle").label == "Use dark theme"
    assert "--paper:#f5f2ea" in str(app.markdown[0].value)


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


def test_search_source_handoff_and_archive_switch(isolated_runtime_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real indexed search keeps the full source and clears drafts when archives change."""
    monkeypatch.setattr(MultiVectorEmbedder, "encode_dense", lambda self, texts: [[1.0, 0.0] for _text in texts])
    vector_path = str(isolated_runtime_home / "vectors")
    sqlite_path = str(isolated_runtime_home / "archive.db")
    runtime = web_app.get_runtime(vector_path, sqlite_path)
    database = runtime.open_archive_database()
    body = "The security review ends on 28 May.\n\nThis final paragraph is absent from the retrieval chunk."
    message = Message(
        message_id="web-flow@example.test",
        subject="Synthetic launch decision",
        sender_name="Test Sender",
        sender_email="sender@example.test",
        to=["reader@example.test"],
        cc=[],
        bcc=[],
        date="2026-05-14",
        body_text=body,
        body_html="",
        folder="Synthetic",
        has_attachments=False,
        conversation_id="synthetic-thread",
    )
    database.messages.insert_email(message)
    runtime.search_engine.collection.add(
        ids=[message.uid + "__chunk_0"],
        embeddings=[[1.0, 0.0]],
        documents=["The security review ends on 28 May."],
        metadatas=[
            {
                "uid": message.uid,
                "subject": message.subject,
                "folder": "Synthetic",
                "date": message.date,
                "conversation_id": "synthetic-thread",
            }
        ],
    )
    web_app.invalidate_runtime_cache()
    app = AppTest.from_file(str(ROOT / "mailarium" / "web_app.py"), default_timeout=45)
    app.session_state["web_vector_path"] = vector_path
    app.session_state["web_sqlite_path"] = sqlite_path
    app.run()
    assert not app.exception, app.exception
    assert any(item.label == "Question or phrase" for item in app.text_input), [
        str(item.value) for item in list(app.error) + list(app.warning)
    ]
    next(item for item in app.text_input if item.label == "Question or phrase").input("Why did the launch move?")
    next(item for item in app.text_input if item.label == "Folder contains").input("Synthetic")
    next(item for item in app.button if item.label == "Search archive").click().run()
    assert not app.exception
    assert app.radio(key="web_navigation").value == "Inspect"
    assert any("This final paragraph is absent from the retrieval chunk." in str(item.value) for item in app.markdown)
    next(item for item in app.button if item.label == "View full thread").click().run()
    assert any("Conversation thread" in str(item.value) for item in app.markdown)
    next(item for item in app.button if item.label == "Close thread view").click().run()
    next(item for item in app.button if item.label == "Capture finding").click().run()
    assert not app.exception
    assert app.session_state["web_capture_uid"] == message.uid
    next(item for item in app.text_area if item.label == "Exact quote").input("Unsaved source draft").run()
    app.radio(key="web_navigation").set_value("Inspect").run()
    assert next(item for item in app.text_input if item.label == "Question or phrase").value == "Why did the launch move?"
    assert next(item for item in app.text_input if item.label == "Folder contains").value == "Synthetic"
    app.text_input(key="web_sqlite_path").input(str(isolated_runtime_home / "another.db")).run()
    assert not app.exception
    assert app.radio(key="web_navigation").value == "Search"
    state = app.session_state.filtered_state
    assert "web_capture_uid" not in state
    assert not state.get("web_results")
    assert not any(key.startswith(("quote-", "capture-draft-")) for key in state)


@pytest.mark.parametrize("destination", ["Overview", "People", "Connections", "Mailbox"])
def test_archive_utilities_remain_reachable(isolated_runtime_home: Path, destination: str) -> None:
    """The new task navigation retains the existing analytical and mailbox surfaces."""
    app = AppTest.from_file(str(ROOT / "mailarium" / "web_app.py"), default_timeout=45).run()
    app.button(key=f"web-tool-{destination}").click().run()
    assert not app.exception
    assert app.session_state["web_route"] == destination
    assert app.radio(key="web_navigation").value is None
