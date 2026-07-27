"""Question definitions and JSON loading helpers for QA evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass(slots=True)
class QuestionCase:
    """One generic retrieval question with optional expected evidence labels."""

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
    forbidden_support_uids: list[str] = field(default_factory=list)
    forbidden_support_source_ids: list[str] = field(default_factory=list)
    triage_tags: list[str] = field(default_factory=list)
    notes: str = ""


_OPTIONAL_STRING_FIELDS = {
    "expected_top_uid",
    "expected_ambiguity",
    "expected_thread_group_id",
    "expected_thread_group_source",
}
_FILTERED_LIST_FIELDS = {
    "expected_answer_terms",
    "expected_support_uids",
    "expected_support_source_ids",
    "expected_quoted_speaker_emails",
    "forbidden_support_uids",
    "forbidden_support_source_ids",
    "triage_tags",
}
_BOOTSTRAP_ONLY_FIELDS = {
    "bootstrap_candidates",
    "bootstrap_label_status",
    "bootstrap_observation",
}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_question_cases(path: Path) -> list[QuestionCase]:
    """Load and validate question-case mappings from a list or versioned case document."""
    raw = _load_json(path)
    case_items = raw["cases"] if isinstance(raw, dict) else raw
    if not isinstance(case_items, list):
        raise ValueError("questions file must contain a list of cases")
    return [_question_case(item) for item in case_items if isinstance(item, dict)]


def _question_case(item: dict[str, Any]) -> QuestionCase:
    unknown_fields = sorted(set(item) - set(QuestionCase.__dataclass_fields__) - _BOOTSTRAP_ONLY_FIELDS)
    if unknown_fields:
        raise ValueError(f"unsupported question-case field(s): {', '.join(unknown_fields)}")
    required = {
        "id": str(item["id"]),
        "bucket": str(item["bucket"]),
        "question": str(item["question"]),
    }
    defaults = QuestionCase(**cast(Any, required))
    values: dict[str, Any] = dict(required)
    for name in QuestionCase.__dataclass_fields__:
        if name in values:
            continue
        values[name] = _normalize_case_field(name, item.get(name, getattr(defaults, name)))
    return QuestionCase(**cast(Any, values))


def _normalize_case_field(name: str, value: Any) -> Any:
    if name == "filters":
        return dict(value or {})
    if name in _OPTIONAL_STRING_FIELDS:
        return _normalize_optional_string(name, value)
    if name in _FILTERED_LIST_FIELDS:
        return _normalize_case_list(name, value)
    return str(value or "")


def _normalize_optional_string(name: str, value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value)
    return normalized.casefold() if name == "expected_thread_group_source" else normalized


def _normalize_case_list(name: str, value: Any) -> list[str]:
    normalized = [str(item).strip() for item in value or [] if str(item).strip()]
    if name == "expected_quoted_speaker_emails":
        return [item.casefold() for item in normalized]
    return normalized
