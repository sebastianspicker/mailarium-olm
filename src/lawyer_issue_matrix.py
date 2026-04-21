"""Counsel-facing legal-relevance matrix for German employment matters."""

from __future__ import annotations

from typing import Any

from .behavioral_taxonomy import issue_track_to_tag_ids
from .comparative_treatment import shared_comparator_points
from .trigger_retaliation import shared_retaliation_points

MATRIX_VERSION = "1"

_ISSUE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "issue_id": "eingruppierung_tarifliche_bewertung",
        "title": "Eingruppierung / tarifliche Bewertung",
        "tracks": {"eingruppierung_dispute"},
        "keywords": ("eingruppierung", "entgeltgruppe", "vergütungsgruppe", "tarif", "td "),
        "document_keywords": ("eingruppierung", "tarif", "rolle", "aufgabe", "klassifizierung"),
    },
    {
        "issue_id": "agg_disadvantage",
        "title": "AGG disadvantage",
        "tracks": {"disability_disadvantage"},
        "keywords": ("agg", "benachteiligung", "disability", "illness", "behinderung"),
        "document_keywords": ("agg", "disability", "benachteiligung", "accommodation", "illness"),
    },
    {
        "issue_id": "burden_shifting_indicators",
        "title": "Burden-shifting indicators",
        "tracks": {"disability_disadvantage", "retaliation_after_protected_event", "eingruppierung_dispute"},
        "keywords": ("comparator", "vergleich", "unequal_treatment", "discrimination"),
        "document_keywords": ("vergleich", "comparator", "unequal", "comparison"),
    },
    {
        "issue_id": "retaliation_massregelungsverbot",
        "title": "Retaliation / Maßregelungsverbot",
        "tracks": {"retaliation_after_protected_event"},
        "keywords": ("retaliation", "maßregelung", "massregelung", "complaint", "objection"),
        "document_keywords": ("complaint", "retaliation", "trigger", "objection"),
    },
    {
        "issue_id": "sgb_ix_164",
        "title": "§164 SGB IX",
        "tracks": {"disability_disadvantage"},
        "keywords": ("164", "sgb ix", "accommodation", "behinderung", "disability"),
        "document_keywords": ("164", "sgb ix", "accommodation", "medical", "adjustment"),
    },
    {
        "issue_id": "sgb_ix_167_bem",
        "title": "§167 SGB IX / BEM",
        "tracks": {"prevention_duty_gap"},
        "keywords": ("167", "sgb ix", "bem", "prävention", "praevention"),
        "document_keywords": ("bem", "prävention", "praevention", "167", "sgb ix"),
    },
    {
        "issue_id": "sgb_ix_178_sbv",
        "title": "§178 SGB IX / SBV",
        "tracks": {"participation_duty_gap"},
        "keywords": ("178", "sgb ix", "sbv", "schwerbehindertenvertretung"),
        "document_keywords": ("sbv", "178", "schwerbehindertenvertretung"),
    },
    {
        "issue_id": "pr_lpvg_participation",
        "title": "PR / LPVG participation",
        "tracks": {"participation_duty_gap"},
        "keywords": ("personalrat", "betriebsrat", "lpvg", "pr", "mitbestimmung"),
        "document_keywords": ("personalrat", "betriebsrat", "lpvg", "mitbestimmung"),
    },
    {
        "issue_id": "fuersorgepflicht",
        "title": "Fürsorgepflicht",
        "tracks": {"prevention_duty_gap", "participation_duty_gap", "disability_disadvantage"},
        "keywords": ("fürsorge", "fuersorge", "workability", "support", "accommodation"),
        "document_keywords": ("fürsorge", "fuersorge", "support", "workability", "adjustment"),
    },
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _scope_text(case_bundle: dict[str, Any]) -> str:
    scope = _as_dict(case_bundle.get("scope"))
    parts: list[str] = []
    for field in ("context_notes", "analysis_goal"):
        value = str(scope.get(field) or "").strip()
        if value:
            parts.append(value)
    for field in ("allegation_focus", "employment_issue_tags", "employment_issue_tracks"):
        for item in _as_list(scope.get(field)):
            text = str(item or "").strip()
            if text:
                parts.append(text)
    return " ".join(parts).lower()


def _find_issue_framework(issue_frameworks: list[dict[str, Any]], issue_track: str) -> dict[str, Any]:
    for item in issue_frameworks:
        if str(item.get("issue_track") or "") == issue_track:
            return item
    return {}


def _document_candidates(
    matter_evidence_index: dict[str, Any],
    *,
    issue_tracks: set[str],
    keywords: tuple[str, ...],
    supporting_finding_ids: list[str],
    supporting_citation_ids: list[str],
    supporting_uids: list[str],
) -> list[dict[str, Any]]:
    rows = [row for row in _as_list(matter_evidence_index.get("rows")) if isinstance(row, dict)]
    priority_by_exhibit = {
        str(row.get("exhibit_id") or ""): int(row.get("priority_score") or 0)
        for row in _as_list(matter_evidence_index.get("top_15_exhibits"))
        if isinstance(row, dict) and str(row.get("exhibit_id") or "")
    }
    issue_tag_ids = {tag_id for issue_track in issue_tracks for tag_id in issue_track_to_tag_ids(issue_track, context_text="")}
    finding_id_set = {str(item) for item in supporting_finding_ids if str(item).strip()}
    citation_id_set = {str(item) for item in supporting_citation_ids if str(item).strip()}
    uid_set = {str(item) for item in supporting_uids if str(item).strip()}
    matches: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        quoted_evidence = _as_dict(row.get("quoted_evidence"))
        document_locator = _as_dict(row.get("document_locator"))
        haystacks = [
            str(row.get("short_description") or ""),
            str(row.get("why_it_matters") or ""),
            " ".join(str(item) for item in _as_list(row.get("main_issue_tags")) if item),
            str(quoted_evidence.get("original_text") or ""),
            str(quoted_evidence.get("translated_text") or ""),
            str(quoted_evidence.get("summary") or ""),
        ]
        score = 0
        selection_basis: list[str] = []
        row_finding_ids = {str(item) for item in _as_list(row.get("supporting_finding_ids")) if str(item).strip()}
        row_citation_ids = {str(item) for item in _as_list(row.get("supporting_citation_ids")) if str(item).strip()}
        row_uids = {str(item) for item in _as_list(row.get("supporting_uids")) if str(item).strip()}
        row_issue_tags = {
            str(item) for field in ("main_issue_tags", "all_issue_tags") for item in _as_list(row.get(field)) if str(item).strip()
        }
        if finding_id_set & row_finding_ids:
            score += 100
            selection_basis.append("supporting_finding_link")
        if citation_id_set & row_citation_ids:
            score += 80
            selection_basis.append("supporting_citation_link")
        if uid_set & row_uids:
            score += 60
            selection_basis.append("supporting_uid_link")
        if issue_tag_ids & row_issue_tags:
            score += 35
            selection_basis.append("issue_tag_link")
        if str(row.get("source_conflict_status") or "") == "disputed":
            score += 6
            selection_basis.append("source_conflict_signal")
        reliability = _as_dict(row.get("exhibit_reliability"))
        strength = str(reliability.get("strength") or "")
        if strength == "strong":
            score += 8
            selection_basis.append("strong_reliability")
        elif strength == "moderate":
            score += 4
            selection_basis.append("moderate_reliability")
        priority_score = priority_by_exhibit.get(str(row.get("exhibit_id") or ""), 0)
        if priority_score > 0:
            score += min(priority_score, 12)
            selection_basis.append("ranked_exhibit_priority")
        support_signal_present = bool(
            selection_basis
            and any(
                basis
                in {
                    "supporting_finding_link",
                    "supporting_citation_link",
                    "supporting_uid_link",
                    "issue_tag_link",
                    "ranked_exhibit_priority",
                }
                for basis in selection_basis
            )
        )
        quoted_text = " ".join(part for part in haystacks[3:] if part).strip()
        if quoted_text:
            score += 12
            if support_signal_present:
                selection_basis.append("quoted_evidence_text")
        if quoted_text and str(document_locator.get("evidence_handle") or ""):
            score += 6
            if support_signal_present:
                selection_basis.append("locator_backed_excerpt")
        if str(_as_dict(row.get("source_reliability")).get("level") or "") == "low":
            score -= 4
        if str(row.get("promotability_status") or "") in {"lead_only_manual_review", "reference_only_not_promotable"}:
            score -= 8
        if keywords and any(keyword in " ".join(haystacks).lower() for keyword in keywords):
            score += 10
            selection_basis.append("keyword_fallback")
        if str(reliability.get("strength") or "") == "weak" and selection_basis == ["keyword_fallback"]:
            score -= 6
        if score <= 0:
            continue
        matches.append(
            (
                score,
                {
                    "exhibit_id": str(row.get("exhibit_id") or ""),
                    "source_id": str(row.get("source_id") or ""),
                    "short_description": str(row.get("short_description") or ""),
                    "source_language": str(row.get("source_language") or "unknown"),
                    "quoted_evidence": dict(row.get("quoted_evidence") or {}),
                    "document_locator": dict(row.get("document_locator") or {}),
                    "why_it_matters": str(row.get("why_it_matters") or ""),
                    "supporting_finding_ids": [str(item) for item in _as_list(row.get("supporting_finding_ids")) if item][:2],
                    "supporting_citation_ids": [str(item) for item in _as_list(row.get("supporting_citation_ids")) if item][:2],
                    "supporting_source_ids": [str(item) for item in _as_list(row.get("supporting_source_ids")) if item][:3],
                    "priority_score": priority_score,
                    "selection_basis": selection_basis,
                },
            )
        )
    return [payload for _score, payload in sorted(matches, key=lambda item: (-item[0], item[1]["exhibit_id"]))]


def _strongest_documents(
    matter_evidence_index: dict[str, Any],
    *,
    issue_tracks: set[str],
    keywords: tuple[str, ...],
    supporting_finding_ids: list[str],
    supporting_citation_ids: list[str],
    supporting_uids: list[str],
) -> list[dict[str, Any]]:
    candidates = _document_candidates(
        matter_evidence_index,
        issue_tracks=issue_tracks,
        keywords=keywords,
        supporting_finding_ids=supporting_finding_ids,
        supporting_citation_ids=supporting_citation_ids,
        supporting_uids=supporting_uids,
    )
    return [
        row
        for row in candidates
        if any(
            basis not in {"keyword_fallback", "quoted_evidence_text", "locator_backed_excerpt"}
            for basis in row.get("selection_basis", [])
        )
    ][:2]


def _heuristic_candidate_documents(
    matter_evidence_index: dict[str, Any],
    *,
    issue_tracks: set[str],
    keywords: tuple[str, ...],
    supporting_finding_ids: list[str],
    supporting_citation_ids: list[str],
    supporting_uids: list[str],
) -> list[dict[str, Any]]:
    candidates = _document_candidates(
        matter_evidence_index,
        issue_tracks=issue_tracks,
        keywords=keywords,
        supporting_finding_ids=supporting_finding_ids,
        supporting_citation_ids=supporting_citation_ids,
        supporting_uids=supporting_uids,
    )
    return [
        row
        for row in candidates
        if row.get("selection_basis")
        and all(
            basis in {"keyword_fallback", "quoted_evidence_text", "locator_backed_excerpt"}
            for basis in row.get("selection_basis", [])
        )
    ][:2]


def _comparator_facts(comparative_treatment: dict[str, Any]) -> tuple[list[str], list[str]]:
    comparator_points = shared_comparator_points(comparative_treatment)
    facts: list[str] = []
    arguments: list[str] = []
    for point in comparator_points:
        strength = str(point.get("comparison_strength") or "")
        issue_label = str(point.get("issue_label") or point.get("issue_id") or "Comparator point")
        if strength in {"strong", "moderate"}:
            facts.append(
                "Comparator point supports unequal-treatment review for "
                f"{issue_label}: {str(point.get('point_summary') or '').strip()}"
            )
        if strength in {"weak", "not_comparable"}:
            arguments.append(
                str(point.get("counterargument") or "Comparator quality remains weak or not comparable on the current record.")
            )
    return facts[:2], arguments[:2]


def _retaliation_facts(retaliation_timeline_assessment: dict[str, Any]) -> tuple[list[str], list[str]]:
    retaliation_points = shared_retaliation_points(retaliation_timeline_assessment=retaliation_timeline_assessment)
    facts: list[str] = []
    arguments: list[str] = []
    for point in retaliation_points:
        strength = str(point.get("support_strength") or "")
        if strength in {"moderate", "limited"}:
            facts.append(f"Retaliation timing point: {str(point.get('point_summary') or '').strip()}")
        if strength != "moderate":
            arguments.append(str(point.get("counterargument") or "Retaliation timing remains limited on the current record."))
    return facts[:2], arguments[:2]


def _supporting_source_ids(
    matter_evidence_index: dict[str, Any],
    *,
    issue_tracks: set[str],
    supporting_finding_ids: list[str],
    supporting_citation_ids: list[str],
    supporting_uids: list[str],
) -> list[str]:
    """Return linked source ids for one issue row, preferring explicit evidence linkage."""
    rows = [row for row in _as_list(matter_evidence_index.get("rows")) if isinstance(row, dict)]
    issue_tag_ids = {tag_id for issue_track in issue_tracks for tag_id in issue_track_to_tag_ids(issue_track, context_text="")}
    finding_id_set = {str(item) for item in supporting_finding_ids if str(item).strip()}
    citation_id_set = {str(item) for item in supporting_citation_ids if str(item).strip()}
    uid_set = {str(item) for item in supporting_uids if str(item).strip()}
    source_ids: list[str] = []
    for row in rows:
        row_source_id = str(row.get("source_id") or "")
        if not row_source_id:
            continue
        row_finding_ids = {str(item) for item in _as_list(row.get("supporting_finding_ids")) if str(item).strip()}
        row_citation_ids = {str(item) for item in _as_list(row.get("supporting_citation_ids")) if str(item).strip()}
        row_uids = {str(item) for item in _as_list(row.get("supporting_uids")) if str(item).strip()}
        row_issue_tags = {str(item) for item in _as_list(row.get("main_issue_tags")) if str(item).strip()}
        if (
            finding_id_set & row_finding_ids
            or citation_id_set & row_citation_ids
            or uid_set & row_uids
            or issue_tag_ids & row_issue_tags
        ):
            if row_source_id not in source_ids:
                source_ids.append(row_source_id)
    return source_ids[:4]


def _urgency_text(issue_id: str, scope_text: str, findings: list[dict[str, Any]]) -> str:
    if issue_id in {"retaliation_massregelungsverbot", "pr_lpvg_participation", "sgb_ix_178_sbv"}:
        return "Potential urgency if current participation or post-complaint measures are ongoing."
    if issue_id in {"sgb_ix_167_bem", "sgb_ix_164", "fuersorgepflicht"}:
        return "Potential urgency if health-related process steps or accommodations are still pending."
    if any("deadline" in str(finding.get("finding_label") or "").lower() for finding in findings):
        return "Review for possible deadline-sensitive employment measures in the supporting record."
    return "No concrete deadline is established from the current record; relevance is mainly evidentiary."


def _source_conflict_signals(
    matter_evidence_index: dict[str, Any],
    *,
    strongest_documents: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Return conflict status and short summaries for one issue row."""
    rows_by_exhibit = {
        str(row.get("exhibit_id") or ""): row
        for row in _as_list(matter_evidence_index.get("rows"))
        if isinstance(row, dict) and str(row.get("exhibit_id") or "")
    }
    conflict_summaries: list[str] = []
    disputed = False
    for document in strongest_documents:
        exhibit_id = str(document.get("exhibit_id") or "")
        row = _as_dict(rows_by_exhibit.get(exhibit_id))
        if str(row.get("source_conflict_status") or "") != "disputed":
            continue
        disputed = True
        for item in _as_list(row.get("linked_source_conflicts")):
            summary = str(_as_dict(item).get("summary") or "").strip()
            if summary and summary not in conflict_summaries:
                conflict_summaries.append(summary)
    return ("contains_unresolved_source_conflict" if disputed else "no_material_conflict_detected", conflict_summaries[:2])


def _scope_missing_proof(
    *,
    issue_id: str,
    case_scope_quality: dict[str, Any],
    analysis_limits: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> list[str]:
    missing_fields = {str(item) for item in _as_list(case_scope_quality.get("missing_recommended_fields")) if str(item).strip()}
    downgrade_reasons = {str(item) for item in _as_list(analysis_limits.get("downgrade_reasons")) if str(item).strip()}
    comparator_summary = _as_dict(comparative_treatment.get("summary"))
    insufficiency = _as_dict(comparative_treatment.get("insufficiency"))
    rows: list[str] = []
    if issue_id in {"agg_disadvantage", "burden_shifting_indicators"} and (
        "comparator_actors" in missing_fields or comparator_summary.get("status") == "insufficient_comparator_scope"
    ):
        rows.append("Role-matched comparator actors and treatment records are still missing from the supplied case scope.")
    if issue_id == "retaliation_massregelungsverbot":
        if "trigger_events" in missing_fields:
            rows.append("Explicit dated trigger events are still missing from the supplied case scope.")
        if (
            "alleged_adverse_actions" in missing_fields
            or "retaliation_focus_without_alleged_adverse_actions" in downgrade_reasons
        ):
            rows.append("Dated alleged adverse actions are still missing from the supplied case scope.")
    if issue_id in {"sgb_ix_178_sbv", "pr_lpvg_participation"} and "participation_duty_gap_under_documented" in downgrade_reasons:
        rows.append("The intake still does not identify the relevant participation body or participation path clearly enough.")
    if issue_id in {"fuersorgepflicht", "sgb_ix_164", "sgb_ix_167_bem"} and "org_context" in missing_fields:
        rows.append("Organization or dependency context is still missing and weakens responsibility and accommodation analysis.")
    if insufficiency:
        rows.extend([str(item) for item in _as_list(insufficiency.get("recommended_next_inputs")) if str(item).strip()][:1])
    return list(dict.fromkeys(rows))


def build_lawyer_issue_matrix(
    *,
    case_bundle: dict[str, Any] | None,
    findings: list[dict[str, Any]] | None,
    matter_evidence_index: dict[str, Any] | None,
    comparative_treatment: dict[str, Any] | None,
    retaliation_timeline_assessment: dict[str, Any] | None,
    employment_issue_frameworks: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None = None,
    case_scope_quality: dict[str, Any] | None = None,
    analysis_limits: dict[str, Any] | None = None,
    include_full_issue_set: bool = False,
) -> dict[str, Any] | None:
    """Return a lawyer-facing legal-relevance matrix without giving final legal advice."""
    if not isinstance(case_bundle, dict):
        return None
    issue_framework_section = _as_dict(employment_issue_frameworks)
    issue_framework_rows = [item for item in _as_list(issue_framework_section.get("issue_tracks")) if isinstance(item, dict)]
    scope = _as_dict(case_bundle.get("scope"))
    selected_tracks = {str(item) for item in _as_list(scope.get("employment_issue_tracks")) if item}
    scope_text = _scope_text(case_bundle)
    findings_list = [item for item in (findings or []) if isinstance(item, dict)]
    matter_index = _as_dict(matter_evidence_index)
    comparator_payload = _as_dict(comparative_treatment)
    scope_quality = _as_dict(case_scope_quality)
    limits = _as_dict(analysis_limits)
    comparator_facts, comparator_arguments = _comparator_facts(comparator_payload)
    retaliation_facts, retaliation_arguments = _retaliation_facts(_as_dict(retaliation_timeline_assessment))
    rows: list[dict[str, Any]] = []

    for definition in _ISSUE_ROWS:
        issue_id = str(definition.get("issue_id") or "")
        title = str(definition.get("title") or issue_id)
        related_frameworks = [
            _find_issue_framework(issue_framework_rows, track)
            for track in definition.get("tracks", set())
            if _find_issue_framework(issue_framework_rows, track)
        ]
        is_selected = bool(set(definition.get("tracks", set())) & selected_tracks)
        has_scope_keywords = any(keyword in scope_text for keyword in definition.get("keywords", ()))
        if not include_full_issue_set and not is_selected and not has_scope_keywords:
            continue

        relevant_facts: list[str] = []
        opposing_arguments: list[str] = []
        missing_proof: list[str] = []
        supporting_finding_ids: list[str] = []
        supporting_citation_ids: list[str] = []
        supporting_uids: list[str] = []

        for framework in related_frameworks:
            status = str(framework.get("status") or "")
            support_reason = str(framework.get("support_reason") or "")
            if support_reason:
                relevant_facts.append(support_reason)
            if status != "supported_by_current_record":
                opposing_arguments.extend([str(item) for item in _as_list(framework.get("why_not_yet_supported")) if item])
            opposing_arguments.extend(
                [str(item) for item in _as_list(framework.get("normal_alternative_explanations"))[:1] if item]
            )
            missing_proof.extend([str(item) for item in _as_list(framework.get("missing_document_checklist"))[:2] if item])
            supporting_finding_ids.extend([str(item) for item in _as_list(framework.get("supporting_finding_ids")) if item])
            supporting_citation_ids.extend([str(item) for item in _as_list(framework.get("supporting_citation_ids")) if item])
            supporting_uids.extend([str(item) for item in _as_list(framework.get("supporting_uids")) if item])

        if issue_id in {"agg_disadvantage", "burden_shifting_indicators", "retaliation_massregelungsverbot"}:
            relevant_facts.extend(comparator_facts)
            opposing_arguments.extend(comparator_arguments)
        if issue_id == "retaliation_massregelungsverbot":
            relevant_facts.extend(retaliation_facts)
            opposing_arguments.extend(retaliation_arguments)
        if issue_id == "burden_shifting_indicators" and not comparator_facts:
            relevant_facts.append("Comparator asymmetry is not yet strong enough for a fuller burden-shifting read.")

        relevant_facts = list(dict.fromkeys([fact for fact in relevant_facts if fact]))[:4]
        opposing_arguments = list(dict.fromkeys([item for item in opposing_arguments if item]))[:3]
        missing_proof = list(dict.fromkeys([item for item in missing_proof if item]))[:4]
        missing_proof.extend(
            [
                item
                for item in _scope_missing_proof(
                    issue_id=issue_id,
                    case_scope_quality=scope_quality,
                    analysis_limits=limits,
                    comparative_treatment=comparator_payload,
                )
                if item not in missing_proof
            ]
        )
        missing_proof = list(dict.fromkeys([item for item in missing_proof if item]))[:4]
        strongest_documents = _strongest_documents(
            matter_index,
            issue_tracks=set(definition.get("tracks", set())),
            keywords=tuple(definition.get("document_keywords", ())),
            supporting_finding_ids=supporting_finding_ids,
            supporting_citation_ids=supporting_citation_ids,
            supporting_uids=supporting_uids,
        )
        heuristic_candidate_documents = _heuristic_candidate_documents(
            matter_index,
            issue_tracks=set(definition.get("tracks", set())),
            keywords=tuple(definition.get("document_keywords", ())),
            supporting_finding_ids=supporting_finding_ids,
            supporting_citation_ids=supporting_citation_ids,
            supporting_uids=supporting_uids,
        )
        supporting_source_ids = _supporting_source_ids(
            matter_index,
            issue_tracks=set(definition.get("tracks", set())),
            supporting_finding_ids=supporting_finding_ids,
            supporting_citation_ids=supporting_citation_ids,
            supporting_uids=supporting_uids,
        )
        source_conflict_status, unresolved_source_conflicts = _source_conflict_signals(
            matter_index,
            strongest_documents=strongest_documents,
        )
        chronology_conflicts = _as_dict(_as_dict(_as_dict(master_chronology).get("summary")).get("source_conflict_registry"))
        if (
            source_conflict_status == "no_material_conflict_detected"
            and int(chronology_conflicts.get("conflict_count") or 0) > 0
            and related_frameworks
        ):
            source_conflict_status = "possible_conflict_elsewhere_in_record"

        legal_relevance = "potentially_relevant"
        if related_frameworks and all(
            str(item.get("status") or "") == "supported_by_current_record" for item in related_frameworks
        ):
            legal_relevance = "supported_relevance"
        elif not relevant_facts:
            legal_relevance = "currently_under_supported"

        has_issue_support = bool(include_full_issue_set or related_frameworks or relevant_facts or missing_proof)
        if not has_issue_support:
            continue

        likely_opposing_argument = (
            opposing_arguments[0]
            if opposing_arguments
            else "Current record may still reflect ordinary management or incomplete proof."
        )

        rows.append(
            {
                "issue_id": issue_id,
                "title": title,
                "legal_relevance_status": legal_relevance,
                "relevant_facts": relevant_facts,
                "strongest_documents": strongest_documents,
                "heuristic_candidate_documents": heuristic_candidate_documents,
                "likely_opposing_argument": likely_opposing_argument,
                "missing_proof": missing_proof,
                "urgency_or_deadline_relevance": _urgency_text(issue_id, scope_text, findings_list),
                "source_conflict_status": source_conflict_status,
                "unresolved_source_conflicts": unresolved_source_conflicts,
                "supporting_finding_ids": list(dict.fromkeys(supporting_finding_ids))[:4],
                "supporting_citation_ids": list(dict.fromkeys(supporting_citation_ids))[:4],
                "supporting_uids": list(dict.fromkeys(supporting_uids))[:4],
                "supporting_source_ids": list(dict.fromkeys(supporting_source_ids))[:4],
                "not_legal_advice": True,
            }
        )

    return {
        "version": MATRIX_VERSION,
        "row_count": len(rows),
        "rows": rows,
    }
