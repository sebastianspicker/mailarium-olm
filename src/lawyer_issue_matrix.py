"""Counsel-facing legal-relevance matrix for German employment matters."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._utils import _as_dict, _as_list
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


def _scope_text(case_bundle: dict[str, Any]) -> str:
    scope = _as_dict(case_bundle.get("scope"))
    parts: list[str] = []
    for key in ("context_notes", "analysis_goal"):
        value = str(scope.get(key) or "").strip()
        if value:
            parts.append(value)
    for key in ("allegation_focus", "employment_issue_tags", "employment_issue_tracks"):
        for item in _as_list(scope.get(key)):
            text = str(item or "").strip()
            if text:
                parts.append(text)
    return " ".join(parts).lower()


def _find_issue_framework(issue_frameworks: list[dict[str, Any]], issue_track: str) -> dict[str, Any]:
    for item in issue_frameworks:
        if str(item.get("issue_track") or "") == issue_track:
            return item
    return {}


@dataclass(slots=True)
class _DocumentContext:
    issue_tag_ids: set[str]
    finding_ids: set[str]
    citation_ids: set[str]
    uids: set[str]
    priority_by_exhibit: dict[str, int]
    keywords: tuple[str, ...]


@dataclass(slots=True)
class _DocumentScore:
    value: int = 0
    basis: list[str] = field(default_factory=list)


def _document_candidates(
    matter_evidence_index: dict[str, Any],
    *,
    issue_tracks: set[str],
    keywords: tuple[str, ...],
    supporting_finding_ids: list[str],
    supporting_citation_ids: list[str],
    supporting_uids: list[str],
) -> list[dict[str, Any]]:
    rows = _dict_rows(matter_evidence_index.get("rows"))
    priorities = _priority_map(matter_evidence_index.get("top_15_exhibits"))
    context = _DocumentContext(
        issue_tag_ids=_issue_tag_ids(issue_tracks),
        finding_ids=_string_set(supporting_finding_ids),
        citation_ids=_string_set(supporting_citation_ids),
        uids=_string_set(supporting_uids),
        priority_by_exhibit=priorities,
        keywords=keywords,
    )
    matches = _document_matches(rows, context)
    return [payload for _score, payload in sorted(matches, key=lambda item: (-item[0], item[1]["exhibit_id"]))]


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [row for row in _as_list(value) if isinstance(row, dict)]


def _priority_map(value: object) -> dict[str, int]:
    return {
        exhibit_id: int(row.get("priority_score") or 0)
        for row in _dict_rows(value)
        if (exhibit_id := str(row.get("exhibit_id") or ""))
    }


def _issue_tag_ids(issue_tracks: set[str]) -> set[str]:
    return {tag_id for track in issue_tracks for tag_id in issue_track_to_tag_ids(track, context_text="")}


def _document_matches(rows, context):
    matches = []
    for row in rows:
        match = _document_match(row, context)
        if match:
            matches.append(match)
    return matches


def _document_match(row: dict[str, Any], context: _DocumentContext) -> tuple[int, dict[str, Any]] | None:
    quoted = _as_dict(row.get("quoted_evidence"))
    locator = _as_dict(row.get("document_locator"))
    haystacks = _document_haystacks(row, quoted)
    state = _DocumentScore()
    _apply_link_scores(state, row, context)
    _apply_quality_scores(state, row, context)
    _apply_text_scores(state, haystacks, locator)
    _apply_score_adjustments(state, row, context, haystacks)
    if state.value <= 0:
        return None
    priority = context.priority_by_exhibit.get(str(row.get("exhibit_id") or ""), 0)
    return state.value, _document_payload(row, priority, state.basis)


def _document_haystacks(row: dict[str, Any], quoted: dict[str, Any]) -> list[str]:
    return [
        str(row.get("short_description") or ""),
        str(row.get("why_it_matters") or ""),
        " ".join(str(item) for item in _as_list(row.get("main_issue_tags")) if item),
        str(quoted.get("original_text") or ""),
        str(quoted.get("translated_text") or ""),
        str(quoted.get("summary") or ""),
    ]


def _add_score(state: _DocumentScore, amount: int, basis: str) -> None:
    state.value += amount
    state.basis.append(basis)


def _apply_link_scores(state: _DocumentScore, row: dict[str, Any], context: _DocumentContext) -> None:
    checks = (
        (context.finding_ids & _string_set(row.get("supporting_finding_ids")), 100, "supporting_finding_link"),
        (context.citation_ids & _string_set(row.get("supporting_citation_ids")), 80, "supporting_citation_link"),
        (context.uids & _string_set(row.get("supporting_uids")), 60, "supporting_uid_link"),
        (context.issue_tag_ids & _row_issue_tags(row), 35, "issue_tag_link"),
    )
    for matched, amount, basis in checks:
        if matched:
            _add_score(state, amount, basis)


def _row_issue_tags(row: dict[str, Any]) -> set[str]:
    return {str(item) for key in ("main_issue_tags", "all_issue_tags") for item in _as_list(row.get(key)) if str(item).strip()}


def _apply_quality_scores(state: _DocumentScore, row: dict[str, Any], context: _DocumentContext) -> None:
    if str(row.get("source_conflict_status") or "") == "disputed":
        _add_score(state, 6, "source_conflict_signal")
    strength = str(_as_dict(row.get("exhibit_reliability")).get("strength") or "")
    if strength == "strong":
        _add_score(state, 8, "strong_reliability")
    elif strength == "moderate":
        _add_score(state, 4, "moderate_reliability")
    priority = context.priority_by_exhibit.get(str(row.get("exhibit_id") or ""), 0)
    if priority > 0:
        _add_score(state, min(priority, 12), "ranked_exhibit_priority")


def _has_support_signal(state: _DocumentScore) -> bool:
    support_bases = {
        "supporting_finding_link",
        "supporting_citation_link",
        "supporting_uid_link",
        "issue_tag_link",
        "ranked_exhibit_priority",
    }
    return any(basis in support_bases for basis in state.basis)


def _apply_text_scores(state: _DocumentScore, haystacks: list[str], locator: dict[str, Any]) -> None:
    quoted_text = " ".join(part for part in haystacks[3:] if part).strip()
    if not quoted_text:
        return
    state.value += 12
    if _has_support_signal(state):
        state.basis.append("quoted_evidence_text")
    if str(locator.get("evidence_handle") or ""):
        state.value += 6
        if _has_support_signal(state):
            state.basis.append("locator_backed_excerpt")


def _apply_score_adjustments(state: _DocumentScore, row: dict[str, Any], context: _DocumentContext, haystacks: list[str]) -> None:
    if str(_as_dict(row.get("source_reliability")).get("level") or "") == "low":
        state.value -= 4
    if str(row.get("promotability_status") or "") in {"lead_only_manual_review", "reference_only_not_promotable"}:
        state.value -= 8
    if context.keywords and any(keyword in " ".join(haystacks).lower() for keyword in context.keywords):
        _add_score(state, 10, "keyword_fallback")
    strength = str(_as_dict(row.get("exhibit_reliability")).get("strength") or "")
    if strength == "weak" and state.basis == ["keyword_fallback"]:
        state.value -= 6


def _document_payload(row: dict[str, Any], priority: int, basis: list[str]) -> dict[str, Any]:
    return {
        "exhibit_id": _text(row, "exhibit_id"),
        "source_id": _text(row, "source_id"),
        "short_description": _text(row, "short_description"),
        "source_language": _text(row, "source_language") or "unknown",
        "quoted_evidence": dict(row.get("quoted_evidence") or {}),
        "document_locator": dict(row.get("document_locator") or {}),
        "why_it_matters": _text(row, "why_it_matters"),
        "supporting_finding_ids": _strings(row.get("supporting_finding_ids"))[:2],
        "supporting_citation_ids": _strings(row.get("supporting_citation_ids"))[:2],
        "supporting_source_ids": _strings(row.get("supporting_source_ids"))[:3],
        "priority_score": priority,
        "selection_basis": basis,
    }


def _text(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "")


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
    rows = _dict_rows(matter_evidence_index.get("rows"))
    issue_tag_ids = _issue_tag_ids(issue_tracks)
    finding_id_set = _string_set(supporting_finding_ids)
    citation_id_set = _string_set(supporting_citation_ids)
    uid_set = _string_set(supporting_uids)
    source_ids: list[str] = []
    for row in rows:
        row_source_id = str(row.get("source_id") or "")
        if not row_source_id:
            continue
        _append_source_if_supported(source_ids, row_source_id, row, finding_id_set, citation_id_set, uid_set, issue_tag_ids)
    return source_ids[:4]


def _append_source_if_supported(source_ids, source_id, row, finding_ids, citation_ids, uids, issue_tags):
    if source_id not in source_ids and _row_supports_issue(row, finding_ids, citation_ids, uids, issue_tags):
        source_ids.append(source_id)


def _string_set(value: object) -> set[str]:
    return {str(item) for item in _as_list(value) if str(item).strip()}


def _row_supports_issue(row, finding_ids, citation_ids, uids, issue_tags):
    return bool(
        finding_ids & _string_set(row.get("supporting_finding_ids"))
        or citation_ids & _string_set(row.get("supporting_citation_ids"))
        or uids & _string_set(row.get("supporting_uids"))
        or issue_tags & _string_set(row.get("main_issue_tags"))
    )


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
    rows_by_exhibit = _rows_by_id(matter_evidence_index.get("rows"), "exhibit_id")
    conflict_summaries: list[str] = []
    disputed = False
    for document in strongest_documents:
        exhibit_id = str(document.get("exhibit_id") or "")
        row = _as_dict(rows_by_exhibit.get(exhibit_id))
        summaries = _disputed_conflict_summaries(row)
        if summaries:
            disputed = True
            for summary in summaries:
                if summary not in conflict_summaries:
                    conflict_summaries.append(summary)
    return ("contains_unresolved_source_conflict" if disputed else "no_material_conflict_detected", conflict_summaries[:2])


def _rows_by_id(value: object, field: str) -> dict[str, dict[str, Any]]:
    return {row_id: row for row in _as_list(value) if isinstance(row, dict) and (row_id := str(row.get(field) or ""))}


def _disputed_conflict_summaries(row: dict[str, Any]) -> list[str]:
    if str(row.get("source_conflict_status") or "") != "disputed":
        return []
    return [
        summary
        for item in _as_list(row.get("linked_source_conflicts"))
        if (summary := str(_as_dict(item).get("summary") or "").strip())
    ]


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
    rows = _base_scope_missing_proof(issue_id, missing_fields, downgrade_reasons, comparator_summary)
    if insufficiency:
        rows.extend([str(item) for item in _as_list(insufficiency.get("recommended_next_inputs")) if str(item).strip()][:1])
    return list(dict.fromkeys(rows))


def _base_scope_missing_proof(issue_id, missing_fields, downgrade_reasons, comparator_summary):
    rows = []
    comparator_missing = (
        "comparator_actors" in missing_fields or comparator_summary.get("status") == "insufficient_comparator_scope"
    )
    if issue_id in {"agg_disadvantage", "burden_shifting_indicators"} and comparator_missing:
        rows.append("Role-matched comparator actors and treatment records are still missing from the supplied case scope.")
    if issue_id == "retaliation_massregelungsverbot":
        rows.extend(_retaliation_scope_gaps(missing_fields, downgrade_reasons))
    if issue_id in {"sgb_ix_178_sbv", "pr_lpvg_participation"} and "participation_duty_gap_under_documented" in downgrade_reasons:
        rows.append("The intake still does not identify the relevant participation body or participation path clearly enough.")
    if issue_id in {"fuersorgepflicht", "sgb_ix_164", "sgb_ix_167_bem"} and "org_context" in missing_fields:
        rows.append("Organization or dependency context is still missing and weakens responsibility and accommodation analysis.")
    return rows


def _retaliation_scope_gaps(missing_fields, downgrade_reasons):
    rows = []
    if "trigger_events" in missing_fields:
        rows.append("Explicit dated trigger events are still missing from the supplied case scope.")
    if "alleged_adverse_actions" in missing_fields or "retaliation_focus_without_alleged_adverse_actions" in downgrade_reasons:
        rows.append("Dated alleged adverse actions are still missing from the supplied case scope.")
    return rows


@dataclass(slots=True)
class _MatrixContext:
    issue_framework_rows: list[dict[str, Any]]
    selected_tracks: set[str]
    scope_text: str
    findings: list[dict[str, Any]]
    matter_index: dict[str, Any]
    comparator_payload: dict[str, Any]
    comparator_facts: list[str]
    comparator_arguments: list[str]
    retaliation_facts: list[str]
    retaliation_arguments: list[str]
    master_chronology: dict[str, Any]
    scope_quality: dict[str, Any]
    limits: dict[str, Any]
    include_full_issue_set: bool


@dataclass(slots=True)
class _IssueSupport:
    relevant_facts: list[str] = field(default_factory=list)
    opposing_arguments: list[str] = field(default_factory=list)
    missing_proof: list[str] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)
    citation_ids: list[str] = field(default_factory=list)
    uids: list[str] = field(default_factory=list)


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
    context = _matrix_context(
        case_bundle,
        findings,
        matter_evidence_index,
        comparative_treatment,
        retaliation_timeline_assessment,
        employment_issue_frameworks,
        master_chronology,
        case_scope_quality,
        analysis_limits,
        include_full_issue_set,
    )
    rows = [row for definition in _ISSUE_ROWS if (row := _issue_row(definition, context))]
    return {"version": MATRIX_VERSION, "row_count": len(rows), "rows": rows}


def _matrix_context(
    case_bundle, findings, matter_index, comparator, retaliation, frameworks, chronology, scope_quality, limits, include_full
):
    framework_rows = [item for item in _as_list(_as_dict(frameworks).get("issue_tracks")) if isinstance(item, dict)]
    scope = _as_dict(case_bundle.get("scope"))
    comparator_payload = _as_dict(comparator)
    comparator_facts, comparator_arguments = _comparator_facts(comparator_payload)
    retaliation_facts, retaliation_arguments = _retaliation_facts(_as_dict(retaliation))
    return _MatrixContext(
        issue_framework_rows=framework_rows,
        selected_tracks={str(item) for item in _as_list(scope.get("employment_issue_tracks")) if item},
        scope_text=_scope_text(case_bundle),
        findings=[item for item in (findings or []) if isinstance(item, dict)],
        matter_index=_as_dict(matter_index),
        comparator_payload=comparator_payload,
        comparator_facts=comparator_facts,
        comparator_arguments=comparator_arguments,
        retaliation_facts=retaliation_facts,
        retaliation_arguments=retaliation_arguments,
        master_chronology=_as_dict(chronology),
        scope_quality=_as_dict(scope_quality),
        limits=_as_dict(limits),
        include_full_issue_set=include_full,
    )


def _issue_row(definition: dict[str, Any], context: _MatrixContext) -> dict[str, Any] | None:
    issue_id = str(definition.get("issue_id") or "")
    tracks = set(definition.get("tracks", set()))
    related = [_find_issue_framework(context.issue_framework_rows, track) for track in tracks]
    related = [row for row in related if row]
    if not _definition_in_scope(definition, context, tracks):
        return None
    support = _framework_support(related)
    _apply_issue_facts(issue_id, support, context)
    support.relevant_facts = _unique(support.relevant_facts, 4)
    support.opposing_arguments = _unique(support.opposing_arguments, 3)
    support.missing_proof = _missing_proof(issue_id, support.missing_proof, context)
    strongest, heuristic, source_ids = _issue_documents(definition, support, context)
    conflict_status, conflicts = _issue_conflicts(strongest, related, context)
    legal_relevance = _legal_relevance(related, support.relevant_facts)
    if not (context.include_full_issue_set or related or support.relevant_facts or support.missing_proof):
        return None
    opposing = (
        support.opposing_arguments[0]
        if support.opposing_arguments
        else "Current record may still reflect ordinary management or incomplete proof."
    )
    return {
        "issue_id": issue_id,
        "title": str(definition.get("title") or issue_id),
        "legal_relevance_status": legal_relevance,
        "relevant_facts": support.relevant_facts,
        "strongest_documents": strongest,
        "heuristic_candidate_documents": heuristic,
        "likely_opposing_argument": opposing,
        "missing_proof": support.missing_proof,
        "urgency_or_deadline_relevance": _urgency_text(issue_id, context.scope_text, context.findings),
        "source_conflict_status": conflict_status,
        "unresolved_source_conflicts": conflicts,
        "supporting_finding_ids": _unique(support.finding_ids, 4),
        "supporting_citation_ids": _unique(support.citation_ids, 4),
        "supporting_uids": _unique(support.uids, 4),
        "supporting_source_ids": _unique(source_ids, 4),
        "not_legal_advice": True,
    }


def _definition_in_scope(definition, context, tracks):
    selected = bool(tracks & context.selected_tracks)
    keyword_match = any(keyword in context.scope_text for keyword in definition.get("keywords", ()))
    return context.include_full_issue_set or selected or keyword_match


def _framework_support(frameworks) -> _IssueSupport:
    support = _IssueSupport()
    for framework in frameworks:
        reason = str(framework.get("support_reason") or "")
        if reason:
            support.relevant_facts.append(reason)
        if str(framework.get("status") or "") != "supported_by_current_record":
            support.opposing_arguments.extend(_strings(framework.get("why_not_yet_supported")))
        support.opposing_arguments.extend(_strings(_as_list(framework.get("normal_alternative_explanations"))[:1]))
        support.missing_proof.extend(_strings(_as_list(framework.get("missing_document_checklist"))[:2]))
        support.finding_ids.extend(_strings(framework.get("supporting_finding_ids")))
        support.citation_ids.extend(_strings(framework.get("supporting_citation_ids")))
        support.uids.extend(_strings(framework.get("supporting_uids")))
    return support


def _strings(value: object) -> list[str]:
    return [str(item) for item in _as_list(value) if item]


def _apply_issue_facts(issue_id: str, support: _IssueSupport, context: _MatrixContext) -> None:
    if issue_id in {"agg_disadvantage", "burden_shifting_indicators", "retaliation_massregelungsverbot"}:
        support.relevant_facts.extend(context.comparator_facts)
        support.opposing_arguments.extend(context.comparator_arguments)
    if issue_id == "retaliation_massregelungsverbot":
        support.relevant_facts.extend(context.retaliation_facts)
        support.opposing_arguments.extend(context.retaliation_arguments)
    if issue_id == "burden_shifting_indicators" and not context.comparator_facts:
        support.relevant_facts.append("Comparator asymmetry is not yet strong enough for a fuller burden-shifting read.")


def _unique(values: list[str], limit: int) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))[:limit]


def _missing_proof(issue_id: str, values: list[str], context: _MatrixContext) -> list[str]:
    rows = _unique(values, 4)
    additions = _scope_missing_proof(
        issue_id=issue_id,
        case_scope_quality=context.scope_quality,
        analysis_limits=context.limits,
        comparative_treatment=context.comparator_payload,
    )
    rows.extend(item for item in additions if item not in rows)
    return _unique(rows, 4)


def _issue_documents(definition, support, context):
    kwargs = {
        "issue_tracks": set(definition.get("tracks", set())),
        "keywords": tuple(definition.get("document_keywords", ())),
        "supporting_finding_ids": support.finding_ids,
        "supporting_citation_ids": support.citation_ids,
        "supporting_uids": support.uids,
    }
    strongest = _strongest_documents(context.matter_index, **kwargs)
    heuristic = _heuristic_candidate_documents(context.matter_index, **kwargs)
    sources = _supporting_source_ids(
        context.matter_index,
        issue_tracks=kwargs["issue_tracks"],
        supporting_finding_ids=support.finding_ids,
        supporting_citation_ids=support.citation_ids,
        supporting_uids=support.uids,
    )
    return strongest, heuristic, sources


def _issue_conflicts(strongest, related, context):
    status, conflicts = _source_conflict_signals(context.matter_index, strongest_documents=strongest)
    chronology = _as_dict(_as_dict(context.master_chronology.get("summary")).get("source_conflict_registry"))
    if status == "no_material_conflict_detected" and int(chronology.get("conflict_count") or 0) > 0 and related:
        status = "possible_conflict_elsewhere_in_record"
    return status, conflicts


def _legal_relevance(related, relevant_facts):
    if related and all(str(item.get("status") or "") == "supported_by_current_record" for item in related):
        return "supported_relevance"
    if not relevant_facts:
        return "currently_under_supported"
    return "potentially_relevant"
