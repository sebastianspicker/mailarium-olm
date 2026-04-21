"""Case definitions and JSON loading helpers for QA evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .mcp_models import BehavioralCaseScopeInput


@dataclass(slots=True)
class QuestionCase:
    """One evaluation question with optional expected evidence labels."""

    id: str
    bucket: str
    question: str
    status: str = "todo"
    evidence_mode: str = "retrieval"
    filters: dict[str, Any] = field(default_factory=dict)
    expected_answer: str = ""
    expected_answer_terms: list[str] = field(default_factory=list)
    expected_support_uids: list[str] = field(default_factory=list)
    expected_support_source_ids: list[str] = field(default_factory=list)
    expected_top_uid: str | None = None
    expected_ambiguity: str | None = None
    expected_quoted_speaker_emails: list[str] = field(default_factory=list)
    expected_thread_group_id: str | None = None
    expected_thread_group_source: str | None = None
    benchmark_pack: dict[str, Any] = field(default_factory=dict)
    case_scope: BehavioralCaseScopeInput | None = None
    expected_case_bundle_uids: list[str] = field(default_factory=list)
    expected_case_bundle_source_ids: list[str] = field(default_factory=list)
    expected_source_types: list[str] = field(default_factory=list)
    expected_timeline_uids: list[str] = field(default_factory=list)
    expected_timeline_source_ids: list[str] = field(default_factory=list)
    expected_behavior_ids: list[str] = field(default_factory=list)
    expected_counter_indicator_markers: list[str] = field(default_factory=list)
    expected_max_claim_level: str | None = None
    expected_report_sections: list[str] = field(default_factory=list)
    expected_legal_support_products: list[str] = field(default_factory=list)
    expected_legal_support_source_ids: list[str] = field(default_factory=list)
    expected_comparator_issue_ids: list[str] = field(default_factory=list)
    expected_dashboard_cards: list[str] = field(default_factory=list)
    expected_actor_ids: list[str] = field(default_factory=list)
    expected_checklist_group_ids: list[str] = field(default_factory=list)
    expected_draft_ceiling_level: str | None = None
    expected_draft_sections: list[str] = field(default_factory=list)
    forbidden_support_uids: list[str] = field(default_factory=list)
    forbidden_support_source_ids: list[str] = field(default_factory=list)
    forbidden_issue_ids: list[str] = field(default_factory=list)
    forbidden_actor_ids: list[str] = field(default_factory=list)
    forbidden_dashboard_cards: list[str] = field(default_factory=list)
    forbidden_checklist_group_ids: list[str] = field(default_factory=list)
    triage_tags: list[str] = field(default_factory=list)
    notes: str = ""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_question_cases(path: Path) -> list[QuestionCase]:
    """Load evaluation question cases from a JSON file."""
    raw = _load_json(path)
    case_items = raw["cases"] if isinstance(raw, dict) else raw
    cases: list[QuestionCase] = []
    for item in case_items:
        cases.append(
            QuestionCase(
                id=str(item["id"]),
                bucket=str(item["bucket"]),
                question=str(item["question"]),
                status=str(item.get("status", "todo")),
                evidence_mode=str(item.get("evidence_mode", "retrieval")),
                filters=dict(item.get("filters") or {}),
                expected_answer=str(item.get("expected_answer", "")),
                expected_answer_terms=[str(term) for term in item.get("expected_answer_terms", []) if str(term).strip()],
                expected_support_uids=[str(uid) for uid in item.get("expected_support_uids", [])],
                expected_support_source_ids=[
                    str(source_id) for source_id in item.get("expected_support_source_ids", []) if str(source_id).strip()
                ],
                expected_top_uid=str(item["expected_top_uid"]) if item.get("expected_top_uid") else None,
                expected_ambiguity=str(item["expected_ambiguity"]) if item.get("expected_ambiguity") else None,
                expected_quoted_speaker_emails=[str(email).lower() for email in item.get("expected_quoted_speaker_emails", [])],
                expected_thread_group_id=(
                    str(item["expected_thread_group_id"]) if item.get("expected_thread_group_id") else None
                ),
                expected_thread_group_source=(
                    str(item["expected_thread_group_source"]).lower() if item.get("expected_thread_group_source") else None
                ),
                benchmark_pack=dict(item.get("benchmark_pack") or {}),
                case_scope=(BehavioralCaseScopeInput.model_validate(item["case_scope"]) if item.get("case_scope") else None),
                expected_case_bundle_uids=[str(uid) for uid in item.get("expected_case_bundle_uids", [])],
                expected_case_bundle_source_ids=[
                    str(source_id) for source_id in item.get("expected_case_bundle_source_ids", []) if str(source_id).strip()
                ],
                expected_source_types=[str(source_type) for source_type in item.get("expected_source_types", [])],
                expected_timeline_uids=[str(uid) for uid in item.get("expected_timeline_uids", [])],
                expected_timeline_source_ids=[
                    str(source_id) for source_id in item.get("expected_timeline_source_ids", []) if str(source_id).strip()
                ],
                expected_behavior_ids=[str(behavior_id) for behavior_id in item.get("expected_behavior_ids", [])],
                expected_counter_indicator_markers=[str(marker) for marker in item.get("expected_counter_indicator_markers", [])],
                expected_max_claim_level=(
                    str(item["expected_max_claim_level"]) if item.get("expected_max_claim_level") else None
                ),
                expected_report_sections=[str(section_id) for section_id in item.get("expected_report_sections", [])],
                expected_legal_support_products=[
                    str(product_id) for product_id in item.get("expected_legal_support_products", [])
                ],
                expected_legal_support_source_ids=[
                    str(source_id) for source_id in item.get("expected_legal_support_source_ids", []) if str(source_id).strip()
                ],
                expected_comparator_issue_ids=[str(issue_id) for issue_id in item.get("expected_comparator_issue_ids", [])],
                expected_dashboard_cards=[str(card_id) for card_id in item.get("expected_dashboard_cards", [])],
                expected_actor_ids=[str(actor_id) for actor_id in item.get("expected_actor_ids", [])],
                expected_checklist_group_ids=[str(group_id) for group_id in item.get("expected_checklist_group_ids", [])],
                expected_draft_ceiling_level=(
                    str(item["expected_draft_ceiling_level"]) if item.get("expected_draft_ceiling_level") else None
                ),
                expected_draft_sections=[str(section_id) for section_id in item.get("expected_draft_sections", [])],
                forbidden_support_uids=[str(uid) for uid in item.get("forbidden_support_uids", []) if str(uid).strip()],
                forbidden_support_source_ids=[
                    str(source_id) for source_id in item.get("forbidden_support_source_ids", []) if str(source_id).strip()
                ],
                forbidden_issue_ids=[str(issue_id) for issue_id in item.get("forbidden_issue_ids", []) if str(issue_id).strip()],
                forbidden_actor_ids=[str(actor_id) for actor_id in item.get("forbidden_actor_ids", []) if str(actor_id).strip()],
                forbidden_dashboard_cards=[
                    str(card_id) for card_id in item.get("forbidden_dashboard_cards", []) if str(card_id).strip()
                ],
                forbidden_checklist_group_ids=[
                    str(group_id) for group_id in item.get("forbidden_checklist_group_ids", []) if str(group_id).strip()
                ],
                triage_tags=[str(tag) for tag in item.get("triage_tags", [])],
                notes=str(item.get("notes", "")),
            )
        )
    return cases
