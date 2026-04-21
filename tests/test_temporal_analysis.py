"""Tests for temporal email analysis."""

from zoneinfo import ZoneInfo

from src.email_db import EmailDatabase
from src.parse_olm import Email
from src.temporal_analysis import TemporalAnalyzer


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
    # Mon Jan 15 2024
    db.insert_email(_make_email(message_id="<m1@example.test>", date="2024-01-15T10:30:00"))
    # Tue Jan 16 2024
    db.insert_email(_make_email(message_id="<m2@example.test>", date="2024-01-16T14:00:00"))
    # Wed Feb 14 2024
    db.insert_email(_make_email(message_id="<m3@example.test>", date="2024-02-14T09:00:00"))
    return db


class TestVolumeOverTime:
    def test_volume_by_day(self):
        db = _populated_db()
        analyzer = TemporalAnalyzer(db)
        result = analyzer.volume_over_time(period="day")
        assert len(result) == 3
        assert all("period" in r and "count" in r for r in result)

    def test_volume_by_week(self):
        db = _populated_db()
        analyzer = TemporalAnalyzer(db)
        result = analyzer.volume_over_time(period="week")
        # Jan 15 and Jan 16 same week, Feb 14 different week
        assert len(result) == 2

    def test_volume_by_month(self):
        db = _populated_db()
        analyzer = TemporalAnalyzer(db)
        result = analyzer.volume_over_time(period="month")
        assert len(result) == 2

    def test_volume_filtered_by_sender(self):
        db = _populated_db()
        db.insert_email(
            _make_email(
                message_id="<m4@example.test>",
                sender_email="bob@example.com",
                date="2024-01-20T10:00:00",
            )
        )
        analyzer = TemporalAnalyzer(db)
        result = analyzer.volume_over_time(sender="bob@example.com")
        assert len(result) == 1
        assert result[0]["count"] == 1

    def test_volume_filtered_by_date_range(self):
        db = _populated_db()
        analyzer = TemporalAnalyzer(db)
        result = analyzer.volume_over_time(date_from="2024-02-01")
        assert len(result) == 1

    def test_volume_empty(self):
        db = EmailDatabase(":memory:")
        analyzer = TemporalAnalyzer(db)
        assert analyzer.volume_over_time() == []

    def test_volume_buckets_in_display_timezone_for_positive_offset(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<tz-pos@example.test>",
                date="2024-01-01T00:30:00+02:00",
            )
        )

        analyzer = TemporalAnalyzer(db, display_timezone="Europe/Helsinki")

        assert analyzer.volume_over_time(period="day") == [{"period": "2024-01-01", "count": 1}]

    def test_volume_buckets_in_display_timezone_for_negative_offset(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<tz-neg@example.test>",
                date="2024-01-01T23:30:00-05:00",
            )
        )

        analyzer = TemporalAnalyzer(db, display_timezone="America/New_York")

        assert analyzer.volume_over_time(period="day") == [{"period": "2024-01-01", "count": 1}]

    def test_volume_date_filters_use_display_timezone(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<tz-filter@example.test>",
                date="2024-01-01T23:30:00-05:00",
            )
        )

        analyzer = TemporalAnalyzer(db, display_timezone="Europe/Berlin")

        assert analyzer.volume_over_time(period="day", date_from="2024-01-02") == [{"period": "2024-01-02", "count": 1}]
        assert analyzer.volume_over_time(period="day", date_to="2024-01-01") == []


class TestActivityHeatmap:
    def test_heatmap_structure(self):
        db = _populated_db()
        analyzer = TemporalAnalyzer(db)
        result = analyzer.activity_heatmap()
        assert len(result) > 0
        for entry in result:
            assert 0 <= entry["day_of_week"] <= 6
            assert 0 <= entry["hour"] <= 23
            assert entry["count"] > 0

    def test_heatmap_empty(self):
        db = EmailDatabase(":memory:")
        analyzer = TemporalAnalyzer(db)
        assert analyzer.activity_heatmap() == []

    def test_heatmap_uses_display_timezone_hour(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<heatmap@example.test>",
                date="2024-01-01T00:30:00-05:00",
            )
        )

        analyzer = TemporalAnalyzer(db, display_timezone="America/New_York")

        assert analyzer.activity_heatmap() == [{"day_of_week": 0, "hour": 0, "count": 1}]

    def test_heatmap_respects_named_zone_across_dst_boundary(self):
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<dst-1@example.test>",
                date="2024-03-10T01:30:00-05:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<dst-2@example.test>",
                date="2024-03-10T03:30:00-04:00",
            )
        )

        analyzer = TemporalAnalyzer(db, display_timezone="America/New_York")

        assert analyzer.activity_heatmap() == [
            {"day_of_week": 6, "hour": 1, "count": 1},
            {"day_of_week": 6, "hour": 3, "count": 1},
        ]

    def test_local_timezone_uses_named_zone_rules(self, monkeypatch):
        from src.temporal_analysis import _local_display_timezone

        monkeypatch.setenv("TZ", "Europe/Berlin")

        tz = _local_display_timezone()

        assert isinstance(tz, ZoneInfo)
        assert tz.key == "Europe/Berlin"


class TestResponseTimes:
    def test_basic_response_time(self):
        db = EmailDatabase(":memory:")
        # Original email
        db.insert_email(
            _make_email(
                message_id="<orig@example.test>",
                date="2024-01-15T10:00:00",
            )
        )
        # Reply 2 hours later
        db.insert_email(
            _make_email(
                message_id="<reply@example.test>",
                subject="RE: Hello",
                sender_email="bob@example.com",
                sender_name="Bob",
                to=["Alice <employee@example.test>"],
                in_reply_to="<orig@example.test>",
                date="2024-01-15T12:00:00",
            )
        )
        analyzer = TemporalAnalyzer(db)
        result = analyzer.response_times()
        assert len(result) == 1
        assert result[0]["replier"] == "bob@example.com"
        assert result[0]["avg_response_hours"] == 2.0
        assert result[0]["response_sample_scope"] == "recent_canonical_reply_pairs"
        assert result[0]["response_sample_pair_limit"] == 500

    def test_negative_times_excluded(self):
        db = EmailDatabase(":memory:")
        # "Reply" is before original (malformed data)
        db.insert_email(
            _make_email(
                message_id="<orig@example.test>",
                date="2024-01-15T12:00:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<reply@example.test>",
                sender_email="bob@example.com",
                in_reply_to="<orig@example.test>",
                date="2024-01-15T10:00:00",
            )
        )
        analyzer = TemporalAnalyzer(db)
        result = analyzer.response_times()
        assert result == []

    def test_response_times_empty(self):
        db = EmailDatabase(":memory:")
        analyzer = TemporalAnalyzer(db)
        assert analyzer.response_times() == []
