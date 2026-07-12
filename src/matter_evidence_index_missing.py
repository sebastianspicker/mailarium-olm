"""Missing-exhibit and chronology-gap helpers for the matter evidence index."""
# pylint: disable=too-many-locals

from __future__ import annotations

from typing import Any

from .employment_issue_frameworks import ISSUE_TRACK_DEFINITIONS


def source_coverage_text(rows: list[dict[str, Any]]) -> str:
    """Generate a normalized coverage text string from a list of evidence rows.

    Concatenates document_type, short_description, key_quoted_passage, and main_issue_tags
    from each row into a single lowercase string for coverage analysis.

    Args:
        rows: List of evidence row dictionaries containing document metadata.

    Returns:
        A space-joined, lowercase string containing all coverage text from the rows.
    """
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
    """Extract source conflicts from master chronology grouped by source ID.

    Parses the source_conflict_registry from the master chronology summary and
    groups conflicts by their associated source IDs for easy lookup.

    Args:
        master_chronology: The master chronology dictionary containing summary data.
        as_dict: Callable to safely convert values to dictionaries.
        as_list: Callable to safely convert values to lists.

    Returns:
        A dictionary mapping source IDs to lists of conflict dictionaries.
    """
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
    """Check if a checklist item is covered by the given coverage text.

    Tokenizes the item and checks if any significant token (4+ chars, excluding
    common stop words) appears in the coverage text.

    Args:
        item: The checklist item string to check for coverage.
        coverage_text: The normalized coverage text to search within.

    Returns:
        True if the item is considered covered, False otherwise.
    """
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
    """Find date gaps in master chronology that are linked to a specific issue track.

    Filters the date_gaps_and_unexplained_sequences from the chronology summary
    to return only those gaps that reference the given issue track.

    Args:
        master_chronology: The master chronology dictionary containing summary data.
        issue_track: The employment issue track identifier to filter by.
        as_dict: Callable to safely convert values to dictionaries.
        as_list: Callable to safely convert values to lists.

    Returns:
        A list of gap dictionaries that are linked to the specified issue track.
    """
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
    """Identify missing exhibit rows based on issue track checklists and current coverage.

    For each selected employment issue track, checks the missing_document_checklist
    against current evidence coverage and chronology gaps to identify missing exhibits.
    Results are scored by priority and limited to the top 10.

    Args:
        case_bundle: The case bundle dictionary containing scope information.
        rows: List of current evidence rows for coverage analysis.
        master_chronology: The master chronology dictionary for gap analysis.
        as_dict: Callable to safely convert values to dictionaries.
        as_list: Callable to safely convert values to lists.

    Returns:
        A list of up to 10 prioritized missing exhibit row dictionaries, each containing
        issue_track, requested_exhibit, priority_score, and related metadata.
    """
    scope = as_dict(case_bundle.get("scope"))
    selected_tracks = [
        str(track) for track in as_list(scope.get("employment_issue_tracks")) if str(track).strip() in ISSUE_TRACK_DEFINITIONS
    ]
    if not selected_tracks:
        return []
    coverage_text = source_coverage_text(rows)
    missing_rows: list[dict[str, Any]] = []
    for issue_track in selected_tracks:
        missing_rows.extend(
            _missing_rows_for_track(
                issue_track,
                coverage_text=coverage_text,
                master_chronology=master_chronology,
                as_dict=as_dict,
                as_list=as_list,
            )
        )
    ordered = sorted(missing_rows, key=_missing_row_sort_key)
    for index, item in enumerate(ordered, start=1):
        item["rank"] = index
    return ordered[:10]


def _missing_rows_for_track(
    issue_track: str, *, coverage_text: str, master_chronology: dict[str, Any], as_dict: Any, as_list: Any
) -> list[dict[str, Any]]:
    definition = as_dict(ISSUE_TRACK_DEFINITIONS.get(issue_track))
    gap_links = gap_links_for_track(master_chronology, issue_track, as_dict=as_dict, as_list=as_list)
    missing_rows: list[dict[str, Any]] = []
    for item in as_list(definition.get("missing_document_checklist")):
        requested_exhibit = str(item).strip()
        if requested_exhibit and not checklist_item_covered(requested_exhibit, coverage_text):
            missing_rows.append(_missing_exhibit_row(issue_track, requested_exhibit, definition, gap_links, as_list=as_list))
    return missing_rows


def _missing_exhibit_row(
    issue_track: str,
    requested_exhibit: str,
    definition: dict[str, Any],
    gap_links: list[dict[str, Any]],
    *,
    as_list: Any,
) -> dict[str, Any]:
    priority_score = 60 + min(len(gap_links) * 8, 16) + _document_type_bonus(requested_exhibit)
    quality_expectations = as_list(definition.get("minimum_source_quality_expectations")) or [""]
    minimum_quality = str(quality_expectations[0]).strip()
    return {
        "issue_track": issue_track,
        "issue_track_title": str(definition.get("title") or issue_track),
        "requested_exhibit": requested_exhibit,
        "priority_score": priority_score,
        "why_missing_matters": minimum_quality
        or f"This concrete document would help close the current {issue_track.replace('_', ' ')} proof gap.",
        "chronology_signal": _chronology_signal(gap_links),
        "linked_date_gap_ids": _gap_ids(gap_links),
    }


def _document_type_bonus(requested_exhibit: str) -> int:
    normalized = requested_exhibit.lower()
    return 6 if "record" in normalized or "correspondence" in normalized else 0


def _chronology_signal(gap_links: list[dict[str, Any]]) -> str:
    if gap_links:
        return f"{len(gap_links)} chronology gap(s) currently intersect this issue track."
    return "No direct chronology gap is currently linked, but the document checklist remains unfilled."


def _gap_ids(gap_links: list[dict[str, Any]]) -> list[str]:
    return [gap_id for gap in gap_links if (gap_id := str(gap.get("gap_id") or ""))]


def _missing_row_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    return (
        -int(item.get("priority_score") or 0),
        str(item.get("issue_track") or ""),
        str(item.get("requested_exhibit") or ""),
    )
