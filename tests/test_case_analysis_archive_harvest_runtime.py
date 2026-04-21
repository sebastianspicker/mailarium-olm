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


async def test_build_case_analysis_payload_clamps_answer_context_query_and_results(monkeypatch) -> None:
    payload = _case_payload()
    payload["max_results"] = 20
    assert isinstance(payload["case_scope"], dict)
    payload["case_scope"]["context_notes"] = " ".join(["very long context"] * 80)
    params = EmailCaseAnalysisInput.model_validate(payload)

    captured: dict[str, object] = {}

    async def fake_build_answer_context_payload(_deps, answer_params, **kwargs):
        captured["question"] = answer_params.question
        captured["max_results"] = answer_params.max_results
        captured["query_lanes"] = list(answer_params.query_lanes)
        return {
            "search": {
                "top_k": answer_params.max_results,
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
                "hybrid": False,
                "rerank": False,
            },
            "case_bundle": {"bundle_id": "case-123"},
            "power_context": {"missing_org_context": True},
            "case_patterns": {},
            "retaliation_analysis": None,
            "comparative_treatment": None,
            "actor_identity_graph": {"actors": []},
            "communication_graph": {"graph_findings": []},
            "finding_evidence_index": {"findings": []},
            "evidence_table": {"row_count": 0},
            "behavioral_strength_rubric": {"version": "1"},
            "investigation_report": {"summary": {"section_count": 0}, "sections": {}},
            "multi_source_case_bundle": {"summary": {"missing_source_types": []}, "sources": []},
            "candidates": [],
        }

    async def fake_build_archive_harvest_bundle(_deps, _params, *, query_lanes, selected_top_k):
        return {
            "selected_results": [],
            "lane_diagnostics": [],
            "summary": {
                "enabled": True,
                "query_lanes": list(query_lanes),
                "selected_top_k": selected_top_k,
                "lane_top_k": 18,
                "merge_budget": 30,
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "adaptive_breadth": {
                    "effective_lane_top_k": 18,
                    "effective_merge_budget": 30,
                    "coverage_rerun_triggered": False,
                },
                "source_basis": {"primary_source": "email_archive_primary"},
                "coverage_metrics": {},
                "coverage_thresholds": {},
                "coverage_gate": {"status": "pass", "reasons": []},
                "evidence_bank": [],
            },
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    monkeypatch.setattr("src.case_analysis.build_archive_harvest_bundle", fake_build_archive_harvest_bundle)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)

    question = captured["question"]
    assert isinstance(question, str)
    assert len(question) <= 500
    assert question.endswith("...")
    assert captured["max_results"] == 15
    assert captured["query_lanes"]
    assert payload_out["retrieval_plan"]["requested_max_results"] == 20
    assert payload_out["retrieval_plan"]["effective_max_results"] == 15
    assert payload_out["retrieval_plan"]["capped"] is True
    assert payload_out["retrieval_plan"]["archive_harvest"]["adaptive_breadth"]["effective_lane_top_k"] == 18


async def test_build_case_analysis_payload_preserves_candidates_for_wave_harvest(monkeypatch) -> None:
    params = EmailCaseAnalysisInput.model_validate(_case_payload())

    async def fake_build_answer_context_payload(_deps, answer_params, **kwargs):
        del answer_params, kwargs
        return {
            "search": {
                "top_k": 8,
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
                "hybrid": False,
                "rerank": False,
            },
            "case_bundle": {"bundle_id": "case-123"},
            "power_context": {"missing_org_context": True},
            "case_patterns": {},
            "retaliation_analysis": None,
            "comparative_treatment": None,
            "actor_identity_graph": {"actors": []},
            "communication_graph": {"graph_findings": []},
            "finding_evidence_index": {"findings": []},
            "evidence_table": {"row_count": 0},
            "behavioral_strength_rubric": {"version": "1"},
            "investigation_report": {"summary": {"section_count": 0}, "sections": {}},
            "multi_source_case_bundle": {"summary": {"missing_source_types": []}, "sources": []},
            "candidates": [
                {
                    "uid": "uid-1",
                    "snippet": "Wir haben entschieden, den mobilen Arbeitstag zu streichen.",
                    "verification_status": "retrieval_exact",
                }
            ],
            "attachment_candidates": [
                {
                    "uid": "uid-1",
                    "snippet": "Anhangsauszug",
                    "attachment": {"filename": "protokoll.pdf"},
                }
            ],
        }

    async def fake_build_archive_harvest_bundle(_deps, _params, *, query_lanes, selected_top_k):
        return {
            "selected_results": [],
            "lane_diagnostics": [],
            "summary": {
                "enabled": True,
                "query_lanes": list(query_lanes),
                "selected_top_k": selected_top_k,
                "lane_top_k": 18,
                "merge_budget": 30,
                "candidate_pool_count": 1,
                "selected_result_count": 1,
                "adaptive_breadth": {
                    "effective_lane_top_k": 18,
                    "effective_merge_budget": 30,
                    "coverage_rerun_triggered": False,
                },
                "source_basis": {"primary_source": "email_archive_primary"},
                "coverage_metrics": {},
                "coverage_thresholds": {},
                "coverage_gate": {"status": "pass", "reasons": []},
                "evidence_bank": [],
            },
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    monkeypatch.setattr("src.case_analysis.build_archive_harvest_bundle", fake_build_archive_harvest_bundle)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)

    assert payload_out["candidates"][0]["snippet"] == "Wir haben entschieden, den mobilen Arbeitstag zu streichen."
    assert payload_out["attachment_candidates"][0]["attachment"]["filename"] == "protokoll.pdf"


async def test_build_case_analysis_payload_uses_wave_specific_query_lanes(monkeypatch) -> None:
    payload = _case_payload()
    payload["output_language"] = "de"
    payload["translation_mode"] = "source_only"
    payload["wave_id"] = "wave_1"
    params = EmailCaseAnalysisInput.model_validate(payload)

    captured: dict[str, object] = {}

    async def fake_build_answer_context_payload(_deps, answer_params, **kwargs):
        captured["query_lanes"] = list(answer_params.query_lanes)
        return {
            "search": {"top_k": answer_params.max_results},
            "investigation_report": {"summary": {"section_count": 0}, "sections": {}},
            "multi_source_case_bundle": {"summary": {"missing_source_types": []}, "sources": []},
            "candidates": [],
        }

    async def fake_build_archive_harvest_bundle(_deps, _params, *, query_lanes, selected_top_k):
        return {
            "selected_results": [],
            "lane_diagnostics": [],
            "summary": {
                "enabled": True,
                "query_lanes": list(query_lanes),
                "selected_top_k": selected_top_k,
                "lane_top_k": 18,
                "merge_budget": 30,
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "adaptive_breadth": {
                    "effective_lane_top_k": 18,
                    "effective_merge_budget": 30,
                    "coverage_rerun_triggered": False,
                },
                "source_basis": {"primary_source": "email_archive_primary"},
                "coverage_metrics": {},
                "coverage_thresholds": {},
                "coverage_gate": {"status": "pass", "reasons": []},
                "evidence_bank": [],
            },
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    monkeypatch.setattr("src.case_analysis.build_archive_harvest_bundle", fake_build_archive_harvest_bundle)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)

    query_lanes = captured["query_lanes"]
    assert isinstance(query_lanes, list)
    assert query_lanes
    assert any("Protokoll" in lane or "mobiles Arbeiten" in lane for lane in query_lanes)
    assert payload_out["wave_execution"]["wave_id"] == "wave_1"
    assert payload_out["wave_execution"]["query_lane_count"] == len(query_lanes)


async def test_build_case_analysis_payload_passes_scan_id_to_answer_context(monkeypatch) -> None:
    payload = _case_payload()
    payload["wave_id"] = "wave_8"
    payload["scan_id"] = "wave-scan-8"
    params = EmailCaseAnalysisInput.model_validate(payload)

    captured: dict[str, object] = {}

    async def fake_build_answer_context_payload(_deps, answer_params, **kwargs):
        captured["scan_id"] = answer_params.scan_id
        return {
            "search": {"top_k": answer_params.max_results},
            "investigation_report": {"summary": {"section_count": 0}, "sections": {}},
            "multi_source_case_bundle": {"summary": {"missing_source_types": []}, "sources": []},
            "candidates": [],
        }

    async def fake_build_archive_harvest_bundle(_deps, _params, *, query_lanes, selected_top_k):
        return {
            "selected_results": [],
            "lane_diagnostics": [],
            "summary": {
                "enabled": True,
                "query_lanes": list(query_lanes),
                "selected_top_k": selected_top_k,
                "lane_top_k": 18,
                "merge_budget": 30,
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "adaptive_breadth": {
                    "effective_lane_top_k": 18,
                    "effective_merge_budget": 30,
                    "coverage_rerun_triggered": False,
                },
                "source_basis": {"primary_source": "email_archive_primary"},
                "coverage_metrics": {},
                "coverage_thresholds": {},
                "coverage_gate": {"status": "pass", "reasons": []},
                "evidence_bank": [],
            },
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    monkeypatch.setattr("src.case_analysis.build_archive_harvest_bundle", fake_build_archive_harvest_bundle)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)

    assert captured["scan_id"] == "wave-scan-8"
    assert payload_out["wave_execution"]["scan_id"] == "wave-scan-8"


async def test_build_case_analysis_payload_emits_archive_harvest_summary(monkeypatch) -> None:
    payload = _case_payload()
    payload["wave_id"] = "wave_9"
    payload["source_scope"] = "mixed_case_file"
    payload["review_mode"] = "exhaustive_matter_review"
    payload["matter_manifest"] = {
        "manifest_id": "manifest-1",
        "artifacts": [
            {
                "source_id": "artifact-1",
                "source_class": "formal_document",
                "title": "thread.html",
                "filename": "thread.html",
                "source_path": "private/tests/materials/thread.html",
                "content_sha256": "a" * 64,
                "review_status": "parsed",
            }
        ],
    }
    params = EmailCaseAnalysisInput.model_validate(payload)

    captured: dict[str, object] = {}

    async def fake_build_answer_context_payload(_deps, answer_params, **kwargs):
        captured["preloaded_results"] = kwargs.get("preloaded_results")
        captured["lane_diagnostics_override"] = kwargs.get("lane_diagnostics_override")
        return {
            "search": {"top_k": answer_params.max_results},
            "investigation_report": {"summary": {"section_count": 0}, "sections": {}},
            "multi_source_case_bundle": {"summary": {"missing_source_types": []}, "sources": []},
            "candidates": [],
        }

    async def fake_build_archive_harvest_bundle(_deps, _params, *, query_lanes, selected_top_k):
        return {
            "selected_results": [],
            "lane_diagnostics": [{"lane_id": "lane_1", "query": query_lanes[0], "result_count": 4}],
            "summary": {
                "enabled": True,
                "query_lanes": list(query_lanes),
                "selected_top_k": selected_top_k,
                "lane_top_k": 18,
                "merge_budget": 30,
                "candidate_pool_count": 7,
                "selected_result_count": 0,
                "adaptive_breadth": {
                    "effective_lane_top_k": 18,
                    "effective_merge_budget": 30,
                    "coverage_rerun_triggered": False,
                },
                "source_basis": {
                    "primary_source": "email_archive_primary_manifest_supplement",
                    "email_archive_available": True,
                    "manifest_artifact_count": 1,
                },
                "coverage_metrics": {
                    "unique_hits": 4,
                    "unique_threads": 1,
                    "unique_senders": 2,
                    "unique_months": 1,
                    "attachment_hits": 0,
                    "folders_touched": 1,
                    "lane_coverage": 1,
                },
                "coverage_thresholds": {
                    "min_unique_hits": 10,
                    "min_unique_threads": 3,
                    "min_unique_months": 2,
                    "min_attachment_hits": 1,
                    "min_lane_coverage": 3,
                },
                "coverage_gate": {
                    "status": "needs_more_harvest",
                    "reasons": ["unique_hits_below_threshold", "attachment_hits_below_threshold"],
                },
                "evidence_bank": [],
            },
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    monkeypatch.setattr("src.case_analysis.build_archive_harvest_bundle", fake_build_archive_harvest_bundle)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)

    assert isinstance(captured["preloaded_results"], list)
    assert isinstance(captured["lane_diagnostics_override"], list)
    assert payload_out["archive_harvest"]["source_basis"]["primary_source"] == "email_archive_primary_manifest_supplement"
    assert payload_out["archive_harvest"]["coverage_gate"]["status"] == "needs_more_harvest"
    assert payload_out["wave_execution"]["archive_harvest_status"] == "needs_more_harvest"
    assert payload_out["retrieval_plan"]["archive_harvest"]["candidate_pool_count"] == 7


async def test_build_case_analysis_payload_augments_archive_harvest_with_mixed_source_metrics(monkeypatch) -> None:
    payload = _case_payload()
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-harvest-1",
        "artifacts": [
            {
                "source_id": "manifest:doc:1",
                "source_class": "formal_document",
                "title": "Status export",
                "text": (
                    "From: manager <manager@example.test>\n"
                    "To: employee <employee@example.test>\n"
                    "Date: 2025-03-15T10:00:00\n"
                    "Subject: Status update\n"
                    "Status text."
                ),
            }
        ],
    }
    params = EmailCaseAnalysisInput.model_validate(payload)

    async def fake_build_answer_context_payload(_deps, _answer_params, **kwargs):
        return {
            "case_bundle": {
                "bundle_id": "case-123",
                "scope": {
                    "target_person": {"name": "employee", "email": "employee@example.test"},
                    "allegation_focus": ["retaliation"],
                    "analysis_goal": "lawyer_briefing",
                    "date_from": "2025-01-01",
                    "date_to": "2025-06-30",
                },
            },
            "multi_source_case_bundle": {
                "summary": {"source_count": 1, "source_type_counts": {"email": 1}},
                "sources": [
                    {
                        "source_id": "email:uid-1",
                        "source_type": "email",
                        "uid": "uid-1",
                        "title": "Status update",
                        "date": "2025-03-15T10:00:00",
                        "snippet": "Status email.",
                        "sender_name": "manager",
                        "sender_email": "manager@example.test",
                        "to": ["employee@example.test"],
                        "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                        "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    }
                ],
                "source_links": [],
                "source_type_profiles": [],
            },
            "finding_evidence_index": {"findings": []},
            "investigation_report": {
                "summary": {"section_count": 1, "supported_section_count": 1, "insufficient_section_count": 0},
                "sections": {
                    "missing_information": {
                        "section_id": "missing_information",
                        "title": "Missing Information / Further Evidence Needed",
                        "status": "supported",
                        "entries": [],
                    }
                },
            },
            "candidates": [],
        }

    async def fake_build_archive_harvest_bundle(_deps, _params, *, query_lanes, selected_top_k):
        del query_lanes, selected_top_k
        return {
            "selected_results": [],
            "lane_diagnostics": [],
            "summary": {
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "raw_candidate_count": 0,
                "compact_candidate_count": 0,
                "lane_top_k": 12,
                "merge_budget": 24,
                "adaptive_breadth": {"coverage_rerun_triggered": False},
                "coverage_gate": {"status": "pass", "reasons": [], "recommendations": []},
                "quality_gate": {"status": "pass", "score": 0.8, "reasons": []},
                "actor_discovery": {"discovered_actor_count": 0, "roles": {}, "top_discovered_actors": []},
                "source_basis": {"primary_source": "email_archive_primary_manifest_supplement"},
                "coverage_metrics": {},
                "evidence_bank": [],
            },
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)
    monkeypatch.setattr("src.case_analysis.build_archive_harvest_bundle", fake_build_archive_harvest_bundle)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)

    assert payload_out["archive_harvest"]["mixed_source_metrics"]["non_email_source_count"] == 0
    assert payload_out["archive_harvest"]["mixed_source_metrics"]["linked_non_email_source_count"] == 0
    assert payload_out["archive_harvest"]["coverage_gate"]["status"] == "pass"


def test_derive_wave_query_lane_specs_keeps_actor_free_and_counterevidence_lanes() -> None:
    payload = _case_payload()
    assert isinstance(payload["case_scope"], dict)
    payload["case_scope"]["context_people"] = [{"name": "Lara Langer", "email": "lara.langer@example.test"}]
    payload["case_scope"]["institutional_actors"] = [
        {
            "label": "HR mailbox",
            "actor_type": "shared_mailbox",
            "email": "hr-mailbox@example.test",
        }
    ]
    params = EmailCaseAnalysisInput.model_validate(payload)

    specs = derive_wave_query_lane_specs(params, "wave_6")

    assert any(spec.lane_class == "actor_free_issue_family" for spec in specs)
    assert any(spec.lane_class == "comparator_actor_anchor" for spec in specs)
    assert any(spec.lane_class == "counterevidence_or_silence" for spec in specs)
    assert all(spec.query for spec in specs)
    assert any("hr-mailbox@example.test" in spec.query or "Lara Langer" in spec.query for spec in specs)


def test_derive_case_analysis_query_uses_case_scope_context() -> None:
    payload = _case_payload()
    payload.pop("output_language")
    payload.pop("translation_mode")
    assert isinstance(payload["case_scope"], dict)
    payload["case_scope"]["comparator_actors"] = [{"name": "Pat Peer", "email": "pat@example.org", "role_hint": "employee"}]
    payload["case_scope"]["context_people"] = [{"name": "Lara Langer", "email": "lara.langer@example.test"}]
    payload["case_scope"]["institutional_actors"] = [
        {
            "label": "HR mailbox",
            "actor_type": "shared_mailbox",
            "email": "hr-mailbox@example.test",
        }
    ]
    payload["case_scope"]["trigger_events"] = [{"trigger_type": "complaint", "date": "2025-02-02"}]
    payload["case_scope"]["employment_issue_tracks"] = ["participation_duty_gap"]
    params = EmailCaseAnalysisInput.model_validate(payload)
    query = derive_case_analysis_query(params)
    assert "arbeitsrechtliche fallanalyse" in query
    assert "employee" in query
    assert "retaliation, exclusion" in query
    assert "vergleichspersonen Pat Peer pat@example.org" in query
    assert "weitere akteure Lara Langer lara.langer@example.test" in query
    assert "institutionelle routen HR mailbox hr-mailbox@example.test" in query
    assert "ausloesende ereignisse complaint" in query
    assert "themenstraenge participation duty gap, participation_duty_gap" in query


def test_derive_case_analysis_query_uses_english_template_when_requested() -> None:
    payload = _case_payload()
    payload["output_language"] = "en"
    params = EmailCaseAnalysisInput.model_validate(payload)

    query = derive_case_analysis_query(params)

    assert "workplace case analysis" in query
    assert "target employee" in query
