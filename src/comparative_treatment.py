"""Comparative-treatment helpers for behavioural-analysis cases."""
# pylint: disable=too-many-locals

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from . import comparative_treatment_helpers as _helpers
from ._utils import _as_dict, _as_list, _compact
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


def _source_text(source: dict[str, Any]) -> str:
    """Extract searchable text from a source document.

    Combines title, snippet, and documentary text preview into a single
    searchable string.

    Args:
        source: A dict containing source document fields.

    Returns:
        A concatenated string of all available text parts from the source.
    """
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
    """Extract signature strings from a party dict for matching.

    Creates a set of normalized email and name strings that can be used
    to identify mentions of the party in source text.

    Args:
        party: A dict with optional 'email' and 'name' keys.

    Returns:
        A set of lowercase, compacted signature strings.
    """
    signatures: set[str] = set()
    for key in ("email", "name"):
        value = _compact(party.get(key)).lower()
        if not value:
            continue
        signatures.add(value)
    return signatures


def _source_mentions_party(source: dict[str, Any], party: dict[str, Any]) -> bool:
    """Check if a source document mentions a given party.

    Searches the source text and participants list for any of the party's
    signature strings (email or name).

    Args:
        source: A dict containing source document fields.
        party: A dict with optional 'email' and 'name' keys.

    Returns:
        True if any party signature is found in the source, False otherwise.
    """
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
    """Identify which comparator issue IDs are matched by a source's text.

    Checks the source text against all known issue keyword sets and returns
    the IDs of issues whose keywords appear in the text.

    Args:
        source: A dict containing source document fields.

    Returns:
        A set of issue_id strings that match the source text.
    """
    text = _source_text(source).lower()
    return {
        issue_id
        for issue_id, keywords in _SOURCE_COMPARATOR_ISSUE_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }


def _source_date(source: dict[str, Any]) -> date | None:
    """Extract and parse the date from a source document.

    Args:
        source: A dict containing source document fields.

    Returns:
        A date object if a valid date can be parsed, otherwise None.
    """
    return _helpers.parse_day(_compact(source.get("date")))


def _source_reliability_rank(source: dict[str, Any]) -> int:
    """Compute a numeric reliability rank for a source.

    Maps the source's reliability level string to a numeric rank.

    Args:
        source: A dict containing source document fields with source_reliability.

    Returns:
        An integer rank: 3 for high, 2 for medium, 1 for low, 0 otherwise.
    """
    level = _compact(_as_dict(source.get("source_reliability")).get("level")).lower()
    return {"high": 3, "medium": 2, "low": 1}.get(level, 0)


def _source_side_summary(source: dict[str, Any]) -> str:
    """Generate a human-readable summary of a source for comparison display.

    Constructs a summary string from the source type, title, and snippet,
    falling back to generic descriptions when specific fields are missing.

    Args:
        source: A dict containing source document fields.

    Returns:
        A formatted summary string describing the source.
    """
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
    *, case_bundle: dict[str, Any], multi_source_case_bundle: dict[str, Any] | None
) -> list[dict[str, Any]]:
    scope = _as_dict(case_bundle.get("scope"))
    target = _as_dict(scope.get("target_person"))
    comparators = [item for item in _as_list(scope.get("comparator_actors")) if isinstance(item, dict)]
    if not target or not comparators:
        return []
    definitions = {
        str(item.get("issue_id") or ""): item for item in _helpers.COMPARATOR_ISSUE_DEFINITIONS if str(item.get("issue_id") or "")
    }
    sources = [source for source in _as_list(_as_dict(multi_source_case_bundle).get("sources")) if _eligible_source(source)]
    points: list[dict[str, Any]] = []
    for comparator in comparators:
        points.extend(_comparator_source_points(comparator, target, sources, definitions, points))
    points.sort(key=_comparator_point_sort_key)
    return points


def _eligible_source(source):
    return isinstance(source, dict) and _compact(source.get("source_type")).lower() != "email" and bool(_source_text(source))


def _comparator_source_points(comparator, target, sources, definitions, prior_points):
    comparator_id, comparator_email = _compact(comparator.get("actor_id")), _compact(comparator.get("email")).lower()
    target_sources = _party_sources(sources, target)
    comparator_sources = _party_sources(sources, comparator)
    points, seen = [], set()
    for issue_id, definition in definitions.items():
        target_matches = _issue_sources(target_sources, issue_id)
        comparator_matches = _issue_sources(comparator_sources, issue_id)
        pair = _best_source_pair(target_matches, comparator_matches)
        if pair is None:
            continue
        source_ids = tuple(sorted({_compact(pair[0].get("source_id")), _compact(pair[1].get("source_id"))}))
        key = (comparator_id or comparator_email, issue_id, source_ids)
        if key in seen:
            continue
        seen.add(key)
        points.append(
            _source_point(
                comparator_id, comparator_email, issue_id, definition, pair, source_ids, len(prior_points) + len(points) + 1
            )
        )
    return points


def _party_sources(sources, party):
    return [source for source in sources if _source_mentions_party(source, party)]


def _issue_sources(sources, issue_id):
    return [source for source in sources if issue_id in _matched_issue_ids(source)]


def _best_source_pair(target_sources, comparator_sources):
    best_pair, best_key = None, None
    for target_source in target_sources:
        for comparator_source in comparator_sources:
            key = _source_pair_key(target_source, comparator_source)
            if best_key is None or key > best_key:
                best_pair, best_key = (target_source, comparator_source), key
    return best_pair


def _source_pair_key(target, comparator):
    same_type = int(_compact(target.get("source_type")).lower() == _compact(comparator.get("source_type")).lower())
    target_date, comparator_date = _source_date(target), _source_date(comparator)
    delta = abs((target_date - comparator_date).days) if target_date is not None and comparator_date is not None else 9999
    return same_type, -delta, _source_reliability_rank(target) + _source_reliability_rank(comparator)


def _source_point(comparator_id, comparator_email, issue_id, definition, pair, source_ids, ordinal):
    target_source, comparator_source = pair
    strength = _source_pair_strength(target_source, comparator_source, source_ids)
    point = {
        "comparator_point_id": f"comparator:{comparator_id or comparator_email or 'unknown'}:source:{issue_id}:{ordinal}",
        "summary_index": 0,
        "comparator_actor_id": comparator_id,
        "comparator_email": comparator_email,
        "sender_actor_id": "",
        "comparison_status": "source_backed_comparator",
        "comparison_quality": "partial" if strength in {"strong", "moderate"} else "weak",
        "comparison_quality_label": "source_backed_comparator",
        "issue_id": issue_id,
        "issue_label": str(definition.get("issue_label") or issue_id),
        "comparison_strength": strength,
        "claimant_treatment": _source_side_summary(target_source),
        "comparator_treatment": _source_side_summary(comparator_source),
        "likely_significance": str(definition.get("significance") or ""),
        "evidence_uids": _source_uids(pair),
        "supporting_source_ids": [source_id for source_id in source_ids if source_id],
        "supported_signal_ids": ["mixed_source_pair"],
        "missing_proof": [
            str(item) for item in _as_list(definition.get("evidence_needed_to_strengthen_point")) if _compact(item)
        ],
        "counterargument": (
            "The current mixed-source comparator pair is directionally useful, but the records are not tightly matched."
        )
        if strength == "weak"
        else "The mixed-source pair still needs closer role/process comparability review.",
        "uncertainty_reasons": ["Current mixed-source pair does not yet show tightly matched timing or source type."]
        if strength == "weak"
        else [],
        "supports_unequal_treatment_review": strength in {"strong", "moderate"},
    }
    point["point_summary"] = point_summary(point)
    return point


def _source_pair_strength(target, comparator, source_ids):
    if source_ids and len(source_ids) == 1:
        return "strong"
    same_type = _compact(target.get("source_type")).lower() == _compact(comparator.get("source_type")).lower()
    target_date, comparator_date = _source_date(target), _source_date(comparator)
    within_month = target_date is not None and comparator_date is not None and abs((target_date - comparator_date).days) <= 31
    return "moderate" if same_type and within_month else "weak"


def _source_uids(pair):
    return [uid for source in pair if (uid := _compact(source.get("uid")))]


def _comparator_point_sort_key(item):
    return (
        -comparison_strength_rank(str(item.get("comparison_strength") or "")),
        -quality_rank(str(item.get("comparison_quality") or "")),
        str(item.get("issue_id") or ""),
        str(item.get("comparator_actor_id") or item.get("comparator_email") or ""),
    )


def _merge_comparator_points(
    existing_points: list[dict[str, Any]],
    source_backed_points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge existing and source-backed comparator points, deduplicating by ID.

    Combines two lists of comparator points, removing duplicates based on
    comparator_point_id, and returns a sorted merged list.

    Args:
        existing_points: List of existing comparator point dicts.
        source_backed_points: List of source-backed comparator point dicts.

    Returns:
        A merged, deduplicated, and sorted list of comparator point dicts.
    """
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
    """Augment a comparative treatment payload with source-backed comparator points.

    Takes an existing comparative treatment (or None) and enhances it with
    source-backed comparator points derived from the case bundle and
    multi-source case bundle. Updates summary statistics accordingly.

    Args:
        comparative_treatment: Optional existing comparative treatment dict.
        case_bundle: A dict containing the case scope.
        multi_source_case_bundle: Optional dict containing additional sources.

    Returns:
        The augmented comparative treatment dict with source-backed points
        merged in, or the original if no sources are available.
    """
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
    summary = _augmented_summary(payload, merged_points)
    summary["source_backed_point_count"] = len(source_backed_points)
    payload["summary"] = summary
    payload["comparator_points"] = merged_points
    payload["source_backed_comparator_points"] = source_backed_points
    if "version" not in payload:
        payload["version"] = _helpers.COMPARATIVE_TREATMENT_VERSION
    return payload


def _augmented_summary(payload, points):
    counts = Counter(str(point.get("comparison_strength") or "") for point in points)
    summary = dict(payload.get("summary") or {})
    summary.update(
        {
            "matrix_row_count": len(points),
            "strong_matrix_row_count": counts["strong"],
            "moderate_matrix_row_count": counts["moderate"],
            "weak_matrix_row_count": counts["weak"],
            "not_comparable_matrix_row_count": counts["not_comparable"],
        }
    )
    return summary


def shared_comparator_points(comparative_treatment: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return shared comparator points, deriving them from comparator summaries if needed.

    Extracts comparator points from the treatment payload, falling back to
    generating them from comparator summaries if points are not present.

    Args:
        comparative_treatment: Optional dict containing comparator_points or
            comparator_summaries.

    Returns:
        A list of comparator point dicts.
    """
    payload = _as_dict(comparative_treatment)
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
    """Create an insufficient comparative treatment response.

    Generates a standardized response indicating that comparative treatment
    analysis cannot be performed due to missing required inputs.

    Args:
        scope: A dict containing the case scope.
        reason_codes: List of reason codes explaining why analysis is not possible.

    Returns:
        A dict with version info, empty results, and insufficiency metadata
        including status, reason text, missing inputs, and recommendations.
    """
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
    """Build a comprehensive comparative treatment analysis for a case.

    Validates the case scope, checks for required inputs (target person and
    comparator actors), and either returns an insufficiency response or
    generates a full comparative treatment with source augmentation.

    Args:
        case_bundle: Optional dict containing the case scope.
        candidates: List of candidate dicts for comparison.
        full_map: Dict containing full mapping data.
        multi_source_case_bundle: Optional dict containing additional sources.

    Returns:
        A comparative treatment dict with analysis results, or None if the
        case_bundle is invalid. Returns an insufficiency response if required
        inputs are missing.
    """
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
