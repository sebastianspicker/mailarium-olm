"""Real-archive checks for source-linked web capture and evidence report export."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mailarium.archive import ArchiveDatabase

_SOURCE_UID = "synthetic-web-source"
_QUOTE = "The launch moved because the review was delayed."
_BODY = f"Hello team,\n\n{_QUOTE}\n\nA final source paragraph."
_SUMMARY = "Included decision. <script>synthetic()</script>"
_APP = """
import streamlit as st
from mailarium.interfaces.web.evidence import render_evidence_page
from mailarium.interfaces.web.export import render_evidence_export_page
if st.session_state.web_route == "Export":
    render_evidence_export_page(database=st.session_state.database)
else:
    render_evidence_page(database=st.session_state.database)
"""


@pytest.fixture
def evidence_archive(tmp_path: Path) -> Iterator[ArchiveDatabase]:
    """Create a temporary archive containing synthetic correspondence only."""
    database = ArchiveDatabase(str(tmp_path / "archive.sqlite"))
    database.conn.execute(
        "INSERT INTO emails (uid, subject, sender_name, sender_email, date, body_text, folder) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_SOURCE_UID, "Synthetic launch decision", "Test Sender", "sender@example.test", "2026-09-09", _BODY, "Synthetic"),
    )
    database.conn.commit()
    yield database
    database.close()


@pytest.fixture
def allowed_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Restrict test writes to a dedicated temporary directory."""
    directory = (tmp_path / "exports").resolve()
    directory.mkdir()
    monkeypatch.setenv("MAILARIUM_ALLOWED_OUTPUT_ROOTS", str(directory))
    return directory


def _app(database: ArchiveDatabase, *, route: str = "Evidence") -> AppTest:
    """Mount the owned UI flow with a caller-owned archive connection."""
    app = AppTest.from_string(_APP)
    app.session_state["database"] = database
    app.session_state["web_capture_uid"] = _SOURCE_UID
    app.session_state["web_route"] = route
    app.run()
    assert not app.exception
    return app


def _fill_capture(
    app: AppTest, *, quote: str = _QUOTE, category: str = "decision", summary: str = "A recorded decision."
) -> None:
    """Enter the required evidence fields through the native controls."""
    next(element for element in app.text_area if element.label == "Exact quote").input(quote)
    next(element for element in app.text_input if element.label == "Category").input(category)
    next(element for element in app.text_area if element.label == "Why this matters").input(summary)


def _seed_evidence(database: ArchiveDatabase) -> int:
    """Provide two relevance levels and categories for real export filtering."""
    included = database.evidence.add_evidence(_SOURCE_UID, "decision", _QUOTE, _SUMMARY, 4)
    database.evidence.add_evidence(_SOURCE_UID, "background", "Hello team,", "Excluded background.", 1)
    return included["id"]


def _configure_export(app: AppTest, fmt: str) -> None:
    """Select a report format and meaningful evidence filters."""
    app.selectbox(key="evidence-export-category").set_value("decision")
    app.selectbox(key="evidence-export-relevance").set_value(4)
    app.selectbox(key="evidence-export-format").set_value(fmt).run()
    assert not app.exception


@pytest.mark.parametrize("missing", ["quote", "category", "summary"])
def test_capture_requires_quote_category_and_summary(evidence_archive: ArchiveDatabase, missing: str) -> None:
    """Incomplete evidence must not create a record or custody event."""
    app = _app(evidence_archive)
    values = {"quote": _QUOTE, "category": "decision", "summary": "A recorded decision."}
    values[missing] = " "
    _fill_capture(app, **values)
    app.button(key="capture-save").click().run()
    assert not app.exception
    assert app.error
    assert evidence_archive.evidence.evidence_stats()["total"] == 0
    assert not evidence_archive.custody.get_custody_chain(action="evidence_add")


@pytest.mark.parametrize("quote, verified", [(_QUOTE, 1), (_QUOTE.upper(), 1), ("A quotation absent from the source.", 0)])
def test_capture_uses_canonical_matching_and_saves_once(evidence_archive: ArchiveDatabase, quote: str, verified: int) -> None:
    """Exact and unmatched submissions retain repository semantics and one custody event."""
    app = _app(evidence_archive)
    _fill_capture(app, quote=quote)
    app.button(key="capture-save").click().run()
    assert not app.exception
    item = app.session_state["web_capture_saved"]["item"]
    stored = evidence_archive.evidence.get_evidence(item["id"])
    assert stored is not None
    assert stored["key_quote"] == quote
    assert stored["verified"] == verified
    assert stored["email_uid"] == _SOURCE_UID
    if not verified:
        assert any("saved as unverified" in warning.value for warning in app.warning)
    app.run()
    assert not app.exception
    assert evidence_archive.evidence.evidence_stats()["total"] == 1
    assert len(evidence_archive.custody.get_custody_chain(action="evidence_add", target_id=str(item["id"]))) == 1
    app.button(key="capture-export").click().run()
    assert app.session_state["web_route"] == "Export"
    assert not app.exception


@pytest.mark.parametrize("fmt", ["html", "csv"])
def test_browser_export_filters_actual_findings_and_retains_download(evidence_archive: ArchiveDatabase, fmt: str) -> None:
    """Preview, report content and retained receipt use evidence filters independently of search."""
    included_id = _seed_evidence(evidence_archive)
    app = _app(evidence_archive, route="Export")
    app.session_state["web_filters"] = {"folder": "An unrelated search folder"}
    _configure_export(app, fmt)
    preview = app.dataframe[0].value
    assert preview["Finding"].tolist() == [included_id]
    assert preview["Subject"].tolist() == ["Synthetic launch decision"]
    assert preview["Category"].tolist() == ["decision"]
    assert preview["Relevance"].tolist() == [4]
    next(button for button in app.button if button.label == "Prepare download").click().run()
    assert not app.exception
    report = app.session_state["web_evidence_export"]
    assert report["format"] == fmt and report["item_count"] == 1
    assert not report["local"] and not report.get("output_path")
    assert [item["id"] for item in report["items"]] == [included_id]
    if fmt == "html":
        assert "A final source paragraph." in report["html"]
        assert "Included decision." in report["html"]
        assert "&lt;script&gt;synthetic()&lt;/script&gt;" in report["html"]
        assert "<script>synthetic()</script>" not in report["html"]
        assert "Excluded background." not in report["html"]
    else:
        rows = list(csv.DictReader(io.StringIO(report["csv"])))
        assert len(rows) == 1
        assert rows[0]["email_uid"] == _SOURCE_UID
        assert rows[0]["key_quote"] == _QUOTE
        assert rows[0]["summary"] == _SUMMARY
    app.run()
    assert not app.exception
    assert app.session_state["web_evidence_export"][fmt] == report[fmt]
    assert len(app.get("download_button")) == 1


@pytest.mark.parametrize("fmt", ["html", "csv"])
def test_explicit_local_export_writes_real_artifact(evidence_archive: ArchiveDatabase, allowed_exports: Path, fmt: str) -> None:
    """Local success names the actual file and leaves it stable on rerun."""
    _seed_evidence(evidence_archive)
    app = _app(evidence_archive, route="Export")
    _configure_export(app, fmt)
    output = allowed_exports / f"report.{fmt}"
    app.checkbox(key="evidence-export-local").check().run()
    app.text_input(key="evidence-export-path").input(str(output))
    next(button for button in app.button if button.label == "Save report locally").click().run()
    assert not app.exception
    assert not app.error
    report = app.session_state["web_evidence_export"]
    assert report["local"] and report["format"] == fmt and report["item_count"] == 1
    assert Path(report["output_path"]) == output
    content = output.read_text()
    assert _QUOTE in content
    assert "Excluded background." not in content
    if fmt == "html":
        assert "A final source paragraph." in content
    else:
        assert len(list(csv.DictReader(io.StringIO(content)))) == 1
    app.run()
    assert not app.exception
    assert output.read_text() == content


@pytest.mark.parametrize("fmt", ["html", "csv"])
@pytest.mark.parametrize("failure", ["existing", "outside-root"])
def test_local_export_rejects_overwrite_and_unallowed_destination(
    evidence_archive: ArchiveDatabase, allowed_exports: Path, tmp_path: Path, fmt: str, failure: str
) -> None:
    """Rejected destination checks neither write data nor claim export success."""
    _seed_evidence(evidence_archive)
    output = allowed_exports / f"existing.{fmt}" if failure == "existing" else tmp_path / f"outside.{fmt}"
    if failure == "existing":
        output.write_text("Preserve this existing file.")
    app = _app(evidence_archive, route="Export")
    _configure_export(app, fmt)
    app.checkbox(key="evidence-export-local").check().run()
    app.text_input(key="evidence-export-path").input(str(output))
    next(button for button in app.button if button.label == "Save report locally").click().run()
    assert not app.exception
    assert app.error
    assert "web_evidence_export" not in app.session_state
    if failure == "existing":
        assert output.read_text() == "Preserve this existing file."
    else:
        assert not output.exists()


def test_export_preview_keeps_larger_matching_selection_reviewable(evidence_archive: ArchiveDatabase) -> None:
    """Findings beyond the initial twenty remain available for scope review."""
    identifiers = {
        evidence_archive.evidence.add_evidence(_SOURCE_UID, "decision", _QUOTE, f"Synthetic finding {index}.", 4)["id"]
        for index in range(21)
    }
    app = _app(evidence_archive, route="Export")
    assert not app.exception
    assert len(app.dataframe) == 2
    first_page = app.dataframe[0].value["Finding"].tolist()
    remainder = app.dataframe[1].value["Finding"].tolist()
    assert len(first_page) == 20 and len(remainder) == 1
    assert set(first_page + remainder) == identifiers


def test_missing_capture_source_cannot_create_evidence(evidence_archive: ArchiveDatabase) -> None:
    """A stale capture UID provides navigation instead of a writable form."""
    app = _app(evidence_archive)
    app.session_state["web_capture_uid"] = "absent-synthetic-source"
    app.run()
    assert not app.exception
    assert app.warning
    assert not any(button.key == "capture-save" for button in app.button)
    assert evidence_archive.evidence.evidence_stats()["total"] == 0
