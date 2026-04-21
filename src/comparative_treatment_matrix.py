"""Matrix and shared-point helpers for comparative-treatment analysis."""

from __future__ import annotations

from typing import Any


def issue_row_strength(*, comparison_quality: str, supported_signal_count: int) -> str:
    if comparison_quality == "high" and supported_signal_count >= 2:
        return "strong"
    if comparison_quality in {"high", "partial"} and supported_signal_count >= 1:
        return "moderate"
    if comparison_quality in {"high", "partial"}:
        return "weak"
    return "not_comparable"


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
    text = scope_text(scope)
    evidence = [
        str(uid)
        for uid in [*list(evidence_chain.get("target_uids") or []), *list(evidence_chain.get("comparator_uids") or [])]
        if uid
    ]

    def has_scope_terms(*terms: str) -> bool:
        return any(term in text for term in terms)

    def issue_support(issue_id: str) -> tuple[list[str], str, str]:
        if issue_id == "control_intensity":
            matched = [
                signal
                for signal in unequal_treatment_signals
                if signal
                in {
                    "tone_to_target_harsher_than_to_comparator",
                    "same_sender_escalates_more_against_target",
                    "same_sender_criticizes_target_more",
                    "same_sender_demands_more_from_target",
                    "same_sender_uses_more_procedural_pressure_against_target",
                    "same_sender_uses_more_public_visibility_against_target",
                    "same_sender_uses_broader_visibility_against_target",
                }
            ]
            return (
                matched,
                (
                    "Same sender demands more from target, escalates more against target, "
                    "or uses broader/public visibility against the claimant."
                ),
                "Comparator messages show lower control, criticism, or visibility intensity in the current record.",
            )
        if issue_id == "formality_of_application_requirements":
            matched = [
                signal
                for signal in unequal_treatment_signals
                if signal in {"same_sender_demands_more_from_target", "same_sender_uses_more_procedural_pressure_against_target"}
            ]
            return (
                matched,
                "Claimant-facing messages use stricter demand or procedural framing.",
                "Comparator-facing messages show fewer formal-demand cues in the current record.",
            )
        if issue_id == "treatment_after_complaints_or_rights_assertions":
            matched = [
                signal
                for signal in unequal_treatment_signals
                if signal in {"same_sender_escalates_more_against_target", "same_sender_replies_slower_to_target_requests"}
            ]
            if has_scope_terms("complaint", "rights", "retaliation", "grievance", "sbv", "personalrat"):
                matched = matched or ["scope_context_only"]
            return (
                matched,
                "Current comparator path may matter for post-complaint or post-rights-assertion treatment.",
                "Comparator path does not currently show the same post-trigger worsening in this slice.",
            )
        if issue_id == "sbv_or_pr_participation":
            matched = (
                ["scope_context_only"] if has_scope_terms("sbv", "personalrat", "betriebsrat", "lpvg", "participation") else []
            )
            return (
                matched,
                "Participation-related process context is named in intake or context notes.",
                "Comparator-specific participation handling is not yet well documented in the current slice.",
            )
        if issue_id == "flexibility_around_medical_needs":
            matched = ["scope_context_only"] if has_scope_terms("disability", "medical", "illness", "bem", "sgb ix") else []
            return (
                matched,
                "Health-related flexibility may be relevant for this comparison path.",
                "Comparator-side flexibility context is not yet well documented in the current slice.",
            )
        if issue_id == "mobile_work_approvals_or_restrictions":
            matched = ["scope_context_only"] if has_scope_terms("mobile work", "home office", "remote", "hybrid") else []
            return (
                matched,
                "Mobile-work treatment may be relevant, but direct comparator records are still thin.",
                "Comparator-side mobile-work handling is not yet shown in the current slice.",
            )
        if issue_id == "project_allocation":
            matched = ["scope_context_only"] if has_scope_terms("project", "allocation", "assignment") else []
            return (
                matched,
                "Project-allocation treatment may matter for this case.",
                "Comparator project-allocation handling is not yet visible in the current slice.",
            )
        if issue_id == "training_or_development_opportunities":
            matched = ["scope_context_only"] if has_scope_terms("training", "development", "schulung", "fortbildung") else []
            return (
                matched,
                "Training or development access may be relevant in this matter.",
                "Comparator-side training treatment is not yet visible in the current slice.",
            )
        if issue_id == "reaction_to_technical_incidents":
            matched = ["scope_context_only"] if has_scope_terms("technical", "incident", "system", "vpn", "it", "outage") else []
            return (
                matched,
                "Technical-incident response may be relevant in this matter.",
                "Comparator incident response is not yet well documented in the current slice.",
            )
        return [], "", ""

    rows: list[dict[str, Any]] = []
    for definition in comparator_issue_definitions:
        issue_id = str(definition.get("issue_id") or "")
        issue_label = str(definition.get("issue_label") or issue_id)
        matched_signals, claimant_treatment, comparator_treatment = issue_support(issue_id)
        row_strength = issue_row_strength(
            comparison_quality=comparison_quality,
            supported_signal_count=len([signal for signal in matched_signals if signal != "scope_context_only"]),
        )
        if matched_signals == ["scope_context_only"] and comparison_quality == "weak":
            row_strength = "not_comparable"
        rows.append(
            {
                "matrix_row_id": f"comparator:{comparator_actor_id or 'unknown'}:{issue_id}",
                "issue_id": issue_id,
                "issue_label": issue_label,
                "claimant_treatment": claimant_treatment or "Current record does not yet show claimant-side comparator evidence.",
                "comparator_treatment": comparator_treatment
                or "Current record does not yet show comparator-side comparator evidence.",
                "evidence": evidence,
                "comparison_strength": row_strength,
                "evidence_needed_to_strengthen_point": list(definition.get("evidence_needed_to_strengthen_point") or []),
                "likely_significance": str(definition.get("significance") or ""),
                "supported_signal_ids": matched_signals,
                "target_message_count": int(target_metrics.get("message_count") or 0),
                "comparator_message_count": int(comparator_metrics.get("message_count") or 0),
            }
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


def comparison_strength_rank(value: str) -> int:
    return {"strong": 4, "moderate": 3, "weak": 2, "not_comparable": 1}.get(str(value or ""), 0)


def quality_rank(value: str) -> int:
    return {"high": 3, "partial": 2, "weak": 1}.get(str(value or ""), 0)


def point_summary(point: dict[str, Any]) -> str:
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
    points: list[dict[str, Any]] = []
    for summary_index, summary in enumerate(comparator_summaries, start=1):
        if not isinstance(summary, dict):
            continue
        matrix_rows = [row for row in ((summary.get("comparator_matrix") or {}).get("rows") or []) if isinstance(row, dict)]
        for row_index, row in enumerate(matrix_rows, start=1):
            point_id = str(row.get("matrix_row_id") or f"comparator_point:{summary_index}:{row_index}")
            comparison_strength = str(row.get("comparison_strength") or "")
            missing_proof = [str(item) for item in row.get("evidence_needed_to_strengthen_point") or [] if str(item).strip()]
            is_weak_or_missing = (
                comparison_strength in {"weak", "not_comparable"} or str(summary.get("status") or "") == "no_suitable_comparator"
            )
            uncertainty_reasons = [str(item) for item in summary.get("uncertainty_reasons") or [] if str(item).strip()]
            counterargument = (
                "Comparator quality remains weak or not comparable on the current record."
                if is_weak_or_missing
                else uncertainty_reasons[0]
                if uncertainty_reasons
                else "Current comparator support remains bounded by the present record."
            )
            point = {
                "comparator_point_id": point_id,
                "summary_index": summary_index,
                "comparator_actor_id": str(summary.get("comparator_actor_id") or ""),
                "comparator_email": str(summary.get("comparator_email") or ""),
                "sender_actor_id": str(summary.get("sender_actor_id") or ""),
                "comparison_status": str(summary.get("status") or ""),
                "comparison_quality": str(summary.get("comparison_quality") or ""),
                "comparison_quality_label": str(summary.get("comparison_quality_label") or ""),
                "issue_id": str(row.get("issue_id") or ""),
                "issue_label": str(row.get("issue_label") or row.get("title") or ""),
                "comparison_strength": comparison_strength,
                "claimant_treatment": str(row.get("claimant_treatment") or ""),
                "comparator_treatment": str(row.get("comparator_treatment") or ""),
                "likely_significance": str(row.get("likely_significance") or ""),
                "evidence_uids": [str(item) for item in row.get("evidence") or [] if str(item).strip()],
                "supported_signal_ids": [str(item) for item in row.get("supported_signal_ids") or [] if str(item).strip()],
                "missing_proof": missing_proof,
                "counterargument": counterargument,
                "uncertainty_reasons": uncertainty_reasons,
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
