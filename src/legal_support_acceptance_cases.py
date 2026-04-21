"""Fixture case declarations for realistic legal-support acceptance scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mcp_models import EmailCaseFullPackInput

_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = _ROOT / "tests" / "fixtures" / "full_pack_matters"


@dataclass(frozen=True)
class FullPackAcceptanceCase:
    """Definition for one realistic full-pack fixture matter."""

    case_id: str
    prompt_text: str
    blocked_prompt_text: str | None
    intake_overrides: dict[str, Any]
    expected_source_classes: tuple[str, ...]
    expected_products: tuple[str, ...]
    expected_issue_ids: tuple[str, ...]


FIXTURE_CASES: dict[str, FullPackAcceptanceCase] = {
    "disability_participation_failures": FullPackAcceptanceCase(
        case_id="disability_participation_failures",
        prompt_text=(
            "Claimant: Target Employee. Prepare a neutral lawyer briefing from 2025-01-01 to 2025-06-30 on "
            "disability-related disadvantage, SBV/PR participation, ignored medical recommendations, mobile-work "
            "restrictions, and prevention/BEM failures based on all supplied matter materials."
        ),
        blocked_prompt_text=None,
        intake_overrides={
            "case_scope": {
                "target_person": {"name": "Target Employee", "email": "employee@example.test", "role_hint": "employee"},
                "suspected_actors": [
                    {"name": "manager", "email": "manager@example.test", "role_hint": "manager"},
                    {"name": "Hanna HR", "email": "hr@example.org", "role_hint": "hr"},
                ],
                "allegation_focus": ["exclusion"],
                "employment_issue_tracks": [
                    "disability_disadvantage",
                    "participation_duty_gap",
                    "prevention_duty_gap",
                ],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        },
        expected_source_classes=(
            "formal_document",
            "note_record",
            "attendance_export",
            "calendar_export",
            "chat_export",
            "participation_record",
            "screenshot",
        ),
        expected_products=(
            "matter_evidence_index",
            "master_chronology",
            "lawyer_issue_matrix",
            "case_dashboard",
            "document_request_checklist",
        ),
        expected_issue_ids=(
            "agg_disadvantage",
            "sgb_ix_178_sbv",
            "sgb_ix_167_bem",
        ),
    ),
    "retaliation_rights_assertion": FullPackAcceptanceCase(
        case_id="retaliation_rights_assertion",
        prompt_text=(
            "Claimant: Target Employee. Prepare a lawyer briefing from 2025-01-01 to 2025-06-30 on retaliation "
            "after disability-related rights assertions, project withdrawal, tighter controls, and exclusion from "
            "process based on all supplied matter materials."
        ),
        blocked_prompt_text=(
            "Claimant: Target Employee. Review retaliation from 2025-01-01 to 2025-06-30 after rights assertions "
            "based on all supplied matter materials."
        ),
        intake_overrides={
            "case_scope": {
                "target_person": {"name": "Target Employee", "email": "employee@example.test", "role_hint": "employee"},
                "suspected_actors": [
                    {"name": "manager", "email": "manager@example.test", "role_hint": "manager"},
                    {"name": "Hanna HR", "email": "hr@example.org", "role_hint": "hr"},
                ],
                "allegation_focus": ["retaliation", "exclusion"],
                "employment_issue_tracks": ["retaliation_after_protected_event"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
                "trigger_events": [{"trigger_type": "complaint", "date": "2025-03-01"}],
                "alleged_adverse_actions": [{"action_type": "task_withdrawal", "date": "2025-03-05"}],
            }
        },
        expected_source_classes=(
            "formal_document",
            "note_record",
            "attendance_export",
            "calendar_export",
            "chat_export",
            "screenshot",
        ),
        expected_products=(
            "retaliation_analysis",
            "lawyer_briefing_memo",
            "controlled_factual_drafting",
            "case_dashboard",
        ),
        expected_issue_ids=("retaliation_massregelungsverbot",),
    ),
    "comparator_unequal_treatment": FullPackAcceptanceCase(
        case_id="comparator_unequal_treatment",
        prompt_text=(
            "Claimant: Target Employee. Compare the claimant's treatment from 2025-01-01 to 2025-06-30 with "
            "comparable colleagues regarding mobile work, control intensity, SBV/PR process, and training access, "
            "using all supplied matter materials."
        ),
        blocked_prompt_text=(
            "Claimant: Target Employee. Compare unequal treatment from 2025-01-01 to 2025-06-30 regarding mobile "
            "work, control intensity, and SBV/PR process using all supplied matter materials."
        ),
        intake_overrides={
            "case_scope": {
                "target_person": {"name": "Target Employee", "email": "employee@example.test", "role_hint": "employee"},
                "suspected_actors": [
                    {"name": "manager", "email": "manager@example.test", "role_hint": "manager"},
                    {"name": "Hanna HR", "email": "hr@example.org", "role_hint": "hr"},
                ],
                "comparator_actors": [{"name": "Pat Vergleich", "email": "pat@example.org", "role_hint": "peer"}],
                "allegation_focus": ["unequal_treatment", "discrimination"],
                "employment_issue_tracks": ["disability_disadvantage", "participation_duty_gap"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        },
        expected_source_classes=(
            "formal_document",
            "note_record",
            "attendance_export",
            "calendar_export",
            "chat_export",
            "participation_record",
        ),
        expected_products=(
            "comparative_treatment",
            "lawyer_issue_matrix",
            "skeptical_employer_review",
            "case_dashboard",
        ),
        expected_issue_ids=("agg_disadvantage",),
    ),
    "eingruppierung_task_withdrawal": FullPackAcceptanceCase(
        case_id="eingruppierung_task_withdrawal",
        prompt_text=(
            "Claimant: Target Employee. Prepare a lawyer briefing from 2025-01-01 to 2025-06-30 on "
            "Eingruppierung, task withdrawal, Tätigkeitsdarstellung, and changes in actual duties using all "
            "supplied matter materials."
        ),
        blocked_prompt_text=None,
        intake_overrides={
            "case_scope": {
                "target_person": {"name": "Target Employee", "email": "employee@example.test", "role_hint": "employee"},
                "suspected_actors": [{"name": "manager", "email": "manager@example.test", "role_hint": "manager"}],
                "allegation_focus": ["exclusion"],
                "employment_issue_tracks": ["eingruppierung_dispute"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        },
        expected_source_classes=(
            "formal_document",
            "note_record",
            "attendance_export",
            "calendar_export",
            "screenshot",
        ),
        expected_products=(
            "matter_evidence_index",
            "master_chronology",
            "lawyer_issue_matrix",
            "lawyer_briefing_memo",
        ),
        expected_issue_ids=("eingruppierung_tarifliche_bewertung",),
    ),
    "chronology_contradiction": FullPackAcceptanceCase(
        case_id="chronology_contradiction",
        prompt_text=(
            "Claimant: Target Employee. Build a neutral chronology from 2025-01-01 to 2025-06-30 and review all "
            "meeting notes, summaries, follow-up emails, and contradictions using all supplied matter materials."
        ),
        blocked_prompt_text=None,
        intake_overrides={
            "case_scope": {
                "target_person": {"name": "Target Employee", "email": "employee@example.test", "role_hint": "employee"},
                "suspected_actors": [{"name": "manager", "email": "manager@example.test", "role_hint": "manager"}],
                "allegation_focus": ["exclusion"],
                "employment_issue_tracks": ["participation_duty_gap"],
                "analysis_goal": "neutral_chronology",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        },
        expected_source_classes=(
            "formal_document",
            "note_record",
            "calendar_export",
            "chat_export",
            "screenshot",
        ),
        expected_products=(
            "master_chronology",
            "promise_contradiction_analysis",
            "actor_map",
            "witness_map",
            "case_dashboard",
        ),
        expected_issue_ids=("sgb_ix_178_sbv",),
    ),
}


def acceptance_case(case_id: str) -> FullPackAcceptanceCase:
    """Return one declared realistic fixture case."""
    return FIXTURE_CASES[case_id]


def acceptance_case_dir(case_id: str) -> Path:
    """Return the on-disk matter directory for one realistic fixture case."""
    return FIXTURE_ROOT / case_id


def acceptance_case_ids() -> tuple[str, ...]:
    """Return the declared realistic fixture ids in stable order."""
    return tuple(FIXTURE_CASES)


def build_fixture_full_pack_input(
    case_id: str,
    *,
    output_path: str | None = None,
    blocked: bool = False,
    compile_only: bool = False,
) -> EmailCaseFullPackInput:
    """Return one full-pack input bound to a committed realistic fixture folder."""
    case = acceptance_case(case_id)
    return EmailCaseFullPackInput.model_validate(
        {
            "prompt_text": case.blocked_prompt_text if blocked and case.blocked_prompt_text else case.prompt_text,
            "materials_dir": str(acceptance_case_dir(case_id)),
            "output_path": output_path,
            "compile_only": compile_only,
            "intake_overrides": {} if blocked else case.intake_overrides,
            "output_language": "de",
            "translation_mode": "translation_aware",
            "privacy_mode": "external_counsel_export",
            "today": "2026-04-13",
        }
    )
