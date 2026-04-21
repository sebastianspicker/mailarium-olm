"""Smoke-test the shared campaign workflow, results-control rules, and export boundary."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.case_campaign_workflow import execute_all_waves_payload
from src.investigation_results_workspace import write_active_results_manifest
from src.legal_support_exporter import LegalSupportExporter
from src.mcp_models import EmailCaseAnalysisInput
from src.question_execution_waves import list_wave_definitions


class _SmokeDeps:
    def get_retriever(self) -> object:
        return object()

    def get_email_db(self) -> None:
        return None

    async def offload(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def _fixture_case_input() -> dict[str, object]:
    return {
        "case_scope": {
            "target_person": {"name": "employee", "email": "employee@example.test"},
            "suspected_actors": [{"name": "manager", "email": "manager@example.test"}],
            "allegation_focus": ["exclusion"],
            "analysis_goal": "internal_review",
            "date_from": "2025-01-01",
            "date_to": "2025-06-30",
        },
        "source_scope": "emails_only",
        "output_language": "de",
        "translation_mode": "source_only",
    }


def _fake_case_analysis_payload(wave_id: str, query_lanes: list[str]) -> dict[str, object]:
    return {
        "workflow": "case_analysis",
        "retrieval_plan": {
            "effective_max_results": 12,
            "effective_query_lane_count": len(query_lanes),
        },
        "archive_harvest": {
            "coverage_gate": {"status": "pass"},
            "source_basis": {"primary_source": "email_archive_primary"},
            "coverage_metrics": {
                "unique_hits": 14,
                "unique_threads": 5,
                "unique_months": 3,
            },
        },
        "wave_local_views": {
            "surface_counts": {
                "master_chronology": 2,
                "lawyer_issue_matrix": 1,
            }
        },
        "wave_execution": {
            "wave_id": wave_id,
            "query_lane_count": len(query_lanes),
            "status": "completed",
        },
    }


def _exercise_shared_campaign_owner() -> None:
    params = EmailCaseAnalysisInput.model_validate(_fixture_case_input())

    async def _fake_build_case_analysis_payload(_deps, wave_params):
        return _fake_case_analysis_payload(wave_params.wave_id or "", list(wave_params.query_lanes))

    with patch("src.case_campaign_workflow.build_case_analysis_payload", _fake_build_case_analysis_payload):
        payload = asyncio.run(
            execute_all_waves_payload(
                _SmokeDeps(),
                params,
                scan_id_prefix="campaign-smoke",
                include_payloads=False,
            )
        )

    assert payload["workflow"] == "case_execute_all_waves"
    assert payload["wave_count"] == len(list_wave_definitions())
    assert payload["waves"][0]["scan_id"] == "campaign-smoke:wave_1"
    assert payload["waves"][0]["archive_harvest"]["status"] == "pass"
    assert payload["waves"][0]["wave_local_views"]["master_chronology"] == 2


def _exercise_results_control() -> None:
    with TemporaryDirectory() as tmpdir:
        results_root = Path(tmpdir) / "results"
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

        current_manifest = write_active_results_manifest(
            results_root=results_root,
            matter_id="matter:smoke",
            run_id="investigation_2026-04-16_P50",
            phase_id="P50",
            active_checkpoint=checkpoint,
            active_result_paths=[report],
            question_register_path=register,
            open_tasks_companion_path=open_tasks,
        )
        assert current_manifest["curation"]["status"] == "curated_current"

        stale_checkpoint = results_root / "_checkpoints" / "P51.md"
        stale_report = results_root / "03_exhaustive_run" / "P51.json"
        stale_checkpoint.write_text("checkpoint P51", encoding="utf-8")
        stale_report.write_text("{}", encoding="utf-8")

        stale_manifest = write_active_results_manifest(
            results_root=results_root,
            matter_id="matter:smoke",
            run_id="investigation_2026-04-16_P51",
            phase_id="P51",
            active_checkpoint=stale_checkpoint,
            active_result_paths=[stale_report],
            question_register_path=register,
            open_tasks_companion_path=open_tasks,
        )
        assert stale_manifest["curation"]["status"] == "stale_curated_ledgers"


def _exercise_counsel_export_boundary() -> None:
    export_status = LegalSupportExporter().counsel_export_status(
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
    readiness = export_status["export_metadata"]["counsel_export_readiness"]
    assert export_status["ready"] is False
    assert "snapshot_review_state:machine_extracted" in export_status["blockers"]
    assert readiness["policy_state"] == "internal_only"
    assert "human review" in str(readiness["next_step"]).lower()


def main() -> None:
    _exercise_shared_campaign_owner()
    _exercise_results_control()
    _exercise_counsel_export_boundary()
    print("campaign workflow smoke passed")


if __name__ == "__main__":
    main()
