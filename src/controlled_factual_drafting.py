"""Controlled factual drafting with framing preflight and allegation ceilings."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from typing import Any

from ._utils import _as_dict, _as_list, _compact, _first_nonempty
from .behavioral_interpretation_policy import (
    guarded_statement_for_finding,
    interpretation_policy_payload,
)
from .comparative_treatment import shared_comparator_points
from .trigger_retaliation import shared_retaliation_points

CONTROLLED_FACTUAL_DRAFTING_VERSION = "1"
_GENERIC_DRAFTING_TEXTS = {
    "provides direct record material relevant to the synthetic matter review.",
    "documented record material relevant to the synthetic matter review.",
}


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = _compact(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _draft_item(
    *,
    item_id: str,
    text: str,
    exhibit_ids: list[str] | None = None,
    chronology_ids: list[str] | None = None,
    issue_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    claim_level: str = "",
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "text": _compact(text),
        "claim_level": str(claim_level or ""),
        "supporting_exhibit_ids": _clean_ids(exhibit_ids),
        "supporting_chronology_ids": _clean_ids(chronology_ids),
        "supporting_issue_ids": _clean_ids(issue_ids),
        "supporting_source_ids": _clean_ids(source_ids),
    }


def _clean_ids(values: list[str] | None) -> list[str]:
    return [str(item) for item in values or [] if _compact(item)]


def _ceiling_level(findings: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    has_observed_fact = False
    has_pattern_concern = False
    has_stronger_interpretation = False
    for finding in findings:
        statement, claim_level, policy_reason, _, _ = guarded_statement_for_finding(finding)
        _ = statement
        reasons.append(policy_reason)
        if claim_level == "observed_fact":
            has_observed_fact = True
        elif claim_level == "pattern_concern":
            has_pattern_concern = True
        elif claim_level == "stronger_interpretation":
            has_stronger_interpretation = True
    if has_stronger_interpretation:
        return "concern_plus_procedural_requests_only", list(dict.fromkeys(reasons))
    if has_pattern_concern:
        return "concern_only", list(dict.fromkeys(reasons))
    if has_observed_fact:
        return "observed_facts_only", list(dict.fromkeys(reasons))
    return (
        "insufficient_for_adversarial_draft",
        ["The current record supports only factual preservation and clarification requests, not adversarial attribution."],
    )


def _objective(case_bundle: dict[str, Any], document_request_checklist: dict[str, Any]) -> str:
    scope = _as_dict(case_bundle.get("scope"))
    analysis_goal = str(scope.get("analysis_goal") or "")
    group_count = int(_as_dict(document_request_checklist).get("group_count") or 0)
    if analysis_goal == "lawyer_briefing":
        return (
            "Prepare an evidence-bound professional draft that documents the current concerns, "
            "requests clarification, and preserves access to relevant records."
        )
    if group_count > 0:
        return (
            "Prepare a disciplined draft that records the factual sequence and asks for concrete records "
            "or explanations without outrunning the current proof."
        )
    return "Prepare a conservative factual draft that stays within the established record."


def _rendered_text(sections: dict[str, list[dict[str, Any]]]) -> str:
    heading_map = {
        "established_facts": "Established Facts",
        "concerns": "Concerns",
        "requests_for_clarification": "Requests for Clarification",
        "formal_demands": "Formal Demands",
    }
    blocks: list[str] = []
    for section_id in ("established_facts", "concerns", "requests_for_clarification", "formal_demands"):
        rows = [row for row in sections.get(section_id, []) if isinstance(row, dict) and _compact(row.get("text"))]
        if not rows:
            continue
        blocks.append(heading_map[section_id] + ":")
        blocks.extend(f"- {row['text']}" for row in rows)
    return "\n".join(blocks)


def _usable_text(value: Any) -> str:
    text = _compact(value)
    if not text:
        return ""
    if text.lower() in _GENERIC_DRAFTING_TEXTS:
        return ""
    if "case_prompt" in text.lower():
        return ""
    return text


def _anchor_maps(
    *,
    evidence_rows: list[dict[str, Any]],
    chronology_entries: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    maps: dict[str, dict[str, list[str]]] = {
        key: {}
        for key in (
            "source_ids_by_uid",
            "exhibit_ids_by_uid",
            "chronology_ids_by_uid",
            "exhibit_ids_by_source_id",
            "chronology_ids_by_source_id",
            "source_ids_by_uid_guess",
            "exhibit_ids_by_uid_guess",
        )
    }
    _index_evidence_anchors(evidence_rows, maps)
    _index_chronology_anchors(chronology_entries, maps)
    return {key: {item_key: _ordered_unique(value) for item_key, value in mapping.items()} for key, mapping in maps.items()}


def _index_evidence_anchors(rows, maps):
    for row in rows:
        source_id, exhibit_id = _compact(row.get("source_id")), _compact(row.get("exhibit_id"))
        if source_id and exhibit_id:
            maps["exhibit_ids_by_source_id"].setdefault(source_id, []).append(exhibit_id)
        if source_id:
            _index_guessed_uids(source_id, exhibit_id, maps)
        for uid in _clean_ids(_as_list(row.get("supporting_uids"))):
            if source_id:
                maps["source_ids_by_uid"].setdefault(uid, []).append(source_id)
            if exhibit_id:
                maps["exhibit_ids_by_uid"].setdefault(uid, []).append(exhibit_id)


def _index_guessed_uids(source_id, exhibit_id, maps):
    for token in source_id.split(":"):
        if not (token.startswith("uid") or "@" in token):
            continue
        maps["source_ids_by_uid_guess"].setdefault(token, []).append(source_id)
        if exhibit_id:
            maps["exhibit_ids_by_uid_guess"].setdefault(token, []).append(exhibit_id)


def _index_chronology_anchors(rows, maps):
    for row in rows:
        chronology_id, uid = _compact(row.get("chronology_id")), _compact(row.get("uid"))
        if chronology_id and uid:
            maps["chronology_ids_by_uid"].setdefault(uid, []).append(chronology_id)
        for source_id in _clean_ids(_as_list(_as_dict(row.get("source_linkage")).get("source_ids"))):
            if chronology_id:
                maps["chronology_ids_by_source_id"].setdefault(source_id, []).append(chronology_id)


def _anchors_from_sources_and_uids(
    *,
    source_ids: list[str],
    uids: list[str],
    anchor_maps: dict[str, dict[str, list[str]]],
) -> dict[str, list[str]]:
    resolved_source_ids = list(source_ids)
    resolved_exhibit_ids: list[str] = []
    resolved_chronology_ids: list[str] = []
    source_ids_by_uid = anchor_maps.get("source_ids_by_uid", {})
    source_ids_by_uid_guess = anchor_maps.get("source_ids_by_uid_guess", {})
    exhibit_ids_by_uid = anchor_maps.get("exhibit_ids_by_uid", {})
    exhibit_ids_by_uid_guess = anchor_maps.get("exhibit_ids_by_uid_guess", {})
    chronology_ids_by_uid = anchor_maps.get("chronology_ids_by_uid", {})
    exhibit_ids_by_source_id = anchor_maps.get("exhibit_ids_by_source_id", {})
    chronology_ids_by_source_id = anchor_maps.get("chronology_ids_by_source_id", {})
    for uid in uids:
        resolved_source_ids.extend(source_ids_by_uid.get(uid, []))
        resolved_source_ids.extend(source_ids_by_uid_guess.get(uid, []))
        resolved_exhibit_ids.extend(exhibit_ids_by_uid.get(uid, []))
        resolved_exhibit_ids.extend(exhibit_ids_by_uid_guess.get(uid, []))
        resolved_chronology_ids.extend(chronology_ids_by_uid.get(uid, []))
    for source_id in resolved_source_ids:
        resolved_exhibit_ids.extend(exhibit_ids_by_source_id.get(source_id, []))
        resolved_chronology_ids.extend(chronology_ids_by_source_id.get(source_id, []))
    return {
        "source_ids": _ordered_unique(resolved_source_ids),
        "exhibit_ids": _ordered_unique(resolved_exhibit_ids),
        "chronology_ids": _ordered_unique(resolved_chronology_ids),
    }


def build_controlled_factual_drafting(
    *,
    case_bundle: dict[str, Any] | None,
    findings: list[dict[str, Any]] | None,
    matter_evidence_index: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
    lawyer_issue_matrix: dict[str, Any] | None,
    comparative_treatment: dict[str, Any] | None,
    retaliation_timeline_assessment: dict[str, Any] | None,
    skeptical_employer_review: dict[str, Any] | None,
    document_request_checklist: dict[str, Any] | None,
    promise_contradiction_analysis: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a controlled drafting preflight plus evidence-bound draft."""
    if not isinstance(case_bundle, dict):
        return None

    findings_list = _dict_rows(findings)
    evidence_rows = _dict_rows(_as_dict(matter_evidence_index).get("rows"))
    chronology_entries = _dict_rows(_as_dict(master_chronology).get("entries"))
    issue_rows = _dict_rows(_as_dict(lawyer_issue_matrix).get("rows"))
    comparator_points = shared_comparator_points(_as_dict(comparative_treatment))
    retaliation_points = shared_retaliation_points(retaliation_timeline_assessment=_as_dict(retaliation_timeline_assessment))
    weakness_rows = _dict_rows(_as_dict(skeptical_employer_review).get("weaknesses"))
    request_groups = _dict_rows(_as_dict(document_request_checklist).get("groups"))
    contradiction_rows = _dict_rows(_as_dict(promise_contradiction_analysis).get("contradiction_table"))
    if not _has_drafting_input(findings_list, evidence_rows, chronology_entries, issue_rows, request_groups):
        return None

    anchor_maps = _anchor_maps(evidence_rows=evidence_rows, chronology_entries=chronology_entries)

    ceiling_level, ceiling_reasons = _ceiling_level(findings_list)
    scope = _as_dict(case_bundle.get("scope"))
    target_person = _as_dict(scope.get("target_person"))
    target_label = _first_nonempty(target_person.get("name"), target_person.get("email"), "the employee")

    strongest_framing = _build_strongest_framing(findings_list, comparator_points, retaliation_points, anchor_maps)

    safest_framing = _build_safest_framing(evidence_rows, contradiction_rows)

    risks = _drafting_risks(weakness_rows)

    established_facts = _established_facts(chronology_entries, evidence_rows)

    concerns = _drafting_concerns(strongest_framing)

    requests_for_clarification = _clarification_requests(request_groups, contradiction_rows)

    formal_demands = _formal_demands(request_groups, ceiling_level, issue_rows)

    policy = interpretation_policy_payload()
    framing_preflight: dict[str, Any] = {
        "objective_of_draft": _objective(case_bundle, _as_dict(document_request_checklist)),
        "legal_and_factual_risks": risks,
        "strongest_framing": strongest_framing,
        "safest_framing": safest_framing,
        "allegation_ceiling": {
            "ceiling_level": ceiling_level,
            "reasoning": ceiling_reasons,
            "allowed_moves": [
                "state documented facts",
                "state bounded concerns",
                "request clarification",
                "request preservation and production of records",
            ],
            "prohibited_moves": list(_as_list(policy.get("prohibited_claims"))),
            "release_status": "ready_for_controlled_draft"
            if established_facts or requests_for_clarification
            else "insufficient_for_controlled_draft",
        },
    }

    section_map = {
        "established_facts": established_facts,
        "concerns": concerns,
        "requests_for_clarification": requests_for_clarification,
        "formal_demands": formal_demands,
    }
    controlled_draft = {
        "audience": "employer_or_employer_counsel",
        "tone": "firm_professional_evidence_bound",
        "target_person_label": target_label,
        "allegation_ceiling_applied": ceiling_level,
        "sections": section_map,
        "rendered_text": _rendered_text(section_map),
    }
    return {
        "version": CONTROLLED_FACTUAL_DRAFTING_VERSION,
        "drafting_format": "controlled_factual_drafting",
        "summary": {
            "preflight_ready": bool(framing_preflight["allegation_ceiling"]["release_status"] == "ready_for_controlled_draft"),
            "fact_count": len(established_facts),
            "concern_count": len(concerns),
            "clarification_count": len(requests_for_clarification),
            "formal_demand_count": len(formal_demands),
        },
        "framing_preflight": framing_preflight,
        "controlled_draft": controlled_draft,
    }


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _has_drafting_input(*collections: list[dict[str, Any]]) -> bool:
    return any(collections)


def _build_strongest_framing(
    findings_list: list[dict[str, Any]],
    comparator_points: list[dict[str, Any]],
    retaliation_points: list[dict[str, Any]],
    anchor_maps: dict[str, dict[str, list[str]]],
) -> list[dict[str, Any]]:
    strongest_framing: list[dict[str, Any]] = []
    _append_finding_framing(strongest_framing, findings_list, anchor_maps)
    _append_comparator_framing(strongest_framing, comparator_points, anchor_maps)
    _append_retaliation_framing(strongest_framing, retaliation_points, anchor_maps)

    return strongest_framing


def _build_safest_framing(evidence_rows: list[dict[str, Any]], contradiction_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safest_framing: list[dict[str, Any]] = []
    for index, row in enumerate(evidence_rows[:3], start=1):
        text = _first_nonempty(
            _usable_text(row.get("short_description")),
            _usable_text(row.get("why_it_matters")),
        )
        if not text:
            continue
        safest_framing.append(
            {
                "framing_id": f"safest:{index}",
                "text": f"The documented record currently shows: {text}",
                "basis": "documented_source_or_exhibit",
                "supporting_exhibit_ids": [str(row.get("exhibit_id") or "")] if str(row.get("exhibit_id") or "") else [],
            }
        )
    if contradiction_rows:
        row = contradiction_rows[0]
        safest_framing.append(
            {
                "framing_id": "safest:contradiction",
                "text": (
                    "The current record contains a contradiction that requires explanation: "
                    f"{_first_nonempty(row.get('original_statement_or_promise'), row.get('later_action'))}"
                ),
                "basis": "documented_record_contradiction",
                "supporting_source_ids": [
                    str(item) for item in [row.get("original_source_id"), row.get("later_source_id")] if _compact(item)
                ],
            }
        )

    return safest_framing


def _drafting_risks(weakness_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks = [
        {
            "risk_id": str(row.get("weakness_id") or f"risk:{index}"),
            "text": _first_nonempty(row.get("critique"), _as_dict(row.get("repair_guidance")).get("how_to_fix")),
            "risk_type": str(row.get("category") or "drafting_risk"),
        }
        for index, row in enumerate(weakness_rows[:4], start=1)
        if _first_nonempty(row.get("critique"), _as_dict(row.get("repair_guidance")).get("how_to_fix"))
    ]

    return risks


def _established_facts(chronology_entries: list[dict[str, Any]], evidence_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    established_facts: list[dict[str, Any]] = []
    for index, row in enumerate(chronology_entries[:3], start=1):
        fact = _chronology_fact(index, row)
        if fact:
            established_facts.append(fact)
    for index, row in enumerate(evidence_rows[:2], start=10):
        fact = _evidence_fact(index, row)
        if fact:
            established_facts.append(fact)
    return established_facts


def _chronology_fact(index: int, row: dict[str, Any]) -> dict[str, Any] | None:
    linkage = _as_dict(row.get("source_linkage"))
    evidence_status = str(linkage.get("source_evidence_status") or "")
    if evidence_status in {"scope_only", "timeline_only"} or not _as_list(linkage.get("source_ids")):
        return None
    if not _first_nonempty(row.get("date"), _usable_text(row.get("title")), _usable_text(row.get("description"))):
        return None
    title = _usable_text(row.get("title")) or _usable_text(row.get("description"))
    return _draft_item(
        item_id=f"draft:fact:{index}",
        text=_first_nonempty(f"On {row.get('date') or ''}, {title}", _usable_text(row.get("description"))),
        chronology_ids=_clean_ids([str(row.get("chronology_id") or "")]),
        source_ids=[str(item) for item in _as_list(linkage.get("source_ids"))[:2] if item],
        claim_level="observed_fact",
    )


def _evidence_fact(index: int, row: dict[str, Any]) -> dict[str, Any] | None:
    text = _first_nonempty(_usable_text(row.get("short_description")), _usable_text(row.get("why_it_matters")))
    if not text:
        return None
    return _draft_item(
        item_id=f"draft:fact:{index}",
        text=text,
        exhibit_ids=_clean_ids([str(row.get("exhibit_id") or "")]),
        source_ids=_clean_ids([str(row.get("source_id") or "")]),
        claim_level="observed_fact",
    )


def _drafting_concerns(strongest_framing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    concerns: list[dict[str, Any]] = []
    for index, entry in enumerate(strongest_framing[:3], start=1):
        concern = _drafting_concern(index, entry)
        if concern:
            concerns.append(concern)
    return concerns


def _drafting_concern(index: int, entry: dict[str, Any]) -> dict[str, Any] | None:
    claim_level = str(entry.get("claim_level") or "")
    if claim_level not in {"pattern_concern", "stronger_interpretation"}:
        return None
    source_ids = _clean_ids(_as_list(entry.get("supporting_source_ids")))
    exhibit_ids = _clean_ids(_as_list(entry.get("supporting_exhibit_ids")))
    chronology_ids = _clean_ids(_as_list(entry.get("supporting_chronology_ids")))
    if not source_ids and not exhibit_ids and not chronology_ids:
        return None
    return _draft_item(
        item_id=f"draft:concern:{index}",
        text=str(entry.get("text") or ""),
        exhibit_ids=exhibit_ids,
        chronology_ids=chronology_ids,
        claim_level=claim_level,
        source_ids=source_ids,
    )


def _clarification_requests(
    request_groups: list[dict[str, Any]], contradiction_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for index, group in enumerate(request_groups[:3], start=1):
        request = _group_clarification(index, group)
        if request:
            requests.append(request)
    for index, row in enumerate(contradiction_rows[:2], start=20):
        request = _contradiction_clarification(index, row)
        if request:
            requests.append(request)
    return requests


def _group_clarification(index: int, group: dict[str, Any]) -> dict[str, Any] | None:
    items = _dict_rows(group.get("items"))
    request_text = _first_nonempty(_as_dict(items[0]).get("request") if items else "", group.get("title"))
    if not request_text:
        return None
    return _draft_item(
        item_id=f"draft:clarification:{index}",
        text=f"Please clarify and provide the record for the following point: {request_text}",
        source_ids=_clean_ids([str(group.get("group_id") or "")]),
    )


def _contradiction_clarification(index: int, row: dict[str, Any]) -> dict[str, Any] | None:
    text = _first_nonempty(row.get("original_statement_or_promise"), row.get("later_action"))
    if not text:
        return None
    return _draft_item(
        item_id=f"draft:clarification:{index}",
        text=f"Please explain the discrepancy in the current record regarding: {text}",
        source_ids=_clean_ids([str(row.get("original_source_id") or ""), str(row.get("later_source_id") or "")]),
    )


def _formal_demands(
    request_groups: list[dict[str, Any]], ceiling_level: str, issue_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    formal_demands: list[dict[str, Any]] = []
    if request_groups:
        for index, group in enumerate(request_groups[:2], start=1):
            group_title = _first_nonempty(group.get("title"), "relevant records")
            if ceiling_level == "insufficient_for_adversarial_draft":
                text = f"Please preserve all documents and native records relating to {group_title}."
            else:
                text = (
                    f"Please preserve and provide the existing records relating to {group_title}, "
                    "including native metadata and related follow-up communications."
                )
            formal_demands.append(
                _draft_item(
                    item_id=f"draft:demand:{index}",
                    text=text,
                    source_ids=[str(group.get("group_id") or "")] if str(group.get("group_id") or "") else [],
                )
            )
    if issue_rows and ceiling_level in {"concern_only", "concern_plus_procedural_requests_only"}:
        issue = issue_rows[0]
        issue_title = _first_nonempty(issue.get("title"), issue.get("issue_id"), "the current issue")
        formal_demands.append(
            _draft_item(
                item_id="draft:demand:issue_response",
                text=(
                    f"Please provide a reasoned written response addressing the factual basis for {issue_title}, "
                    "without treating this request as a final legal conclusion."
                ),
                issue_ids=[str(issue.get("issue_id") or "")] if str(issue.get("issue_id") or "") else [],
            )
        )

    return formal_demands


def _append_finding_framing(
    strongest_framing: list[dict[str, Any]],
    findings_list: list[dict[str, Any]],
    anchor_maps: dict[str, dict[str, list[str]]],
) -> None:
    for finding in findings_list[:3]:
        statement, claim_level, policy_reason, ambiguity_disclosures, alternatives = guarded_statement_for_finding(finding)
        supporting_evidence = [item for item in _as_list(finding.get("supporting_evidence")) if isinstance(item, dict)]
        source_ids = [
            str(item)
            for evidence in supporting_evidence
            for item in (
                evidence.get("source_id"),
                evidence.get("evidence_handle"),
            )
            if _compact(item)
        ]
        uids = [
            str(evidence.get("message_or_document_id") or "")
            for evidence in supporting_evidence
            if _compact(evidence.get("message_or_document_id"))
        ]
        anchors = _anchors_from_sources_and_uids(source_ids=source_ids, uids=uids, anchor_maps=anchor_maps)
        strongest_framing.append(
            {
                "finding_id": str(finding.get("finding_id") or ""),
                "text": statement,
                "claim_level": claim_level,
                "policy_reason": policy_reason,
                "ambiguity_disclosures": ambiguity_disclosures,
                "alternative_explanations": alternatives,
                "supporting_source_ids": anchors["source_ids"],
                "supporting_exhibit_ids": anchors["exhibit_ids"],
                "supporting_chronology_ids": anchors["chronology_ids"],
            }
        )


def _append_comparator_framing(
    strongest_framing: list[dict[str, Any]],
    comparator_points: list[dict[str, Any]],
    anchor_maps: dict[str, dict[str, list[str]]],
) -> None:
    strong_comparator_points = [
        row for row in comparator_points if str(row.get("comparison_strength") or "") in {"strong", "moderate"}
    ]
    if strong_comparator_points:
        point = strong_comparator_points[0]
        issue_label = _first_nonempty(point.get("issue_label"), point.get("issue_id"))
        point_summary = _first_nonempty(point.get("point_summary"))
        counterargument = _first_nonempty(point.get("counterargument"))
        strongest_framing.append(
            {
                "finding_id": str(point.get("comparator_point_id") or "comparator-point"),
                "text": (f"Comparator evidence may support unequal-treatment review for {issue_label}: {point_summary}"),
                "claim_level": "pattern_concern",
                "policy_reason": (
                    "Comparator support remains concern-level unless the overall record removes material comparability doubts."
                ),
                "ambiguity_disclosures": [counterargument] if counterargument else [],
                "alternative_explanations": [counterargument] if counterargument else [],
                **_anchors_from_sources_and_uids(
                    source_ids=[str(item) for item in _as_list(point.get("supporting_source_ids")) if _compact(item)],
                    uids=[str(item) for item in _as_list(point.get("evidence_uids")) if _compact(item)],
                    anchor_maps=anchor_maps,
                ),
            }
        )


def _append_retaliation_framing(
    strongest_framing: list[dict[str, Any]],
    retaliation_points: list[dict[str, Any]],
    anchor_maps: dict[str, dict[str, list[str]]],
) -> None:
    strong_retaliation_points = [
        row for row in retaliation_points if str(row.get("support_strength") or "") in {"moderate", "limited"}
    ]
    if strong_retaliation_points:
        point = strong_retaliation_points[0]
        point_summary = _first_nonempty(point.get("point_summary"))
        counterargument = _first_nonempty(point.get("counterargument"))
        strongest_framing.append(
            {
                "finding_id": str(point.get("retaliation_point_id") or "retaliation-point"),
                "text": f"Retaliation timing may support further review: {point_summary}",
                "claim_level": "pattern_concern",
                "policy_reason": (
                    "Retaliation timing remains concern-level unless explicit triggers, sequence, "
                    "and counterarguments align more strongly."
                ),
                "ambiguity_disclosures": [counterargument] if counterargument else [],
                "alternative_explanations": [counterargument] if counterargument else [],
                **_anchors_from_sources_and_uids(
                    source_ids=[str(item) for item in _as_list(point.get("supporting_source_ids")) if _compact(item)],
                    uids=[str(item) for item in _as_list(point.get("supporting_uids")) if _compact(item)],
                    anchor_maps=anchor_maps,
                ),
            }
        )
