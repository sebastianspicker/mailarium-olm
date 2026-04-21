"""Integration tests for CLI analytics commands and dispatch logic."""

from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from src.cli import (
    _run_entities,
    _run_export_network,
    _run_generate_report,
    _run_heatmap,
    _run_response_times,
    _run_suggest,
    _run_top_contacts,
    _run_volume,
    parse_args,
)

# ── Fixtures ─────────────────────────────────────────────────────────


class _FakeDB:
    """Minimal EmailDatabase stand-in for CLI analytics tests."""

    def top_contacts(self, email: str, limit: int = 20) -> list[dict]:
        return [
            {"partner": "bob@example.com", "total": 42},
            {"partner": "carol@example.com", "total": 10},
        ]

    def top_entities(self, entity_type: str | None = None, limit: int = 30) -> list[dict]:
        return [
            {"entity_text": "Acme Corp", "entity_type": "organization", "total_mentions": 15},
        ]

    def top_keywords(self, limit: int = 200) -> list[dict]:
        return [{"keyword": "invoice", "count": 5}]


class _FakeTemporalAnalyzer:
    """Minimal stand-in for TemporalAnalyzer."""

    def __init__(self, db):
        pass

    def volume_over_time(self, period: str = "day") -> list[dict]:
        return [{"period": "2024-01-01", "count": 10}]

    def activity_heatmap(self) -> list[dict]:
        return [{"hour": 9, "day_of_week": 1, "count": 5}]

    def response_times(self, limit: int = 20) -> list[dict]:
        return [{"replier": "alice@example.com", "avg_response_hours": 2.5, "response_count": 10}]


def _capture_stdout(func, *args, **kwargs) -> str:
    """Capture stdout from a function call."""
    old_stdout = sys.stdout
    sys.stdout = buffer = StringIO()
    try:
        func(*args, **kwargs)
    finally:
        sys.stdout = old_stdout
    return buffer.getvalue()


# ── _run_top_contacts ────────────────────────────────────────────────


def test_run_top_contacts_prints_partners():
    db = _FakeDB()
    output = _capture_stdout(_run_top_contacts, db, "alice@example.com")
    assert "bob@example.com" in output
    assert "carol@example.com" in output
    assert "42" in output


def test_run_top_contacts_no_contacts():
    db = MagicMock()
    db.top_contacts.return_value = []
    output = _capture_stdout(_run_top_contacts, db, "nobody@example.com")
    assert "No contacts found" in output


# ── _run_volume ──────────────────────────────────────────────────────


def test_run_volume_prints_bars():
    db = _FakeDB()
    with patch("src.cli.TemporalAnalyzer", _FakeTemporalAnalyzer, create=True), patch.dict("sys.modules", {}):
        # We need to patch the import inside _run_volume
        import src.cli as cli_mod

        original = cli_mod.__dict__.get("TemporalAnalyzer")
        try:
            # Patch the lazy import
            with patch(
                "src.temporal_analysis.TemporalAnalyzer",
                _FakeTemporalAnalyzer,
            ):
                output = _capture_stdout(_run_volume, db, "day")
                assert "2024-01-01" in output
                assert "10" in output
        finally:
            if original:
                cli_mod.__dict__["TemporalAnalyzer"] = original


# ── _run_entities ────────────────────────────────────────────────────


def test_run_entities_prints_entities():
    db = _FakeDB()
    output = _capture_stdout(_run_entities, db, None)
    assert "Acme Corp" in output
    assert "organization" in output
    assert "15" in output


def test_run_entities_no_results():
    db = MagicMock()
    db.top_entities.return_value = []
    output = _capture_stdout(_run_entities, db, "phone")
    assert "No entities found" in output


# ── _run_heatmap ─────────────────────────────────────────────────────


def test_run_heatmap_prints_grid():
    db = _FakeDB()
    with patch("src.temporal_analysis.TemporalAnalyzer", _FakeTemporalAnalyzer):
        output = _capture_stdout(_run_heatmap, db)
        # Works with both rich (Panel title "Activity Heatmap") and plain text
        assert "heatmap" in output.lower() or "Heatmap" in output
        assert "Mon" in output


# ── _run_response_times ──────────────────────────────────────────────


def test_run_response_times_prints_times():
    db = _FakeDB()
    with patch("src.temporal_analysis.TemporalAnalyzer", _FakeTemporalAnalyzer):
        output = _capture_stdout(_run_response_times, db)
        assert "alice@example.com" in output
        assert "2.5" in output


# ── _run_suggest ─────────────────────────────────────────────────────


def test_run_suggest_prints_suggestions():
    fake_db = _FakeDB()
    fake_suggester = MagicMock()
    fake_suggester.suggest_flat.return_value = ["recent invoices", "security review"]

    with patch("src.cli_commands._get_email_db", return_value=fake_db):
        with patch("src.query_suggestions.QuerySuggester", return_value=fake_suggester):
            output = _capture_stdout(_run_suggest)
            assert "recent invoices" in output
            assert "security review" in output


def test_run_suggest_no_suggestions():
    fake_db = _FakeDB()
    fake_suggester = MagicMock()
    fake_suggester.suggest_flat.return_value = []

    with patch("src.cli_commands._get_email_db", return_value=fake_db):
        with patch("src.query_suggestions.QuerySuggester", return_value=fake_suggester):
            output = _capture_stdout(_run_suggest)
            assert "No suggestions available" in output


# ── _run_generate_report ─────────────────────────────────────────────


def test_run_generate_report_calls_generator():
    fake_db = _FakeDB()
    mock_generator = MagicMock()

    with patch("src.cli_commands._get_email_db", return_value=fake_db):
        with patch("src.report_generator.ReportGenerator", return_value=mock_generator):
            output = _capture_stdout(_run_generate_report, "report.html")
            assert "report.html" in output
            mock_generator.generate.assert_called_once_with(output_path="report.html")


# ── _run_export_network ──────────────────────────────────────────────


def test_run_export_network_success():
    fake_db = _FakeDB()
    mock_network = MagicMock()
    mock_network.export_graphml.return_value = {
        "output_path": "network.graphml",
        "total_nodes": 10,
        "total_edges": 25,
    }

    with patch("src.cli_commands._get_email_db", return_value=fake_db):
        with patch("src.network_analysis.CommunicationNetwork", return_value=mock_network):
            output = _capture_stdout(_run_export_network, "network.graphml")
            assert "network.graphml" in output
            assert "Nodes: 10" in output
            assert "Edges: 25" in output


def test_run_export_network_error():
    fake_db = _FakeDB()
    mock_network = MagicMock()
    mock_network.export_graphml.return_value = {"error": "No data"}

    with patch("src.cli_commands._get_email_db", return_value=fake_db):
        with patch("src.network_analysis.CommunicationNetwork", return_value=mock_network):
            with pytest.raises(SystemExit) as exc_info:
                _run_export_network("network.graphml")
            assert exc_info.value.code == 1


# ── parse_args validation ────────────────────────────────────────────


def test_parse_args_suggest_flag():
    args = parse_args(["--suggest"])
    assert args.suggest is True


def test_parse_args_top_contacts_flag():
    args = parse_args(["--top-contacts", "alice@example.com"])
    assert args.top_contacts == "alice@example.com"


def test_parse_args_volume_flag():
    args = parse_args(["--volume", "week"])
    assert args.volume == "week"


def test_parse_args_entities_flag():
    args = parse_args(["--entities"])
    assert args.entities == "all"


def test_parse_args_entities_with_type():
    args = parse_args(["--entities", "organization"])
    assert args.entities == "organization"


def test_parse_args_heatmap_flag():
    args = parse_args(["--heatmap"])
    assert args.heatmap is True


def test_parse_args_response_times_flag():
    args = parse_args(["--response-times"])
    assert args.response_times is True


def test_parse_args_generate_report_default():
    args = parse_args(["--generate-report"])
    assert args.generate_report == "report.html"


def test_parse_args_generate_report_custom():
    args = parse_args(["--generate-report", "custom.html"])
    assert args.generate_report == "custom.html"


def test_parse_args_export_network_default():
    args = parse_args(["--export-network"])
    assert args.export_network == "network.graphml"


def test_parse_args_mutually_exclusive_operational():
    """Operational flags are mutually exclusive."""
    with pytest.raises(SystemExit):
        parse_args(["--stats", "--suggest"])
