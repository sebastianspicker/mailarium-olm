"""Case definitions and JSON loading helpers for QA evaluation."""
# pylint: disable=too-many-instance-attributes

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
    return [_question_case(item) for item in case_items]


_OPTIONAL_STRING_FIELDS = {
    "expected_top_uid",
    "expected_ambiguity",
    "expected_thread_group_id",
    "expected_thread_group_source",
    "expected_max_claim_level",
    "expected_draft_ceiling_level",
}
_FILTERED_LIST_FIELDS = {
    "expected_answer_terms",
    "expected_support_source_ids",
    "expected_case_bundle_source_ids",
    "expected_timeline_source_ids",
    "expected_legal_support_source_ids",
    "forbidden_support_uids",
    "forbidden_support_source_ids",
    "forbidden_issue_ids",
    "forbidden_actor_ids",
    "forbidden_dashboard_cards",
    "forbidden_checklist_group_ids",
}


def _question_case(item: dict[str, Any]) -> QuestionCase:
    values: dict[str, Any] = {"id": str(item["id"]), "bucket": str(item["bucket"]), "question": str(item["question"])}
    defaults = QuestionCase(**values)
    for name in QuestionCase.__dataclass_fields__:
        if name in values or name == "case_scope":
            continue
        raw = item.get(name, getattr(defaults, name))
        values[name] = _normalize_case_field(name, raw)
    values["case_scope"] = BehavioralCaseScopeInput.model_validate(item["case_scope"]) if item.get("case_scope") else None
    return QuestionCase(**values)


def _normalize_case_field(name: str, value: Any) -> Any:
    if name in {"filters", "benchmark_pack"}:
        return dict(value or {})
    if name in _OPTIONAL_STRING_FIELDS:
        return _optional_case_string(name, value)
    if name == "expected_quoted_speaker_emails":
        return [str(item).lower() for item in value or []]
    if isinstance(value, list):
        return _case_string_list(name, value)
    return str(value or "")


def _optional_case_string(name: str, value: Any) -> str | None:
    if not value:
        return None
    normalized = str(value)
    return normalized.lower() if name == "expected_thread_group_source" else normalized


def _case_string_list(name: str, values: list[Any]) -> list[str]:
    if name in _FILTERED_LIST_FIELDS:
        return [str(item) for item in values if str(item).strip()]
    return [str(item) for item in values]
