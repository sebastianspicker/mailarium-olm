"""Missing-exhibit and chronology-gap helpers for the matter evidence index."""

from __future__ import annotations

from typing import Any

from .employment_issue_frameworks import ISSUE_TRACK_DEFINITIONS


def source_coverage_text(rows: list[dict[str, Any]]) -> str:
    return " ".join(
        " ".join(
            part
            for part in (
                str(row.get("document_type") or ""),
                str(row.get("short_description") or ""),
                str(row.get("key_quoted_passage") or ""),
                " ".join(str(tag) for tag in row.get("main_issue_tags", []) if str(tag).strip()),
            )
            if part
        ).lower()
        for row in rows
    )


def source_conflicts_by_source_id(
    master_chronology: dict[str, Any], *, as_dict: Any, as_list: Any
) -> dict[str, list[dict[str, Any]]]:
    registry = as_dict(as_dict(master_chronology.get("summary")).get("source_conflict_registry"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for conflict in as_list(registry.get("conflicts")):
        if not isinstance(conflict, dict):
            continue
        for source_id in as_list(conflict.get("source_ids")):
            source_key = str(source_id or "").strip()
            if not source_key:
                continue
            grouped.setdefault(source_key, []).append(conflict)
    return grouped


def checklist_item_covered(item: str, coverage_text: str) -> bool:
    normalized = str(item or "").lower()
    token_candidates = [
        token.strip(" ,.-()")
        for token in normalized.replace("/", " ").replace("-", " ").split()
        if len(token.strip(" ,.-()")) >= 4
    ]
    signal_tokens = [
        token
        for token in token_candidates
        if token not in {"other", "record", "messages", "message", "decision", "decisions", "notes", "neutral", "about"}
    ]
    return bool(signal_tokens) and any(token in coverage_text for token in signal_tokens[:4])


def gap_links_for_track(
    master_chronology: dict[str, Any], issue_track: str, *, as_dict: Any, as_list: Any
) -> list[dict[str, Any]]:
    chronology_summary = as_dict(master_chronology.get("summary"))
    linked: list[dict[str, Any]] = []
    for gap in as_list(chronology_summary.get("date_gaps_and_unexplained_sequences")):
        if not isinstance(gap, dict):
            continue
        linked_tracks = [str(item) for item in as_list(gap.get("linked_issue_tracks")) if str(item).strip()]
        if issue_track in linked_tracks:
            linked.append(gap)
    return linked


def missing_exhibit_rows(
    *, case_bundle: dict[str, Any], rows: list[dict[str, Any]], master_chronology: dict[str, Any], as_dict: Any, as_list: Any
) -> list[dict[str, Any]]:
    scope = as_dict(case_bundle.get("scope"))
    selected_tracks = [
        str(track) for track in as_list(scope.get("employment_issue_tracks")) if str(track).strip() in ISSUE_TRACK_DEFINITIONS
    ]
    if not selected_tracks:
        return []
    coverage_text = source_coverage_text(rows)
    missing_rows: list[dict[str, Any]] = []
    for issue_track in selected_tracks:
        definition = as_dict(ISSUE_TRACK_DEFINITIONS.get(issue_track))
        gap_links = gap_links_for_track(master_chronology, issue_track, as_dict=as_dict, as_list=as_list)
        for item in as_list(definition.get("missing_document_checklist")):
            requested_exhibit = str(item).strip()
            if not requested_exhibit or checklist_item_covered(requested_exhibit, coverage_text):
                continue
            base_score = 60 + min(len(gap_links) * 8, 16)
            if "record" in requested_exhibit.lower() or "correspondence" in requested_exhibit.lower():
                base_score += 6
            minimum_quality = str((as_list(definition.get("minimum_source_quality_expectations")) or [""])[0]).strip()
            chronology_signal = (
                f"{len(gap_links)} chronology gap(s) currently intersect this issue track."
                if gap_links
                else "No direct chronology gap is currently linked, but the document checklist remains unfilled."
            )
            missing_rows.append(
                {
                    "issue_track": issue_track,
                    "issue_track_title": str(definition.get("title") or issue_track),
                    "requested_exhibit": requested_exhibit,
                    "priority_score": base_score,
                    "why_missing_matters": minimum_quality
                    or f"This concrete document would help close the current {issue_track.replace('_', ' ')} proof gap.",
                    "chronology_signal": chronology_signal,
                    "linked_date_gap_ids": [str(gap.get("gap_id") or "") for gap in gap_links if str(gap.get("gap_id") or "")],
                }
            )
    ordered = sorted(
        missing_rows,
        key=lambda item: (
            -int(item.get("priority_score") or 0),
            str(item.get("issue_track") or ""),
            str(item.get("requested_exhibit") or ""),
        ),
    )
    for index, item in enumerate(ordered, start=1):
        item["rank"] = index
    return ordered[:10]
