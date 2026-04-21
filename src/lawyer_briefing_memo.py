"""Compact lawyer-briefing memo rendering from shared matter registries."""

from __future__ import annotations

from typing import Any

from .trigger_retaliation import shared_retaliation_points

LAWYER_BRIEFING_MEMO_VERSION = "1"
_GENERIC_MEMO_TEXTS = {
    "provides direct record material relevant to the synthetic matter review.",
    "documented record material relevant to the synthetic matter review.",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _memo_entry(
    *,
    entry_id: str,
    text: str,
    exhibit_ids: list[str] | None = None,
    chronology_ids: list[str] | None = None,
    issue_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_language: str = "",
    quoted_evidence: dict[str, Any] | None = None,
    document_locator: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "text": _compact(text),
        "supporting_exhibit_ids": [str(item) for item in exhibit_ids or [] if _compact(item)],
        "supporting_chronology_ids": [str(item) for item in chronology_ids or [] if _compact(item)],
        "supporting_issue_ids": [str(item) for item in issue_ids or [] if _compact(item)],
        "supporting_source_ids": [str(item) for item in source_ids or [] if _compact(item)],
        "source_language": str(source_language or ""),
        "quoted_evidence": dict(quoted_evidence or {}),
        "document_locator": dict(document_locator or {}),
    }


def _usable_text(value: Any) -> str:
    text = _compact(value)
    if not text:
        return ""
    if text.lower() in _GENERIC_MEMO_TEXTS:
        return ""
    if text.lower().startswith("on 2024-01-01, case_prompt"):
        return ""
    return text


def _chronology_source_status(entry: dict[str, Any]) -> str:
    return str(_as_dict(entry.get("source_linkage")).get("source_evidence_status") or "").strip()


def _has_source_linkage(entry: dict[str, Any]) -> bool:
    return bool([item for item in _as_list(_as_dict(entry.get("source_linkage")).get("source_ids")) if _compact(item)])


def _timeline_entry_text(entry: dict[str, Any]) -> str:
    base_text = _first_nonempty(
        f"{entry.get('date') or ''}: {entry.get('title') or ''}",
        entry.get("description"),
    )
    source_status = _chronology_source_status(entry)
    if source_status == "scope_only":
        return f"[Scope-supplied chronology] {base_text}".strip()
    if source_status == "timeline_only" or not _has_source_linkage(entry):
        return f"[Timeline-only chronology] {base_text}".strip()
    return base_text


def build_lawyer_briefing_memo(
    *,
    case_bundle: dict[str, Any] | None,
    matter_workspace: dict[str, Any] | None,
    matter_evidence_index: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
    lawyer_issue_matrix: dict[str, Any] | None,
    retaliation_timeline_assessment: dict[str, Any] | None,
    skeptical_employer_review: dict[str, Any] | None,
    document_request_checklist: dict[str, Any] | None,
    promise_contradiction_analysis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a compact, evidence-bound onboarding memo for counsel."""
    scope = _as_dict(_as_dict(case_bundle).get("scope"))
    matter = _as_dict(_as_dict(matter_workspace).get("matter"))
    evidence_rows = [row for row in _as_list(_as_dict(matter_evidence_index).get("rows")) if isinstance(row, dict)]
    chronology_entries = [row for row in _as_list(_as_dict(master_chronology).get("entries")) if isinstance(row, dict)]
    issue_rows = [row for row in _as_list(_as_dict(lawyer_issue_matrix).get("rows")) if isinstance(row, dict)]
    retaliation_timeline = _as_dict(retaliation_timeline_assessment)
    retaliation_points = shared_retaliation_points(retaliation_timeline_assessment=retaliation_timeline)
    weaknesses = [row for row in _as_list(_as_dict(skeptical_employer_review).get("weaknesses")) if isinstance(row, dict)]
    request_groups = [row for row in _as_list(_as_dict(document_request_checklist).get("groups")) if isinstance(row, dict)]
    contradiction_rows = [
        row for row in _as_list(_as_dict(promise_contradiction_analysis).get("contradiction_table")) if isinstance(row, dict)
    ]

    if not (evidence_rows or chronology_entries or issue_rows or weaknesses or request_groups or contradiction_rows):
        return None

    target_person = _as_dict(scope.get("target_person"))
    target_label = _first_nonempty(
        _compact(target_person.get("name")),
        _compact(target_person.get("email")),
        _compact(matter.get("case_label")),
        "the target employee",
    )
    source_backed_chronology = [row for row in chronology_entries if _has_source_linkage(row)]
    lead_chronology = source_backed_chronology[0] if source_backed_chronology else None
    date_range = _as_dict(_as_dict(master_chronology).get("summary")).get("date_range")
    date_range_text = _first_nonempty(
        f"{_as_dict(date_range).get('first') or ''} to {_as_dict(date_range).get('last') or ''}".strip(" to"),
        f"{scope.get('date_from') or ''} to {scope.get('date_to') or ''}".strip(" to"),
    )

    executive_summary = [
        _memo_entry(
            entry_id="memo:executive:1",
            text=(
                f"This memo summarizes the current record concerning {target_label}"
                f"{f' for the period {date_range_text}' if date_range_text else ''}. "
                f"It is intended as a rapid onboarding product for counsel and stays evidence-bound."
            ),
            exhibit_ids=[str(evidence_rows[0].get("exhibit_id") or "")] if evidence_rows else [],
            chronology_ids=[str(lead_chronology.get("chronology_id") or "")] if lead_chronology else [],
            source_ids=[str(evidence_rows[0].get("source_id") or "")] if evidence_rows else [],
        )
    ]

    key_facts = [
        _memo_entry(
            entry_id=f"memo:key_fact:{index}",
            text=_first_nonempty(_usable_text(row.get("short_description")), _usable_text(row.get("why_it_matters"))),
            exhibit_ids=[str(row.get("exhibit_id") or "")],
            source_ids=[str(row.get("source_id") or "")],
        )
        for index, row in enumerate(evidence_rows[:3], start=1)
        if _first_nonempty(_usable_text(row.get("short_description")), _usable_text(row.get("why_it_matters")))
    ]

    timeline_entries = source_backed_chronology[:4] if source_backed_chronology else chronology_entries[:2]
    timeline = [
        _memo_entry(
            entry_id=f"memo:timeline:{index}",
            text=_timeline_entry_text(row),
            chronology_ids=[str(row.get("chronology_id") or "")],
            source_ids=[str(item) for item in _as_list(_as_dict(row.get("source_linkage")).get("source_ids"))[:2] if item],
        )
        for index, row in enumerate(timeline_entries, start=1)
        if _first_nonempty(row.get("title"), row.get("description"), row.get("date"))
    ]

    core_theories = [
        _memo_entry(
            entry_id=f"memo:theory:{index}",
            text=(
                f"{row.get('title') or row.get('issue_id') or 'Issue'}: "
                f"{str(row.get('legal_relevance_status') or 'currently_under_supported').replace('_', ' ')}. "
                f"{_first_nonempty(row.get('relevant_facts'), row.get('missing_proof'), row.get('likely_opposing_argument'))}"
            ),
            issue_ids=[str(row.get("issue_id") or "")],
            exhibit_ids=[
                str(item.get("exhibit_id") or "")
                for item in _as_list(row.get("strongest_documents"))[:2]
                if isinstance(item, dict)
            ],
        )
        for index, row in enumerate(issue_rows[:3], start=1)
    ]

    strongest_evidence = [
        _memo_entry(
            entry_id=f"memo:evidence:{index}",
            text=(
                f"{row.get('exhibit_id') or ''}: "
                f"{_first_nonempty(_usable_text(row.get('short_description')), _usable_text(row.get('why_it_matters')))} "
                f"[{_as_dict(row.get('exhibit_reliability')).get('strength') or ''}]"
            ),
            exhibit_ids=[str(row.get("exhibit_id") or "")],
            source_ids=[str(row.get("source_id") or "")],
            source_language=str(row.get("source_language") or ""),
            quoted_evidence=_as_dict(row.get("quoted_evidence")),
            document_locator=_as_dict(row.get("document_locator")),
        )
        for index, row in enumerate(_as_list(_as_dict(matter_evidence_index).get("top_15_exhibits"))[:3], start=1)
        if isinstance(row, dict)
        and _first_nonempty(_usable_text(row.get("short_description")), _usable_text(row.get("why_it_matters")))
    ]

    weaknesses_or_risks = [
        _memo_entry(
            entry_id=f"memo:risk:{index}",
            text=_first_nonempty(row.get("critique"), _as_dict(row.get("repair_guidance")).get("how_to_fix")),
            exhibit_ids=[str(item) for item in _as_list(row.get("supporting_exhibit_ids"))[:2] if item],
            chronology_ids=[str(item) for item in _as_list(row.get("supporting_chronology_ids"))[:2] if item],
            issue_ids=[str(item) for item in _as_list(row.get("supporting_issue_ids"))[:2] if item],
            source_ids=[str(item) for item in _as_list(row.get("supporting_source_ids"))[:2] if item],
        )
        for index, row in enumerate(weaknesses[:3], start=1)
        if _first_nonempty(row.get("critique"), _as_dict(row.get("repair_guidance")).get("how_to_fix"))
    ]
    confounders = [
        row for row in _as_list(retaliation_timeline.get("strongest_non_retaliatory_explanations")) if isinstance(row, dict)
    ]
    if retaliation_points:
        point = retaliation_points[0]
        core_theories.append(
            _memo_entry(
                entry_id="memo:theory:retaliation",
                text=f"Retaliation timing: {_first_nonempty(point.get('point_summary'))}",
            )
        )
    if confounders:
        explanations = ", ".join(
            str(row.get("explanation") or "") for row in confounders[:2] if str(row.get("explanation") or "")
        )
        weaknesses_or_risks.append(
            _memo_entry(
                entry_id="memo:risk:retaliation_confounders",
                text=(f"Retaliation timing remains bounded by explicit confounders in the current record: {explanations}."),
            )
        )

    urgent_next_steps = [
        _memo_entry(
            entry_id=f"memo:next_step:{index}",
            text=_first_nonempty(
                _as_dict(items[0]).get("request") if items else "",
                group.get("title"),
            ),
            source_ids=[
                str(item.get("source_id") or "")
                for issue in issue_rows[:1]
                for item in _as_list(issue.get("strongest_documents"))[:1]
                if isinstance(item, dict) and str(item.get("source_id") or "")
            ],
            issue_ids=[str(issue_rows[0].get("issue_id") or "")] if issue_rows else [],
        )
        for index, group in enumerate(request_groups[:3], start=1)
        for items in [[item for item in _as_list(group.get("items")) if isinstance(item, dict)]]
    ]

    open_questions_for_counsel = [
        _memo_entry(
            entry_id=f"memo:question:{index}",
            text=(
                f"How should counsel treat this contradiction: "
                f"{_first_nonempty(row.get('original_statement_or_promise'), row.get('later_action'))}"
            ),
            source_ids=[str(item) for item in [row.get("original_source_id"), row.get("later_source_id")] if _compact(item)],
        )
        for index, row in enumerate(contradiction_rows[:2], start=1)
    ]
    if not open_questions_for_counsel and issue_rows:
        open_questions_for_counsel.append(
            _memo_entry(
                entry_id="memo:question:default",
                text=(
                    "Which issue track should receive priority in early counsel review given the current mix of "
                    "supported documents, chronology, and missing proof?"
                ),
                issue_ids=[str(row.get("issue_id") or "") for row in issue_rows[:2] if str(row.get("issue_id") or "")],
                source_ids=[
                    str(item.get("source_id") or "")
                    for row in issue_rows[:2]
                    for item in _as_list(row.get("strongest_documents"))[:1]
                    if isinstance(item, dict) and str(item.get("source_id") or "")
                ],
            )
        )

    section_map = {
        "executive_summary": executive_summary,
        "key_facts": key_facts,
        "timeline": timeline,
        "core_theories": core_theories,
        "strongest_evidence": strongest_evidence,
        "weaknesses_or_risks": weaknesses_or_risks,
        "urgent_next_steps": urgent_next_steps,
        "open_questions_for_counsel": open_questions_for_counsel,
    }
    summary = {
        "section_count": len(section_map),
        "entry_count": sum(len(entries) for entries in section_map.values()),
        "compact_length_budget": "short_onboarding_memo",
        "non_repetition_policy": True,
        "evidence_bound": True,
    }
    return {
        "version": LAWYER_BRIEFING_MEMO_VERSION,
        "memo_format": "lawyer_onboarding_brief",
        "summary": summary,
        "sections": section_map,
    }
