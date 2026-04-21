from __future__ import annotations

from src.db_evidence import EvidenceMixin


def _make_mixin():
    mixin = EvidenceMixin.__new__(EvidenceMixin)
    mixin.conn = object()
    return mixin


def test_evidence_query_helpers_delegate_to_extracted_module(monkeypatch):
    mixin = _make_mixin()
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def fake_list(db, **kwargs):
        calls.append(("list", (db,), kwargs))
        return {"items": [], "total": 0}

    def fake_get(db, evidence_id):
        calls.append(("get", (db, evidence_id), {}))
        return {"id": evidence_id}

    def fake_verify(db):
        calls.append(("verify", (db,), {}))
        return {"verified": 0, "failed": 0, "orphaned": 0, "total": 0, "failures": []}

    def fake_stats(db, **kwargs):
        calls.append(("stats", (db,), kwargs))
        return {"total": 0, "verified": 0, "unverified": 0, "by_category": [], "by_relevance": []}

    def fake_search(db, **kwargs):
        calls.append(("search", (db,), kwargs))
        return {"items": [], "total": 0, "query": kwargs["query"]}

    def fake_timeline(db, **kwargs):
        calls.append(("timeline", (db,), kwargs))
        return []

    def fake_categories(db):
        calls.append(("categories", (db,), {}))
        return [{"category": "general", "count": 0}]

    monkeypatch.setattr("src.db_evidence.list_evidence_impl", fake_list)
    monkeypatch.setattr("src.db_evidence.get_evidence_impl", fake_get)
    monkeypatch.setattr("src.db_evidence.verify_evidence_quotes_impl", fake_verify)
    monkeypatch.setattr("src.db_evidence.evidence_stats_impl", fake_stats)
    monkeypatch.setattr("src.db_evidence.search_evidence_impl", fake_search)
    monkeypatch.setattr("src.db_evidence.evidence_timeline_impl", fake_timeline)
    monkeypatch.setattr("src.db_evidence.evidence_categories_impl", fake_categories)

    assert mixin.list_evidence(category="harassment", limit=5)["total"] == 0
    assert mixin.get_evidence(7) == {"id": 7}
    assert mixin.verify_evidence_quotes()["total"] == 0
    assert mixin.evidence_stats(min_relevance=4)["verified"] == 0
    assert mixin.search_evidence("deadline", category="bossing")["query"] == "deadline"
    assert mixin.evidence_timeline(limit=2) == []
    assert mixin.evidence_categories() == [{"category": "general", "count": 0}]

    assert calls == [
        ("list", (mixin,), {"category": "harassment", "min_relevance": None, "email_uid": None, "limit": 5, "offset": 0}),
        ("get", (mixin, 7), {}),
        ("verify", (mixin,), {}),
        ("stats", (mixin,), {"category": None, "min_relevance": 4}),
        ("search", (mixin,), {"query": "deadline", "category": "bossing", "min_relevance": None, "limit": 50}),
        ("timeline", (mixin,), {"category": None, "min_relevance": None, "limit": 2, "offset": 0}),
        ("categories", (mixin,), {}),
    ]
