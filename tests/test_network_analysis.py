"""Tests for communication network analysis."""

from src.email_db import EmailDatabase
from src.network_analysis import CommunicationNetwork
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


class TestCommunicationNetwork:
    def test_top_contacts_ordering(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        contacts = net.top_contacts("employee@example.test")
        assert contacts[0]["partner"] == "bob@example.com"
        assert contacts[0]["total"] >= 2

    def test_top_contacts_empty(self):
        db = EmailDatabase(":memory:")
        net = CommunicationNetwork(db)
        assert net.top_contacts("nobody@example.com") == []

    def test_top_contacts_bidirectional(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        contacts = net.top_contacts("employee@example.test")
        # Bob should show up with both sent and received counts
        bob = next(c for c in contacts if c["partner"] == "bob@example.com")
        assert bob["total"] == 3  # 2 alice→bob + 1 bob→alice

    def test_communication_between(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.communication_between("employee@example.test", "bob@example.com")
        assert result["a_to_b"] == 2
        assert result["b_to_a"] == 1
        assert result["total"] == 3

    def test_communication_between_no_relationship(self):
        db = EmailDatabase(":memory:")
        net = CommunicationNetwork(db)
        result = net.communication_between("a@example.test", "b@example.test")
        assert result["total"] == 0

    def test_network_analysis_structure(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.network_analysis()
        assert result["total_nodes"] > 0
        assert result["total_edges"] > 0
        assert len(result["most_connected"]) > 0
        assert "email" in result["most_connected"][0]
        assert "centrality" in result["most_connected"][0]

    def test_network_analysis_centrality(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.network_analysis()
        # Alice should be most connected (sends to bob and carol, receives from bob)
        emails = [n["email"] for n in result["most_connected"]]
        assert "employee@example.test" in emails

    def test_network_analysis_empty(self):
        db = EmailDatabase(":memory:")
        net = CommunicationNetwork(db)
        result = net.network_analysis()
        assert result["total_nodes"] == 0
        assert result["total_edges"] == 0

    def test_network_analysis_communities(self):
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.network_analysis()
        assert isinstance(result["communities"], list)

    def test_network_analysis_cached(self):
        """Second call with same top_n returns cached result."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        result1 = net.network_analysis(top_n=5)
        result2 = net.network_analysis(top_n=5)
        assert result1 is result2  # exact same dict object (cached)

    def test_betweenness_cached(self):
        """Betweenness centrality is computed once and reused."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        import networkx as nx

        net._ensure_graph()
        b1 = net._get_betweenness(nx)
        b2 = net._get_betweenness(nx)
        assert b1 is b2

    def test_communities_are_dicts_with_members_key(self):
        """Communities should be list[dict] with 'members' key for web UI compat."""
        db = _populated_db()
        net = CommunicationNetwork(db)
        result = net.network_analysis(top_n=5)
        for community in result.get("communities", []):
            assert isinstance(community, dict)
            assert "members" in community
            assert isinstance(community["members"], list)


class TestCoordinatedTimingMixedTimezones:
    """coordinated_timing must not crash on mixed timezone-aware and naive dates."""

    def test_mixed_timezone_dates_no_crash(self):
        db = EmailDatabase(":memory:")
        # Mix of naive and timezone-aware dates
        db.insert_email(
            _make_email(
                message_id="<tz1@example.test>",
                sender_email="employee@example.test",
                to=["Bob <bob@example.com>"],
                date="2024-01-15T10:30:00",  # naive
            )
        )
        db.insert_email(
            _make_email(
                message_id="<tz2@example.test>",
                sender_email="bob@example.com",
                to=["Alice <employee@example.test>"],
                date="2024-01-15T11:00:00Z",  # UTC
            )
        )
        db.insert_email(
            _make_email(
                message_id="<tz3@example.test>",
                sender_email="charlie@example.com",
                to=["Alice <employee@example.test>"],
                date="2024-01-15T12:00:00+02:00",  # offset
            )
        )
        net = CommunicationNetwork(db)
        # Should not raise TypeError
        results = net.coordinated_timing(
            ["employee@example.test", "bob@example.com", "charlie@example.com"],
            window_hours=24,
        )
        assert isinstance(results, list)
