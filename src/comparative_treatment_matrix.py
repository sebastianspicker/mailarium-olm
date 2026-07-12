"""Matrix and shared-point helpers for comparative-treatment analysis."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-return-statements

from __future__ import annotations

from typing import Any


def issue_row_strength(*, comparison_quality: str, supported_signal_count: int) -> str:
    """Determine the strength level of a comparator issue row.

    Args:
        comparison_quality: The quality of the comparison ('high', 'partial', or 'weak').
        supported_signal_count: Number of supporting signals for the issue.

    Returns:
        A strength string: 'strong', 'moderate', 'weak', or 'not_comparable'.

    """
    if comparison_quality == "high" and supported_signal_count >= 2:
        return "strong"
    if comparison_quality in {"high", "partial"} and supported_signal_count >= 1:
        return "moderate"
    if comparison_quality in {"high", "partial"}:
        return "weak"
    return "not_comparable"


_ISSUE_TEXT = {
    "control_intensity": (
        (
            "Same sender demands more from target, escalates more against target, or uses broader/public visibility against "
            "the claimant."
        ),
        "Comparator messages show lower control, criticism, or visibility intensity in the current record.",
    ),
    "formality_of_application_requirements": (
        "Claimant-facing messages use stricter demand or procedural framing.",
        "Comparator-facing messages show fewer formal-demand cues in the current record.",
    ),
    "treatment_after_complaints_or_rights_assertions": (
        "Current comparator path may matter for post-complaint or post-rights-assertion treatment.",
        "Comparator path does not currently show the same post-trigger worsening in this slice.",
    ),
    "sbv_or_pr_participation": (
        "Participation-related process context is named in intake or context notes.",
        "Comparator-specific participation handling is not yet well documented in the current slice.",
    ),
    "flexibility_around_medical_needs": (
        "Health-related flexibility may be relevant for this comparison path.",
        "Comparator-side flexibility context is not yet well documented in the current slice.",
    ),
    "mobile_work_approvals_or_restrictions": (
        "Mobile-work treatment may be relevant, but direct comparator records are still thin.",
        "Comparator-side mobile-work handling is not yet shown in the current slice.",
    ),
    "project_allocation": (
        "Project-allocation treatment may matter for this case.",
        "Comparator project-allocation handling is not yet visible in the current slice.",
    ),
    "training_or_development_opportunities": (
        "Training or development access may be relevant in this matter.",
        "Comparator-side training treatment is not yet visible in the current slice.",
    ),
    "reaction_to_technical_incidents": (
        "Technical-incident response may be relevant in this matter.",
        "Comparator incident response is not yet well documented in the current slice.",
    ),
}
_ISSUE_SIGNALS = {
    "control_intensity": {
        "tone_to_target_harsher_than_to_comparator",
        "same_sender_escalates_more_against_target",
        "same_sender_criticizes_target_more",
        "same_sender_demands_more_from_target",
        "same_sender_uses_more_procedural_pressure_against_target",
        "same_sender_uses_more_public_visibility_against_target",
        "same_sender_uses_broader_visibility_against_target",
    },
    "formality_of_application_requirements": {
        "same_sender_demands_more_from_target",
        "same_sender_uses_more_procedural_pressure_against_target",
    },
    "treatment_after_complaints_or_rights_assertions": {
        "same_sender_escalates_more_against_target",
        "same_sender_replies_slower_to_target_requests",
    },
}
_ISSUE_SCOPE_TERMS = {
    "treatment_after_complaints_or_rights_assertions": ("complaint", "rights", "retaliation", "grievance", "sbv", "personalrat"),
    "sbv_or_pr_participation": ("sbv", "personalrat", "betriebsrat", "lpvg", "participation"),
    "flexibility_around_medical_needs": ("disability", "medical", "illness", "bem", "sgb ix"),
    "mobile_work_approvals_or_restrictions": ("mobile work", "home office", "remote", "hybrid"),
    "project_allocation": ("project", "allocation", "assignment"),
    "training_or_development_opportunities": ("training", "development", "schulung", "fortbildung"),
    "reaction_to_technical_incidents": ("technical", "incident", "system", "vpn", "it", "outage"),
}


def _issue_support(issue_id, unequal_signals, scope_text):
    descriptions = _ISSUE_TEXT.get(issue_id)
    if descriptions is None:
        return [], "", ""
    matched = [signal for signal in unequal_signals if signal in _ISSUE_SIGNALS.get(issue_id, set())]
    scope_matched = any(term in scope_text for term in _ISSUE_SCOPE_TERMS.get(issue_id, ()))
    if scope_matched and not matched:
        matched = ["scope_context_only"]
    return matched, *descriptions


def issue_rows(
    *,
    comparator_actor_id: str,
    comparison_quality: str,
    unequal_treatment_signals: list[str],
    target_metrics: dict[str, float | int],
    comparator_metrics: dict[str, float | int],
    evidence_chain: dict[str, Any],
    scope: dict[str, Any],
    scope_text: Any,
    comparator_issue_definitions: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Generate comparator matrix rows for a given comparator actor.

    Args:
        comparator_actor_id: Identifier for the comparator actor.
        comparison_quality: Quality level of the comparison.
        unequal_treatment_signals: List of signals indicating unequal treatment.
        target_metrics: Metrics dictionary for the target.
        comparator_metrics: Metrics dictionary for the comparator.
        evidence_chain: Dictionary containing evidence UIDs for both sides.
        scope: The case scope dictionary.
        scope_text: Function to extract text from scope.
        comparator_issue_definitions: Tuple of issue definition dictionaries.

    Returns:
        A dictionary containing:
        - row_count: Number of generated rows
        - table_columns: List of column names
        - rows: List of matrix row dictionaries

    """
    text = scope_text(scope)
    evidence = _evidence_uids(evidence_chain)

    rows: list[dict[str, Any]] = []
    for definition in comparator_issue_definitions:
        rows.append(
            _matrix_row(
                definition,
                comparator_actor_id,
                comparison_quality,
                unequal_treatment_signals,
                text,
                evidence,
                target_metrics,
                comparator_metrics,
            )
        )
    rows.sort(
        key=lambda row: (
            {"strong": 3, "moderate": 2, "weak": 1, "not_comparable": 0}.get(str(row.get("comparison_strength") or ""), 0) * -1,
            str(row.get("issue_id") or ""),
        )
    )
    return {
        "row_count": len(rows),
        "table_columns": ["Comparator issue", "Claimant treatment", "Colleague treatment", "Evidence", "Likely significance"],
        "rows": rows,
    }


def _evidence_uids(chain):
    return [str(uid) for key in ("target_uids", "comparator_uids") for uid in list(chain.get(key) or []) if uid]


def _matrix_row(definition, actor_id, quality, unequal_signals, text, evidence, target_metrics, comparator_metrics):
    issue_id = str(definition.get("issue_id") or "")
    matched, claimant, comparator = _issue_support(issue_id, unequal_signals, text)
    strength = issue_row_strength(
        comparison_quality=quality, supported_signal_count=sum(signal != "scope_context_only" for signal in matched)
    )
    if matched == ["scope_context_only"] and quality == "weak":
        strength = "not_comparable"
    return {
        "matrix_row_id": f"comparator:{actor_id or 'unknown'}:{issue_id}",
        "issue_id": issue_id,
        "issue_label": str(definition.get("issue_label") or issue_id),
        "claimant_treatment": claimant or "Current record does not yet show claimant-side comparator evidence.",
        "comparator_treatment": comparator or "Current record does not yet show comparator-side comparator evidence.",
        "evidence": evidence,
        "comparison_strength": strength,
        "evidence_needed_to_strengthen_point": list(definition.get("evidence_needed_to_strengthen_point") or []),
        "likely_significance": str(definition.get("significance") or ""),
        "supported_signal_ids": matched,
        "target_message_count": int(target_metrics.get("message_count") or 0),
        "comparator_message_count": int(comparator_metrics.get("message_count") or 0),
    }


def comparison_strength_rank(value: str) -> int:
    """Convert a comparison strength string to a numeric rank.

    Args:
        value: The comparison strength string ('strong', 'moderate', 'weak', 'not_comparable').

    Returns:
        A numeric rank: 4 for 'strong', 3 for 'moderate', 2 for 'weak', 1 for 'not_comparable', 0 otherwise.

    """
    return {"strong": 4, "moderate": 3, "weak": 2, "not_comparable": 1}.get(str(value or ""), 0)


def quality_rank(value: str) -> int:
    """Convert a comparison quality string to a numeric rank.

    Args:
        value: The comparison quality string ('high', 'partial', 'weak').

    Returns:
        A numeric rank: 3 for 'high', 2 for 'partial', 1 for 'weak', 0 otherwise.

    """
    return {"high": 3, "partial": 2, "weak": 1}.get(str(value or ""), 0)


def point_summary(point: dict[str, Any]) -> str:
    """Generate a human-readable summary of a comparator point.

    Args:
        point: A dictionary containing comparator point data with keys like
            issue_label, issue_id, comparison_strength, claimant_treatment,
            comparator_treatment.

    Returns:
        A formatted summary string describing the comparator point.

    """
    issue_label = str(point.get("issue_label") or point.get("issue_id") or "Comparator point")
    strength = str(point.get("comparison_strength") or "not_comparable").replace("_", " ")
    claimant = str(point.get("claimant_treatment") or "").strip()
    comparator = str(point.get("comparator_treatment") or "").strip()
    if claimant and comparator:
        return f"{issue_label}: {claimant} Comparator side: {comparator} Strength: {strength}."
    if claimant:
        return f"{issue_label}: {claimant} Strength: {strength}."
    return f"{issue_label}: comparator support is currently {strength}."


def shared_comparator_points_from_summaries(comparator_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract and normalize comparator points from a list of comparator summaries.

    Args:
        comparator_summaries: List of comparator summary dictionaries, each potentially
            containing a comparator_matrix with rows.

    Returns:
        A sorted list of normalized comparator point dictionaries with computed
        fields like point_summary, supports_unequal_treatment_review, etc.
        Points are sorted by strength (strongest first), then quality, then issue_id.

    """
    points: list[dict[str, Any]] = []
    for summary_index, summary in enumerate(comparator_summaries, start=1):
        if not isinstance(summary, dict):
            continue
        matrix_rows = _matrix_rows(summary)
        for row_index, row in enumerate(matrix_rows, start=1):
            points.append(_comparator_point(summary, row, summary_index, row_index))
    points.sort(
        key=lambda item: (
            -comparison_strength_rank(str(item.get("comparison_strength") or "")),
            -quality_rank(str(item.get("comparison_quality") or "")),
            str(item.get("issue_id") or ""),
            str(item.get("comparator_actor_id") or item.get("comparator_email") or ""),
        )
    )
    return points


def _matrix_rows(summary):
    matrix = summary.get("comparator_matrix") or {}
    return [row for row in matrix.get("rows") or [] if isinstance(row, dict)]


def _string_list(mapping, key):
    return [str(item) for item in mapping.get(key) or [] if str(item).strip()]


def _text(mapping, key, fallback_key=""):
    return str(mapping.get(key) or (mapping.get(fallback_key) if fallback_key else "") or "")


def _comparator_point(summary, row, summary_index, row_index):
    strength = _text(row, "comparison_strength")
    uncertainty = _string_list(summary, "uncertainty_reasons")
    point = {
        "comparator_point_id": _text(row, "matrix_row_id") or f"comparator_point:{summary_index}:{row_index}",
        "summary_index": summary_index,
        "comparator_actor_id": _text(summary, "comparator_actor_id"),
        "comparator_email": _text(summary, "comparator_email"),
        "sender_actor_id": _text(summary, "sender_actor_id"),
        "comparison_status": _text(summary, "status"),
        "comparison_quality": _text(summary, "comparison_quality"),
        "comparison_quality_label": _text(summary, "comparison_quality_label"),
        "issue_id": _text(row, "issue_id"),
        "issue_label": _text(row, "issue_label", "title"),
        "comparison_strength": strength,
        "claimant_treatment": _text(row, "claimant_treatment"),
        "comparator_treatment": _text(row, "comparator_treatment"),
        "likely_significance": _text(row, "likely_significance"),
        "evidence_uids": _string_list(row, "evidence"),
        "supported_signal_ids": _string_list(row, "supported_signal_ids"),
        "missing_proof": _string_list(row, "evidence_needed_to_strengthen_point"),
        "counterargument": _point_counterargument(summary, strength, uncertainty),
        "uncertainty_reasons": uncertainty,
        "supports_unequal_treatment_review": strength in {"strong", "moderate"},
    }
    point["point_summary"] = point_summary(point)
    return point


def _point_counterargument(summary, strength, uncertainty):
    if strength in {"weak", "not_comparable"} or str(summary.get("status") or "") == "no_suitable_comparator":
        return "Comparator quality remains weak or not comparable on the current record."
    return uncertainty[0] if uncertainty else "Current comparator support remains bounded by the present record."
