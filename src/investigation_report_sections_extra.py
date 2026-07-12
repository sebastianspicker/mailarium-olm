"""Lower-level report section builders extracted from the main investigation renderer."""

from __future__ import annotations

from typing import Any

from .investigation_report_sections import _as_dict, _as_list, _section_with_entries
from .matter_evidence_index import build_matter_evidence_index

_SKEPTICAL_REVIEW_INSUFFICIENCY_REASON = (
    "The current case bundle does not yet expose enough concrete weakness patterns for a skeptical employer-side review."
)
_MATTER_INDEX_REASON = "The current case bundle does not yet contain enough source material for an exhibit index."
_LAWYER_MATRIX_REASON = "The current case bundle does not yet contain enough issue-linked support for the lawyer issue matrix."
_PROMISE_REASON = (
    "The current case bundle does not yet contain enough mixed-source promise, omission, "
    "or contradiction material for this section."
)
_MEMO_REASON = (
    "The current case bundle does not yet contain enough stable matter, evidence, chronology, "
    "and issue data for the lawyer briefing memo."
)
_DRAFTING_REASON = (
    "The current case bundle does not yet contain enough stable evidence and framing data for controlled factual drafting."
)


def _empty_payload_section(
    section_id: str, title: str, payload: dict[str, Any] | None, field: str, reason: str
) -> dict[str, Any]:
    section = _section_with_entries(section_id=section_id, title=title, entries=[], insufficiency_reason=reason)
    section[field] = payload
    return section


def _short_values(value: object, limit: int = 3) -> list[str]:
    return [str(item) for item in _as_list(value) if item][:limit]


def _matter_index_entry(row: dict[str, Any], index: int) -> dict[str, Any]:
    reliability = _as_dict(row.get("exhibit_reliability"))
    readiness = _as_dict(reliability.get("next_step_logic")).get("readiness") or row.get("readiness") or "readiness_unknown"
    strength = reliability.get("strength") or row.get("strength") or row.get("reliability_or_evidentiary_strength") or ""
    return {
        "entry_id": f"matter_index:{row.get('exhibit_id') or index}",
        "statement": f"{row.get('exhibit_id') or ''}: {row.get('short_description') or ''} [{strength}; {readiness}]".strip(),
        "supporting_finding_ids": _short_values(row.get("supporting_finding_ids")),
        "supporting_citation_ids": _short_values(row.get("supporting_citation_ids")),
        "supporting_uids": _short_values(row.get("supporting_uids")),
        "supporting_source_ids": _short_values(row.get("supporting_source_ids")),
        "supporting_evidence_handles": _short_values(row.get("supporting_evidence_handles")),
    }


def _lawyer_matrix_entry(row: dict[str, Any], index: int) -> dict[str, Any]:
    status = str(row.get("legal_relevance_status") or "currently_under_supported").replace("_", " ")
    return {
        "entry_id": f"lawyer_matrix:{row.get('issue_id') or index}",
        "statement": f"{row.get('title') or ''} is currently mapped as {status}.".strip(),
        "supporting_finding_ids": _short_values(row.get("supporting_finding_ids")),
        "supporting_citation_ids": _short_values(row.get("supporting_citation_ids")),
        "supporting_uids": _short_values(row.get("supporting_uids")),
        "supporting_source_ids": _short_values(row.get("supporting_source_ids")),
    }


def _promise_entry(row: dict[str, Any], index: int) -> dict[str, Any]:
    source_ids = [
        str(item)
        for item in [row.get("original_source_id"), row.get("later_source_id"), *_as_list(row.get("later_source_ids"))]
        if str(item or "")
    ]
    later = row.get("later_action") or row.get("later_summary_context") or "not clearly reflected"
    confidence = row.get("confidence_level") or "low"
    statement = f"{row.get('original_statement_or_promise') or ''} Later record: {later} [{confidence} confidence]"
    return {
        "entry_id": f"promise_contradiction:{row.get('row_id') or index}",
        "statement": statement.strip(),
        "supporting_finding_ids": [],
        "supporting_citation_ids": [],
        "supporting_uids": _short_values(row.get("supporting_uids")),
        "supporting_source_ids": source_ids[:3],
    }


def _linked_entry(entry: dict[str, Any], identifier: str, fallback: str) -> dict[str, Any]:
    return {
        "entry_id": str(entry.get(identifier) or fallback),
        "statement": str(entry.get("text") or ""),
        "supporting_finding_ids": [],
        "supporting_citation_ids": [],
        "supporting_uids": [],
        "supporting_exhibit_ids": _short_values(entry.get("supporting_exhibit_ids"), 2),
        "supporting_chronology_ids": _short_values(entry.get("supporting_chronology_ids"), 2),
        "supporting_issue_ids": _short_values(entry.get("supporting_issue_ids"), 2),
        "supporting_source_ids": _short_values(entry.get("supporting_source_ids"), 2),
    }


def _matter_evidence_index_section(
    *,
    case_bundle: dict[str, Any],
    multi_source_case_bundle: dict[str, Any] | None,
    finding_evidence_index: dict[str, Any],
    master_chronology: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a report-facing summary section for the durable exhibit register."""
    matter_evidence_index = build_matter_evidence_index(
        case_bundle=case_bundle,
        multi_source_case_bundle=multi_source_case_bundle,
        finding_evidence_index=finding_evidence_index,
        master_chronology=master_chronology,
    )
    if not isinstance(matter_evidence_index, dict):
        return _empty_payload_section(
            "matter_evidence_index", "Matter Evidence Index", {}, "matter_evidence_index", _MATTER_INDEX_REASON
        )

    ranked_exhibits = [row for row in _as_list(matter_evidence_index.get("top_15_exhibits")) if isinstance(row, dict)]
    rows = ranked_exhibits or [row for row in _as_list(matter_evidence_index.get("rows")) if isinstance(row, dict)]
    entries = [_matter_index_entry(row, index) for index, row in enumerate(rows[:4], start=1)]
    section = _section_with_entries(
        section_id="matter_evidence_index",
        title="Matter Evidence Index",
        entries=entries,
        insufficiency_reason="The current case bundle does not yet contain enough source material for an exhibit index.",
    )
    section["matter_evidence_index"] = matter_evidence_index
    return section


def _lawyer_issue_matrix_section(
    *,
    lawyer_issue_matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a lawyer-facing issue matrix that stays at legal-relevance mapping."""
    matrix_rows = [row for row in _as_list(_as_dict(lawyer_issue_matrix).get("rows")) if isinstance(row, dict)]
    if not matrix_rows:
        return _empty_payload_section(
            "lawyer_issue_matrix",
            "German Employment Lawyer Issue Matrix",
            _as_dict(lawyer_issue_matrix),
            "lawyer_issue_matrix",
            _LAWYER_MATRIX_REASON,
        )

    actionable_rows = [row for row in matrix_rows if str(row.get("legal_relevance_status") or "") != "currently_under_supported"]
    if not actionable_rows:
        return _empty_payload_section(
            "lawyer_issue_matrix",
            "German Employment Lawyer Issue Matrix",
            lawyer_issue_matrix,
            "lawyer_issue_matrix",
            _LAWYER_MATRIX_REASON,
        )

    entries = [_lawyer_matrix_entry(row, index) for index, row in enumerate(actionable_rows[:4], start=1)]
    section = _section_with_entries(
        section_id="lawyer_issue_matrix",
        title="German Employment Lawyer Issue Matrix",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet contain enough issue-linked support for the lawyer issue matrix."
        ),
    )
    section["lawyer_issue_matrix"] = lawyer_issue_matrix
    return section


def _actor_and_witness_map_section(
    *,
    actor_witness_map: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report-facing actor and witness map section."""
    actor_map = _as_dict(_as_dict(actor_witness_map).get("actor_map"))
    witness_map = _as_dict(_as_dict(actor_witness_map).get("witness_map"))
    actors = [row for row in _as_list(actor_map.get("actors")) if isinstance(row, dict)]
    if not actors:
        section = _section_with_entries(
            section_id="actor_and_witness_map",
            title="Actor And Witness Map",
            entries=[],
            insufficiency_reason=(
                "The current case bundle does not yet contain enough stable actor linkage for an actor and witness map."
            ),
        )
        section["actor_map"] = actor_map
        section["witness_map"] = witness_map
        return section

    entries: list[dict[str, Any]] = []
    for index, actor in enumerate(actors[:4], start=1):
        status = _as_dict(actor.get("status"))
        status_labels = [
            label.replace("_", " ")
            for label in ("decision_maker", "witness", "gatekeeper", "supporter")
            if bool(status.get(label))
        ]
        entries.append(
            {
                "entry_id": f"actor_map:{actor.get('actor_id') or index}",
                "statement": (
                    f"{actor.get('name') or actor.get('email') or actor.get('actor_id')}: "
                    f"{actor.get('relationship_to_events') or ''} "
                    f"Current status reads as {', '.join(status_labels) if status_labels else 'unclassified actor'}; "
                    f"case impact is {str(actor.get('helps_hurts_mixed') or 'mixed').replace('_', ' ')}."
                ).strip(),
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [str(item) for item in _as_list(actor.get("tied_message_or_document_ids")) if item][:3],
            }
        )

    section = _section_with_entries(
        section_id="actor_and_witness_map",
        title="Actor And Witness Map",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet contain enough stable actor linkage for an actor and witness map."
        ),
    )
    section["actor_map"] = actor_map
    section["witness_map"] = witness_map
    return section


def _promise_and_contradiction_analysis_section(
    *,
    promise_contradiction_analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report-facing promise/action and contradiction section."""
    analysis = _as_dict(promise_contradiction_analysis)
    promise_rows = [row for row in _as_list(analysis.get("promises_vs_actions")) if isinstance(row, dict)]
    omission_rows = [row for row in _as_list(analysis.get("omission_rows")) if isinstance(row, dict)]
    contradiction_rows = [row for row in _as_list(analysis.get("contradiction_table")) if isinstance(row, dict)]
    if not promise_rows and not omission_rows and not contradiction_rows:
        return _empty_payload_section(
            "promise_and_contradiction_analysis",
            "Promise And Contradiction Analysis",
            analysis,
            "promise_contradiction_analysis",
            _PROMISE_REASON,
        )

    rows = promise_rows + omission_rows + contradiction_rows
    entries = [_promise_entry(row, index) for index, row in enumerate(rows[:4], start=1)]
    section = _section_with_entries(
        section_id="promise_and_contradiction_analysis",
        title="Promise And Contradiction Analysis",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet contain enough mixed-source promise, omission, "
            "or contradiction material for this section."
        ),
    )
    section["promise_contradiction_analysis"] = analysis
    return section


def _witness_question_packs_section(
    *,
    witness_question_packs: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report-facing witness interview prep section."""
    payload = _as_dict(witness_question_packs)
    packs = [item for item in _as_list(payload.get("packs")) if isinstance(item, dict)]
    if not packs:
        section = _section_with_entries(
            section_id="witness_question_packs",
            title="Witness Interview And Question Packs",
            entries=[],
            insufficiency_reason=(
                "The current case bundle does not yet contain enough stable witness "
                "or record-holder mapping for interview prep packs."
            ),
        )
        section["witness_question_packs"] = payload
        return section
    entries = [
        {
            "entry_id": str(pack.get("pack_id") or f"witness_pack:{index}"),
            "statement": (
                f"{pack.get('actor_name') or pack.get('actor_id') or 'Witness'}: "
                f"{_as_list(pack.get('likely_knowledge_areas'))[0] if _as_list(pack.get('likely_knowledge_areas')) else ''}"
            ).strip(": "),
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": [],
        }
        for index, pack in enumerate(packs[:3], start=1)
    ]
    section = _section_with_entries(
        section_id="witness_question_packs",
        title="Witness Interview And Question Packs",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet contain enough stable witness "
            "or record-holder mapping for interview prep packs."
        ),
    )
    section["witness_question_packs"] = payload
    return section


def _lawyer_briefing_memo_section(
    *,
    lawyer_briefing_memo: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report-facing lawyer briefing memo section."""
    memo = _as_dict(lawyer_briefing_memo)
    section_map = _as_dict(memo.get("sections"))
    executive_entries = [entry for entry in _as_list(section_map.get("executive_summary")) if isinstance(entry, dict)]
    if not executive_entries:
        return _empty_payload_section("lawyer_briefing_memo", "Lawyer Briefing Memo", memo, "lawyer_briefing_memo", _MEMO_REASON)
    entries = [_linked_entry(entry, "entry_id", f"memo:{index}") for index, entry in enumerate(executive_entries[:2], start=1)]
    section = _section_with_entries(
        section_id="lawyer_briefing_memo",
        title="Lawyer Briefing Memo",
        entries=entries,
        insufficiency_reason=_MEMO_REASON,
    )
    section["lawyer_briefing_memo"] = memo
    return section


def _controlled_factual_drafting_section(
    *,
    controlled_factual_drafting: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report-facing controlled-drafting section."""
    drafting = _as_dict(controlled_factual_drafting)
    preflight = _as_dict(drafting.get("framing_preflight"))
    draft = _as_dict(drafting.get("controlled_draft"))
    draft_sections = _as_dict(draft.get("sections"))
    established_facts = [entry for entry in _as_list(draft_sections.get("established_facts")) if isinstance(entry, dict)]
    if not established_facts and not any(_as_list(value) for value in draft_sections.values() if isinstance(value, list)):
        return _empty_payload_section(
            "controlled_factual_drafting",
            "Controlled Factual Drafting",
            drafting,
            "controlled_factual_drafting",
            _DRAFTING_REASON,
        )
    entries = [
        _linked_entry(entry, "item_id", f"controlled_draft:{index}") for index, entry in enumerate(established_facts[:2], start=1)
    ]
    if not entries:
        entries = [
            {
                "entry_id": "controlled_draft:summary",
                "statement": str(preflight.get("objective_of_draft") or "Controlled drafting output is available."),
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        ]
    section = _section_with_entries(
        section_id="controlled_factual_drafting",
        title="Controlled Factual Drafting",
        entries=entries,
        insufficiency_reason=_DRAFTING_REASON,
    )
    section["controlled_factual_drafting"] = drafting
    return section


def _case_dashboard_section(
    *,
    case_dashboard: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report-facing compact dashboard section."""
    dashboard = _as_dict(case_dashboard)
    cards = _as_dict(dashboard.get("cards"))
    issue_cards = [item for item in _as_list(cards.get("main_claims_or_issues")) if isinstance(item, dict)]
    if not issue_cards and not any(_as_list(value) for value in cards.values() if isinstance(value, list)):
        section = _section_with_entries(
            section_id="case_dashboard",
            title="Case Dashboard",
            entries=[],
            insufficiency_reason=(
                "The current case bundle does not yet contain enough stable shared-entity data "
                "for the refreshable case dashboard."
            ),
        )
        section["case_dashboard"] = dashboard
        return section

    entries = [
        {
            "entry_id": f"dashboard:issue:{index}",
            "statement": f"{item.get('title') or item.get('summary') or ''}: {item.get('status') or ''}".strip(": "),
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": [],
        }
        for index, item in enumerate(issue_cards[:3], start=1)
    ]
    if not entries:
        entries = [
            {
                "entry_id": "dashboard:summary",
                "statement": "The refreshable dashboard is available from the current shared matter entities.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        ]
    section = _section_with_entries(
        section_id="case_dashboard",
        title="Case Dashboard",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet contain enough stable shared-entity data for the refreshable case dashboard."
        ),
    )
    section["case_dashboard"] = dashboard
    return section


def _cross_output_consistency_section(
    *,
    cross_output_consistency: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a report-facing cross-output consistency section."""
    consistency = _as_dict(cross_output_consistency)
    checks = [item for item in _as_list(consistency.get("checks")) if isinstance(item, dict)]
    mismatches = [item for item in checks if str(item.get("status") or "") == "mismatch"]
    if not checks:
        section = _section_with_entries(
            section_id="cross_output_consistency",
            title="Cross-Output Consistency",
            entries=[],
            insufficiency_reason=(
                "The current case bundle does not yet contain enough downstream products for cross-output consistency checks."
            ),
        )
        section["cross_output_consistency"] = consistency
        return section

    entries = [
        {
            "entry_id": str(check.get("check_id") or f"consistency:{index}"),
            "statement": str(check.get("summary") or ""),
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": [],
        }
        for index, check in enumerate((mismatches or checks)[:3], start=1)
    ]
    section = _section_with_entries(
        section_id="cross_output_consistency",
        title="Cross-Output Consistency",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet contain enough downstream products for cross-output consistency checks."
        ),
    )
    section["cross_output_consistency"] = consistency
    return section


def _skeptical_employer_review_section(
    *,
    skeptical_employer_review: dict[str, Any],
) -> dict[str, Any]:
    """Return a report-facing skeptical employer-side review section."""
    weaknesses = [
        weakness for weakness in _as_list(_as_dict(skeptical_employer_review).get("weaknesses")) if isinstance(weakness, dict)
    ]
    if not weaknesses:
        return _skeptical_review_empty_section(skeptical_employer_review)
    entries = [_skeptical_review_entry(weakness, index) for index, weakness in enumerate(weaknesses[:4], start=1)]
    section = _section_with_entries(
        section_id="skeptical_employer_review",
        title="Skeptical Employer-Side Review",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet expose enough concrete weakness patterns for a skeptical employer-side review."
        ),
    )
    section["skeptical_employer_review"] = skeptical_employer_review
    return section


def _skeptical_review_empty_section(review: dict[str, Any]) -> dict[str, Any]:
    section = _section_with_entries(
        section_id="skeptical_employer_review",
        title="Skeptical Employer-Side Review",
        entries=[],
        insufficiency_reason=_SKEPTICAL_REVIEW_INSUFFICIENCY_REASON,
    )
    section["skeptical_employer_review"] = _as_dict(review)
    return section


def _skeptical_review_entry(weakness: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "entry_id": str(weakness.get("weakness_id") or f"skeptical_review:{index}"),
        "statement": str(weakness.get("critique") or ""),
        "supporting_finding_ids": _short_strings(weakness.get("supporting_finding_ids")),
        "supporting_citation_ids": _short_strings(weakness.get("supporting_citation_ids")),
        "supporting_uids": _short_strings(weakness.get("supporting_uids")),
    }


def _short_strings(value: object) -> list[str]:
    return [str(item) for item in _as_list(value) if item][:3]


def _document_request_checklist_section(
    *,
    document_request_checklist: dict[str, Any],
) -> dict[str, Any]:
    """Return a report-facing document-request and preservation checklist section."""
    groups = [group for group in _as_list(_as_dict(document_request_checklist).get("groups")) if isinstance(group, dict)]
    if not groups:
        section = _section_with_entries(
            section_id="document_request_checklist",
            title="Document Request And Preservation Checklist",
            entries=[],
            insufficiency_reason=(
                "The current case bundle does not yet contain enough concrete missing-proof detail "
                "for a document-request checklist."
            ),
        )
        section["document_request_checklist"] = _as_dict(document_request_checklist)
        return section
    entries = [
        {
            "entry_id": f"document_request:{group.get('group_id') or index}",
            "statement": (
                f"{group.get('title') or 'Request group'} currently contains "
                f"{int(group.get('item_count') or len(_as_list(group.get('items'))))} request item(s)."
            ),
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": [],
        }
        for index, group in enumerate(groups[:4], start=1)
    ]
    section = _section_with_entries(
        section_id="document_request_checklist",
        title="Document Request And Preservation Checklist",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle does not yet contain enough concrete missing-proof detail for a document-request checklist."
        ),
    )
    section["document_request_checklist"] = document_request_checklist
    return section
