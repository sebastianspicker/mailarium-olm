"""Tests for dashboard chart data preparation helpers."""

from unittest.mock import MagicMock

from src.dashboard_charts import (
    prepare_contacts_chart_data,
    prepare_entity_summary,
    prepare_heatmap_data,
    prepare_network_summary,
    prepare_response_times_data,
    prepare_volume_chart_data,
)


def _make_mock_analyzer():
    analyzer = MagicMock()
    analyzer.volume_over_time.return_value = [
        {"period": "2024-01", "count": 100},
        {"period": "2024-02", "count": 150},
    ]
    analyzer.activity_heatmap.return_value = [
        {"day_of_week": 0, "hour": 9, "count": 42},
        {"day_of_week": 0, "hour": 10, "count": 35},
        {"day_of_week": 4, "hour": 14, "count": 20},
    ]
    analyzer.response_times.return_value = [
        {"replier": "alice@example.com", "avg_response_hours": 2.5, "response_count": 10},
    ]
    return analyzer


def _make_mock_db():
    db = MagicMock()
    db.top_contacts.return_value = [
        {"partner": "alice@example.com", "total_count": 50},
        {"partner": "bob@example.com", "total_count": 30},
    ]
    db.top_entities.return_value = [
        {"entity_text": "Acme Corp", "entity_type": "organization", "mention_count": 15},
    ]
    return db


def test_volume_chart_data():
    analyzer = _make_mock_analyzer()
    data = prepare_volume_chart_data(analyzer, period="month")
    assert len(data) == 2
    assert data[0]["period"] == "2024-01"
    analyzer.volume_over_time.assert_called_once()


def test_volume_chart_data_with_filters():
    analyzer = _make_mock_analyzer()
    prepare_volume_chart_data(
        analyzer,
        period="day",
        date_from="2024-01-01",
        date_to="2024-12-31",
        sender="alice@example.com",
    )
    call_kwargs = analyzer.volume_over_time.call_args[1]
    assert call_kwargs["period"] == "day"
    assert call_kwargs["date_from"] == "2024-01-01"
    assert call_kwargs["sender"] == "alice@example.com"


def test_heatmap_data_structure():
    analyzer = _make_mock_analyzer()
    grid = prepare_heatmap_data(analyzer)
    # 7 days × 24 hours
    assert len(grid) == 7
    assert all(len(row) == 24 for row in grid)


def test_heatmap_data_values():
    analyzer = _make_mock_analyzer()
    grid = prepare_heatmap_data(analyzer)
    # Monday (0) at 9am should be 42
    assert grid[0][9] == 42
    # Monday at 10am should be 35
    assert grid[0][10] == 35
    # Friday (4) at 2pm should be 20
    assert grid[4][14] == 20
    # Unset cell should be 0
    assert grid[6][23] == 0


def test_heatmap_empty_data():
    analyzer = MagicMock()
    analyzer.activity_heatmap.return_value = []
    grid = prepare_heatmap_data(analyzer)
    assert len(grid) == 7
    assert all(cell == 0 for row in grid for cell in row)


def test_contacts_chart_data():
    db = _make_mock_db()
    data = prepare_contacts_chart_data(db, "me@example.com", limit=10)
    assert len(data) == 2
    assert data[0]["partner"] == "alice@example.com"
    db.top_contacts.assert_called_once_with("me@example.com", limit=10)


def test_response_times_data():
    analyzer = _make_mock_analyzer()
    data = prepare_response_times_data(analyzer, limit=10)
    assert len(data) == 1
    assert data[0]["avg_response_hours"] == 2.5


def test_entity_summary():
    db = _make_mock_db()
    data = prepare_entity_summary(db, entity_type="organization", limit=10)
    assert len(data) == 1
    db.top_entities.assert_called_once_with(entity_type="organization", limit=10)


def test_entity_summary_all_types():
    db = _make_mock_db()
    prepare_entity_summary(db, entity_type=None)
    db.top_entities.assert_called_once_with(entity_type=None, limit=20)


def test_network_summary_error_handling():
    db = MagicMock()
    # Force an error in network analysis
    db.communication_graph_data.side_effect = Exception("No data")
    result = prepare_network_summary(db, top_n=10)
    # Should return error dict, not raise
    assert isinstance(result, dict)


def test_volume_empty():
    analyzer = MagicMock()
    analyzer.volume_over_time.return_value = []
    data = prepare_volume_chart_data(analyzer, period="day")
    assert data == []


def test_contacts_empty():
    db = MagicMock()
    db.top_contacts.return_value = []
    data = prepare_contacts_chart_data(db, "nobody@example.com")
    assert data == []


def test_response_times_empty():
    analyzer = MagicMock()
    analyzer.response_times.return_value = []
    data = prepare_response_times_data(analyzer)
    assert data == []
