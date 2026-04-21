# ruff: noqa: F401, F403
from __future__ import annotations

import pytest

from src.case_analysis import (
    build_case_analysis_payload,
    derive_case_analysis_query,
    transform_case_analysis_payload,
)
from src.case_analysis_harvest import _coverage_metrics, _split_evidence_bank_layers, build_archive_harvest_bundle
from src.mcp_models import EmailCaseAnalysisInput, EmailLegalSupportInput
from src.question_execution_waves import derive_wave_query_lane_specs

from ._case_analysis_integration_cases import *
from .helpers.case_analysis_fixtures import case_payload as _case_payload


async def test_build_archive_harvest_bundle_widens_dense_corpus_after_coverage_failure(monkeypatch) -> None:
    payload = _case_payload()
    assert isinstance(payload["case_scope"], dict)
    payload["wave_id"] = "wave_1"
    payload["max_results"] = 8
    payload["case_scope"]["date_to"] = "2027-02-01"
    params = EmailCaseAnalysisInput.model_validate(payload)
    calls: list[tuple[int, int]] = []

    def fake_answer_context_search_kwargs(_params, _top_k):
        return {"query": "archive harvest"}

    def fake_search_across_query_lanes(
        *,
        retriever,
        search_kwargs,
        query_lanes,
        top_k,
        scan_id,
        lane_top_k,
        reserve_per_lane,
        bank_limit,
    ):
        del retriever, search_kwargs, top_k, scan_id, reserve_per_lane
        calls.append((lane_top_k, bank_limit))
        if len(calls) == 1:
            evidence_bank = [
                {
                    "uid": "uid-1",
                    "conversation_id": "thread-1",
                    "sender_email": "a@example.org",
                    "date": "2025-01-01",
                    "matched_query_lanes": ["lane_1"],
                }
            ]
        else:
            evidence_bank = [
                {
                    "uid": f"uid-{index}",
                    "conversation_id": f"thread-{(index % 5) + 1}",
                    "sender_email": f"sender-{index % 4}@example.org",
                    "date": f"2025-{(index % 6) + 1:02d}-01",
                    "has_attachments": index % 3 == 0,
                    "matched_query_lanes": [f"lane_{(index % len(query_lanes)) + 1}"],
                }
                for index in range(1, 13)
            ]
        return (
            [],
            [{"lane_id": f"lane_{idx}", "result_count": 1} for idx, _lane in enumerate(query_lanes, start=1)],
            {
                "lane_top_k": lane_top_k,
                "merge_budget": bank_limit,
                "candidate_pool_count": len(evidence_bank),
                "selected_result_count": 0,
                "evidence_bank": evidence_bank,
            },
        )

    monkeypatch.setattr("src.tools.search_answer_context_impl._answer_context_search_kwargs", fake_answer_context_search_kwargs)
    monkeypatch.setattr("src.tools.search_answer_context_runtime._search_across_query_lanes", fake_search_across_query_lanes)

    class _Retriever:
        @staticmethod
        def search_filtered(**kwargs):
            return []

        @staticmethod
        def stats():
            return {"total_emails": 19948}

    class _Deps:
        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return None

    summary = (
        await build_archive_harvest_bundle(
            _Deps(),
            params,
            query_lanes=[f"lane {index}" for index in range(1, 6)],
            selected_top_k=8,
        )
    )["summary"]

    assert len(calls) >= 2
    assert calls[1][0] > calls[0][0]
    assert summary["adaptive_breadth"]["coverage_rerun_triggered"] is True
    assert summary["adaptive_breadth"]["rerun_round_count"] >= 1
    assert len(summary["rerun_rounds"]) >= 2
    assert summary["adaptive_breadth"]["effective_lane_top_k"] > 25
    assert summary["adaptive_breadth"]["effective_merge_budget"] > 40
    assert summary["coverage_metrics"]["lane_coverage"] >= 4


async def test_build_archive_harvest_bundle_changes_query_shape_for_zero_result_and_attachment_gaps(monkeypatch) -> None:
    payload = _case_payload()
    assert isinstance(payload["case_scope"], dict)
    payload["wave_id"] = "wave_1"
    params = EmailCaseAnalysisInput.model_validate(payload)
    calls: list[list[str]] = []

    def fake_answer_context_search_kwargs(_params, _top_k):
        return {"query": "archive harvest", "expand_query": True}

    def fake_search_across_query_lanes(
        *,
        retriever,
        search_kwargs,
        query_lanes,
        top_k,
        scan_id,
        lane_top_k,
        reserve_per_lane,
        bank_limit,
    ):
        del retriever, search_kwargs, top_k, scan_id, lane_top_k, reserve_per_lane, bank_limit
        calls.append(list(query_lanes))
        if len(calls) == 1:
            return (
                [],
                [
                    {"lane_id": "lane_1", "query": query_lanes[0], "result_count": 1},
                    {"lane_id": "lane_2", "query": query_lanes[1], "result_count": 0},
                ],
                {
                    "lane_top_k": 12,
                    "merge_budget": 24,
                    "candidate_pool_count": 1,
                    "selected_result_count": 0,
                    "evidence_bank": [
                        {
                            "uid": "uid-1",
                            "candidate_kind": "body",
                            "sender_name": "Neue Beteiligte",
                            "sender_email": "peer@example.org",
                            "subject": "Koordination und Weiterleitung",
                            "date": "2025-01-05",
                            "conversation_id": "thread-1",
                            "matched_query_lanes": ["lane_1"],
                            "verification_status": "retrieval_exact",
                            "provenance": {"evidence_handle": "email:uid-1:retrieval"},
                        }
                    ],
                    "evidence_results": [],
                },
            )
        return (
            [],
            [{"lane_id": f"lane_{index}", "query": lane, "result_count": 1} for index, lane in enumerate(query_lanes, start=1)],
            {
                "lane_top_k": 20,
                "merge_budget": 36,
                "candidate_pool_count": 3,
                "selected_result_count": 0,
                "evidence_bank": [
                    {
                        "uid": "uid-1",
                        "candidate_kind": "body",
                        "sender_name": "Neue Beteiligte",
                        "sender_email": "peer@example.org",
                        "subject": "Koordination und Weiterleitung",
                        "date": "2025-01-05",
                        "conversation_id": "thread-1",
                        "matched_query_lanes": ["lane_1"],
                        "verification_status": "retrieval_exact",
                        "provenance": {"evidence_handle": "email:uid-1:retrieval"},
                    },
                    {
                        "uid": "uid-2",
                        "candidate_kind": "attachment",
                        "attachment_filename": "protocol.pdf",
                        "sender_name": "Neue Beteiligte",
                        "sender_email": "peer@example.org",
                        "subject": "Meeting notes",
                        "date": "2025-01-06",
                        "conversation_id": "thread-2",
                        "matched_query_lanes": ["lane_3"],
                        "verification_status": "attachment_reference",
                        "provenance": {"evidence_handle": "attachment:uid-2:protocol.pdf"},
                    },
                ],
                "evidence_results": [],
            },
        )

    monkeypatch.setattr("src.tools.search_answer_context_impl._answer_context_search_kwargs", fake_answer_context_search_kwargs)
    monkeypatch.setattr("src.tools.search_answer_context_runtime._search_across_query_lanes", fake_search_across_query_lanes)

    class _Retriever:
        @staticmethod
        def search_filtered(**kwargs):
            return []

        @staticmethod
        def stats():
            return {"total_emails": 2500}

        @staticmethod
        def _expand_query_lanes(query, max_lanes=3):
            del max_lanes
            return [query, f"{query} timeline", f"{query} protocol"]

    class _Deps:
        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return None

    summary = (await build_archive_harvest_bundle(_Deps(), params, query_lanes=["lane a", "lane b"], selected_top_k=8))["summary"]

    assert len(calls) == 2
    assert calls[1] != calls[0]
    assert any("timeline" in lane for lane in calls[1])
    assert any("protocol" in lane.casefold() for lane in calls[1])
    assert "zero_result_lane_expansion" in summary["adaptive_breadth"]["rerun_actions"]


async def test_build_archive_harvest_bundle_emits_quality_gate_and_actor_discovery(monkeypatch) -> None:
    payload = _case_payload()
    assert isinstance(payload["case_scope"], dict)
    payload["wave_id"] = "wave_9"
    params = EmailCaseAnalysisInput.model_validate(payload)

    def fake_answer_context_search_kwargs(_params, _top_k):
        return {"query": "archive harvest"}

    def fake_search_across_query_lanes(
        *,
        retriever,
        search_kwargs,
        query_lanes,
        top_k,
        scan_id,
        lane_top_k,
        reserve_per_lane,
        bank_limit,
    ):
        del retriever, search_kwargs, query_lanes, top_k, scan_id, lane_top_k, reserve_per_lane, bank_limit
        return (
            [],
            [{"lane_id": "lane_1", "result_count": 2}],
            {
                "lane_top_k": 18,
                "merge_budget": 30,
                "candidate_pool_count": 2,
                "selected_result_count": 0,
                "evidence_bank": [
                    {
                        "uid": "uid-1",
                        "candidate_kind": "body",
                        "sender_name": "Neue Beteiligte",
                        "sender_email": "peer@example.org",
                        "subject": "Koordination und Weiterleitung",
                        "date": "2025-01-05",
                        "conversation_id": "thread-1",
                        "snippet": "Koordination und Absage.",
                        "has_attachments": True,
                        "matched_query_lanes": ["lane_1"],
                        "verification_status": "retrieval_exact",
                        "provenance": {"evidence_handle": "email:uid-1:retrieval"},
                    },
                    {
                        "uid": "uid-2",
                        "candidate_kind": "attachment",
                        "sender_name": "Neue Beteiligte",
                        "sender_email": "peer@example.org",
                        "subject": "Kalendereinladung",
                        "date": "2025-01-06",
                        "conversation_id": "thread-1",
                        "snippet": "invite.ics",
                        "has_attachments": True,
                        "matched_query_lanes": ["lane_1"],
                        "verification_status": "attachment_reference",
                        "provenance": {"evidence_handle": "attachment:uid-2:invite.ics"},
                    },
                ],
                "evidence_results": [],
            },
        )

    monkeypatch.setattr("src.tools.search_answer_context_impl._answer_context_search_kwargs", fake_answer_context_search_kwargs)
    monkeypatch.setattr("src.tools.search_answer_context_runtime._search_across_query_lanes", fake_search_across_query_lanes)

    class _Retriever:
        @staticmethod
        def search_filtered(**kwargs):
            return []

        @staticmethod
        def stats():
            return {"total_emails": 19948}

    class _Deps:
        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return None

    summary = (await build_archive_harvest_bundle(_Deps(), params, query_lanes=["lane a"], selected_top_k=8))["summary"]

    assert "score" in summary["quality_gate"]
    assert summary["actor_discovery"]["discovered_actor_count"] >= 1


def test_coverage_metrics_counts_only_harvested_attachment_evidence() -> None:
    body_only_metrics = _coverage_metrics(
        evidence_bank=[
            {
                "uid": "uid-1",
                "conversation_id": "thread-1",
                "sender_email": "employee@example.test",
                "date": "2025-01-01",
                "has_attachments": True,
                "candidate_kind": "body",
                "matched_query_lanes": ["lane_1"],
            }
        ],
        lane_diagnostics=[{"lane_id": "lane_1", "result_count": 1}],
    )

    metrics = _coverage_metrics(
        evidence_bank=[
            {
                "uid": "uid-1",
                "conversation_id": "thread-1",
                "sender_email": "employee@example.test",
                "date": "2025-01-01",
                "has_attachments": True,
                "candidate_kind": "body",
                "matched_query_lanes": ["lane_1"],
            },
            {
                "uid": "uid-2",
                "conversation_id": "thread-2",
                "sender_email": "employee@example.test",
                "date": "2025-01-02",
                "candidate_kind": "attachment",
                "attachment_filename": "note.pdf",
                "matched_query_lanes": ["lane_1"],
            },
        ],
        lane_diagnostics=[{"lane_id": "lane_1", "result_count": 2}],
    )

    assert body_only_metrics["attachment_hits"] == 0
    assert metrics["attachment_hits"] == 1
    assert metrics["attachment_candidate_count"] == 1


def test_split_evidence_bank_layers_separates_direct_from_expanded_rows() -> None:
    direct_rows, expanded_rows = _split_evidence_bank_layers(
        [
            {"uid": "uid-1", "harvest_source": "search_result"},
            {"uid": "uid-1", "harvest_source": "attachment_expansion"},
            {"uid": "uid-2", "harvest_source": "thread_expansion"},
        ]
    )

    assert [row["harvest_source"] for row in direct_rows] == ["search_result"]
    assert [row["harvest_source"] for row in expanded_rows] == ["attachment_expansion", "thread_expansion"]


async def test_build_archive_harvest_bundle_surfaces_direct_and_expanded_metrics_separately(monkeypatch) -> None:
    payload = _case_payload()
    params = EmailCaseAnalysisInput.model_validate(payload)

    def fake_answer_context_search_kwargs(_params, _top_k):
        return {"query": "archive harvest"}

    def fake_search_across_query_lanes(**kwargs):
        return (
            [],
            [{"lane_id": "lane_1", "result_count": 1}],
            {
                "lane_top_k": 12,
                "merge_budget": 24,
                "candidate_pool_count": 1,
                "selected_result_count": 0,
                "evidence_bank": [
                    {
                        "uid": "uid-1",
                        "candidate_kind": "body",
                        "sender_email": "alice@example.org",
                        "date": "2025-01-05",
                        "conversation_id": "thread-1",
                        "matched_query_lanes": ["lane_1"],
                    }
                ],
                "evidence_results": [],
            },
        )

    monkeypatch.setattr("src.tools.search_answer_context_impl._answer_context_search_kwargs", fake_answer_context_search_kwargs)
    monkeypatch.setattr("src.tools.search_answer_context_runtime._search_across_query_lanes", fake_search_across_query_lanes)
    monkeypatch.setattr(
        "src.case_analysis_harvest._attachment_expansion_rows",
        lambda db, evidence_bank, exhaustive_review: [
            {
                "uid": "uid-1",
                "candidate_kind": "attachment",
                "attachment_filename": "note.pdf",
                "harvest_source": "attachment_expansion",
                "matched_query_lanes": ["lane_1"],
            }
        ],
    )

    class _Retriever:
        @staticmethod
        def search_filtered(**kwargs):
            return []

        @staticmethod
        def stats():
            return {"total_emails": 500}

    class _Deps:
        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return None

    summary = (await build_archive_harvest_bundle(_Deps(), params, query_lanes=["lane a"], selected_top_k=8))["summary"]

    assert summary["coverage_metrics"]["attachment_hits"] == 1
    assert summary["direct_coverage_metrics"]["attachment_hits"] == 0
    assert summary["expanded_coverage_metrics"]["attachment_hits"] == 1
    assert summary["direct_evidence_count"] == 1
    assert summary["expanded_evidence_count"] == 1


async def test_build_archive_harvest_bundle_surfaces_expansion_failures_as_partial(monkeypatch) -> None:
    payload = _case_payload()
    params = EmailCaseAnalysisInput.model_validate(payload)

    def fake_answer_context_search_kwargs(_params, _top_k):
        return {"query": "archive harvest"}

    def fake_search_across_query_lanes(**kwargs):
        return (
            [],
            [{"lane_id": "lane_1", "result_count": 1}],
            {
                "lane_top_k": 12,
                "merge_budget": 24,
                "candidate_pool_count": 1,
                "selected_result_count": 0,
                "evidence_bank": [
                    {
                        "uid": "uid-1",
                        "candidate_kind": "body",
                        "sender_email": "alice@example.org",
                        "date": "2025-01-05",
                        "conversation_id": "thread-1",
                        "matched_query_lanes": ["lane_1"],
                    }
                ],
                "evidence_results": [],
            },
        )

    monkeypatch.setattr("src.tools.search_answer_context_impl._answer_context_search_kwargs", fake_answer_context_search_kwargs)
    monkeypatch.setattr("src.tools.search_answer_context_runtime._search_across_query_lanes", fake_search_across_query_lanes)

    class _Retriever:
        @staticmethod
        def search_filtered(**kwargs):
            return []

        @staticmethod
        def stats():
            return {"total_emails": 500}

    class _FailingDb:
        @staticmethod
        def get_thread_emails(_conversation_id):
            raise RuntimeError("thread expansion failed")

        @staticmethod
        def attachments_for_email(_uid):
            raise RuntimeError("attachment expansion failed")

    class _Deps:
        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return _FailingDb()

    summary = (await build_archive_harvest_bundle(_Deps(), params, query_lanes=["lane a"], selected_top_k=8))["summary"]

    assert summary["harvest_run_status"] == "partial"
    assert summary["expansion_diagnostics"]["status"] == "partial"
    assert summary["expansion_diagnostics"]["error_count"] >= 2
    assert summary["quality_gate"]["status"] == "weak"
    assert "archive_expansion_partial" in summary["quality_gate"]["reasons"]


async def test_build_archive_harvest_bundle_uses_real_case_query_for_search_kwargs(monkeypatch) -> None:
    payload = _case_payload()
    payload["analysis_query"] = "Mit welchem Wortlaut genau wurde der Aufgabenentzug angekündigt?"
    params = EmailCaseAnalysisInput.model_validate(payload)
    captured: dict[str, str] = {}

    def fake_answer_context_search_kwargs(answer_params, _top_k):
        captured["question"] = answer_params.question
        return {"query": answer_params.question}

    def fake_search_across_query_lanes(**kwargs):
        captured["search_query"] = str((kwargs.get("search_kwargs") or {}).get("query") or "")
        return (
            [],
            [{"lane_id": "lane_1", "result_count": 0}],
            {
                "lane_top_k": 12,
                "merge_budget": 24,
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "evidence_bank": [],
                "evidence_results": [],
            },
        )

    monkeypatch.setattr("src.tools.search_answer_context_impl._answer_context_search_kwargs", fake_answer_context_search_kwargs)
    monkeypatch.setattr("src.tools.search_answer_context_runtime._search_across_query_lanes", fake_search_across_query_lanes)

    class _Retriever:
        @staticmethod
        def search_filtered(**kwargs):
            return []

        @staticmethod
        def stats():
            return {"total_emails": 500}

    class _Deps:
        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return None

    await build_archive_harvest_bundle(_Deps(), params, query_lanes=["lane a"], selected_top_k=5)

    assert captured["question"] == params.analysis_query
    assert captured["search_query"] == params.analysis_query


async def test_build_archive_harvest_bundle_promotes_manifest_rows_even_without_archive_retriever() -> None:
    payload = _case_payload()
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-archive-offline",
        "artifacts": [
            {
                "source_id": "manifest:doc:1",
                "source_class": "formal_document",
                "title": "Meeting summary",
                "date": "2025-03-01",
                "text": "Meeting summary documenting the participation gap.",
                "review_status": "parsed",
            }
        ],
    }
    params = EmailCaseAnalysisInput.model_validate(payload)

    class _Deps:
        @staticmethod
        def get_retriever():
            return None

        @staticmethod
        def get_email_db():
            return None

    bundle = await build_archive_harvest_bundle(_Deps(), params, query_lanes=["lane a"], selected_top_k=5)

    assert bundle["summary"]["mixed_source_candidate_count"] == 1
    assert bundle["promoted_evidence_rows"][0]["source_id"] == "manifest:doc:1"


async def test_build_archive_harvest_bundle_marks_empty_archive_unavailable(monkeypatch) -> None:
    payload = _case_payload()
    payload["wave_id"] = "wave_1"
    params = EmailCaseAnalysisInput.model_validate(payload)

    def fake_answer_context_search_kwargs(_params, _top_k):
        return {"query": "archive harvest"}

    def fake_search_across_query_lanes(**kwargs):
        del kwargs
        return (
            [],
            [{"lane_id": "lane_1", "result_count": 0}],
            {
                "lane_top_k": 12,
                "merge_budget": 24,
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "evidence_bank": [],
                "evidence_results": [],
            },
        )

    monkeypatch.setattr("src.tools.search_answer_context_impl._answer_context_search_kwargs", fake_answer_context_search_kwargs)
    monkeypatch.setattr("src.tools.search_answer_context_runtime._search_across_query_lanes", fake_search_across_query_lanes)

    class _Retriever:
        @staticmethod
        def search_filtered(**kwargs):
            return []

        @staticmethod
        def stats():
            return {"total_emails": 0}

    class _Deps:
        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return None

    summary = (await build_archive_harvest_bundle(_Deps(), params, query_lanes=["lane a"], selected_top_k=8))["summary"]

    assert summary["source_basis"]["email_archive_available"] is False


def test_augment_mixed_source_harvest_summary_relaxes_email_gap_reasons_for_manifest_primary_runs() -> None:
    from src.case_analysis_harvest import augment_mixed_source_harvest_summary

    params = EmailCaseAnalysisInput.model_validate(_case_payload())
    summary = augment_mixed_source_harvest_summary(
        summary={
            "source_basis": {"email_archive_available": False, "primary_source": "matter_manifest_primary"},
            "coverage_gate": {
                "status": "needs_more_harvest",
                "reasons": [
                    "unique_hits_below_threshold",
                    "unique_threads_below_threshold",
                    "lane_coverage_below_threshold",
                ],
                "recommendations": [
                    "Raise harvest breadth and widen actor-plus-issue query lanes.",
                    "Expand the strongest hits with thread lookup and similar-message replay.",
                ],
            },
            "quality_gate": {"status": "weak", "score": 0.0, "reasons": ["empty_evidence_bank"]},
            "actor_discovery": {"discovered_actor_count": 0, "roles": {}, "top_discovered_actors": []},
        },
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "manifest:doc:1",
                    "source_type": "formal_document",
                    "title": "2026-03-12 dossier.pdf",
                    "document_locator": {"evidence_handle": "manifest:doc:1", "text_locator": {"line_start": 1}},
                },
                {
                    "source_id": "manifest:doc:2",
                    "source_type": "formal_document",
                    "title": "2026-03-13 memo.pdf",
                    "document_locator": {"evidence_handle": "manifest:doc:2", "text_locator": {"line_start": 1}},
                },
                {
                    "source_id": "manifest:doc:3",
                    "source_type": "formal_document",
                    "title": "2026-03-14 note.pdf",
                    "document_locator": {"evidence_handle": "manifest:doc:3", "text_locator": {"line_start": 1}},
                },
            ],
            "source_links": [],
            "chronology_anchors": [
                {"source_id": "manifest:doc:1", "date": "2026-03-12"},
                {"source_id": "manifest:doc:2", "date": "2026-03-13"},
                {"source_id": "manifest:doc:3", "date": "2026-03-14"},
            ],
        },
        params=params,
    )

    assert summary["coverage_gate"]["status"] == "pass"
    assert summary["coverage_gate"]["reasons"] == []
    assert summary["quality_gate"]["status"] == "pass"
