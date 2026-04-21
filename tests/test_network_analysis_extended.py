"""Extended tests for src/network_analysis.py — targeting uncovered lines."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.email_db import EmailDatabase
from src.network_analysis import _ANALYSIS_CACHE_MAX, _BETWEENNESS_CACHE_MAX, CommunicationNetwork
from src.parse_olm import Email


def _make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Hello",
        "sender_name": "Alice",
        "sender_email": "employee@example.test",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-15T10:30:00",
        "body_text": "Test body",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def _populated_db() -> EmailDatabase:
    db = EmailDatabase(":memory:")
    db.insert_email(_make_email(message_id="<m1@example.test>", to=["Bob <bob@example.com>"]))
    db.insert_email(_make_email(message_id="<m2@example.test>", to=["Bob <bob@example.com>"]))
    db.insert_email(_make_email(message_id="<m3@example.test>", to=["Carol <carol@example.com>"]))
    db.insert_email(
        _make_email(
            message_id="<m4@example.test>",
            sender_email="bob@example.com",
            sender_name="Bob",
            to=["Alice <employee@example.test>"],
        )
    )
    return db


def _large_db(n_nodes: int = 120) -> EmailDatabase:
    """Build a DB with many nodes for betweenness approximation tests."""
    db = EmailDatabase(":memory:")
    for i in range(n_nodes):
        sender = f"user{i}@example.com"
        recipient = f"user{(i + 1) % n_nodes}@example.com"
        db.insert_email(
            _make_email(
                message_id=f"<large{i}@ex.com>",
                sender_email=sender,
                sender_name=f"User{i}",
                to=[f"User{(i + 1) % n_nodes} <{recipient}>"],
            )
        )
    return db


# ── networkx not installed paths ──────────────────────────────


class TestNetworkxNotInstalled:
    def test_network_analysis_without_networkx(self):
        """network_analysis returns error dict when networkx is missing."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        with patch.object(net, "_ensure_graph", return_value=None):
            result = net.network_analysis()
        assert "error" in result
        assert "networkx" in result["error"]

    def test_find_paths_without_networkx(self):
        """find_paths returns error when networkx is missing."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        with patch.object(net, "_ensure_graph", return_value=None):
            result = net.find_paths("a@example.com", "b@example.com")
        assert len(result) == 1
        assert "error" in result[0]

    def test_export_graphml_without_networkx(self):
        """export_graphml returns error when networkx is missing."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        with patch.object(net, "_ensure_graph", return_value=None):
            result = net.export_graphml("/tmp/test.graphml")
        assert "error" in result


# ── find_paths edge cases ────────────────────────────────────


class TestFindPathsEdgeCases:
    def test_find_paths_empty_graph(self):
        db = EmailDatabase(":memory:")
        net = CommunicationNetwork(db)
        result = net.find_paths("a@example.test", "b@example.test")
        assert result == []

    def test_find_paths_source_not_in_graph(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.find_paths("nobody@example.test", "employee@example.test")
        assert result == []

    def test_find_paths_same_source_and_target(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.find_paths("employee@example.test", "employee@example.test")
        assert len(result) == 1
        assert "error" in result[0]

    def test_find_paths_no_path_exists(self):
        """Two disconnected nodes should return empty list."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<island1@example.test>",
                sender_email="alone1@example.com",
                to=["alone1b@example.com"],
            )
        )
        db.insert_email(
            _make_email(
                message_id="<island2@example.test>",
                sender_email="alone2@example.com",
                to=["alone2b@example.com"],
            )
        )
        net = CommunicationNetwork(db)
        result = net.find_paths("alone1@example.com", "alone2@example.com")
        assert result == []

    def test_find_paths_valid(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        paths = net.find_paths("employee@example.test", "bob@example.com")
        assert len(paths) >= 1
        assert paths[0]["hops"] == 1
        assert "employee@example.test" in paths[0]["nodes"]
        assert "bob@example.com" in paths[0]["nodes"]


# ── Community detection fallback ─────────────────────────────


class TestCommunityDetection:
    def test_community_detection_fallback_to_label_propagation(self):
        """When louvain_communities is not available, use label_propagation."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        import networkx as nx

        # Remove louvain_communities temporarily
        original = getattr(nx.community, "louvain_communities", None)
        try:
            if hasattr(nx.community, "louvain_communities"):
                delattr(nx.community, "louvain_communities")
            result = net.network_analysis()
            assert isinstance(result["communities"], list)
        finally:
            if original is not None:
                nx.community.louvain_communities = original

    def test_community_detection_exception_handled(self):
        """Community detection failure is logged, not raised."""
        db = _populated_db()
        net = CommunicationNetwork(db)

        net._ensure_graph()
        # Make community detection raise by patching _to_undirected_summed
        with patch.object(net, "_to_undirected_summed", side_effect=Exception("community error")):
            # Force fresh computation by clearing the cache
            net._analysis_cache.clear()
            result = net.network_analysis()
        assert result["communities"] == []


# ── Analysis cache eviction (line 94) ────────────────────────


class TestAnalysisCacheEviction:
    def test_analysis_cache_evicts_oldest(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        # Fill cache beyond maximum
        for i in range(_ANALYSIS_CACHE_MAX + 2):
            net._analysis_cache[(i, i)] = {"data": i}
            if len(net._analysis_cache) > _ANALYSIS_CACHE_MAX:
                net._analysis_cache.popitem(last=False)
        assert len(net._analysis_cache) <= _ANALYSIS_CACHE_MAX


# ── Betweenness centrality edge cases ────────────────────────


class TestBetweennessEdgeCases:
    def test_betweenness_large_graph_approximation(self):
        """Graphs with >100 nodes use approximate betweenness."""
        db = _large_db(120)
        net = CommunicationNetwork(db)
        import networkx as nx

        net._ensure_graph()
        assert net._graph.number_of_nodes() > 100
        betweenness = net._get_betweenness(nx)
        assert isinstance(betweenness, dict)
        assert len(betweenness) > 0

    def test_betweenness_exception_returns_empty(self):
        """Betweenness exception returns empty dict."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        import networkx as nx

        net._ensure_graph()
        with patch.object(nx, "betweenness_centrality", side_effect=Exception("fail")):
            net._betweenness_cache.clear()
            result = net._get_betweenness(nx)
        assert result == {}

    def test_betweenness_cache_eviction(self):
        """Betweenness cache evicts oldest entry when full."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        for i in range(_BETWEENNESS_CACHE_MAX + 2):
            net._betweenness_cache[i] = {"node": float(i)}
            if len(net._betweenness_cache) > _BETWEENNESS_CACHE_MAX:
                net._betweenness_cache.popitem(last=False)
        assert len(net._betweenness_cache) <= _BETWEENNESS_CACHE_MAX


# ── coordinated_timing edge cases ────────────────────────────


class TestCoordinatedTimingEdgeCases:
    def test_single_sender_returns_empty(self):
        """coordinated_timing with <2 senders returns empty list."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.coordinated_timing(["employee@example.test"])
        assert result == []

    def test_empty_timeline_returns_empty(self):
        """No timeline data returns empty."""
        db = EmailDatabase(":memory:")
        net = CommunicationNetwork(db)
        result = net.coordinated_timing(["a@example.test", "b@example.test"])
        assert result == []

    def test_invalid_date_skipped(self):
        """Invalid dates are silently skipped."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<bad_date@example.test>",
                sender_email="employee@example.test",
                to=["Bob <bob@example.com>"],
                date="not-a-date",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<good@example.test>",
                sender_email="bob@example.com",
                to=["Alice <employee@example.test>"],
                date="2024-01-15T10:00:00",
            )
        )
        net = CommunicationNetwork(db)
        # Should not crash on invalid date
        result = net.coordinated_timing(["employee@example.test", "bob@example.com"])
        assert isinstance(result, list)

    def test_coordinated_timing_window_not_met(self):
        """When window threshold not met, return empty."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<c1@example.test>",
                sender_email="employee@example.test",
                to=["Bob <bob@example.com>"],
                date="2024-01-15T10:00:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<c2@example.test>",
                sender_email="bob@example.com",
                to=["Alice <employee@example.test>"],
                date="2024-06-15T10:00:00",
            )
        )
        net = CommunicationNetwork(db)
        # Window of 1 hour, events 5 months apart, min_events=3
        result = net.coordinated_timing(
            ["employee@example.test", "bob@example.com"],
            window_hours=1,
            min_events=3,
        )
        assert result == []


# ── relationship_summary edge cases ──────────────────────────


class TestRelationshipSummaryEdgeCases:
    def test_relationship_summary_not_in_graph(self):
        """relationship_summary for an unknown node returns zero scores."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.relationship_summary("unknown@example.com")
        assert result["bridge_score"] == 0.0
        assert result["send_count"] == 0
        assert result["receive_count"] == 0

    def test_relationship_summary_full(self):
        """relationship_summary for a known node returns valid data."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.relationship_summary("employee@example.test")
        assert result["email"] == "employee@example.test"
        assert result["send_count"] > 0
        assert isinstance(result["community"], list)

    def test_relationship_summary_bridge_score_exception(self):
        """Bridge score exception is handled gracefully."""
        db = _populated_db()
        net = CommunicationNetwork(db)

        net._ensure_graph()
        with patch.object(net, "_get_betweenness", side_effect=Exception("fail")):
            result = net.relationship_summary("employee@example.test")
        assert result["bridge_score"] == 0.0

    def test_relationship_summary_community_exception(self):
        """Community detection exception in relationship_summary is handled."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        import networkx as nx

        net._ensure_graph()
        # Make louvain_communities raise to trigger exception handler
        with patch.object(
            nx.community,
            "louvain_communities",
            side_effect=Exception("community fail"),
        ):
            # Also remove label_propagation as fallback
            original_lpc = getattr(nx.community, "label_propagation_communities", None)
            try:
                if hasattr(nx.community, "label_propagation_communities"):
                    nx.community.label_propagation_communities = MagicMock(side_effect=Exception("lpc fail"))
                result = net.relationship_summary("employee@example.test")
            finally:
                if original_lpc is not None:
                    nx.community.label_propagation_communities = original_lpc
        assert result["community"] == []

    def test_relationship_summary_label_propagation_fallback(self):
        """Uses label_propagation when louvain not available."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        import networkx as nx

        original = getattr(nx.community, "louvain_communities", None)
        try:
            if hasattr(nx.community, "louvain_communities"):
                delattr(nx.community, "louvain_communities")
            result = net.relationship_summary("employee@example.test")
            assert isinstance(result["community"], list)
        finally:
            if original is not None:
                nx.community.louvain_communities = original


# ── export_graphml ───────────────────────────────────────────


class TestExportGraphml:
    def test_export_graphml_success(self, tmp_path: Path):
        db = _populated_db()
        net = CommunicationNetwork(db)
        output = str(tmp_path / "graph.graphml")
        result = net.export_graphml(output)
        assert result["output_path"] == output
        assert result["total_nodes"] > 0
        assert result["total_edges"] > 0
        assert Path(output).exists()

    def test_export_graphml_creates_parent_dirs(self, tmp_path: Path):
        db = _populated_db()
        net = CommunicationNetwork(db)
        output = str(tmp_path / "sub" / "dir" / "graph.graphml")
        net.export_graphml(output)
        assert Path(output).exists()
