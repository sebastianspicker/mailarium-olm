"""Wave-local analytical views derived from structured evidence linkage."""

from __future__ import annotations

from typing import Any

from .question_execution_waves import get_wave_definition

_LINKAGE_KEYS = {
    "uid": "uids",
    "supporting_uids": "uids",
    "message_or_document_id": "uids",
    "source_uid": "uids",
    "source_id": "source_ids",
    "source_ids": "source_ids",
    "supporting_source_ids": "source_ids",
    "original_source_id": "source_ids",
    "later_source_id": "source_ids",
    "later_source_ids": "source_ids",
    "finding_id": "finding_ids",
    "supporting_finding_ids": "finding_ids",
    "citation_id": "citation_ids",
    "supporting_citation_ids": "citation_ids",
    "exhibit_id": "exhibit_ids",
    "supporting_exhibit_ids": "exhibit_ids",
    "chronology_id": "chronology_ids",
    "linked_chronology_ids": "chronology_ids",
    "gap_id": "gap_ids",
    "linked_date_gap_ids": "gap_ids",
}
_LINKAGE_BUCKETS = tuple(sorted(set(_LINKAGE_KEYS.values())))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _wave_terms(wave_id: str) -> list[str]:
    definition = get_wave_definition(wave_id)
    label_terms = [item.strip() for item in definition.label.replace("/", " ").split() if len(item.strip()) >= 4]
    terms = [
        *definition.question_ids,
        *definition.issue_terms,
        *definition.attachment_terms,
        *definition.english_fallback_terms,
        *label_terms,
    ]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in terms:
        term = str(item or "").strip().casefold()
        if not term or term in seen:
            continue
        seen.add(term)
        normalized.append(term)
    return normalized


def _empty_context() -> dict[str, set[str]]:
    return {bucket: set() for bucket in _LINKAGE_BUCKETS}


def _normalize_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value for text in _normalize_values(item)]
    text = " ".join(str(value or "").split()).strip()
    return [text] if text else []


def _collect_linkage_ids(value: Any, *, collected: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    bucketed = _empty_context() if collected is None else collected
    if isinstance(value, dict):
        for key, item in value.items():
            bucket = _LINKAGE_KEYS.get(str(key))
            if bucket:
                bucketed[bucket].update(_normalize_values(item))
            if isinstance(item, (dict, list)):
                _collect_linkage_ids(item, collected=bucketed)
        return bucketed
    if isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                _collect_linkage_ids(item, collected=bucketed)
        return bucketed
    return bucketed


def _row_matches_context(row: dict[str, Any], *, context: dict[str, set[str]]) -> bool:
    linkage = _collect_linkage_ids(row)
    return any(linkage[bucket] & context[bucket] for bucket in _LINKAGE_BUCKETS if context[bucket])


def _merge_context(context: dict[str, set[str]], addition: dict[str, set[str]]) -> bool:
    changed = False
    for bucket in _LINKAGE_BUCKETS:
        new_values = addition[bucket] - context[bucket]
        if new_values:
            context[bucket].update(new_values)
            changed = True
    return changed


def _finding_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _as_list(_as_dict(payload.get("finding_evidence_index")).get("findings")) if isinstance(row, dict)]


def _matter_evidence_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _as_list(_as_dict(payload.get("matter_evidence_index")).get("rows")) if isinstance(row, dict)]


def _chronology_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _as_list(_as_dict(payload.get("master_chronology")).get("entries")) if isinstance(row, dict)]


def _issue_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _as_list(_as_dict(payload.get("lawyer_issue_matrix")).get("rows")) if isinstance(row, dict)]


def _checklist_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _as_list(_as_dict(payload.get("document_request_checklist")).get("groups")) if isinstance(row, dict)]


def _promise_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    promise_analysis = _as_dict(payload.get("promise_contradiction_analysis"))
    promises = [row for row in _as_list(promise_analysis.get("promises_vs_actions")) if isinstance(row, dict)]
    omissions = [row for row in _as_list(promise_analysis.get("omission_rows")) if isinstance(row, dict)]
    contradictions = [row for row in _as_list(promise_analysis.get("contradiction_table")) if isinstance(row, dict)]
    return promises, omissions, contradictions


def _seed_context_from_archive(payload: dict[str, Any]) -> dict[str, set[str]]:
    context = _empty_context()
    evidence_bank = [
        row for row in _as_list(_as_dict(payload.get("archive_harvest")).get("evidence_bank")) if isinstance(row, dict)
    ]
    for row in evidence_bank:
        _merge_context(context, _collect_linkage_ids(row))
        uid = str(row.get("uid") or "").strip()
        if uid:
            context["uids"].add(uid)
    return context


def _linked_rows(rows: list[dict[str, Any]], *, context: dict[str, set[str]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if _row_matches_context(row, context=context)]


def _expand_context(payload: dict[str, Any], *, context: dict[str, set[str]]) -> dict[str, set[str]]:
    row_sets = [
        _finding_rows(payload),
        _matter_evidence_rows(payload),
        _chronology_entries(payload),
        _issue_rows(payload),
        _checklist_groups(payload),
        *_promise_rows(payload),
    ]
    for _ in range(4):
        changed = False
        for rows in row_sets:
            for row in rows:
                if not _row_matches_context(row, context=context):
                    continue
                changed = _merge_context(context, _collect_linkage_ids(row)) or changed
        if not changed:
            break
    return context


def _wave_dashboard(
    *,
    matter_rows: list[dict[str, Any]],
    chronology_entries: list[dict[str, Any]],
    issue_rows: list[dict[str, Any]],
    checklist_groups: list[dict[str, Any]],
    contradiction_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    cards: dict[str, Any] = {}
    if issue_rows:
        cards["main_claims_or_issues"] = [
            {
                "issue_id": str(row.get("issue_id") or ""),
                "title": str(row.get("title") or ""),
                "status": str(row.get("legal_relevance_status") or ""),
                "evidence_hint": str(row.get("relevant_facts") or row.get("missing_proof") or ""),
            }
            for row in issue_rows[:4]
        ]
    if chronology_entries:
        cards["key_dates"] = [
            {
                "chronology_id": str(row.get("chronology_id") or ""),
                "date": str(row.get("date") or ""),
                "title": str(row.get("title") or row.get("description") or ""),
            }
            for row in chronology_entries[:4]
        ]
    if matter_rows:
        cards["strongest_exhibits"] = [
            {
                "exhibit_id": str(row.get("exhibit_id") or ""),
                "summary": str(row.get("short_description") or row.get("why_it_matters") or ""),
                "strength": str(_as_dict(row.get("exhibit_reliability")).get("strength") or ""),
                "quoted_evidence": dict(row.get("quoted_evidence") or {}),
            }
            for row in matter_rows[:4]
        ]
    if checklist_groups:
        cards["recommended_next_actions"] = [
            {
                "group_id": str(group.get("group_id") or ""),
                "summary": str(_as_dict(_as_list(group.get("items"))[0]).get("request") or group.get("title") or ""),
            }
            for group in checklist_groups[:4]
        ]
    if contradiction_rows:
        cards["process_irregularities"] = [
            {
                "summary": str(
                    row.get("summary")
                    or row.get("point_summary")
                    or row.get("original_statement_or_promise")
                    or row.get("later_action")
                    or ""
                )
            }
            for row in contradiction_rows[:4]
        ]
    return {
        "card_count": len(cards),
        "cards": cards,
    }


def build_wave_local_views(payload: dict[str, Any], *, wave_id: str) -> dict[str, Any]:
    """Return evidence-linked wave-local views from a full case-analysis payload."""
    context = _expand_context(payload, context=_seed_context_from_archive(payload))
    chronology_entries = _linked_rows(_chronology_entries(payload), context=context)
    finding_rows = _linked_rows(_finding_rows(payload), context=context)
    matter_rows = _linked_rows(_matter_evidence_rows(payload), context=context)
    issue_rows = _linked_rows(_issue_rows(payload), context=context)
    checklist_groups = _linked_rows(_checklist_groups(payload), context=context)
    promise_rows, omission_rows, contradiction_rows = (_linked_rows(rows, context=context) for rows in _promise_rows(payload))
    dashboard = _wave_dashboard(
        matter_rows=matter_rows,
        chronology_entries=chronology_entries,
        issue_rows=issue_rows,
        checklist_groups=checklist_groups,
        contradiction_rows=contradiction_rows,
    )

    return {
        "wave_id": wave_id,
        "terms": _wave_terms(wave_id),
        "linkage_context": {bucket: sorted(values) for bucket, values in context.items() if values},
        "surface_counts": {
            "master_chronology": len(chronology_entries),
            "finding_evidence_index": len(finding_rows),
            "matter_evidence_index": len(matter_rows),
            "lawyer_issue_matrix": len(issue_rows),
            "document_request_checklist": len(checklist_groups),
            "case_dashboard": int(dashboard.get("card_count") or 0),
            "promises_vs_actions": len(promise_rows),
            "omission_rows": len(omission_rows),
            "contradiction_rows": len(contradiction_rows),
        },
        "master_chronology": {
            "entry_count": len(chronology_entries),
            "entries": chronology_entries,
        },
        "finding_evidence_index": {
            "finding_count": len(finding_rows),
            "findings": finding_rows,
        },
        "matter_evidence_index": {
            "row_count": len(matter_rows),
            "rows": matter_rows,
        },
        "lawyer_issue_matrix": {
            "row_count": len(issue_rows),
            "rows": issue_rows,
        },
        "document_request_checklist": {
            "group_count": len(checklist_groups),
            "groups": checklist_groups,
        },
        "case_dashboard": dashboard,
        "promise_contradiction_analysis": {
            "promises_vs_actions": promise_rows,
            "omission_rows": omission_rows,
            "contradiction_table": contradiction_rows,
        },
    }
