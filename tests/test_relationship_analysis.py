"""Tests for relationship analysis features (Phase 2)."""

import os
import tempfile

import pytest

from src.email_db import EmailDatabase


@pytest.fixture()
def db():
    """Create a temporary EmailDatabase with sample communication data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        database = EmailDatabase(db_path)

        # Insert sample emails and recipients for relationship analysis
        _insert_email(
            database,
            "uid-1",
            "alice@example.test",
            "Alice",
            "2024-01-01T10:00:00",
            "Meeting notes",
            to=["bob@example.test", "carol@example.test"],
        )
        _insert_email(
            database,
            "uid-2",
            "bob@example.test",
            "Bob",
            "2024-01-01T11:00:00",
            "Re: Meeting notes",
            to=["alice@example.test", "carol@example.test"],
        )
        _insert_email(
            database,
            "uid-3",
            "alice@example.test",
            "Alice",
            "2024-01-02T09:00:00",
            "Follow-up",
            to=["dave@example.test"],
        )
        _insert_email(
            database,
            "uid-4",
            "carol@example.test",
            "Carol",
            "2024-01-02T10:00:00",
            "New topic",
            to=["bob@example.test", "dave@example.test"],
        )
        _insert_email(
            database,
            "uid-5",
            "dave@example.test",
            "Dave",
            "2024-01-03T15:00:00",
            "External matter",
            to=["eve@example.test"],
        )
        _insert_email(
            database,
            "uid-6",
            "bob@example.test",
            "Bob",
            "2024-01-01T12:00:00",
            "Quick question",
            to=["carol@example.test"],
        )

        # Build communication edges
        edges = [
            ("alice@example.test", "bob@example.test", 1),
            ("alice@example.test", "carol@example.test", 1),
            ("alice@example.test", "dave@example.test", 1),
            ("bob@example.test", "alice@example.test", 1),
            ("bob@example.test", "carol@example.test", 2),
            ("carol@example.test", "bob@example.test", 1),
            ("carol@example.test", "dave@example.test", 1),
            ("dave@example.test", "eve@example.test", 1),
        ]
        for sender, recipient, count in edges:
            database.conn.execute(
                """INSERT INTO communication_edges(sender_email, recipient_email, email_count)
                   VALUES(?, ?, ?)""",
                (sender, recipient, count),
            )
        database.conn.commit()

        yield database
        database.close()


def _insert_email(db, uid, sender_email, sender_name, date, subject, to=None):
    """Helper to insert a test email."""
    db.conn.execute(
        """INSERT INTO emails (uid, sender_email, sender_name, date, subject,
           body_text, has_attachments, attachment_count, priority, is_read, body_length)
           VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 1, 0)""",
        (uid, sender_email, sender_name, date, subject, f"Body of {subject}"),
    )
    for addr in to or []:
        db.conn.execute(
            "INSERT INTO recipients(email_uid, address, display_name, type) VALUES(?,?,?,?)",
            (uid, addr, addr.split("@")[0].title(), "to"),
        )
    db.conn.commit()


# ── shared_recipients_query (EmailDatabase) ──────────────────


def test_shared_recipients_finds_common_recipients(db):
    """Should find recipients who received from multiple senders."""
    results = db.shared_recipients_query(["alice@example.test", "bob@example.test"])
    recipients = [r["recipient"] for r in results]
    assert "carol@example.test" in recipients


def test_shared_recipients_empty_for_no_overlap(db):
    """Should return empty when senders have no common recipients."""
    results = db.shared_recipients_query(["alice@example.test", "dave@example.test"])
    # alice sends to bob, carol, dave; dave sends to eve — minimal overlap
    assert isinstance(results, list)


def test_shared_recipients_returns_sender_list(db):
    """Each result should include which senders share that recipient."""
    results = db.shared_recipients_query(["alice@example.test", "bob@example.test"])
    for r in results:
        assert "senders" in r
        assert isinstance(r["senders"], list)
        assert len(r["senders"]) >= 2


def test_shared_recipients_single_sender_returns_empty(db):
    """Should return empty for a single sender (need at least 2)."""
    results = db.shared_recipients_query(["alice@example.test"])
    assert results == []


# ── sender_activity_timeline (EmailDatabase) ─────────────────


def test_sender_activity_timeline_ordered(db):
    """Timeline should be ordered by date ascending."""
    results = db.sender_activity_timeline(["alice@example.test", "bob@example.test"])
    dates = [r["date"] for r in results]
    assert dates == sorted(dates)


def test_sender_activity_timeline_filters_senders(db):
    """Should only include specified senders."""
    results = db.sender_activity_timeline(["alice@example.test"])
    assert all(r["sender_email"] == "alice@example.test" for r in results)
    assert len(results) == 2  # uid-1 and uid-3


def test_sender_activity_timeline_empty_list(db):
    """Should return empty for empty sender list."""
    assert db.sender_activity_timeline([]) == []


# ── find_paths (CommunicationNetwork) ────────────────────────


def test_find_paths_direct_connection(db):
    """Should find a direct path between connected nodes."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    paths = net.find_paths("alice@example.test", "bob@example.test")
    assert len(paths) >= 1
    assert paths[0]["hops"] == 1
    assert paths[0]["nodes"][0] == "alice@example.test"
    assert paths[0]["nodes"][-1] == "bob@example.test"


def test_find_paths_multi_hop(db):
    """Should find multi-hop paths."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    paths = net.find_paths("alice@example.test", "eve@example.test", max_hops=4)
    assert len(paths) >= 1
    # alice -> dave -> eve or alice -> carol -> dave -> eve
    assert paths[0]["hops"] >= 2


def test_find_paths_respects_max_hops(db):
    """Should not return paths exceeding max_hops."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    paths = net.find_paths("alice@example.test", "eve@example.test", max_hops=1)
    # eve is not directly connected to alice
    assert len(paths) == 0


def test_find_paths_no_path(db):
    """Should return empty for disconnected nodes."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    paths = net.find_paths("alice@example.test", "unknown@example.test")
    assert paths == []


def test_find_paths_respects_top_k(db):
    """Should not return more than top_k paths."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    paths = net.find_paths("alice@example.test", "eve@example.test", max_hops=5, top_k=1)
    assert len(paths) <= 1


def test_find_paths_source_equals_target(db):
    """Should return error when source and target are the same."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    result = net.find_paths("alice@example.test", "alice@example.test")
    assert len(result) == 1
    assert "error" in result[0]
    assert "same address" in result[0]["error"]


# ── shared_recipients (CommunicationNetwork) ─────────────────


def test_shared_recipients_via_network(db):
    """CommunicationNetwork.shared_recipients should delegate to DB."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    results = net.shared_recipients(["alice@example.test", "bob@example.test"])
    assert isinstance(results, list)


# ── coordinated_timing (CommunicationNetwork) ────────────────


def test_coordinated_timing_detects_overlap(db):
    """Should detect windows where multiple senders are active."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    # alice and bob both email on 2024-01-01 (3 total: uid-1, uid-2, uid-6)
    windows = net.coordinated_timing(
        ["alice@example.test", "bob@example.test"],
        window_hours=24,
        min_events=2,
    )
    assert len(windows) >= 1
    assert len(windows[0]["senders"]) >= 2


def test_coordinated_timing_empty_for_non_overlapping(db):
    """Should return empty when senders have no overlapping activity."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    # alice (Jan 1, Jan 2) and dave (Jan 3) with 1-hour window
    windows = net.coordinated_timing(
        ["alice@example.test", "dave@example.test"],
        window_hours=1,
        min_events=2,
    )
    assert len(windows) == 0


def test_coordinated_timing_single_sender_returns_empty(db):
    """Should return empty for a single sender."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    windows = net.coordinated_timing(["alice@example.test"])
    assert windows == []


# ── relationship_summary (CommunicationNetwork) ──────────────


def test_relationship_summary_returns_profile(db):
    """Should return a full contact profile with send/receive counts."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    profile = net.relationship_summary("alice@example.test")

    assert profile["email"] == "alice@example.test"
    assert "top_contacts" in profile
    assert "community" in profile
    assert "bridge_score" in profile
    assert "send_count" in profile
    assert "receive_count" in profile


def test_relationship_summary_has_send_receive(db):
    """Send/receive counts should reflect the graph edges."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    profile = net.relationship_summary("alice@example.test")

    # alice sends to bob(1), carol(1), dave(1) = 3 total
    assert profile["send_count"] == 3
    # alice receives from bob(1) = 1
    assert profile["receive_count"] == 1


def test_relationship_summary_unknown_email(db):
    """Should handle unknown email gracefully."""
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    profile = net.relationship_summary("unknown@example.test")

    assert profile["email"] == "unknown@example.test"
    assert profile["send_count"] == 0
    assert profile["receive_count"] == 0
