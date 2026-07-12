"""Durable exhibit-register builder for mixed-source case analysis."""
# pylint: disable=too-many-locals

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .matter_evidence_index_helpers import (
    as_dict as _as_dict,
)
from .matter_evidence_index_helpers import (
    as_list as _as_list,
)
from .matter_evidence_index_helpers import (
    citation_ids_for_source as _citation_ids_for_source,
)
from .matter_evidence_index_helpers import (
    exhibit_priority_score as _exhibit_priority_score,
)
from .matter_evidence_index_helpers import (
    exhibit_reliability as _exhibit_reliability,
)
from .matter_evidence_index_helpers import (
    finding_ids as _finding_ids,
)
from .matter_evidence_index_helpers import (
    findings_for_source as _findings_for_source,
)
from .matter_evidence_index_helpers import (
    follow_up_needed as _follow_up_needed,
)
from .matter_evidence_index_helpers import (
    issue_tags as _issue_tags,
)
from .matter_evidence_index_helpers import (
    linked_source_ids as _linked_source_ids,
)
from .matter_evidence_index_helpers import (
    make_quoted_evidence as _make_quoted_evidence,
)
from .matter_evidence_index_helpers import (
    missing_exhibit_rows as _missing_exhibit_rows,
)
from .matter_evidence_index_helpers import (
    recipient_identities as _recipient_identities,
)
from .matter_evidence_index_helpers import (
    recipients as _recipients,
)
from .matter_evidence_index_helpers import (
    reliability_label as _reliability_label,
)
from .matter_evidence_index_helpers import (
    sender_identity as _sender_identity,
)
from .matter_evidence_index_helpers import (
    sender_or_author as _sender_or_author,
)
from .matter_evidence_index_helpers import (
    short_description as _short_description,
)
from .matter_evidence_index_helpers import (
    source_by_id as _source_by_id,
)
from .matter_evidence_index_helpers import (
    source_conflicts_by_source_id as _source_conflicts_by_source_id,
)
from .matter_evidence_index_helpers import (
    source_language as _source_language,
)
from .matter_evidence_index_helpers import (
    source_rows as _source_rows,
)
from .matter_evidence_index_helpers import (
    top_exhibit_payload as _top_exhibit_payload,
)
from .matter_evidence_index_helpers import (
    why_it_matters as _why_it_matters,
)

MATTER_EVIDENCE_INDEX_VERSION = "1"


def _tag_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Build a mapping from tag string to occurrence count across rows for a given key."""
    counts: dict[str, int] = {}
    for row in rows:
        tags = row.get(key) or []
        if not isinstance(tags, list):
            tags = []
        for tag in tags:
            if isinstance(tag, str) and tag:
                counts[tag] = counts.get(tag, 0) + 1
    return counts


@dataclass(frozen=True)
class _IndexContext:
    case_bundle: dict[str, Any]
    finding_evidence_index: dict[str, Any]
    source_lookup: dict[str, dict[str, Any]]
    source_links: list[dict[str, Any]]
    conflicts_by_source_id: dict[str, list[dict[str, Any]]]


def _text(values: dict[str, Any], key: str) -> str:
    return str(values.get(key) or "")


def _sorted_sources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        _source_rows(bundle), key=lambda item: (_text(item, "date"), _text(item, "source_type"), _text(item, "source_id"))
    )


def _source_links(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [link for link in _as_list(bundle.get("source_links")) if isinstance(link, dict)]


def _unique_nonempty(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(values) if value]


def _supporting_uids(source: dict[str, Any], linked_ids: list[str], source_lookup: dict[str, dict[str, Any]]) -> list[str]:
    linked_uids = [_text(_as_dict(source_lookup.get(linked_id)), "uid") for linked_id in linked_ids]
    return _unique_nonempty([_text(source, "uid"), *linked_uids])


def _tag_ids(issue_tags: list[dict[str, Any]], assignment_basis: str | None = None) -> list[str]:
    values: list[str] = []
    for tag in issue_tags:
        tag_id = _text(tag, "tag_id")
        if tag_id and (assignment_basis is None or _text(tag, "assignment_basis") == assignment_basis):
            values.append(tag_id)
    return list(dict.fromkeys(values))


def _linked_conflict_payload(conflicts: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "conflict_id": _text(conflict, "conflict_id"),
            "conflict_kind": _text(conflict, "conflict_kind"),
            "resolution_status": _text(conflict, "resolution_status"),
            "summary": _text(conflict, "summary"),
        }
        for conflict in conflicts[:2]
    ]


def _evidence_row(index: int, source: dict[str, Any], context: _IndexContext) -> dict[str, Any]:
    findings = _findings_for_source(
        context.finding_evidence_index, source, source_lookup=context.source_lookup, source_links=context.source_links
    )
    citation_ids = _citation_ids_for_source(
        context.finding_evidence_index, source, source_lookup=context.source_lookup, source_links=context.source_links
    )
    source_id = _text(source, "source_id")
    linked_source_ids = [item for item in _linked_source_ids(source_id, context.source_links) if item]
    supporting_uids = _supporting_uids(source, linked_source_ids, context.source_lookup)
    provenance = _as_dict(source.get("provenance"))
    document_locator = _as_dict(source.get("document_locator"))
    issue_tags = _issue_tags(context.case_bundle, source, findings)
    linked_conflicts = context.conflicts_by_source_id.get(source_id, [])
    language = _source_language(source)
    reliability = _exhibit_reliability(source, findings)
    readiness = _text(_as_dict(reliability.get("next_step_logic")), "readiness")
    documentary_support = _as_dict(source.get("documentary_support"))
    return {
        "exhibit_id": f"EXH-{index:03d}",
        "date": _text(source, "date"),
        "document_type": _text(source, "document_kind") or _text(source, "source_type"),
        "sender_or_author": _sender_or_author(source, source_lookup=context.source_lookup, source_links=context.source_links),
        "sender_identity": _sender_identity(source, source_lookup=context.source_lookup, source_links=context.source_links),
        "recipients": _recipients(source, context.source_lookup, context.source_links),
        "recipient_identities": _recipient_identities(
            source, source_lookup=context.source_lookup, source_links=context.source_links
        ),
        "short_description": _short_description(source),
        "issue_tags": issue_tags,
        "main_issue_tags": _tag_ids(issue_tags, "direct_document_content"),
        "scope_issue_tags": _tag_ids(issue_tags, "operator_supplied"),
        "inferred_issue_tags": _tag_ids(issue_tags, "bounded_inference"),
        "all_issue_tags": _tag_ids(issue_tags),
        "key_quoted_passage": _text(source, "snippet"),
        "source_language": language,
        "quoted_evidence": _make_quoted_evidence(source, source_language=language),
        "why_it_matters": _why_it_matters(source, findings),
        "exhibit_reliability": reliability,
        "strength": _text(reliability, "strength"),
        "readiness": readiness,
        "reliability_or_evidentiary_strength": _reliability_label(source),
        "source_reliability": _as_dict(source.get("source_reliability")),
        "promotability_status": _text(source, "promotability_status"),
        "follow_up_needed": _follow_up_needed(source, findings),
        "source_format_support": _as_dict(documentary_support.get("format_profile")),
        "extraction_quality": _as_dict(documentary_support.get("extraction_quality")),
        "source_id": source_id,
        "source_type": _text(source, "source_type"),
        "supporting_finding_ids": _finding_ids(findings),
        "supporting_citation_ids": citation_ids,
        "supporting_uids": supporting_uids,
        "linked_uids": [item for item in supporting_uids if item != _text(source, "uid")],
        "supporting_source_ids": _unique_nonempty([source_id, *linked_source_ids]),
        "linked_source_ids": linked_source_ids,
        "candidate_related_source_ids": _candidate_related_source_ids(source),
        "source_link_ambiguity": _as_dict(source.get("source_link_ambiguity")),
        "supporting_evidence_handles": _unique_nonempty(
            [_text(provenance, "evidence_handle"), _text(document_locator, "evidence_handle")]
        ),
        "provenance": provenance,
        "document_locator": document_locator,
        "source_conflict_ids": [
            _text(conflict, "conflict_id") for conflict in linked_conflicts if _text(conflict, "conflict_id")
        ],
        "source_conflict_status": "disputed" if linked_conflicts else "stable",
        "linked_source_conflicts": _linked_conflict_payload(linked_conflicts),
    }


def _candidate_related_source_ids(source: dict[str, Any]) -> list[str]:
    return [text for item in _as_list(source.get("candidate_related_source_ids")) if (text := str(item).strip())][:6]


def _ranked_rows(rows: list[dict[str, Any]], source_lookup: dict[str, dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    scored = [(_exhibit_priority_score(row, _as_dict(source_lookup.get(_text(row, "source_id")))), row) for row in rows]
    return sorted(scored, key=lambda item: (-item[0], _text(item[1], "date"), _text(item[1], "exhibit_id")))


def _top_exhibits(
    ranked_rows: list[tuple[int, dict[str, Any]]], source_lookup: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        _top_exhibit_payload(
            row,
            source=_as_dict(source_lookup.get(_text(row, "source_id"))),
            rank=index,
            priority_score=score,
        )
        for index, (score, row) in enumerate(ranked_rows[:15], start=1)
    ]


def _value_counts(values: list[str], expected: tuple[str, ...]) -> dict[str, int]:
    return {value: values.count(value) for value in expected}


def _row_text_values(rows: list[dict[str, Any]], key: str) -> list[str]:
    return [_text(row, key) for row in rows]


def _issue_tag_basis_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    bases = [_text(tag, "assignment_basis") for row in rows for tag in _as_list(row.get("issue_tags")) if isinstance(tag, dict)]
    return _value_counts(bases, ("operator_supplied", "direct_document_content", "bounded_inference"))


def _index_summary(
    rows: list[dict[str, Any]], bundle: dict[str, Any], top_exhibits: list[dict[str, Any]], missing_exhibits: list[dict[str, Any]]
) -> dict[str, Any]:
    strengths = [_text(_as_dict(row.get("exhibit_reliability")), "strength") for row in rows]
    readiness = [_text(_as_dict(_as_dict(row.get("exhibit_reliability")).get("next_step_logic")), "readiness") for row in rows]
    return {
        "source_type_counts": dict(_as_dict(bundle.get("summary")).get("source_type_counts") or {}),
        "exhibit_strength_counts": _value_counts(strengths, ("strong", "moderate", "weak", "unknown")),
        "exhibit_readiness_counts": _value_counts(
            readiness, ("usable_now", "usable_with_original_source_check", "manual_review_required")
        ),
        "issue_tag_counts": _tag_counts(rows, "all_issue_tags"),
        "main_issue_tag_counts": _tag_counts(rows, "main_issue_tags"),
        "scope_issue_tag_counts": _tag_counts(rows, "scope_issue_tags"),
        "inferred_issue_tag_counts": _tag_counts(rows, "inferred_issue_tags"),
        "issue_tag_basis_counts": _issue_tag_basis_counts(rows),
        "top_exhibit_count": len(top_exhibits),
        "missing_exhibit_count": len(missing_exhibits),
        "source_conflict_status_counts": _value_counts(_row_text_values(rows, "source_conflict_status"), ("stable", "disputed")),
    }


def build_matter_evidence_index(
    *,
    case_bundle: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
    finding_evidence_index: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a durable exhibit register from current case-analysis sources."""
    if not isinstance(case_bundle, dict) or not isinstance(multi_source_case_bundle, dict):
        return None
    source_lookup = _source_by_id(multi_source_case_bundle)
    source_links = _source_links(multi_source_case_bundle)
    context = _IndexContext(
        case_bundle=case_bundle,
        finding_evidence_index=_as_dict(finding_evidence_index),
        source_lookup=source_lookup,
        source_links=source_links,
        conflicts_by_source_id=_source_conflicts_by_source_id(_as_dict(master_chronology)),
    )
    rows = [
        _evidence_row(index, source, context) for index, source in enumerate(_sorted_sources(multi_source_case_bundle), start=1)
    ]
    top_15_exhibits = _top_exhibits(_ranked_rows(rows, source_lookup), source_lookup)
    top_10_missing_exhibits = _missing_exhibit_rows(
        case_bundle=case_bundle,
        rows=rows,
        master_chronology=_as_dict(master_chronology),
        as_dict=_as_dict,
        as_list=_as_list,
    )
    return {
        "version": MATTER_EVIDENCE_INDEX_VERSION,
        "row_count": len(rows),
        "summary": _index_summary(rows, multi_source_case_bundle, top_15_exhibits, top_10_missing_exhibits),
        "rows": rows,
        "top_15_exhibits": top_15_exhibits,
        "top_10_missing_exhibits": top_10_missing_exhibits,
    }
