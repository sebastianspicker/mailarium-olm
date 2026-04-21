# mypy: disable-error-code=name-defined
"""Split QA evaluation scoring helpers (qa_eval_scoring_legal_metrics)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .qa_eval_cases import QuestionCase

_ANSWER_TERM_RE = re.compile(r"[0-9a-zA-ZäöüÄÖÜß._-]+")
_ANSWER_STOPWORDS = {
    "aber",
    "after",
    "and",
    "auch",
    "because",
    "beim",
    "beziehungsweise",
    "dann",
    "dass",
    "dem",
    "denn",
    "der",
    "des",
    "die",
    "dies",
    "does",
    "eine",
    "einer",
    "eines",
    "evidence",
    "from",
    "have",
    "into",
    "kein",
    "keine",
    "likely",
    "message",
    "nach",
    "oder",
    "over",
    "says",
    "sein",
    "some",
    "that",
    "their",
    "there",
    "these",
    "this",
    "under",
    "used",
    "with",
    "without",
}

# ruff: noqa: F401,F821


def _legal_support_product_completeness(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_legal_support_products:
        return None
    for product_id in case.expected_legal_support_products:
        product = payload.get(product_id)
        if not isinstance(product, dict) or not product or not _dict_has_substance(product):
            return False
    return True


def _legal_support_grounding_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_legal_support_source_ids:
        return None
    observed = _legal_support_product_source_ids(payload, product_ids=case.expected_legal_support_products)
    return any(source_id in observed for source_id in case.expected_legal_support_source_ids)


def _legal_support_grounding_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_legal_support_source_ids:
        return None
    observed = _legal_support_product_source_ids(payload, product_ids=case.expected_legal_support_products)
    matched = [source_id for source_id in case.expected_legal_support_source_ids if source_id in observed]
    return _ratio(len(matched), len(case.expected_legal_support_source_ids))


def _observed_comparator_issue_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    comparative_treatment = payload.get("comparative_treatment")
    if not isinstance(comparative_treatment, dict):
        return observed
    for summary in comparative_treatment.get("comparator_summaries", []) or []:
        if not isinstance(summary, dict):
            continue
        matrix = summary.get("comparator_matrix")
        if not isinstance(matrix, dict):
            continue
        for row in matrix.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            issue_id = str(row.get("issue_id") or "")
            if issue_id and issue_id not in observed:
                observed.append(issue_id)
    return observed


def _comparator_matrix_coverage(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_comparator_issue_ids:
        return None
    observed = _observed_comparator_issue_ids(payload)
    matched = [issue_id for issue_id in case.expected_comparator_issue_ids if issue_id in observed]
    return _ratio(len(matched), len(case.expected_comparator_issue_ids))


def _dashboard_card_coverage(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_dashboard_cards:
        return None
    dashboard = payload.get("case_dashboard")
    if not isinstance(dashboard, dict):
        return 0.0
    cards = dashboard.get("cards")
    if not isinstance(cards, dict):
        return 0.0
    matched = 0
    for card_id in case.expected_dashboard_cards:
        rows = cards.get(card_id)
        if isinstance(rows, list) and any(isinstance(item, dict) for item in rows):
            matched += 1
    return _ratio(matched, len(case.expected_dashboard_cards))


def _actor_map_coverage(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_actor_ids:
        return None
    actor_map = payload.get("actor_map")
    if not isinstance(actor_map, dict):
        return 0.0
    observed = {
        str(actor.get("actor_id") or "")
        for actor in actor_map.get("actors", []) or []
        if isinstance(actor, dict) and str(actor.get("actor_id") or "")
    }
    matched = [actor_id for actor_id in case.expected_actor_ids if actor_id in observed]
    return _ratio(len(matched), len(case.expected_actor_ids))


def _checklist_group_coverage(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_checklist_group_ids:
        return None
    checklist = payload.get("document_request_checklist")
    if not isinstance(checklist, dict):
        return 0.0
    observed = {
        str(group.get("group_id") or "")
        for group in checklist.get("groups", []) or []
        if isinstance(group, dict) and str(group.get("group_id") or "")
    }
    matched = [group_id for group_id in case.expected_checklist_group_ids if group_id in observed]
    return _ratio(len(matched), len(case.expected_checklist_group_ids))


def _drafting_ceiling_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_draft_ceiling_level:
        return None
    drafting = payload.get("controlled_factual_drafting")
    if not isinstance(drafting, dict):
        return False
    preflight = drafting.get("framing_preflight")
    if not isinstance(preflight, dict):
        return False
    allegation_ceiling = preflight.get("allegation_ceiling")
    if not isinstance(allegation_ceiling, dict):
        return False
    return str(allegation_ceiling.get("ceiling_level") or "") == case.expected_draft_ceiling_level


def _draft_section_completeness(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_draft_sections:
        return None
    drafting = payload.get("controlled_factual_drafting")
    if not isinstance(drafting, dict):
        return False
    draft = drafting.get("controlled_draft")
    if not isinstance(draft, dict):
        return False
    sections = draft.get("sections")
    if not isinstance(sections, dict):
        return False
    for section_id in case.expected_draft_sections:
        rows = sections.get(section_id)
        if not isinstance(rows, list) or not any(isinstance(item, dict) for item in rows):
            return False
    return True


def _forbidden_support_ids_excluded(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    observed = [*_candidate_uids(payload), *_observed_support_source_ids(payload), *_bundle_support_source_ids(payload)]
    return _forbidden_values_absent([*case.forbidden_support_uids, *case.forbidden_support_source_ids], observed)


def _forbidden_issue_ids_excluded(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    return _forbidden_values_absent(case.forbidden_issue_ids, _observed_issue_ids(payload))


def _forbidden_actor_ids_excluded(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    return _forbidden_values_absent(case.forbidden_actor_ids, _observed_actor_ids(payload))


def _forbidden_dashboard_cards_excluded(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    return _forbidden_values_absent(case.forbidden_dashboard_cards, _observed_dashboard_card_ids(payload))


def _forbidden_checklist_groups_excluded(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    return _forbidden_values_absent(case.forbidden_checklist_group_ids, _observed_checklist_group_ids(payload))


__all__ = [
    "_ANSWER_STOPWORDS",
    "_ANSWER_TERM_RE",
    "_actor_map_coverage",
    "_checklist_group_coverage",
    "_comparator_matrix_coverage",
    "_dashboard_card_coverage",
    "_draft_section_completeness",
    "_drafting_ceiling_match",
    "_forbidden_actor_ids_excluded",
    "_forbidden_checklist_groups_excluded",
    "_forbidden_dashboard_cards_excluded",
    "_forbidden_issue_ids_excluded",
    "_forbidden_support_ids_excluded",
    "_legal_support_grounding_hit",
    "_legal_support_grounding_recall",
    "_legal_support_product_completeness",
    "_observed_comparator_issue_ids",
]
