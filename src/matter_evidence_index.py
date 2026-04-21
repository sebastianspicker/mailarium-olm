"""Durable exhibit-register builder for mixed-source case analysis."""

from __future__ import annotations

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

    sources = _source_rows(multi_source_case_bundle)
    source_lookup = _source_by_id(multi_source_case_bundle)
    source_links = [link for link in _as_list(multi_source_case_bundle.get("source_links")) if isinstance(link, dict)]
    source_conflicts_by_source_id = _source_conflicts_by_source_id(_as_dict(master_chronology))
    rows: list[dict[str, Any]] = []

    for index, source in enumerate(
        sorted(
            sources,
            key=lambda item: (
                str(item.get("date") or ""),
                str(item.get("source_type") or ""),
                str(item.get("source_id") or ""),
            ),
        ),
        start=1,
    ):
        findings = _findings_for_source(
            _as_dict(finding_evidence_index),
            source,
            source_lookup=source_lookup,
            source_links=source_links,
        )
        citation_ids = _citation_ids_for_source(
            _as_dict(finding_evidence_index),
            source,
            source_lookup=source_lookup,
            source_links=source_links,
        )
        source_id = str(source.get("source_id") or "")
        linked_source_ids = [item for item in _linked_source_ids(source_id, source_links) if item]
        supporting_source_ids = list(dict.fromkeys([source_id, *linked_source_ids]))
        provenance = _as_dict(source.get("provenance"))
        document_locator = _as_dict(source.get("document_locator"))
        evidence_handles = list(
            dict.fromkeys(
                [
                    str(provenance.get("evidence_handle") or ""),
                    str(document_locator.get("evidence_handle") or ""),
                ]
            )
        )
        supporting_uids = list(
            dict.fromkeys(
                [
                    str(source.get("uid") or ""),
                    *[
                        str(_as_dict(source_lookup.get(linked_source_id)).get("uid") or "")
                        for linked_source_id in linked_source_ids
                    ],
                ]
            )
        )
        supporting_uids = [item for item in supporting_uids if item]
        exhibit_id = f"EXH-{index:03d}"
        issue_tags = _issue_tags(case_bundle, source, findings)
        linked_conflicts = source_conflicts_by_source_id.get(str(source.get("source_id") or ""), [])
        source_language = _source_language(source)
        exhibit_reliability = _exhibit_reliability(source, findings)
        next_step_logic = _as_dict(exhibit_reliability.get("next_step_logic"))
        sender_identity = _sender_identity(source, source_lookup=source_lookup, source_links=source_links)
        recipient_identities = _recipient_identities(source, source_lookup=source_lookup, source_links=source_links)
        rows.append(
            {
                "exhibit_id": exhibit_id,
                "date": str(source.get("date") or ""),
                "document_type": str(source.get("document_kind") or source.get("source_type") or ""),
                "sender_or_author": _sender_or_author(source, source_lookup=source_lookup, source_links=source_links),
                "sender_identity": sender_identity,
                "recipients": _recipients(source, source_lookup, source_links),
                "recipient_identities": recipient_identities,
                "short_description": _short_description(source),
                "issue_tags": issue_tags,
                "main_issue_tags": list(
                    dict.fromkeys(
                        str(tag.get("tag_id") or "")
                        for tag in issue_tags
                        if str(tag.get("tag_id") or "") and str(tag.get("assignment_basis") or "") == "direct_document_content"
                    )
                ),
                "scope_issue_tags": list(
                    dict.fromkeys(
                        str(tag.get("tag_id") or "")
                        for tag in issue_tags
                        if str(tag.get("tag_id") or "") and str(tag.get("assignment_basis") or "") == "operator_supplied"
                    )
                ),
                "inferred_issue_tags": list(
                    dict.fromkeys(
                        str(tag.get("tag_id") or "")
                        for tag in issue_tags
                        if str(tag.get("tag_id") or "") and str(tag.get("assignment_basis") or "") == "bounded_inference"
                    )
                ),
                "all_issue_tags": list(
                    dict.fromkeys(str(tag.get("tag_id") or "") for tag in issue_tags if str(tag.get("tag_id") or ""))
                ),
                "key_quoted_passage": str(source.get("snippet") or ""),
                "source_language": source_language,
                "quoted_evidence": _make_quoted_evidence(source, source_language=source_language),
                "why_it_matters": _why_it_matters(source, findings),
                "exhibit_reliability": exhibit_reliability,
                "strength": str(exhibit_reliability.get("strength") or ""),
                "readiness": str(next_step_logic.get("readiness") or ""),
                "reliability_or_evidentiary_strength": _reliability_label(source),
                "source_reliability": _as_dict(source.get("source_reliability")),
                "promotability_status": str(source.get("promotability_status") or ""),
                "follow_up_needed": _follow_up_needed(source, findings),
                "source_format_support": _as_dict(_as_dict(source.get("documentary_support")).get("format_profile")),
                "extraction_quality": _as_dict(_as_dict(source.get("documentary_support")).get("extraction_quality")),
                "source_id": str(source.get("source_id") or ""),
                "source_type": str(source.get("source_type") or ""),
                "supporting_finding_ids": _finding_ids(findings),
                "supporting_citation_ids": citation_ids,
                "supporting_uids": supporting_uids,
                "linked_uids": [item for item in supporting_uids if item != str(source.get("uid") or "")],
                "supporting_source_ids": list(dict.fromkeys([item for item in supporting_source_ids if item])),
                "linked_source_ids": linked_source_ids,
                "candidate_related_source_ids": [
                    str(item) for item in _as_list(source.get("candidate_related_source_ids")) if str(item).strip()
                ][:6],
                "source_link_ambiguity": _as_dict(source.get("source_link_ambiguity")),
                "supporting_evidence_handles": [item for item in evidence_handles if item],
                "provenance": provenance,
                "document_locator": document_locator,
                "source_conflict_ids": [
                    str(conflict.get("conflict_id") or "")
                    for conflict in linked_conflicts
                    if str(conflict.get("conflict_id") or "")
                ],
                "source_conflict_status": ("disputed" if linked_conflicts else "stable"),
                "linked_source_conflicts": [
                    {
                        "conflict_id": str(conflict.get("conflict_id") or ""),
                        "conflict_kind": str(conflict.get("conflict_kind") or ""),
                        "resolution_status": str(conflict.get("resolution_status") or ""),
                        "summary": str(conflict.get("summary") or ""),
                    }
                    for conflict in linked_conflicts[:2]
                ],
            }
        )

    ranked_rows = sorted(
        [(_exhibit_priority_score(row, _as_dict(source_lookup.get(str(row.get("source_id") or "")))), row) for row in rows],
        key=lambda item: (
            -item[0],
            str(item[1].get("date") or ""),
            str(item[1].get("exhibit_id") or ""),
        ),
    )
    top_15_exhibits = [
        _top_exhibit_payload(
            row,
            source=_as_dict(source_lookup.get(str(row.get("source_id") or ""))),
            rank=index,
            priority_score=score,
        )
        for index, (score, row) in enumerate(ranked_rows[:15], start=1)
    ]
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
        "summary": {
            "source_type_counts": dict(_as_dict(multi_source_case_bundle.get("summary")).get("source_type_counts") or {}),
            "exhibit_strength_counts": {
                strength: sum(
                    1 for row in rows if str(_as_dict(row.get("exhibit_reliability")).get("strength") or "") == strength
                )
                for strength in ("strong", "moderate", "weak", "unknown")
            },
            "exhibit_readiness_counts": {
                readiness: sum(
                    1
                    for row in rows
                    if str(_as_dict(_as_dict(row.get("exhibit_reliability")).get("next_step_logic")).get("readiness") or "")
                    == readiness
                )
                for readiness in ("usable_now", "usable_with_original_source_check", "manual_review_required")
            },
            "issue_tag_counts": {
                tag: sum(1 for row in rows if tag in _as_list(row.get("all_issue_tags")))
                for tag in {tag for row in rows for tag in _as_list(row.get("all_issue_tags")) if isinstance(tag, str) and tag}
            },
            "main_issue_tag_counts": {
                tag: sum(1 for row in rows if tag in _as_list(row.get("main_issue_tags")))
                for tag in {tag for row in rows for tag in _as_list(row.get("main_issue_tags")) if isinstance(tag, str) and tag}
            },
            "scope_issue_tag_counts": {
                tag: sum(1 for row in rows if tag in _as_list(row.get("scope_issue_tags")))
                for tag in {tag for row in rows for tag in _as_list(row.get("scope_issue_tags")) if isinstance(tag, str) and tag}
            },
            "inferred_issue_tag_counts": {
                tag: sum(1 for row in rows if tag in _as_list(row.get("inferred_issue_tags")))
                for tag in {
                    tag for row in rows for tag in _as_list(row.get("inferred_issue_tags")) if isinstance(tag, str) and tag
                }
            },
            "issue_tag_basis_counts": {
                basis: sum(
                    1
                    for row in rows
                    for tag in _as_list(row.get("issue_tags"))
                    if isinstance(tag, dict) and str(tag.get("assignment_basis") or "") == basis
                )
                for basis in ("operator_supplied", "direct_document_content", "bounded_inference")
            },
            "top_exhibit_count": len(top_15_exhibits),
            "missing_exhibit_count": len(top_10_missing_exhibits),
            "source_conflict_status_counts": {
                status: sum(1 for row in rows if str(row.get("source_conflict_status") or "") == status)
                for status in ("stable", "disputed")
            },
        },
        "rows": rows,
        "top_15_exhibits": top_15_exhibits,
        "top_10_missing_exhibits": top_10_missing_exhibits,
    }
