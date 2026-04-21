"""Gap and conflict analysis helpers for chronology assembly."""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from .master_chronology_common import _as_dict, _as_list, _date_only

_SUMMARY_CONFLICT_SOURCE_TYPES = {
    "email",
    "formal_document",
    "meeting_note",
    "note_record",
    "participation_record",
}
_CONFLICT_ACTION_TAGS: dict[str, tuple[str, ...]] = {
    "participation_or_consultation": (
        "sbv",
        "personalrat",
        "betriebsrat",
        "beteilig",
        "consult",
        "participation",
        "consultation",
        "include sbv",
    ),
    "include_or_inform": ("include", "inform", "copy", "cc", "einbeziehen", "informieren", "summary"),
    "schedule_or_meet": ("schedule", "meeting", "invite", "calendar", "termin", "einladen", "besprechung"),
    "review_or_decide": ("review", "decide", "approval", "approve", "prüfen", "entscheidung", "freigabe"),
}
_NEGATION_TOKENS = (
    " no ",
    " not ",
    " without ",
    " never ",
    " did not ",
    " didn't ",
    " kein ",
    " keine ",
    " keinen ",
    " ohne ",
    " nicht ",
)
_SOURCE_PRIORITY_RULES: tuple[dict[str, str], ...] = (
    {
        "rule_id": "explicit_document_date_over_source_timestamp",
        "label": "Explicit document date over recorded source timestamp",
        "applies_to": "inconsistent_dates",
    },
    {
        "rule_id": "primary_document_over_operator_note",
        "label": "Primary document over operator note or meeting summary",
        "applies_to": "inconsistent_summary",
    },
    {
        "rule_id": "authored_text_over_metadata",
        "label": "Authored text over metadata-only wording",
        "applies_to": "metadata_vs_authored_text",
    },
    {
        "rule_id": "native_text_over_ocr_or_image",
        "label": "Native text over OCR-only or image-only extraction",
        "applies_to": "extracted_text_vs_image_evidence",
    },
)


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _source_text(source: dict[str, Any]) -> str:
    documentary_support = _as_dict(source.get("documentary_support"))
    return " ".join(
        part
        for part in (
            _compact_text(source.get("title")),
            _compact_text(source.get("snippet")),
            _compact_text(documentary_support.get("text_preview")),
        )
        if part
    )


def _has_negation(text: str) -> bool:
    lowered = f" {_compact_text(text).lower()} "
    return any(token in lowered for token in _NEGATION_TOKENS)


def _action_tags(text: str) -> list[str]:
    lowered = _compact_text(text).lower()
    return [
        action_tag for action_tag, keywords in _CONFLICT_ACTION_TAGS.items() if any(keyword in lowered for keyword in keywords)
    ]


def _source_priority_rank(source: dict[str, Any]) -> int:
    """Return a bounded source priority score for conflict handling."""
    source_type = str(source.get("source_type") or "")
    documentary_support = _as_dict(source.get("documentary_support"))
    reliability = _as_dict(source.get("source_reliability"))
    format_profile = _as_dict(documentary_support.get("format_profile"))
    extraction_state = str(documentary_support.get("extraction_state") or "")
    support_level = str(format_profile.get("support_level") or "")
    basis = str(reliability.get("basis") or "").lower()
    rank = {
        "formal_document": 90,
        "participation_record": 88,
        "time_record": 86,
        "email": 80,
        "note_record": 62,
        "meeting_note": 58,
        "attachment": 46,
    }.get(source_type, 50)
    if "authored" in basis or "native" in basis:
        rank += 12
    if "metadata" in basis:
        rank -= 10
    if extraction_state == "native_text_extracted":
        rank += 10
    elif extraction_state == "ocr_text_extracted":
        rank += 3
    elif extraction_state in {"binary_only", "image_embedding_only", "ocr_failed", "extraction_failed"}:
        rank -= 12
    if support_level == "reference_only":
        rank -= 8
    if bool(documentary_support.get("text_available")):
        rank += 4
    return rank


def _priority_rule_for_summary_conflict(left: dict[str, Any], right: dict[str, Any]) -> str:
    left_rank = _source_priority_rank(left)
    right_rank = _source_priority_rank(right)
    left_basis = str(_as_dict(left.get("source_reliability")).get("basis") or "").lower()
    right_basis = str(_as_dict(right.get("source_reliability")).get("basis") or "").lower()
    left_extraction = str(_as_dict(left.get("documentary_support")).get("extraction_state") or "")
    right_extraction = str(_as_dict(right.get("documentary_support")).get("extraction_state") or "")
    if ("metadata" in left_basis) != ("metadata" in right_basis):
        return "authored_text_over_metadata"
    if left_extraction != right_extraction and {
        left_extraction,
        right_extraction,
    } & {"ocr_text_extracted", "binary_only", "image_embedding_only", "ocr_failed"}:
        return "native_text_over_ocr_or_image"
    if abs(left_rank - right_rank) >= 8:
        return "primary_document_over_operator_note"
    return "primary_document_over_operator_note"


def _entry_source_id(entry: dict[str, Any]) -> str:
    source_ids = [str(item) for item in _as_list(_as_dict(entry.get("source_linkage")).get("source_ids")) if str(item).strip()]
    return source_ids[0] if source_ids else ""


def _gap_issue_tracks(entry: dict[str, Any]) -> list[str]:
    tracks: list[str] = []
    for read_id, read_payload in _as_dict(entry.get("event_support_matrix")).items():
        if read_id == "ordinary_managerial_explanation" or not isinstance(read_payload, dict):
            continue
        status = str(read_payload.get("status") or "")
        if status in {"direct_event_support", "contextual_support_only"} and read_id not in tracks:
            tracks.append(str(read_id))
    return tracks


def _coverage_start(entry: dict[str, Any]) -> Any:
    coverage_window = _as_dict(entry.get("coverage_window"))
    return _date_only(str(coverage_window.get("start") or entry.get("date") or ""))


def _coverage_end(entry: dict[str, Any]) -> Any:
    coverage_window = _as_dict(entry.get("coverage_window"))
    return _date_only(str(coverage_window.get("end") or entry.get("date") or ""))


def _bridge_record_suggestions(earlier: dict[str, Any], later: dict[str, Any]) -> list[str]:
    source_types = {
        str(item)
        for item in [
            *_as_list(_as_dict(earlier.get("source_linkage")).get("source_types")),
            *_as_list(_as_dict(later.get("source_linkage")).get("source_types")),
        ]
        if str(item).strip()
    }
    suggestions: list[str] = []
    if "time_record" in source_types:
        suggestions.append("Intervening attendance or time record")
    if "meeting_note" in source_types or "note_record" in source_types:
        suggestions.append("Bridge meeting note or summary record")
    if "formal_document" in source_types or "participation_record" in source_types:
        suggestions.append("Bridge formal decision, participation, or consultation record")
    if not suggestions:
        suggestions.append("Bridge email, note, or documentary record covering the silent period")
    return suggestions[:3]


def _chronology_entry_by_source_id(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {source_id: entry for entry in entries if (source_id := _entry_source_id(entry))}


def _linked_source_pairs(
    multi_source_case_bundle: dict[str, Any],
    source_lookup: dict[str, dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen: set[tuple[str, ...]] = set()
    for link in _as_list(multi_source_case_bundle.get("source_links")):
        if not isinstance(link, dict):
            continue
        left_id = str(link.get("from_source_id") or "")
        right_id = str(link.get("to_source_id") or "")
        if not left_id or not right_id:
            continue
        pair_key = tuple(sorted((left_id, right_id)))
        if pair_key in seen:
            continue
        left = _as_dict(source_lookup.get(left_id))
        right = _as_dict(source_lookup.get(right_id))
        if not left or not right:
            continue
        seen.add(pair_key)
        pairs.append((left, right))

    grouped_by_uid: dict[str, list[dict[str, Any]]] = {}
    for source in source_lookup.values():
        uid = str(source.get("uid") or "")
        if uid:
            grouped_by_uid.setdefault(uid, []).append(source)
    for group in grouped_by_uid.values():
        for index, left in enumerate(group):
            left_id = str(left.get("source_id") or "")
            for right in group[index + 1 :]:
                right_id = str(right.get("source_id") or "")
                pair_key = tuple(sorted((left_id, right_id)))
                if not left_id or not right_id or pair_key in seen:
                    continue
                seen.add(pair_key)
                pairs.append((left, right))
    return pairs


def _summary_conflicts(
    *,
    entries: list[dict[str, Any]],
    multi_source_case_bundle: dict[str, Any],
    source_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    entry_by_source_id = _chronology_entry_by_source_id(entries)
    conflicts: list[dict[str, Any]] = []
    for left, right in _linked_source_pairs(multi_source_case_bundle, source_lookup):
        left_type = str(left.get("source_type") or "")
        right_type = str(right.get("source_type") or "")
        if left_type not in _SUMMARY_CONFLICT_SOURCE_TYPES or right_type not in _SUMMARY_CONFLICT_SOURCE_TYPES:
            continue
        left_text = _source_text(left)
        right_text = _source_text(right)
        if not left_text or not right_text:
            continue
        left_tags = set(_action_tags(left_text))
        right_tags = set(_action_tags(right_text))
        overlapping_tags = sorted(left_tags & right_tags)
        if not overlapping_tags:
            continue
        left_negated = _has_negation(left_text)
        right_negated = _has_negation(right_text)
        if left_negated == right_negated:
            continue
        left_id = str(left.get("source_id") or "")
        right_id = str(right.get("source_id") or "")
        left_rank = _source_priority_rank(left)
        right_rank = _source_priority_rank(right)
        preferred = left if left_rank >= right_rank else right
        rule_id = _priority_rule_for_summary_conflict(left, right)
        resolution_status = "provisional_preference" if abs(left_rank - right_rank) >= 8 else "unresolved_human_review_needed"
        preferred_id = str(preferred.get("source_id") or "")
        conflicts.append(
            {
                "conflict_id": f"SCF-{len(conflicts) + 1:03d}",
                "conflict_kind": "inconsistent_summary",
                "resolution_status": resolution_status,
                "summary": (
                    "Linked sources describe the same topic differently: one source negates a step that the other source "
                    "describes as expected or completed."
                ),
                "source_ids": [left_id, right_id],
                "source_types": [left_type, right_type],
                "chronology_ids": [
                    str(item.get("chronology_id") or "")
                    for item in (entry_by_source_id.get(left_id), entry_by_source_id.get(right_id))
                    if isinstance(item, dict) and str(item.get("chronology_id") or "")
                ],
                "overlapping_topics": overlapping_tags,
                "priority_rule_applied": rule_id,
                "preferred_source_id": preferred_id,
                "preferred_source_rank": max(left_rank, right_rank),
                "preferred_reason": (
                    f"{preferred.get('source_type') or 'source'} currently ranks higher under the configured "
                    "source-priority rules."
                ),
                "conflicting_claims": [
                    {"source_id": left_id, "statement": left_text[:220], "negated": left_negated},
                    {"source_id": right_id, "statement": right_text[:220], "negated": right_negated},
                ],
            }
        )
    return conflicts


def _source_conflict_registry(
    *,
    entries: list[dict[str, Any]],
    source_lookup: dict[str, dict[str, Any]],
    multi_source_case_bundle: dict[str, Any],
    sequence_breaks: list[dict[str, Any]],
) -> dict[str, Any]:
    date_conflicts: list[dict[str, Any]] = []
    for sequence_break in sequence_breaks:
        chronology_id = str(sequence_break.get("chronology_id") or "")
        chronology_entry = next((entry for entry in entries if str(entry.get("chronology_id") or "") == chronology_id), {})
        source_id = _entry_source_id(chronology_entry) if chronology_entry else ""
        date_conflicts.append(
            {
                "conflict_id": str(sequence_break.get("conflict_id") or ""),
                "conflict_kind": "inconsistent_dates",
                "resolution_status": "unresolved_human_review_needed",
                "summary": (
                    "The chronology event date materially differs from the source-recorded date and needs human "
                    "validation before sequence assumptions are finalized."
                ),
                "source_ids": [source_id] if source_id else [],
                "source_types": [str(item) for item in _as_list(sequence_break.get("source_types")) if str(item).strip()],
                "chronology_ids": [chronology_id] if chronology_id else [],
                "priority_rule_applied": "explicit_document_date_over_source_timestamp",
                "preferred_source_id": source_id,
                "preferred_reason": (
                    "The current chronology prefers the explicit event/date anchor, but the underlying source timestamp "
                    "still needs human review."
                ),
                "conflicting_claims": [
                    {"label": "event_date", "value": str(sequence_break.get("event_date") or "")},
                    {"label": "source_recorded_date", "value": str(sequence_break.get("source_recorded_date") or "")},
                ],
            }
        )

    summary_conflicts = _summary_conflicts(
        entries=entries,
        multi_source_case_bundle=multi_source_case_bundle,
        source_lookup=source_lookup,
    )
    conflicts = [*date_conflicts, *summary_conflicts]
    affected_source_ids = {
        str(source_id) for conflict in conflicts for source_id in _as_list(conflict.get("source_ids")) if str(source_id).strip()
    }
    affected_chronology_ids = {
        str(chronology_id)
        for conflict in conflicts
        for chronology_id in _as_list(conflict.get("chronology_ids"))
        if str(chronology_id).strip()
    }
    for entry in entries:
        source_id = _entry_source_id(entry)
        chronology_id = str(entry.get("chronology_id") or "")
        linked_conflicts = [
            str(conflict.get("conflict_id") or "")
            for conflict in conflicts
            if source_id in _as_list(conflict.get("source_ids")) or chronology_id in _as_list(conflict.get("chronology_ids"))
        ]
        entry["source_conflict_ids"] = [conflict_id for conflict_id in linked_conflicts if conflict_id]
        entry["fact_stability"] = "disputed" if entry["source_conflict_ids"] else "stable"

    return {
        "version": "1",
        "source_conflict_status": "conflicted" if conflicts else "stable",
        "priority_rules": list(_SOURCE_PRIORITY_RULES),
        "conflict_count": len(conflicts),
        "unresolved_conflict_count": sum(
            1 for conflict in conflicts if str(conflict.get("resolution_status") or "") == "unresolved_human_review_needed"
        ),
        "affected_source_count": len(affected_source_ids),
        "affected_chronology_count": len(affected_chronology_ids),
        "conflicts": conflicts,
    }


def _date_gaps(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for earlier, later in pairwise(entries):
        earlier_date = _coverage_end(earlier)
        later_date = _coverage_start(later)
        if earlier_date is None or later_date is None:
            continue
        gap_days = (later_date - earlier_date).days
        if gap_days < 7:
            continue
        linked_issue_tracks = list(dict.fromkeys([*_gap_issue_tracks(earlier), *_gap_issue_tracks(later)]))
        priority = "high" if gap_days >= 14 or linked_issue_tracks else "medium"
        gaps.append(
            {
                "gap_id": f"GAP-{len(gaps) + 1:03d}",
                "from_chronology_id": str(earlier.get("chronology_id") or ""),
                "to_chronology_id": str(later.get("chronology_id") or ""),
                "start_date": str(earlier.get("date") or ""),
                "end_date": str(later.get("date") or ""),
                "gap_days": gap_days,
                "priority": priority,
                "linked_issue_tracks": linked_issue_tracks,
                "involved_source_types": list(
                    dict.fromkeys(
                        [
                            str(item)
                            for item in [
                                *_as_list(_as_dict(earlier.get("source_linkage")).get("source_types")),
                                *_as_list(_as_dict(later.get("source_linkage")).get("source_types")),
                            ]
                            if str(item).strip()
                        ]
                    )
                ),
                "why_it_matters": (
                    "This gap spans potentially material chronology space that is not yet explained by the current dated record."
                ),
                "missing_bridge_record_suggestions": _bridge_record_suggestions(earlier, later),
            }
        )
    gaps.sort(
        key=lambda gap: (
            -int(gap.get("gap_days") or 0),
            str(gap.get("from_chronology_id") or ""),
            str(gap.get("to_chronology_id") or ""),
        )
    )
    for index, gap in enumerate(gaps, start=1):
        gap["gap_id"] = f"GAP-{index:03d}"
    return gaps
