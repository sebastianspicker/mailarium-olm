from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.case_full_pack import build_case_full_pack
from src.legal_support_acceptance_fixtures import (
    acceptance_case,
    acceptance_case_ids,
    build_fixture_full_pack_input,
    execute_fixture_full_pack,
    execute_retrieval_fixture_full_pack,
)
from src.mcp_models import EmailCaseFullPackInput

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "docs" / "agent"


def test_build_case_full_pack_blocks_retaliation_prompt_without_triggers(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "email-note.txt").write_text("Meeting note about follow-up.", encoding="utf-8")

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": (
                "Claimant: employee. Create a lawyer briefing on retaliation from November 2023 to present "
                "based on the email corpus and written communications."
            ),
            "materials_dir": str(materials_dir),
            "output_language": "en",
            "today": "2026-04-13",
        }
    )

    payload = build_case_full_pack(params)

    assert payload["workflow"] == "case_full_pack"
    assert payload["status"] == "blocked"
    blocker_fields = {item["field"] for item in payload["blockers"]}
    assert "case_scope.trigger_events" in blocker_fields
    assert payload["compiled_legal_support_input"]["review_mode"] == "exhaustive_matter_review"
    assert payload["matter_manifest"]["artifacts"]
    trigger_candidate_count = payload["intake_compilation"]["prompt_preflight"]["candidate_structures"]["summary"][
        "trigger_event_candidate_count"
    ]
    assert trigger_candidate_count >= 1
    suggestions = payload["intake_compilation"]["override_suggestions"]
    assert suggestions["repair_mode"] == "explicit_override_required"
    assert "case_scope.trigger_events" in suggestions["blocked_fields"]
    trigger_suggestion = next(item for item in suggestions["suggestions"] if item["field"] == "case_scope.trigger_events")
    assert trigger_suggestion["candidate_values_adequate"] is False
    assert trigger_suggestion["required_fields"] == ["trigger_type", "date"]
    assert trigger_suggestion["minimal_override_example"] == {
        "case_scope": {"trigger_events": [{"trigger_type": None, "date": None}]}
    }
    assert "TODO(human)" not in json.dumps(trigger_suggestion)


def test_build_case_full_pack_merges_overrides_and_becomes_ready(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "message.eml").write_text("Email export note.", encoding="utf-8")

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": (
                "Claimant: employee. Create a lawyer briefing on retaliation from 2025-01-01 to 2025-06-30 "
                "based on the email corpus."
            ),
            "materials_dir": str(materials_dir),
            "output_language": "de",
            "intake_overrides": {
                "case_scope": {
                    "trigger_events": [{"trigger_type": "complaint", "date": "2025-03-01"}],
                    "alleged_adverse_actions": [{"action_type": "task_withdrawal", "date": "2025-03-05"}],
                    "target_person": {"name": "Target Employee", "email": "employee@example.test"},
                }
            },
        }
    )

    payload = build_case_full_pack(params)

    assert payload["status"] == "ready"
    compiled = payload["compiled_legal_support_input"]
    assert compiled["output_language"] == "de"
    assert compiled["review_mode"] == "exhaustive_matter_review"
    assert compiled["case_scope"]["trigger_events"][0]["trigger_type"] == "complaint"
    assert payload["intake_compilation"]["supports_exhaustive_run"] is True


def test_build_case_full_pack_uses_normalized_preflight_scope_for_compilation(tmp_path, monkeypatch) -> None:
    from src import case_full_pack as module

    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "message.eml").write_text("Email export note.", encoding="utf-8")

    monkeypatch.setattr(
        module,
        "_build_preflight",
        lambda _params: {
            "draft_case_scope": {
                "target_person": {"name": "Target Employee", "email": "employee@example.test"},
                "suspected_actors": [{"name": "Line Manager", "email": "manager@example.test"}],
                "context_people": [{"name": "Witness B", "email": "witness.b@example.test"}],
                "institutional_actors": [
                    {
                        "label": "HR mailbox",
                        "actor_type": "shared_mailbox",
                        "email": "hr-mailbox@example.test",
                    }
                ],
                "allegation_focus": ["hostility"],
                "analysis_goal": "neutral_chronology",
                "date_from": "2025-01-01",
                "date_to": "2025-03-31",
            },
            "recommended_source_scope": "emails_and_attachments",
            "matter_factual_context": "## Relevant Email Addresses\n\n- hr-mailbox@example.test",
            "draft_case_analysis_input": {
                "case_scope": {
                    "target_person": {"name": "Target Employee", "email": "employee@example.test"},
                    "suspected_actors": [{"name": "Line Manager", "email": None}],
                    "allegation_focus": ["hostility"],
                    "analysis_goal": "neutral_chronology",
                    "date_from": "2025-01-01",
                    "date_to": "2025-03-31",
                },
                "source_scope": "emails_only",
                "review_mode": "retrieval_only",
                "matter_factual_context": "## Old Context\n\n- stale",
            },
            "candidate_structures": {"summary": {}},
        },
    )

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": "ignored by monkeypatch",
            "materials_dir": str(materials_dir),
            "output_language": "de",
        }
    )

    payload = module.build_case_full_pack(params)

    assert payload["status"] == "ready"
    compiled = payload["compiled_legal_support_input"]
    assert compiled["source_scope"] == "emails_and_attachments"
    assert compiled["matter_factual_context"] == "## Relevant Email Addresses\n\n- hr-mailbox@example.test"
    assert compiled["case_scope"]["suspected_actors"][0]["email"] == "manager@example.test"
    assert compiled["case_scope"]["context_people"] == [
        {"name": "Witness B", "email": "witness.b@example.test", "role_hint": None}
    ]
    assert compiled["case_scope"]["institutional_actors"] == [
        {
            "label": "HR mailbox",
            "actor_type": "shared_mailbox",
            "email": "hr-mailbox@example.test",
            "function": None,
            "notes": None,
        }
    ]


def test_build_case_full_pack_uses_manifest_chat_artifacts_for_mixed_source_scope(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "teams-chat.html").write_text("<html><body>Teams export</body></html>", encoding="utf-8")

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": "Claimant: employee. Build a neutral chronology from 2025-01-01 to 2025-03-31.",
            "materials_dir": str(materials_dir),
            "intake_overrides": {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "allegation_focus": ["hostility"],
                    "analysis_goal": "neutral_chronology",
                    "date_from": "2025-01-01",
                    "date_to": "2025-03-31",
                }
            },
        }
    )

    payload = build_case_full_pack(params)

    assert payload["compiled_legal_support_input"]["source_scope"] == "mixed_case_file"


def test_build_case_full_pack_uses_manifest_non_email_records_for_mixed_source_scope(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "meeting-note.txt").write_text("Gedächtnisprotokoll zur BEM-Besprechung.", encoding="utf-8")

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": "Claimant: employee. Build a neutral chronology from 2025-01-01 to 2025-03-31.",
            "materials_dir": str(materials_dir),
            "intake_overrides": {
                "case_scope": {
                    "target_person": {"name": "Target Employee"},
                    "allegation_focus": ["hostility"],
                    "analysis_goal": "neutral_chronology",
                    "date_from": "2025-01-01",
                    "date_to": "2025-03-31",
                }
            },
        }
    )

    payload = build_case_full_pack(params)

    assert payload["compiled_legal_support_input"]["source_scope"] == "mixed_case_file"


def test_build_case_full_pack_autofills_required_scope_from_materials(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "dossier.md").write_text(
        (
            "# Beweisdossier Target Employee\n"
            "Stand: 12.03.2026\n"
            "02.11.2023: Formale Beschwerde an HR nach behinderungsbedingter Benachteiligung.\n"
            "10.02.2026: Projektentzug nach der Beschwerde und Ausschluss aus dem Arbeitskreis.\n"
        ),
        encoding="utf-8",
    )

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": "Create a lawyer briefing on retaliation based on the supplied dossier materials.",
            "materials_dir": str(materials_dir),
            "output_language": "de",
        }
    )

    payload = build_case_full_pack(params)

    assert payload["status"] == "ready"
    compiled = payload["compiled_legal_support_input"]
    assert compiled["case_scope"]["target_person"]["name"] == "Target Employee"
    assert compiled["case_scope"]["date_from"] == "2023-11-02"
    assert compiled["case_scope"]["date_to"] == "2026-03-12"
    assert compiled["case_scope"]["trigger_events"][0]["trigger_type"] == "complaint"
    assert compiled["case_scope"]["alleged_adverse_actions"][0]["action_type"] == "project_removal"
    assert (
        payload["intake_compilation"]["materials_preflight"]["candidate_structures"]["summary"]["target_person_candidate_count"]
        == 1
    )


def test_build_case_full_pack_keeps_material_target_ambiguity_blocked(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "dossier-a.md").write_text("# Beweisdossier Target Employee\n02.11.2023 Beschwerde", encoding="utf-8")
    (materials_dir / "dossier-b.md").write_text("# Beweisdossier Reference Employee\n10.02.2026 Projektentzug", encoding="utf-8")

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": "Create a lawyer briefing on retaliation based on the supplied dossier materials.",
            "materials_dir": str(materials_dir),
            "output_language": "de",
        }
    )

    payload = build_case_full_pack(params)

    blocker_fields = {item["field"] for item in payload["blockers"]}
    assert payload["status"] == "blocked"
    assert "case_scope.target_person" in blocker_fields
    target_suggestion = next(
        item
        for item in payload["intake_compilation"]["override_suggestions"]["suggestions"]
        if item["field"] == "case_scope.target_person"
    )
    assert len(target_suggestion["candidate_values"]) == 2
    assert {item["candidate_value"]["name"] for item in target_suggestion["candidate_values"]} == {
        "Target Employee",
        "Reference Employee",
    }


def test_execute_case_full_pack_stops_on_blockers_without_running(tmp_path, monkeypatch) -> None:
    from src import case_full_pack as module

    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")
    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": "Claimant: employee. Review retaliation from 2025-01-01 to 2025-06-30.",
            "materials_dir": str(materials_dir),
        }
    )

    async def fake_build_case_analysis_payload(_deps, _params):
        raise AssertionError("build_case_analysis_payload should not run when blockers remain")

    monkeypatch.setattr(module, "build_case_analysis_payload", fake_build_case_analysis_payload)

    payload = asyncio.run(module.execute_case_full_pack(object(), params))

    assert payload["status"] == "blocked"
    assert payload["blockers"]


def test_execute_case_full_pack_runs_and_exports(tmp_path, monkeypatch) -> None:
    from src import case_full_pack as module

    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")
    output_path = tmp_path / "handoff.bundle"
    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": "Claimant: employee. Review retaliation from 2025-01-01 to 2025-06-30.",
            "materials_dir": str(materials_dir),
            "output_path": str(output_path),
            "intake_overrides": {
                "case_scope": {
                    "target_person": {"name": "Target Employee", "email": "employee@example.test"},
                    "allegation_focus": ["retaliation"],
                    "analysis_goal": "lawyer_briefing",
                    "date_from": "2025-01-01",
                    "date_to": "2025-06-30",
                    "trigger_events": [{"trigger_type": "complaint", "date": "2025-03-01"}],
                    "alleged_adverse_actions": [{"action_type": "task_withdrawal", "date": "2025-03-05"}],
                }
            },
        }
    )

    async def fake_build_case_analysis_payload(_deps, full_params):
        assert full_params.review_mode == "exhaustive_matter_review"
        return {
            "workflow": "case_analysis",
            "review_mode": "exhaustive_matter_review",
            "matter_persistence": {"snapshot_id": "", "workspace_id": "", "review_state": ""},
        }

    class _FakeExporter:
        def export_file(self, *, payload, output_path, delivery_target, delivery_format):
            assert payload["workflow"] == "case_analysis"
            assert delivery_target == "counsel_handoff_bundle"
            assert delivery_format == "bundle"
            return {"output_path": output_path, "delivery_target": delivery_target, "delivery_format": delivery_format}

    monkeypatch.setattr(module, "build_case_analysis_payload", fake_build_case_analysis_payload)
    monkeypatch.setattr(module, "LegalSupportExporter", lambda: _FakeExporter())

    payload = asyncio.run(module.execute_case_full_pack(object(), params))

    assert payload["status"] == "completed"
    assert payload["execution"]["status"] == "completed"
    assert payload["full_case_analysis"]["workflow"] == "case_analysis"
    assert payload["export_result"]["delivery_target"] == "counsel_handoff_bundle"


def test_build_case_full_pack_keeps_candidate_structures_review_facing(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "records.txt").write_text("Prompt support note.", encoding="utf-8")

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": (
                "Claimant: employee. Complaint on 2025-03-01 to HR after disability disclosure. Task withdrawal on 2025-03-05."
            ),
            "materials_dir": str(materials_dir),
        }
    )

    payload = build_case_full_pack(params)

    preflight = payload["intake_compilation"]["prompt_preflight"]
    assert preflight["candidate_structures"]["summary"]["trigger_event_candidate_count"] >= 1
    assert preflight["candidate_structures"]["summary"]["adverse_action_candidate_count"] >= 1
    assert payload["status"] == "blocked"
    assert payload["compiled_legal_support_input"]["case_scope"]["trigger_events"] == []


def test_build_case_full_pack_emits_actionable_override_suggestions_from_candidates(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "records.txt").write_text("Prompt support note.", encoding="utf-8")

    params = EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": (
                "Claimant: employee. Review retaliation. Complaint on 2025-03-01 to HR after disability disclosure. "
                "Task withdrawal on 2025-03-05 and compare treatment with colleague: Pat Vergleich."
            ),
            "materials_dir": str(materials_dir),
        }
    )

    payload = build_case_full_pack(params)

    suggestions = payload["intake_compilation"]["override_suggestions"]
    trigger_suggestion = next(item for item in suggestions["suggestions"] if item["field"] == "case_scope.trigger_events")
    adverse_suggestion = next(
        item for item in suggestions["suggestions"] if item["field"] == "case_scope.alleged_adverse_actions"
    )
    assert trigger_suggestion["candidate_values_adequate"] is True
    assert adverse_suggestion["candidate_values_adequate"] is True
    assert trigger_suggestion["candidate_values"][0]["candidate_value"] == {
        "trigger_type": "complaint",
        "date": "2025-03-01",
        "date_confidence": "exact",
    }
    assert adverse_suggestion["candidate_values"][0]["candidate_value"] == {
        "action_type": "task_withdrawal",
        "date": "2025-03-05",
    }
    assert suggestions["example_override_json"]["case_scope"]["trigger_events"][0]["date"] == "2025-03-01"
    assert suggestions["example_override_json"]["case_scope"]["alleged_adverse_actions"][0]["date"] == "2025-03-05"


def test_full_pack_prompt_family_fixtures_emit_repairable_blockers(tmp_path) -> None:
    materials_dir = tmp_path / "matter"
    materials_dir.mkdir()
    (materials_dir / "record.txt").write_text("Meeting note.", encoding="utf-8")

    cases = [
        {
            "fixture": "prompt_fixture.retaliation_heavy.md",
            "blocked_field": "case_scope.trigger_events",
            "suggested_field": "case_scope.trigger_events",
        },
        {
            "fixture": "prompt_fixture.comparator_heavy.md",
            "blocked_field": None,
            "suggested_field": None,
        },
        {
            "fixture": "prompt_fixture.mixed_source_documentary.md",
            "blocked_field": "case_scope.trigger_events",
            "suggested_field": "case_scope.trigger_events",
        },
    ]

    for case in cases:
        payload = build_case_full_pack(
            EmailCaseFullPackInput.model_validate(
                {
                    "prompt_text": (FIXTURE_DIR / case["fixture"]).read_text(encoding="utf-8"),
                    "materials_dir": str(materials_dir),
                }
            )
        )

        blocker_fields = {item["field"] for item in payload["blockers"]}
        if case["blocked_field"] is None:
            assert payload["intake_compilation"]["override_suggestions"] is None
            continue
        assert case["blocked_field"] in blocker_fields
        suggestions = payload["intake_compilation"]["override_suggestions"]
        assert suggestions["repair_mode"] == "explicit_override_required"
        assert case["suggested_field"] in suggestions["blocked_fields"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", acceptance_case_ids())
async def test_realistic_fixture_cases_execute_full_pack(case_id: str) -> None:
    payload = await execute_fixture_full_pack(case_id)

    case = acceptance_case(case_id)
    assert payload["workflow"] == "case_full_pack"
    assert payload["status"] == "completed"
    assert payload["acceptance_lane"] == {"mode": "fixture_assembly", "retrieval_sensitive": False}
    full_case_analysis = payload["full_case_analysis"]
    for product in case.expected_products:
        assert product in full_case_analysis
    source_classes = set(
        full_case_analysis["matter_ingestion_report"]["summary"]["source_class_counts"],
    )
    for source_class in case.expected_source_classes:
        assert source_class in source_classes
    issue_ids = {row["issue_id"] for row in full_case_analysis["lawyer_issue_matrix"]["rows"]}
    for issue_id in case.expected_issue_ids:
        assert issue_id in issue_ids


@pytest.mark.asyncio
async def test_retrieval_fixture_case_executes_real_retrieval_lane() -> None:
    payload = await execute_retrieval_fixture_full_pack("retaliation_rights_assertion")

    assert payload["workflow"] == "case_full_pack"
    assert payload["status"] == "completed"
    assert payload["acceptance_lane"]["mode"] == "retrieval_fixture"
    assert payload["acceptance_lane"]["retrieval_sensitive"] is True
    assert int(payload["acceptance_lane"].get("corpus_email_count") or 0) >= 1
    full_case_analysis = payload["full_case_analysis"]
    assert len(full_case_analysis.get("candidates") or []) >= 1
    assert full_case_analysis["archive_harvest"]["candidate_pool_count"] >= 1
    assert "retaliation_massregelungsverbot" in {row["issue_id"] for row in full_case_analysis["lawyer_issue_matrix"]["rows"]}


@pytest.mark.asyncio
async def test_realistic_retaliation_fixture_blocks_then_repairs() -> None:
    blocked = build_case_full_pack(build_fixture_full_pack_input("retaliation_rights_assertion", blocked=True))
    assert blocked["status"] == "blocked"
    assert {item["field"] for item in blocked["blockers"]} >= {"case_scope.alleged_adverse_actions"}

    repaired = await execute_fixture_full_pack("retaliation_rights_assertion")
    assert repaired["status"] == "completed"
    assert repaired["full_case_analysis"]["retaliation_analysis"]["retaliation_point_count"] == 1


@pytest.mark.asyncio
async def test_realistic_comparator_fixture_blocks_then_repairs() -> None:
    blocked = build_case_full_pack(build_fixture_full_pack_input("comparator_unequal_treatment", blocked=True))
    assert blocked["status"] == "ready"
    assert blocked["blockers"] == []

    repaired = await execute_fixture_full_pack("comparator_unequal_treatment")
    assert repaired["status"] == "completed"
    comparator_points = repaired["full_case_analysis"]["comparative_treatment"]["comparator_points"]
    assert comparator_points
    assert comparator_points[0]["comparison_quality"] == "high_quality_comparator"
