"""Tests for query suggestions module."""

from unittest.mock import MagicMock

from src.query_suggestions import QuerySuggester


def _make_mock_db():
    db = MagicMock()
    db.top_senders.return_value = [
        {"sender_name": "Alice", "sender_email": "employee@example.test", "message_count": 50},
        {"sender_name": "Bob", "sender_email": "bob@example.com", "message_count": 30},
    ]
    db.folder_counts.return_value = {"Inbox": 200, "Sent": 100, "Archive": 50}
    db.top_entities.return_value = [
        {"entity_type": "organization", "entity_text": "Acme Corp", "total_mentions": 15},
        {"entity_type": "url", "entity_text": "https://example.com", "total_mentions": 10},
    ]
    return db


def test_suggest_returns_all_categories():
    db = _make_mock_db()
    suggester = QuerySuggester(db)
    result = suggester.suggest(limit=5)
    assert "senders" in result
    assert "folders" in result
    assert "entities" in result


def test_suggest_senders():
    db = _make_mock_db()
    suggester = QuerySuggester(db)
    result = suggester.suggest(limit=5)
    assert len(result["senders"]) == 2
    assert result["senders"][0]["value"] == "employee@example.test"


def test_suggest_folders():
    db = _make_mock_db()
    suggester = QuerySuggester(db)
    result = suggester.suggest(limit=5)
    assert len(result["folders"]) == 3
    assert result["folders"][0]["label"] == "Inbox"
    assert result["folders"][0]["count"] == 200


def test_suggest_entities():
    db = _make_mock_db()
    suggester = QuerySuggester(db)
    result = suggester.suggest(limit=5)
    assert len(result["entities"]) == 2
    assert result["entities"][0]["type"] == "organization"


def test_suggest_flat():
    db = _make_mock_db()
    suggester = QuerySuggester(db)
    flat = suggester.suggest_flat(limit=10)
    assert any("From:" in s for s in flat)
    assert any("Folder:" in s for s in flat)
    assert any("[organization]" in s for s in flat)


def test_suggest_flat_limit():
    db = _make_mock_db()
    suggester = QuerySuggester(db)
    flat = suggester.suggest_flat(limit=3)
    assert len(flat) <= 3


def test_suggest_handles_empty_db():
    db = MagicMock()
    db.top_senders.return_value = []
    db.folder_counts.return_value = {}
    db.top_entities.return_value = []
    suggester = QuerySuggester(db)
    result = suggester.suggest(limit=5)
    assert result["senders"] == []
    assert result["folders"] == []
    assert result["entities"] == []


def test_suggest_handles_db_errors():
    db = MagicMock()
    db.top_senders.side_effect = Exception("DB error")
    db.folder_counts.side_effect = Exception("DB error")
    db.top_entities.side_effect = Exception("DB error")
    suggester = QuerySuggester(db)
    result = suggester.suggest(limit=5)
    # Should return empty lists, not raise
    assert result["senders"] == []
    assert result["folders"] == []
    assert result["entities"] == []
