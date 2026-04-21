import pytest


def test_dedupe_evidence_items_prefers_first_unique_handle():
    from src.tools.search_answer_context import _dedupe_evidence_items

    items = [
        {
            "uid": "u1",
            "score": 0.9,
            "snippet": "same",
            "provenance": {"evidence_handle": "email:u1:1"},
        },
        {
            "uid": "u1",
            "score": 0.8,
            "snippet": "same",
            "provenance": {"evidence_handle": "email:u1:1"},
        },
        {
            "uid": "u2",
            "score": 0.7,
            "snippet": "other",
            "provenance": {"evidence_handle": "email:u2:1"},
        },
    ]

    kept, dropped = _dedupe_evidence_items(items)

    assert dropped == 1
    assert [item["uid"] for item in kept] == ["u1", "u2"]
    assert kept[0]["score"] == pytest.approx(0.9)


def test_compact_timeline_events_keeps_anchor_uids():
    from src.tools.search_answer_context import _compact_timeline_events

    timeline = {
        "event_count": 6,
        "date_range": {"first": "2025-01-01", "last": "2025-01-06"},
        "first_uid": "u1",
        "last_uid": "u6",
        "key_transition_uid": "u4",
        "events": [
            {"uid": "u1", "date": "2025-01-01"},
            {"uid": "u2", "date": "2025-01-02"},
            {"uid": "u3", "date": "2025-01-03"},
            {"uid": "u4", "date": "2025-01-04"},
            {"uid": "u5", "date": "2025-01-05"},
            {"uid": "u6", "date": "2025-01-06"},
        ],
    }

    compacted, dropped = _compact_timeline_events(timeline, max_events=4)

    kept_uids = [event["uid"] for event in compacted["events"]]
    assert dropped == 2
    assert compacted["event_count"] == 4
    assert "u1" in kept_uids
    assert "u4" in kept_uids
    assert "u6" in kept_uids


def test_summarize_timeline_for_budget_keeps_anchor_uids_without_snippets():
    from src.tools.search_answer_context import _summarize_timeline_for_budget

    timeline = {
        "event_count": 5,
        "date_range": {"first": "2025-06-01", "last": "2025-06-05"},
        "first_uid": "u1",
        "last_uid": "u5",
        "key_transition_uid": "u3",
        "events": [
            {"uid": "u1", "date": "2025-06-01", "score": 0.91, "snippet": "first"},
            {"uid": "u2", "date": "2025-06-02", "score": 0.83, "snippet": "second"},
            {"uid": "u3", "date": "2025-06-03", "score": 0.97, "snippet": "third"},
            {"uid": "u4", "date": "2025-06-04", "score": 0.80, "snippet": "fourth"},
            {"uid": "u5", "date": "2025-06-05", "score": 0.88, "snippet": "fifth"},
        ],
    }

    summarized, dropped = _summarize_timeline_for_budget(timeline)

    assert dropped == 2
    assert summarized["event_count"] == 3
    assert [event["uid"] for event in summarized["events"]] == ["u1", "u3", "u5"]
    assert all("snippet" not in event for event in summarized["events"])


def test_packing_priority_prefers_strong_evidence_over_weak_high_score():
    from src.tools.search_answer_context import _packing_priority

    weak_priority = _packing_priority(
        {
            "uid": "weak-1",
            "rank": 1,
            "score": 0.99,
            "attachment": {"evidence_strength": "weak_reference", "text_available": False},
        },
        cited_candidate_uids=[],
    )
    strong_priority = _packing_priority(
        {
            "uid": "strong-1",
            "rank": 2,
            "score": 0.70,
            "verification_status": "forensic_exact",
        },
        cited_candidate_uids=["strong-1"],
    )

    assert weak_priority < strong_priority
