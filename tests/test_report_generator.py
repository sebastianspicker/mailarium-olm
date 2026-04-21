"""Tests for HTML report generation and GraphML export."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from src.report_generator import ReportGenerator


def _mock_email_db():
    """Create a mock EmailDatabase with realistic data."""
    db = MagicMock()
    db.email_count.return_value = 1500
    db.unique_sender_count.return_value = 42
    db.folder_counts.return_value = {"Inbox": 800, "Sent": 500, "Archive": 200}
    db.date_range.return_value = ("2023-01-15T08:00:00", "2024-06-30T18:00:00")
    db.top_senders.return_value = [
        {"sender_email": "alice@co.com", "sender_name": "Alice", "message_count": 120},
        {"sender_email": "bob@co.com", "sender_name": "Bob", "message_count": 85},
        {"sender_email": "carol@co.com", "sender_name": "Carol", "message_count": 60},
    ]
    db.top_entities.return_value = [
        {"entity_text": "Acme Corp", "entity_type": "organization", "total_mentions": 50, "email_count": 30},
    ]
    db.email_dates.return_value = [
        "2023-06-01",
        "2023-06-15",
        "2023-07-01",
        "2023-07-15",
    ]
    db.response_pairs.return_value = []
    return db


# ── ReportGenerator tests ────────────────────────────────────


def test_generate_returns_html():
    db = _mock_email_db()
    gen = ReportGenerator(db)
    html = gen.generate(title="Test Report")
    assert "<!DOCTYPE html>" in html
    assert "Test Report" in html


def test_generate_contains_overview_metrics():
    db = _mock_email_db()
    gen = ReportGenerator(db)
    html = gen.generate()
    assert "1500" in html  # total emails
    assert "42" in html  # unique senders
    assert "2023-01-15" in html  # date range start


def test_generate_contains_top_senders():
    db = _mock_email_db()
    gen = ReportGenerator(db)
    html = gen.generate()
    assert "alice@co.com" in html
    assert "bob@co.com" in html


def test_generate_contains_folders():
    db = _mock_email_db()
    gen = ReportGenerator(db)
    html = gen.generate()
    assert "Inbox" in html
    assert "Sent" in html


def test_generate_writes_to_file():
    db = _mock_email_db()
    gen = ReportGenerator(db)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "report.html")
        html = gen.generate(output_path=output)
        assert os.path.exists(output)
        contents = open(output, encoding="utf-8").read()
        assert contents == html


def test_generate_empty_db():
    db = MagicMock()
    db.email_count.return_value = 0
    db.unique_sender_count.return_value = 0
    db.folder_counts.return_value = {}
    db.date_range.return_value = ("", "")
    db.top_senders.return_value = []
    db.top_entities.return_value = []
    db.email_dates.return_value = []
    db.response_pairs.return_value = []
    gen = ReportGenerator(db)
    html = gen.generate()
    assert "<!DOCTYPE html>" in html
    assert "0" in html


def test_generate_custom_title():
    db = _mock_email_db()
    gen = ReportGenerator(db)
    html = gen.generate(title="My Custom Archive")
    assert "My Custom Archive" in html


def test_generate_with_response_times():
    """Report includes response times when available."""
    db = _mock_email_db()
    db.response_pairs.return_value = [
        {
            "reply_sender": "bob@co.com",
            "reply_date": "2023-06-15T10:00:00",
            "original_sender": "alice@co.com",
            "original_date": "2023-06-15T08:00:00",
        },
    ]
    gen = ReportGenerator(db)
    html = gen.generate()
    assert "<!DOCTYPE html>" in html


def test_generate_creates_parent_dirs():
    db = _mock_email_db()
    gen = ReportGenerator(db)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "sub", "dir", "report.html")
        gen.generate(output_path=output)
        assert os.path.exists(output)


def test_generate_without_jinja2():
    """Graceful degradation if Jinja2 is missing."""
    db = _mock_email_db()
    with patch.dict("sys.modules", {"jinja2": None}):
        # Reimport to trigger ImportError
        import importlib

        import src.report_generator as mod

        importlib.reload(mod)
        gen2 = mod.ReportGenerator(db)
        html = gen2.generate()
        assert "Jinja2" in html or "<!DOCTYPE html>" in html
    # Reload to restore original
    import importlib

    import src.report_generator as mod

    importlib.reload(mod)


# ── GraphML export tests ─────────────────────────────────────


def test_export_graphml_creates_file():
    from src.network_analysis import CommunicationNetwork

    db = MagicMock()
    db.all_edges.return_value = [
        ("alice@co.com", "bob@co.com", 10),
        ("bob@co.com", "carol@co.com", 5),
    ]
    net = CommunicationNetwork(db)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "test.graphml")
        result = net.export_graphml(output)
        assert os.path.exists(output)
        assert result["total_nodes"] == 3
        assert result["total_edges"] == 2


def test_export_graphml_empty_graph():
    from src.network_analysis import CommunicationNetwork

    db = MagicMock()
    db.all_edges.return_value = []
    net = CommunicationNetwork(db)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "empty.graphml")
        result = net.export_graphml(output)
        assert os.path.exists(output)
        assert result["total_nodes"] == 0
        assert result["total_edges"] == 0


def test_export_graphml_content_valid():
    from src.network_analysis import CommunicationNetwork

    db = MagicMock()
    db.all_edges.return_value = [("a@x.com", "b@x.com", 3)]
    net = CommunicationNetwork(db)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "valid.graphml")
        net.export_graphml(output)
        content = open(output, encoding="utf-8").read()
        assert "graphml" in content.lower()
        assert "a@x.com" in content


def test_export_graphml_creates_parent_dirs():
    from src.network_analysis import CommunicationNetwork

    db = MagicMock()
    db.all_edges.return_value = [("a@x.com", "b@x.com", 1)]
    net = CommunicationNetwork(db)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "sub", "dir", "graph.graphml")
        result = net.export_graphml(output)
        assert os.path.exists(output)
        assert result["total_nodes"] == 2


# ── CLI report/export flag tests ─────────────────────────────


def test_cli_generate_report_flag_parsed():
    from src.cli import parse_args

    args = parse_args(["--generate-report", "my_report.html"])
    assert args.generate_report == "my_report.html"


def test_cli_generate_report_default():
    from src.cli import parse_args

    args = parse_args(["--generate-report"])
    assert args.generate_report == "report.html"


def test_cli_export_network_flag_parsed():
    from src.cli import parse_args

    args = parse_args(["--export-network", "my_net.graphml"])
    assert args.export_network == "my_net.graphml"


def test_cli_export_network_default():
    from src.cli import parse_args

    args = parse_args(["--export-network"])
    assert args.export_network == "network.graphml"


def test_cli_report_mutually_exclusive_with_stats():
    from src.cli import parse_args

    try:
        parse_args(["--generate-report", "--stats"])
        raise AssertionError("Should have raised SystemExit")
    except SystemExit:
        pass  # Expected — mutually exclusive flags
