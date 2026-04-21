"""Evidence aggregation and export-oriented tests split from RF15."""

from __future__ import annotations

from src.email_db import EmailDatabase
from tests._evidence_cases import make_email, seed_evidence


def test_list_evidence_all():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.list_evidence()
    assert result["total"] == 4
    assert len(result["items"]) == 4
    db.close()


def test_list_evidence_filter_category():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.list_evidence(category="gaslighting")
    assert result["total"] == 1
    assert result["items"][0]["category"] == "gaslighting"
    db.close()


def test_list_evidence_filter_min_relevance():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.list_evidence(min_relevance=5)
    assert result["total"] == 2
    for item in result["items"]:
        assert item["relevance"] >= 5
    db.close()


def test_list_evidence_filter_email_uid():
    db = EmailDatabase(":memory:")
    items = seed_evidence(db)

    uid = items[0]["email_uid"]
    result = db.list_evidence(email_uid=uid)
    assert result["total"] == 2
    db.close()


def test_list_evidence_pagination():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    page_one = db.list_evidence(limit=2, offset=0)
    page_two = db.list_evidence(limit=2, offset=2)

    assert len(page_one["items"]) == 2
    assert len(page_two["items"]) == 2
    ids_one = {item["id"] for item in page_one["items"]}
    ids_two = {item["id"] for item in page_two["items"]}
    assert ids_one.isdisjoint(ids_two)
    db.close()


def test_list_evidence_empty():
    db = EmailDatabase(":memory:")
    result = db.list_evidence()
    assert result["total"] == 0
    assert result["items"] == []
    db.close()


def test_evidence_stats():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    stats = db.evidence_stats()
    assert stats["total"] == 4
    assert stats["verified"] + stats["unverified"] == 4

    categories = {category["category"] for category in stats["by_category"]}
    assert "gaslighting" in categories
    assert "bossing" in categories
    assert "harassment" in categories
    assert "discrimination" in categories

    assert len(stats["by_relevance"]) > 0
    db.close()


def test_evidence_stats_empty():
    db = EmailDatabase(":memory:")
    stats = db.evidence_stats()
    assert stats["total"] == 0
    assert stats["verified"] == 0
    assert stats["unverified"] == 0
    assert stats["by_category"] == []
    assert stats["by_relevance"] == []
    db.close()


def test_search_evidence_by_quote():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.search_evidence("incompetent")
    assert result["total"] == 2
    assert result["query"] == "incompetent"
    db.close()


def test_search_evidence_by_summary():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.search_evidence("Blame-shifting")
    assert result["total"] == 1
    assert result["items"][0]["category"] == "bossing"
    db.close()


def test_search_evidence_by_notes():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Bad behavior here.")
    db.insert_email(email)
    db.add_evidence(email.uid, "general", "Bad behavior", "Test.", 2, notes="Pattern since 2020.")

    result = db.search_evidence("Pattern since")
    assert result["total"] == 1
    db.close()


def test_search_evidence_with_category_filter():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.search_evidence("incompetent", category="gaslighting")
    assert result["total"] == 1
    assert result["items"][0]["category"] == "gaslighting"
    db.close()


def test_search_evidence_with_relevance_filter():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.search_evidence("incompetent", min_relevance=5)
    assert result["total"] == 1
    assert result["items"][0]["relevance"] == 5
    db.close()


def test_search_evidence_no_results():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    result = db.search_evidence("nonexistent phrase xyz")
    assert result["total"] == 0
    assert result["items"] == []
    db.close()


def test_evidence_timeline_all():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    items = db.evidence_timeline()
    assert len(items) == 4
    dates = [item["date"] for item in items]
    assert dates == sorted(dates)
    db.close()


def test_evidence_timeline_filter_category():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    items = db.evidence_timeline(category="harassment")
    assert len(items) == 1
    assert items[0]["category"] == "harassment"
    db.close()


def test_evidence_timeline_filter_relevance():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    items = db.evidence_timeline(min_relevance=5)
    assert len(items) == 2
    for item in items:
        assert item["relevance"] >= 5
    db.close()


def test_evidence_timeline_empty():
    db = EmailDatabase(":memory:")
    items = db.evidence_timeline()
    assert items == []
    db.close()


def test_evidence_timeline_offset():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    all_items = db.evidence_timeline()
    assert len(all_items) == 4

    offset_items = db.evidence_timeline(limit=10, offset=2)
    assert len(offset_items) == 2
    assert offset_items[0]["date"] == all_items[2]["date"]
    assert offset_items[1]["date"] == all_items[3]["date"]
    db.close()


def test_evidence_timeline_offset_beyond_results():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    items = db.evidence_timeline(offset=100)
    assert items == []
    db.close()
