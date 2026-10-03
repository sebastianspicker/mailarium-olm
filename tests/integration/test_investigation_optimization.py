"""Regression checks for bounded investigation-query optimizations."""

from __future__ import annotations

import asyncio
import gc
import weakref
from dataclasses import replace

from mailarium.archive import open_archive_database
from mailarium.ingestion.records import ParsedMessage
from mailarium.interfaces.mcp.models.answer_context import EmailAnswerContextInput
from mailarium.interfaces.web.charts import prepare_network_summary
from mailarium.investigation.answer_context import build_answer_context_payload
from mailarium.investigation.dedup_detector import _find_matching_pairs
from mailarium.investigation.network_analysis import CommunicationNetwork
from mailarium.model.conversation_segments import ConversationSegment
from mailarium.platform.settings import Settings
from mailarium.retrieval.models import SearchResult


def _message(
    message_id: str,
    sender: str,
    recipient: str,
    *,
    body: str = "Project handoff approval evidence.",
    attachment: bool = False,
) -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        subject="Handoff record",
        sender_name=sender.split("@", 1)[0].title(),
        sender_email=sender,
        to=[recipient],
        cc=[],
        bcc=[],
        date="2026-08-20T10:00:00",
        body_text=body,
        body_html="",
        folder="Inbox",
        has_attachments=attachment,
        attachment_names=["timeline.txt"] if attachment else [],
        attachments=[
            {
                "name": "timeline.txt",
                "mime_type": "text/plain",
                "size": 24,
                "extracted_text": "Final handoff timeline proof",
                "extraction_state": "text_extracted",
            }
        ]
        if attachment
        else [],
        segments=[
            ConversationSegment(
                ordinal=0,
                segment_type="authored_body",
                depth=0,
                text=body,
                source_surface="body_text",
                provenance={},
            ),
            ConversationSegment(
                ordinal=1,
                segment_type="quoted_reply",
                depth=1,
                text="From: reviewer@example.test\nApproved for handoff.",
                source_surface="body_text",
                provenance={},
            ),
        ],
    )


class _EdgeArchive:
    """Expose a synthetic edge source through the archive's ``analytics`` repository."""

    def __init__(self, analytics: object) -> None:
        self.analytics = analytics


class _EdgeAnalytics:
    def all_edges(self) -> list[tuple[str, str, int]]:
        return [
            ("a@example.test", "b@example.test", 100),
            ("b@example.test", "c@example.test", 100),
            ("c@example.test", "d@example.test", 100),
            ("a@example.test", "d@example.test", 1),
        ]


class _RankedEdgeAnalytics:
    def all_edges(self) -> list[tuple[str, str, int]]:
        return [
            ("a@example.test", "b@example.test", 10),
            ("b@example.test", "d@example.test", 10),
            ("a@example.test", "c@example.test", 5),
            ("c@example.test", "d@example.test", 5),
            ("a@example.test", "d@example.test", 2),
            ("a@example.test", "e@example.test", 4),
            ("e@example.test", "d@example.test", 4),
        ]


class _OverHopEdgeAnalytics:
    def all_edges(self) -> list[tuple[str, str, int]]:
        return [
            ("a@example.test", "b@example.test", 10),
            ("b@example.test", "c@example.test", 10),
            ("c@example.test", "d@example.test", 10),
        ]


def test_weighted_paths_keep_a_valid_hop_bounded_result_after_a_cheaper_overhop_path() -> None:
    network = CommunicationNetwork(_EdgeArchive(_EdgeAnalytics()))

    paths = network.find_paths("a@example.test", "d@example.test", max_hops=2, top_k=3)

    assert paths == [
        {
            "nodes": ["a@example.test", "d@example.test"],
            "edges": [{"from": "a@example.test", "to": "d@example.test", "weight": 1}],
            "hops": 1,
        }
    ]


def test_weighted_paths_return_multiple_valid_results_in_deterministic_cost_order() -> None:
    network = CommunicationNetwork(_EdgeArchive(_RankedEdgeAnalytics()))

    paths = network.find_paths("a@example.test", "d@example.test", max_hops=2, top_k=4)

    assert [path["nodes"] for path in paths] == [
        ["a@example.test", "b@example.test", "d@example.test"],
        ["a@example.test", "c@example.test", "d@example.test"],
        ["a@example.test", "d@example.test"],
        ["a@example.test", "e@example.test", "d@example.test"],
    ]
    assert network.find_paths("a@example.test", "d@example.test", max_hops=2, top_k=4) == paths


def test_weighted_paths_do_not_expand_a_component_when_target_exceeds_hop_bound(monkeypatch) -> None:
    from mailarium.investigation import network_analysis

    def unexpected_frontier_pop(_frontier):
        raise AssertionError("bounded search should reject the source before expanding the weighted frontier")

    monkeypatch.setattr(network_analysis.heapq, "heappop", unexpected_frontier_pop)

    network = CommunicationNetwork(_EdgeArchive(_OverHopEdgeAnalytics()))
    assert network.find_paths("a@example.test", "d@example.test", max_hops=2, top_k=3) == []


def test_duplicate_candidates_prune_impossible_pairs_without_changing_exact_results(monkeypatch) -> None:
    cache = [
        ("u0", "body 0", {"a", "b", "c", "d"}),
        ("u1", "body 1", {"a", "b", "c", "d"}),
        ("u2", "body 2", {"a", "b", "c"}),
        ("u3", "body 3", {"w", "x", "y", "z"}),
        ("u4", "body 4", set()),
        ("u5", "body 5", set()),
    ]
    from mailarium.investigation import dedup_detector

    original = dedup_detector._matching_pair
    comparisons: list[tuple[str, str]] = []

    def tracked(email_a, email_b, base_subject, threshold):
        comparisons.append((email_a[0], email_b[0]))
        return original(email_a, email_b, base_subject, threshold)

    monkeypatch.setattr(dedup_detector, "_matching_pair", tracked)

    assert _find_matching_pairs(cache, "handoff", 0.8, 50) == [
        {"uid_a": "u0", "uid_b": "u1", "similarity": 1.0, "subject": "handoff"},
        {"uid_a": "u4", "uid_b": "u5", "similarity": 1.0, "subject": "handoff"},
    ]
    assert comparisons == [("u0", "u1"), ("u4", "u5")]


def test_duplicate_pruning_preserves_zero_one_and_float_boundary_thresholds() -> None:
    boundary_cache = [
        ("left", "left body", {"shared", "a", "b"}),
        ("right", "right body", {"shared", "c", "d"}),
        ("same", "same body", {"shared", "a", "b"}),
    ]

    assert len(_find_matching_pairs(boundary_cache, "subject", 0.0, 50)) == 3
    assert _find_matching_pairs(boundary_cache, "subject", 0.2, 50)[0]["similarity"] == 0.2
    assert _find_matching_pairs(boundary_cache, "subject", 1.0, 50) == [
        {"uid_a": "left", "uid_b": "same", "similarity": 1.0, "subject": "subject"}
    ]


def test_duplicate_limit_stops_overlap_expansion_for_duplicate_heavy_groups(monkeypatch) -> None:
    from mailarium.investigation import dedup_detector

    cache = [(f"u{index}", "same body", {"a", "b", "c", "d"}) for index in range(800)]
    original_overlap_counts = dedup_detector._candidate_overlap_counts
    original_matching_pair = dedup_detector._matching_pair
    expanded_rows = 0
    comparisons = 0

    def tracked_overlap_counts(*args, **kwargs):
        nonlocal expanded_rows
        expanded_rows += 1
        return original_overlap_counts(*args, **kwargs)

    def tracked_matching_pair(*args, **kwargs):
        nonlocal comparisons
        comparisons += 1
        return original_matching_pair(*args, **kwargs)

    monkeypatch.setattr(dedup_detector, "_candidate_overlap_counts", tracked_overlap_counts)
    monkeypatch.setattr(dedup_detector, "_matching_pair", tracked_matching_pair)

    matches = _find_matching_pairs(cache, "same", 0.85, 50)

    assert len(matches) == 50
    assert expanded_rows == 1
    assert comparisons == 50


def test_dashboard_network_cache_invalidates_for_local_and_external_commits(tmp_path) -> None:
    archive_path = tmp_path / "network-cache.db"
    database = open_archive_database(str(archive_path))
    database.messages.insert_email(_message("one@example.test", "a@example.test", "b@example.test"))

    first = prepare_network_summary(database)
    repeated = prepare_network_summary(database)
    assert repeated is first
    assert first["total_edges"] == 1

    database.messages.insert_email(_message("two@example.test", "c@example.test", "d@example.test"))
    local_update = prepare_network_summary(database)
    assert local_update is not repeated
    assert local_update["total_edges"] == 2

    other_process = open_archive_database(str(archive_path))
    other_process.messages.insert_email(_message("three@example.test", "e@example.test", "f@example.test"))
    other_process.close()

    external_update = prepare_network_summary(database)
    assert external_update is not local_update
    assert external_update["total_edges"] == 3
    database.close()


def test_dashboard_network_cache_does_not_retain_closed_archive_database(tmp_path) -> None:
    database = open_archive_database(str(tmp_path / "network-cache-lifetime.db"))
    database.messages.insert_email(_message("lifetime@example.test", "a@example.test", "b@example.test"))
    prepare_network_summary(database)
    database_reference = weakref.ref(database)

    database.close()
    del database
    gc.collect()

    assert database_reference() is None


class _LaneRetriever:
    def __init__(self, database, first_uid: str, second_uid: str) -> None:
        self.email_db = database
        self.first_uid = first_uid
        self.second_uid = second_uid
        self.queries: list[str] = []
        self.last_search_debug: dict[str, object] = {}

    def search_filtered(self, **kwargs) -> list[SearchResult]:
        query = str(kwargs["query"])
        self.queries.append(query)
        self.last_search_debug = {
            "executed_query": query,
            "use_hybrid": False,
            "used_query_expansion": False,
            "fetch_size": 2,
        }
        body_distance = 0.25 if query == "handoff" else 0.05
        results = [
            SearchResult(
                chunk_id="shared-body",
                text="Project handoff approval evidence.",
                metadata={
                    "uid": self.first_uid,
                    "subject": "Handoff record",
                    "sender_email": "author@example.test",
                    "sender_name": "Author",
                    "date": "2026-08-20T10:00:00",
                },
                distance=body_distance,
            )
        ]
        if query == "handoff":
            attachment = SearchResult(
                chunk_id=f"{self.second_uid}__att_0",
                text='[Attachment: timeline.txt from email "Handoff record"]\nFinal handoff timeline proof',
                metadata={
                    "uid": self.second_uid,
                    "subject": "Handoff record",
                    "sender_email": "owner@example.test",
                    "sender_name": "Owner",
                    "date": "2026-08-20T10:00:00",
                    "is_attachment": True,
                    "attachment_filename": "timeline.txt",
                    "extraction_state": "text_extracted",
                },
                distance=0.12,
            )
            results.extend(
                [
                    attachment,
                    SearchResult(
                        chunk_id=f"{self.second_uid}__att_1",
                        text=attachment.text,
                        metadata=dict(attachment.metadata),
                        distance=0.2,
                    ),
                ]
            )
        return results


class _AnswerDependencies:
    def __init__(self, database, retriever) -> None:
        self.database = database
        self.retriever = retriever

    def get_retriever(self):
        return self.retriever

    def get_archive_database(self):
        return self.database

    async def offload(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def test_answer_context_batches_candidate_archive_reads_across_actual_query_lanes(monkeypatch, tmp_path) -> None:
    database = open_archive_database(str(tmp_path / "answer-context.db"))
    first = _message("answer-one@example.test", "author@example.test", "reviewer@example.test")
    second = _message(
        "answer-two@example.test",
        "owner@example.test",
        "reviewer@example.test",
        attachment=True,
    )
    database.messages.insert_emails_batch([first, second])
    retriever = _LaneRetriever(database, first.uid, second.uid)
    statements: list[str] = []
    database.conn.set_trace_callback(statements.append)
    monkeypatch.setattr(
        "mailarium.platform.settings.get_settings",
        lambda: replace(Settings(), mcp_max_search_results=5, mcp_max_json_response_chars=100_000),
    )

    payload = asyncio.run(
        build_answer_context_payload(
            _AnswerDependencies(database, retriever),
            EmailAnswerContextInput(
                question="What was approved for the handoff?",
                query_lanes=["handoff", "approval"],
                max_results=5,
            ),
        )
    )

    assert retriever.queries == ["handoff", "approval"]
    assert payload["candidates"][0]["uid"] == first.uid
    assert payload["candidates"][0]["matched_query_queries"] == ["handoff", "approval"]
    assert payload["candidates"][0]["provenance"]["evidence_handle"] == (
        f"email:{first.uid}:retrieval:body_text:0:{len(first.body_text)}:0"
    )
    assert payload["attachment_candidates"][0]["attachment"]["filename"] == "timeline.txt"
    assert sum("SELECT * FROM emails WHERE uid IN" in statement for statement in statements) == 1
    assert sum("FROM message_segments WHERE email_uid IN" in statement for statement in statements) == 1
    assert sum("FROM attachments WHERE email_uid =" in statement for statement in statements) == 1
    database.close()
