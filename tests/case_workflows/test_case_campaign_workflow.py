from __future__ import annotations

import json

from src.case_campaign_workflow import build_wave_case_params, execute_all_waves_payload, gather_evidence_payload
from src.email_db import EmailDatabase
from src.investigation_results_workspace import write_active_results_manifest
from src.legal_support_exporter import LegalSupportExporter
from src.mcp_models import EmailCaseAnalysisInput
from src.question_execution_waves import list_wave_definitions
from tests._evidence_cases import make_email


class _Deps:
    def get_retriever(self) -> object:
        return object()

    def get_email_db(self) -> None:
        return None

    async def offload(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def _case_payload() -> dict[str, object]:
    return {
        "case_scope": {
            "target_person": {"name": "employee"},
            "suspected_actors": [{"name": "manager"}],
            "allegation_focus": ["exclusion"],
            "analysis_goal": "internal_review",
            "date_from": "2025-01-01",
            "date_to": "2025-02-01",
        },
        "source_scope": "emails_only",
        "output_language": "de",
        "translation_mode": "source_only",
    }


async def test_execute_all_waves_payload_uses_shared_owner_and_surfaces_campaign_state(monkeypatch) -> None:
    async def fake_build_case_analysis_payload(_deps, params):
        return {
            "workflow": "case_analysis",
            "retrieval_plan": {
                "effective_max_results": 8,
                "effective_query_lane_count": len(params.query_lanes),
                "query_lane_classes": ["actor_seeded_management", "actor_free_issue_family", "counterevidence_or_silence"],
            },
            "archive_harvest": {
                "coverage_gate": {"status": "pass"},
                "quality_gate": {"status": "pass", "score": 0.61},
                "source_basis": {"primary_source": "email_archive_primary"},
                "coverage_metrics": {
                    "unique_hits": 12,
                    "unique_threads": 4,
                    "unique_months": 3,
                    "verified_exact_hits": 2,
                    "attachment_candidate_count": 1,
                },
            },
            "wave_local_views": {"surface_counts": {"master_chronology": 2, "lawyer_issue_matrix": 1}},
            "wave_execution": {"wave_id": params.wave_id, "status": "completed"},
        }

    monkeypatch.setattr("src.case_campaign_workflow.build_case_analysis_payload", fake_build_case_analysis_payload)

    payload = await execute_all_waves_payload(
        _Deps(),
        EmailCaseAnalysisInput.model_validate(_case_payload()),
        scan_id_prefix="campaign-test",
        include_payloads=False,
    )

    assert payload["workflow"] == "case_execute_all_waves"
    assert payload["wave_count"] == len(list_wave_definitions())
    assert payload["waves"][0]["scan_id"] == "campaign-test:wave_1"
    assert payload["waves"][0]["archive_harvest"]["status"] == "pass"
    assert payload["waves"][0]["archive_harvest"]["quality_status"] == "pass"
    assert payload["waves"][0]["archive_harvest"]["verified_exact_hits"] == 2
    assert payload["waves"][0]["query_lane_classes"][0] == "actor_seeded_management"
    assert payload["waves"][0]["wave_local_views"]["master_chronology"] == 2


def test_build_wave_case_params_preserves_operator_query_lanes() -> None:
    params = EmailCaseAnalysisInput.model_validate(
        {
            **_case_payload(),
            "query_lanes": ["operator supplied lane", "counter evidence lane"],
        }
    )

    wave_params, wave_meta = build_wave_case_params(params, wave_id="wave_1", scan_id_prefix="campaign-test")

    assert wave_params.query_lanes == ["operator supplied lane", "counter evidence lane"]
    assert wave_meta["query_lanes"] == ["operator supplied lane", "counter evidence lane"]
    assert wave_meta["query_lane_classes"] == []


async def test_gather_evidence_payload_aggregates_wave_harvest(monkeypatch) -> None:
    async def fake_execute_wave_payload(_deps, _params, *, wave_id, scan_id_prefix=None):
        return {
            "wave_execution": {
                "wave_id": wave_id,
                "label": "Dossier Reconciliation",
                "questions": ["Q10", "Q11", "Q34"],
                "query_lanes": ["lane_1"],
                "scan_id": f"{scan_id_prefix}:{wave_id}",
            },
            "candidates": [],
            "attachment_candidates": [],
        }

    def fake_harvest_wave_payload(_db, *, payload, run_id, phase_id, harvest_limit_per_wave, promote_limit_per_wave):
        assert payload["wave_execution"]["wave_id"].startswith("wave_")
        assert run_id == "investigation_2026-04-16_P60"
        assert phase_id == "P60"
        assert harvest_limit_per_wave == 12
        assert promote_limit_per_wave == 4
        return {
            "status": "completed",
            "candidate_count": 3,
            "body_candidate_count": 2,
            "attachment_candidate_count": 1,
            "exact_body_candidate_count": 1,
            "promoted_count": 1,
            "duplicate_candidate_count": 0,
        }

    monkeypatch.setattr("src.case_campaign_workflow.execute_wave_payload", fake_execute_wave_payload)
    monkeypatch.setattr("src.case_campaign_workflow.harvest_wave_payload", fake_harvest_wave_payload)

    class _DB:
        def evidence_candidate_stats(self, **_kwargs):
            return {"total": 3, "promoted": 1}

        def evidence_stats(self):
            return {"total": 1, "verified": 1, "unverified": 0}

    class _HarvestDeps(_Deps):
        def get_email_db(self):
            return _DB()

    payload = await gather_evidence_payload(
        _HarvestDeps(),
        EmailCaseAnalysisInput.model_validate(_case_payload()),
        run_id="investigation_2026-04-16_P60",
        phase_id="P60",
        harvest_limit_per_wave=12,
        promote_limit_per_wave=4,
        include_payloads=False,
    )

    assert payload["workflow"] == "case_gather_evidence"
    assert payload["evidence_harvest"]["candidate_count"] == 3 * len(list_wave_definitions())
    assert payload["evidence_harvest"]["promoted_count"] == len(list_wave_definitions())
    assert payload["evidence_harvest"]["candidate_stats"]["total"] == 3
    assert payload["evidence_stats"]["verified"] == 1
    assert payload["waves"][0]["evidence_harvest"]["candidate_count"] == 3


async def test_gather_evidence_payload_short_circuits_when_db_unavailable(monkeypatch) -> None:
    async def fail_execute_wave_payload(*args, **kwargs):
        raise AssertionError("wave execution should not start without persistence")

    monkeypatch.setattr("src.case_campaign_workflow.execute_wave_payload", fail_execute_wave_payload)

    payload = await gather_evidence_payload(
        _Deps(),
        EmailCaseAnalysisInput.model_validate(_case_payload()),
        run_id="investigation_2026-04-16_P60",
        phase_id="P60",
    )

    assert payload["status"] == "db_unavailable"
    assert payload["wave_count"] == 0
    assert payload["evidence_harvest"]["candidate_count"] == 0


async def test_gather_evidence_payload_persists_completed_wave_before_later_failure(monkeypatch) -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="We decided to cancel your mobile-work day. Please confirm.")
    db.insert_email(email)

    async def fake_execute_wave_payload(_deps, _params, *, wave_id, scan_id_prefix=None):
        if wave_id == "wave_1":
            return {
                "wave_execution": {
                    "wave_id": "wave_1",
                    "label": "Dossier Reconciliation",
                    "questions": ["Q10", "Q11", "Q34"],
                    "query_lanes": ["lane_1"],
                    "scan_id": f"{scan_id_prefix}:wave_1",
                },
                "candidates": [
                    {
                        "uid": email.uid,
                        "rank": 1,
                        "score": 0.91,
                        "subject": "Meeting notes",
                        "sender_email": "alice@example.test",
                        "sender_name": "Alice Manager",
                        "date": "2024-03-15T10:30:00",
                        "conversation_id": "conv-1",
                        "snippet": "We decided to cancel your mobile-work day.",
                        "verification_status": "retrieval_exact",
                        "matched_query_lanes": ["lane_1"],
                        "matched_query_queries": ["mobiles Arbeiten BEM"],
                        "provenance": {
                            "evidence_handle": "email:test-uid-1:retrieval:body_text:0:42:0",
                        },
                    }
                ],
                "attachment_candidates": [],
            }
        raise RuntimeError("simulated wave failure")

    class _DBDeps(_Deps):
        def get_email_db(self):
            return db

    monkeypatch.setattr("src.case_campaign_workflow.execute_wave_payload", fake_execute_wave_payload)

    try:
        await gather_evidence_payload(
            _DBDeps(),
            EmailCaseAnalysisInput.model_validate(_case_payload()),
            run_id="investigation_2026-04-16_P60",
            phase_id="P60",
            scan_id_prefix="campaign-test",
            harvest_limit_per_wave=12,
            promote_limit_per_wave=4,
        )
    except RuntimeError as exc:
        assert str(exc) == "simulated wave failure"
    else:
        raise AssertionError("expected gather_evidence_payload to propagate the later wave failure")

    candidate_stats = db.evidence_candidate_stats(run_id="investigation_2026-04-16_P60")
    assert candidate_stats["total"] == 1
    assert candidate_stats["promoted"] == 1
    assert db.evidence_stats()["total"] == 1
    db.close()


def test_write_active_results_manifest_marks_stale_ledgers_for_new_raw_run(tmp_path) -> None:
    results_root = tmp_path / "results"
    checkpoint = results_root / "_checkpoints" / "P50.md"
    report = results_root / "03_exhaustive_run" / "P50.json"
    register = results_root / "11_memo_draft_dashboard" / "question_register.md"
    open_tasks = results_root / "11_memo_draft_dashboard" / "open_tasks_companion.md"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    register.parent.mkdir(parents=True, exist_ok=True)
    open_tasks.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("checkpoint P50", encoding="utf-8")
    report.write_text("{}", encoding="utf-8")
    register.write_text("question register P50 investigation_2026-04-16_P50", encoding="utf-8")
    open_tasks.write_text("open tasks P50 investigation_2026-04-16_P50", encoding="utf-8")

    current = write_active_results_manifest(
        results_root=results_root,
        matter_id="matter:123",
        run_id="investigation_2026-04-16_P50",
        phase_id="P50",
        active_checkpoint=checkpoint,
        active_result_paths=[report],
        question_register_path=register,
        open_tasks_companion_path=open_tasks,
    )
    assert current["curation"]["status"] == "curated_current"

    next_checkpoint = results_root / "_checkpoints" / "P51.md"
    next_report = results_root / "03_exhaustive_run" / "P51.json"
    next_checkpoint.write_text("checkpoint P51", encoding="utf-8")
    next_report.write_text("{}", encoding="utf-8")

    stale = write_active_results_manifest(
        results_root=results_root,
        matter_id="matter:123",
        run_id="investigation_2026-04-16_P51",
        phase_id="P51",
        active_checkpoint=next_checkpoint,
        active_result_paths=[next_report],
        question_register_path=register,
        open_tasks_companion_path=open_tasks,
    )
    assert stale["curation"]["status"] == "stale_curated_ledgers"


def test_counsel_export_status_keeps_machine_extracted_payload_internal_only() -> None:
    status = LegalSupportExporter().counsel_export_status(
        payload={
            "matter_persistence": {
                "snapshot_id": "snapshot:1",
                "workspace_id": "workspace:1",
                "matter_id": "matter:1",
                "review_state": "machine_extracted",
            },
            "matter_coverage_ledger": {"summary": {"coverage_status": "complete"}},
            "matter_ingestion_report": {"completeness_status": "complete"},
            "review_classification": {"may_be_presented_as_full_matter_review": True},
        }
    )

    assert status["ready"] is False
    assert "snapshot_review_state:machine_extracted" in status["blockers"]
    readiness = status["export_metadata"]["counsel_export_readiness"]
    assert readiness["policy_state"] == "internal_only"
    assert "dashboard" in json.dumps(readiness)
