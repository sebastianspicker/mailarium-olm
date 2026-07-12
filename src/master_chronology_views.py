"""Chronology rendering views over the shared entry registry."""
# pylint: disable=too-many-locals

from __future__ import annotations

from typing import Any

from .master_chronology_common import _as_dict, _best_supportive_read


def _issue_categories(entry: dict[str, Any]) -> list[str]:
    """Extract issue categories from an entry's event support matrix.

    Returns category labels for all reads in the matrix that have direct_event_support
    or contextual_support_only status, excluding ordinary_managerial_explanation.

    Args:
        entry: A chronology entry dictionary with event_support_matrix.

    Returns:
        A list of issue category strings (read_id with underscores replaced by spaces).
        Limited to 4 categories.
    """
    matrix = _as_dict(entry.get("event_support_matrix"))
    categories = [
        read_id.replace("_", " ")
        for read_id, payload in matrix.items()
        if read_id != "ordinary_managerial_explanation"
        and isinstance(payload, dict)
        and str(_as_dict(payload).get("status") or "") in {"direct_event_support", "contextual_support_only"}
    ]
    return categories[:4]


def _significance(entry: dict[str, Any], *, case_bundle: dict[str, Any]) -> str:
    """Determine the significance explanation for a chronology entry.

    Uses the best supportive read's reason if available, otherwise falls back to
    the ordinary managerial explanation reason.

    Args:
        entry: A chronology entry dictionary.
        case_bundle: The case bundle dictionary for context.

    Returns:
        A string explaining the significance of this entry to the case.
    """
    _read_id, read_payload = _best_supportive_read(entry, case_bundle=case_bundle)
    if read_payload is not None:
        return str(read_payload.get("reason") or "")
    managerial = _as_dict(_as_dict(entry.get("event_support_matrix")).get("ordinary_managerial_explanation"))
    return str(managerial.get("reason") or "Primarily a chronology anchor with no stronger issue-linked support selected.")


def _structured_row(entry: dict[str, Any], *, case_bundle: dict[str, Any]) -> dict[str, Any]:
    """Create a structured row representation for a chronology entry.

    Extracts and formats key information from the entry including date, description,
    people involved, source documents, issue categories, significance, and support status
    for various issue types.

    Args:
        entry: A chronology entry dictionary.
        case_bundle: The case bundle dictionary for context.

    Returns:
        A dictionary containing structured entry information.
    """
    matrix = _as_dict(entry.get("event_support_matrix"))
    source_linkage = _as_dict(entry.get("source_linkage"))
    source_document = _as_dict(entry.get("source_document"))
    return {
        "exact_or_approximate_date": {
            "value": str(entry.get("date") or ""),
            "precision": str(entry.get("date_precision") or ""),
        },
        "event_description": str(entry.get("description") or entry.get("title") or ""),
        "people_involved": _string_items(entry.get("people_involved", [])),
        "source_document": _source_document_payload(entry, source_document, source_linkage),
        "issue_category": _issue_categories(entry),
        "significance_to_case": _significance(entry, case_bundle=case_bundle),
        "supports": _support_statuses(matrix),
    }


def _string_items(values: Any) -> list[str]:
    return [str(item) for item in values if str(item).strip()]


def _source_document_payload(
    entry: dict[str, Any], source_document: dict[str, Any], source_linkage: dict[str, Any]
) -> dict[str, Any]:
    return {
        "title": str(source_document.get("title") or entry.get("title") or ""),
        "source_ids": _string_items(source_linkage.get("source_ids", [])),
        "source_types": _string_items(source_linkage.get("source_types", [])),
    }


def _support_statuses(matrix: dict[str, Any]) -> dict[str, str]:
    return {
        "disability_related_disadvantage": _matrix_status(matrix, "disability_disadvantage"),
        "retaliation": _matrix_status(matrix, "retaliation_after_protected_event"),
        "eingruppierung": _matrix_status(matrix, "eingruppierung_dispute"),
        "prevention_or_participation_failures": _prevention_status(matrix),
        "ordinary_managerial_explanation": _matrix_status(matrix, "ordinary_managerial_explanation"),
    }


def _matrix_status(matrix: dict[str, Any], key: str) -> str:
    return str(_as_dict(matrix.get(key)).get("status") or "not_signaled")


def _prevention_status(matrix: dict[str, Any]) -> str:
    statuses = [
        str(_as_dict(matrix.get(read_id)).get("status") or "")
        for read_id in ("prevention_duty_gap", "participation_duty_gap")
        if str(_as_dict(matrix.get(read_id)).get("status") or "")
    ]
    if "direct_event_support" in statuses:
        return "direct_event_support"
    if "contextual_support_only" in statuses:
        return "contextual_support_only"
    return statuses[0] if statuses else "not_signaled"


def _neutral_view(entries: list[dict[str, Any]], *, case_bundle: dict[str, Any]) -> dict[str, Any]:
    """Create a neutral chronology view from entries.

    Generates a short, neutral chronology that presents each entry with its date,
    title, and entry type without favoring any particular interpretation.

    Args:
        entries: A list of chronology entry dictionaries.
        case_bundle: The case bundle dictionary for context.

    Returns:
        A view dictionary with view_id, entry_count, and items list.
    """
    items = []
    for entry in entries:
        entry_date = str(entry.get("date") or "")
        title = str(entry.get("title") or "")
        entry_type = str(entry.get("entry_type") or "").replace("_", " ")
        items.append(
            {
                "chronology_id": str(entry.get("chronology_id") or ""),
                "date": entry_date,
                "statement": f"{entry_date}: {title}. Recorded as {entry_type}.".strip(),
                "structured_row": _structured_row(entry, case_bundle=case_bundle),
            }
        )
    return {"view_id": "short_neutral_chronology", "entry_count": len(items), "items": items}


def _claimant_view(entries: list[dict[str, Any]], *, case_bundle: dict[str, Any]) -> dict[str, Any]:
    """Create a claimant-favorable chronology view from entries.

    Generates a chronology that emphasizes claimant-favorable readings of each
    entry, including the favored read ID, statement, uncertainty notes, and
    counterargument notes.

    Args:
        entries: A list of chronology entry dictionaries.
        case_bundle: The case bundle dictionary for context.

    Returns:
        A view dictionary with view_id, entry_count, and items list.
    """
    items: list[dict[str, Any]] = []
    for entry in entries:
        read_id, read_payload = _best_supportive_read(entry, case_bundle=case_bundle)
        managerial = _as_dict(_as_dict(entry.get("event_support_matrix")).get("ordinary_managerial_explanation"))
        if read_payload is None:
            read_id = "no_selected_issue_support"
            favored_reason = "No selected issue track is directly advanced by this event on the current record."
        else:
            favored_reason = str(read_payload.get("reason") or "")
        entry_date = str(entry.get("date") or "")
        title = str(entry.get("title") or "")
        managerial_reason = str(managerial.get("reason") or "ordinary alternative remains live.")
        items.append(
            {
                "chronology_id": str(entry.get("chronology_id") or ""),
                "date": entry_date,
                "favored_read_id": read_id,
                "statement": f"{entry_date}: {title}. Claimant-favorable reading: {favored_reason}".strip(),
                "uncertainty_note": f"Current limit: {managerial_reason}",
                "counterargument_note": (
                    "This rendering does not displace the ordinary-managerial alternative or unresolved chronology gaps."
                ),
                "structured_row": _structured_row(entry, case_bundle=case_bundle),
            }
        )
    return {"view_id": "claimant_favorable_chronology", "entry_count": len(items), "items": items}


def _defense_view(entries: list[dict[str, Any]], *, case_bundle: dict[str, Any]) -> dict[str, Any]:
    """Create a defense-favorable chronology view from entries.

    Generates a chronology that emphasizes defense-favorable readings (ordinary
    managerial explanations) of each entry, including uncertainty notes and
    counterargument notes referencing claimant-side support.

    Args:
        entries: A list of chronology entry dictionaries.
        case_bundle: The case bundle dictionary for context.

    Returns:
        A view dictionary with view_id, entry_count, and items list.
    """
    items: list[dict[str, Any]] = []
    for entry in entries:
        managerial = _as_dict(_as_dict(entry.get("event_support_matrix")).get("ordinary_managerial_explanation"))
        _supportive_read_id, supportive_payload = _best_supportive_read(entry, case_bundle=case_bundle)
        entry_date = str(entry.get("date") or "")
        title = str(entry.get("title") or "")
        managerial_reason = str(managerial.get("reason") or "")
        uncertainty_note = (
            "This rendering remains bounded because some issue-linked support is still visible in the same event registry."
            if supportive_payload is not None
            else "No stronger issue-linked support is currently visible in this event."
        )
        items.append(
            {
                "chronology_id": str(entry.get("chronology_id") or ""),
                "date": entry_date,
                "favored_read_id": "ordinary_managerial_explanation",
                "statement": f"{entry_date}: {title}. Defense-favorable reading: {managerial_reason}".strip(),
                "uncertainty_note": uncertainty_note,
                "counterargument_note": (
                    str(supportive_payload.get("reason") or "")
                    if supportive_payload is not None
                    else "Selected claimant-side issue tracks are not directly advanced by this event."
                ),
                "structured_row": _structured_row(entry, case_bundle=case_bundle),
            }
        )
    return {"view_id": "defense_favorable_chronology", "entry_count": len(items), "items": items}


def _balanced_view(
    entries: list[dict[str, Any]],
    *,
    case_bundle: dict[str, Any],
    date_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a balanced timeline assessment view from entries and date gaps.

    Generates a view that weighs both issue-linked support and ordinary managerial
    explanations, including summary information about strongest inferences and limits.

    Args:
        entries: A list of chronology entry dictionaries.
        case_bundle: The case bundle dictionary for context.
        date_gaps: A list of date gap dictionaries to include in the assessment.

    Returns:
        A view dictionary with view_id, entry_count, items list, and summary
        containing strongest_timeline_inferences and strongest_limits.
    """
    items: list[dict[str, Any]] = []
    strongest_inferences: list[str] = []
    strongest_limits: list[str] = []
    for entry in entries:
        chronology_id = str(entry.get("chronology_id") or "")
        read_id, read_payload = _best_supportive_read(entry, case_bundle=case_bundle)
        managerial = _as_dict(_as_dict(entry.get("event_support_matrix")).get("ordinary_managerial_explanation"))
        if read_payload is not None:
            read_status = str(read_payload.get("status") or "")
            strongest_inferences.append(f"{chronology_id} supports {read_id.replace('_', ' ')} at {read_status} level.")
        else:
            strongest_inferences.append(f"{chronology_id} currently supports only a neutral timeline reading.")
        managerial_reason = str(managerial.get("reason") or "ordinary alternative remains live.")
        strongest_limits.append(f"{chronology_id} limit: {managerial_reason}")
        entry_date = str(entry.get("date") or "")
        title = str(entry.get("title") or "")
        items.append(
            {
                "chronology_id": chronology_id,
                "date": entry_date,
                "statement": (
                    f"{entry_date}: {title}. "
                    "Balanced view weighs issue-linked support against the still-live ordinary explanation."
                ).strip(),
                "primary_support_read_id": read_id,
                "primary_limit_read_id": "ordinary_managerial_explanation",
                "structured_row": _structured_row(entry, case_bundle=case_bundle),
            }
        )
    for gap in date_gaps[:2]:
        gap_id = str(gap.get("gap_id") or "")
        gap_days = int(gap.get("gap_days") or 0)
        strongest_limits.append(f"{gap_id} leaves {gap_days} day(s) unexplained between dated events.")
    return {
        "view_id": "balanced_timeline_assessment",
        "entry_count": len(items),
        "items": items,
        "summary": {
            "strongest_timeline_inferences": strongest_inferences[:4],
            "strongest_limits": strongest_limits[:4],
        },
    }


def _chronology_views(
    entries: list[dict[str, Any]],
    *,
    case_bundle: dict[str, Any],
    date_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate all chronology views for a set of entries.

    Creates and returns all four chronology views:
    - short_neutral_chronology
    - claimant_favorable_chronology
    - defense_favorable_chronology
    - balanced_timeline_assessment

    Args:
        entries: A list of chronology entry dictionaries.
        case_bundle: The case bundle dictionary for context.
        date_gaps: A list of date gap dictionaries for the balanced view.

    Returns:
        A dictionary mapping view IDs to their respective view dictionaries.
    """
    return {
        "short_neutral_chronology": _neutral_view(entries, case_bundle=case_bundle),
        "claimant_favorable_chronology": _claimant_view(entries, case_bundle=case_bundle),
        "defense_favorable_chronology": _defense_view(entries, case_bundle=case_bundle),
        "balanced_timeline_assessment": _balanced_view(entries, case_bundle=case_bundle, date_gaps=date_gaps),
    }
