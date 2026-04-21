from src.retriever import SearchResult
from src.web_ui import (
    build_active_filter_labels,
    build_export_payload,
    build_filter_chip_html,
    sort_search_results,
)


def _result(
    chunk_id: str,
    score_distance: float,
    date: str,
    sender_email: str = "a@example.com",
    sender_name: str = "Alice",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        text=f"body-{chunk_id}",
        metadata={
            "subject": f"Subject {chunk_id}",
            "sender_email": sender_email,
            "sender_name": sender_name,
            "date": date,
            "folder": "Inbox",
        },
        distance=score_distance,
    )


def test_build_active_filter_labels_includes_selected_filters():
    labels = build_active_filter_labels(
        sender=" legal@example.com ",
        subject=" renewal ",
        folder=" finance ",
        date_from="2024-01-01",
        date_to="2024-12-31",
        min_score=0.8,
    )

    assert labels == [
        "Sender: legal@example.com",
        "Subject: renewal",
        "Folder: finance",
        "From: 2024-01-01",
        "To date: 2024-12-31",
        "Min score: 0.80",
    ]


def test_build_active_filter_labels_includes_cc():
    labels = build_active_filter_labels(
        sender=None,
        subject=None,
        folder=None,
        date_from=None,
        date_to=None,
        min_score=None,
        cc="finance-team",
    )

    assert labels == ["CC: finance-team"]


def test_sort_search_results_supports_relevance_and_date():
    results = [
        _result("older", 0.2, "2024-01-01T00:00:00Z"),  # score 0.8
        _result("newer", 0.3, "2024-06-01T00:00:00Z"),  # score 0.7
        _result("best", 0.1, "2024-03-01T00:00:00Z"),  # score 0.9
    ]

    by_relevance = sort_search_results(results, "relevance")
    by_newest = sort_search_results(results, "date_desc")
    by_oldest = sort_search_results(results, "date_asc")

    assert [item.chunk_id for item in by_relevance] == ["best", "older", "newer"]
    assert [item.chunk_id for item in by_newest] == ["newer", "best", "older"]
    assert [item.chunk_id for item in by_oldest] == ["older", "best", "newer"]


def test_sort_search_results_uses_full_timestamp_within_same_day():
    results = [
        _result("earlier", 0.2, "2024-06-01T08:00:00Z"),
        _result("later", 0.3, "2024-06-01T17:30:00Z"),
        _result("middle", 0.1, "2024-06-01T12:15:00Z"),
    ]

    by_newest = sort_search_results(results, "date_desc")
    by_oldest = sort_search_results(results, "date_asc")

    assert [item.chunk_id for item in by_newest] == ["later", "middle", "earlier"]
    assert [item.chunk_id for item in by_oldest] == ["earlier", "middle", "later"]


def test_build_export_payload_includes_filters_and_sort():
    results = [_result("best", 0.1, "2024-03-01T00:00:00Z")]
    payload = build_export_payload(
        query="budget",
        results=results,
        filters={
            "sender": "legal@example.com",
            "subject": "renewal",
            "folder": "finance",
            "date_from": "2024-01-01",
            "date_to": "2024-12-31",
            "min_score": 0.8,
        },
        sort_by="date_desc",
        generated_at="2026-03-02T10:00:00Z",
    )

    assert payload["query"] == "budget"
    assert payload["count"] == 1
    assert payload["sort_by"] == "date_desc"
    assert payload["generated_at"] == "2026-03-02T10:00:00Z"
    assert payload["filters"]["subject"] == "renewal"
    assert payload["results"][0]["chunk_id"] == "best"


def test_build_active_filter_labels_includes_to():
    labels = build_active_filter_labels(
        sender=None,
        subject=None,
        folder=None,
        date_from=None,
        date_to=None,
        min_score=None,
        to="alice@example.com",
    )
    assert labels == ["To: alice@example.com"]


def test_build_active_filter_labels_includes_has_attachments():
    labels = build_active_filter_labels(
        sender=None,
        subject=None,
        folder=None,
        date_from=None,
        date_to=None,
        min_score=None,
        has_attachments=True,
    )
    assert labels == ["Has attachments"]


def test_build_active_filter_labels_has_attachments_false_not_shown():
    labels = build_active_filter_labels(
        sender=None,
        subject=None,
        folder=None,
        date_from=None,
        date_to=None,
        min_score=None,
        has_attachments=False,
    )
    assert labels == []


def test_build_filter_chip_html_escapes_untrusted_labels():
    html = build_filter_chip_html(["Sender: <script>alert(1)</script>", "Folder: inbox"])

    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "filter-chip" in html
