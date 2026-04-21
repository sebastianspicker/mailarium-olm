"""Comparative-treatment helpers for behavioural-analysis cases."""

from __future__ import annotations

from datetime import date
from typing import Any

from . import comparative_treatment_helpers as _helpers
from .comparative_treatment_helpers import (
    compare_treatment as _compare_treatment,
)
from .comparative_treatment_helpers import (
    shared_comparator_points_from_summaries as _shared_comparator_points_from_summaries,
)
from .comparative_treatment_matrix import comparison_strength_rank, point_summary, quality_rank

_SOURCE_COMPARATOR_ISSUE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "mobile_work_approvals_or_restrictions": ("home office", "mobile work", "remote work", "remote", "hybrid"),
    "formality_of_application_requirements": ("application", "approval", "request form", "antrag", "formal request"),
    "control_intensity": ("deadline", "time system", "attendance control", "surveillance", "check-in", "escalation"),
    "project_allocation": ("project", "assignment", "task withdrawal", "removed from project", "aufgabenentzug"),
    "training_or_development_opportunities": ("training", "development", "schulung", "fortbildung"),
    "sbv_or_pr_participation": (
        "sbv",
        "personalrat",
        "betriebsrat",
        "lpvg",
        "participation",
        "consultation",
        "mitbestimmung",
    ),
    "reaction_to_technical_incidents": ("incident", "outage", "ticket", "vpn", "system", "technical"),
    "flexibility_around_medical_needs": ("medical", "attest", "illness", "disability", "accommodation", "gesundheit"),
    "treatment_after_complaints_or_rights_assertions": (
        "complaint",
        "grievance",
        "rights assertion",
        "retaliation",
        "maßregelung",
        "massregelung",
        "sbv",
        "hr",
    ),
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _source_text(source: dict[str, Any]) -> str:
    documentary = _as_dict(source.get("documentary_support"))
    return " ".join(
        part
        for part in (
            _compact(source.get("title")),
            _compact(source.get("snippet")),
            _compact(documentary.get("text_preview")),
        )
        if part
    )


def _party_signatures(party: dict[str, Any]) -> set[str]:
    signatures: set[str] = set()
    for key in ("email", "name"):
        value = _compact(party.get(key)).lower()
        if not value:
            continue
        signatures.add(value)
    return signatures


def _source_mentions_party(source: dict[str, Any], party: dict[str, Any]) -> bool:
    signatures = _party_signatures(party)
    if not signatures:
        return False
    searchable = " ".join(
        [
            _source_text(source).lower(),
            " ".join(_compact(item).lower() for item in _as_list(source.get("participants"))),
        ]
    )
    return any(signature in searchable for signature in signatures)


def _matched_issue_ids(source: dict[str, Any]) -> set[str]:
    text = _source_text(source).lower()
    return {
        issue_id
        for issue_id, keywords in _SOURCE_COMPARATOR_ISSUE_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }


def _source_date(source: dict[str, Any]) -> date | None:
    return _helpers.parse_day(_compact(source.get("date")))


def _source_reliability_rank(source: dict[str, Any]) -> int:
    level = _compact(_as_dict(source.get("source_reliability")).get("level")).lower()
    return {"high": 3, "medium": 2, "low": 1}.get(level, 0)


def _source_side_summary(source: dict[str, Any]) -> str:
    source_type = _compact(source.get("source_type")).replace("_", " ")
    title = _compact(source.get("title"))
    snippet = _compact(source.get("snippet"))
    if title and snippet:
        return f"{title}: {snippet}"
    if title:
        return f"{source_type.capitalize()} record {title}."
    if snippet:
        return snippet
    return f"{source_type.capitalize()} record is present in the mixed-source bundle."


def _source_backed_comparator_points(
    *,
    case_bundle: dict[str, Any],
    multi_source_case_bundle: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    scope = _as_dict(case_bundle.get("scope"))
    target = _as_dict(scope.get("target_person"))
    comparators = [item for item in _as_list(scope.get("comparator_actors")) if isinstance(item, dict)]
    if not target or not comparators:
        return []

    issue_definitions = {
        str(item.get("issue_id") or ""): item for item in _helpers.COMPARATOR_ISSUE_DEFINITIONS if str(item.get("issue_id") or "")
    }
    sources = [
        source
        for source in _as_list(_as_dict(multi_source_case_bundle).get("sources"))
        if isinstance(source, dict) and _compact(source.get("source_type")).lower() != "email" and _source_text(source)
    ]
    points: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for comparator in comparators:
        comparator_actor_id = _compact(comparator.get("actor_id"))
        comparator_email = _compact(comparator.get("email")).lower()
        target_sources = [source for source in sources if _source_mentions_party(source, target)]
        comparator_sources = [source for source in sources if _source_mentions_party(source, comparator)]
        for issue_id, definition in issue_definitions.items():
            target_matches = [source for source in target_sources if issue_id in _matched_issue_ids(source)]
            comparator_matches = [source for source in comparator_sources if issue_id in _matched_issue_ids(source)]
            if not target_matches or not comparator_matches:
                continue
            best_pair: tuple[dict[str, Any], dict[str, Any]] | None = None
            best_key: tuple[int, int, int] | None = None
            for target_source in target_matches:
                target_date = _source_date(target_source)
                for comparator_source in comparator_matches:
                    comparator_date = _source_date(comparator_source)
                    same_type = int(
                        _compact(target_source.get("source_type")).lower()
                        == _compact(comparator_source.get("source_type")).lower()
                    )
                    date_delta = (
                        abs((target_date - comparator_date).days)
                        if target_date is not None and comparator_date is not None
                        else 9999
                    )
                    reliability_score = _source_reliability_rank(target_source) + _source_reliability_rank(comparator_source)
                    pair_key = (same_type, -date_delta, reliability_score)
                    if best_key is None or pair_key > best_key:
                        best_key = pair_key
                        best_pair = (target_source, comparator_source)
            if best_pair is None:
                continue
            target_source, comparator_source = best_pair
            source_ids = tuple(
                sorted(
                    {
                        _compact(target_source.get("source_id")),
                        _compact(comparator_source.get("source_id")),
                    }
                )
            )
            dedupe_key = (comparator_actor_id or comparator_email, issue_id, source_ids)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            target_date = _source_date(target_source)
            comparator_date = _source_date(comparator_source)
            same_source = source_ids and len(source_ids) == 1
            within_month = (
                target_date is not None and comparator_date is not None and abs((target_date - comparator_date).days) <= 31
            )
            same_type = (
                _compact(target_source.get("source_type")).lower() == _compact(comparator_source.get("source_type")).lower()
            )
            comparison_strength = "strong" if same_source else "moderate" if same_type and within_month else "weak"
            comparison_quality = "partial" if comparison_strength in {"strong", "moderate"} else "weak"
            point = {
                "comparator_point_id": (
                    f"comparator:{comparator_actor_id or comparator_email or 'unknown'}:source:{issue_id}:{len(points) + 1}"
                ),
                "summary_index": 0,
                "comparator_actor_id": comparator_actor_id,
                "comparator_email": comparator_email,
                "sender_actor_id": "",
                "comparison_status": "source_backed_comparator",
                "comparison_quality": comparison_quality,
                "comparison_quality_label": "source_backed_comparator",
                "issue_id": issue_id,
                "issue_label": str(definition.get("issue_label") or issue_id),
                "comparison_strength": comparison_strength,
                "claimant_treatment": _source_side_summary(target_source),
                "comparator_treatment": _source_side_summary(comparator_source),
                "likely_significance": str(definition.get("significance") or ""),
                "evidence_uids": [
                    _compact(item)
                    for item in (
                        _compact(target_source.get("uid")),
                        _compact(comparator_source.get("uid")),
                    )
                    if _compact(item)
                ],
                "supporting_source_ids": [source_id for source_id in source_ids if source_id],
                "supported_signal_ids": ["mixed_source_pair"],
                "missing_proof": [
                    str(item) for item in _as_list(definition.get("evidence_needed_to_strengthen_point")) if _compact(item)
                ],
                "counterargument": (
                    "The current mixed-source comparator pair is directionally useful, but the records are not tightly matched."
                    if comparison_strength == "weak"
                    else "The mixed-source pair still needs closer role/process comparability review."
                ),
                "uncertainty_reasons": (
                    ["Current mixed-source pair does not yet show tightly matched timing or source type."]
                    if comparison_strength == "weak"
                    else []
                ),
                "supports_unequal_treatment_review": comparison_strength in {"strong", "moderate"},
            }
            point["point_summary"] = point_summary(point)
            points.append(point)
    points.sort(
        key=lambda item: (
            -comparison_strength_rank(str(item.get("comparison_strength") or "")),
            -quality_rank(str(item.get("comparison_quality") or "")),
            str(item.get("issue_id") or ""),
            str(item.get("comparator_actor_id") or item.get("comparator_email") or ""),
        )
    )
    return points


def _merge_comparator_points(
    existing_points: list[dict[str, Any]],
    source_backed_points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for point in [*existing_points, *source_backed_points]:
        point_id = _compact(point.get("comparator_point_id"))
        if point_id and point_id in seen_ids:
            continue
        if point_id:
            seen_ids.add(point_id)
        merged.append(point)
    merged.sort(
        key=lambda item: (
            -comparison_strength_rank(str(item.get("comparison_strength") or "")),
            -quality_rank(str(item.get("comparison_quality") or "")),
            str(item.get("issue_id") or ""),
            str(item.get("comparator_actor_id") or item.get("comparator_email") or ""),
        )
    )
    return merged


def augment_comparative_treatment_with_sources(
    comparative_treatment: dict[str, Any] | None,
    *,
    case_bundle: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(case_bundle, dict):
        return comparative_treatment
    source_backed_points = _source_backed_comparator_points(
        case_bundle=case_bundle,
        multi_source_case_bundle=multi_source_case_bundle,
    )
    if not source_backed_points:
        return comparative_treatment

    payload = dict(comparative_treatment or {})
    existing_points = [point for point in payload.get("comparator_points") or [] if isinstance(point, dict)]
    if not existing_points:
        existing_points = _shared_comparator_points_from_summaries(
            [row for row in payload.get("comparator_summaries") or [] if isinstance(row, dict)]
        )
    merged_points = _merge_comparator_points(existing_points, source_backed_points)
    summary = dict(payload.get("summary") or {})
    summary["matrix_row_count"] = len(merged_points)
    summary["strong_matrix_row_count"] = sum(
        1 for point in merged_points if str(point.get("comparison_strength") or "") == "strong"
    )
    summary["moderate_matrix_row_count"] = sum(
        1 for point in merged_points if str(point.get("comparison_strength") or "") == "moderate"
    )
    summary["weak_matrix_row_count"] = sum(1 for point in merged_points if str(point.get("comparison_strength") or "") == "weak")
    summary["not_comparable_matrix_row_count"] = sum(
        1 for point in merged_points if str(point.get("comparison_strength") or "") == "not_comparable"
    )
    summary["source_backed_point_count"] = len(source_backed_points)
    payload["summary"] = summary
    payload["comparator_points"] = merged_points
    payload["source_backed_comparator_points"] = source_backed_points
    if "version" not in payload:
        payload["version"] = _helpers.COMPARATIVE_TREATMENT_VERSION
    return payload


def shared_comparator_points(comparative_treatment: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return shared comparator points, deriving them from comparator summaries if needed."""
    payload = comparative_treatment if isinstance(comparative_treatment, dict) else {}
    points = [row for row in payload.get("comparator_points") or [] if isinstance(row, dict)]
    if points:
        return points
    summaries = [row for row in payload.get("comparator_summaries") or [] if isinstance(row, dict)]
    return _shared_comparator_points_from_summaries(summaries)


def _insufficient_comparative_treatment(
    *,
    scope: dict[str, Any],
    reason_codes: list[str],
) -> dict[str, Any]:
    target = _as_dict(scope.get("target_person"))
    target_actor_id = _compact(target.get("actor_id"))
    missing_inputs: list[str] = []
    if "missing_comparator_actors" in reason_codes:
        missing_inputs.append("comparator_actors")
    if "missing_target_person" in reason_codes:
        missing_inputs.append("target_person")
    reason_text = (
        "Comparator analysis is not yet supported because the case scope does not identify comparator actors."
        if "missing_comparator_actors" in reason_codes
        else "Comparator analysis is not yet supported because the target person is not identified clearly enough."
    )
    return {
        "version": _helpers.COMPARATIVE_TREATMENT_VERSION,
        "target_actor_id": target_actor_id,
        "summary": {
            "available_comparator_count": 0,
            "high_quality_comparator_count": 0,
            "weak_quality_comparator_count": 0,
            "low_quality_comparator_count": 0,
            "discovery_candidate_count": 0,
            "matrix_row_count": 0,
            "strong_matrix_row_count": 0,
            "moderate_matrix_row_count": 0,
            "weak_matrix_row_count": 0,
            "not_comparable_matrix_row_count": 0,
            "status": "insufficient_comparator_scope",
            "insufficiency_reason": reason_text,
            "missing_inputs": missing_inputs,
        },
        "comparator_summaries": [],
        "comparator_points": [],
        "source_backed_comparator_points": [],
        "insufficiency": {
            "status": "insufficient_comparator_scope",
            "reason_codes": reason_codes,
            "reason": reason_text,
            "missing_inputs": missing_inputs,
            "recommended_next_inputs": [
                "Add named comparator actors tied to the same manager, policy, or decision path."
                if "missing_comparator_actors" in reason_codes
                else "Clarify the target person identity before comparing treatment."
            ],
        },
    }


def build_comparative_treatment(
    *,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
    multi_source_case_bundle: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return conservative comparator analysis for the target versus named comparators."""
    scope = (case_bundle or {}).get("scope") if isinstance(case_bundle, dict) else None
    if not isinstance(scope, dict):
        return None
    target = scope.get("target_person")
    comparators = scope.get("comparator_actors")
    if not isinstance(target, dict) or (
        not _compact(_as_dict(target).get("name")) and not _compact(_as_dict(target).get("email"))
    ):
        return _insufficient_comparative_treatment(scope=scope, reason_codes=["missing_target_person"])
    if not isinstance(comparators, list) or not comparators:
        return _insufficient_comparative_treatment(scope=scope, reason_codes=["missing_comparator_actors"])

    target_actor_id = str(target.get("actor_id") or "")
    payload = _compare_treatment(scope=scope, candidates=candidates, full_map=full_map, target_actor_id=target_actor_id)
    return augment_comparative_treatment_with_sources(
        payload,
        case_bundle=case_bundle,
        multi_source_case_bundle=multi_source_case_bundle,
    )
