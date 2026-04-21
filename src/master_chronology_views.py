"""Chronology rendering views over the shared entry registry."""

from __future__ import annotations

from typing import Any

from .master_chronology_common import _as_dict, _best_supportive_read


def _issue_categories(entry: dict[str, Any]) -> list[str]:
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
    _read_id, read_payload = _best_supportive_read(entry, case_bundle=case_bundle)
    if read_payload is not None:
        return str(read_payload.get("reason") or "")
    managerial = _as_dict(_as_dict(entry.get("event_support_matrix")).get("ordinary_managerial_explanation"))
    return str(managerial.get("reason") or "Primarily a chronology anchor with no stronger issue-linked support selected.")


def _structured_row(entry: dict[str, Any], *, case_bundle: dict[str, Any]) -> dict[str, Any]:
    matrix = _as_dict(entry.get("event_support_matrix"))
    source_linkage = _as_dict(entry.get("source_linkage"))
    source_document = _as_dict(entry.get("source_document"))
    prevention_statuses = [
        str(_as_dict(matrix.get(read_id)).get("status") or "")
        for read_id in ("prevention_duty_gap", "participation_duty_gap")
        if str(_as_dict(matrix.get(read_id)).get("status") or "")
    ]
    prevention_status = (
        "direct_event_support"
        if "direct_event_support" in prevention_statuses
        else "contextual_support_only"
        if "contextual_support_only" in prevention_statuses
        else prevention_statuses[0]
        if prevention_statuses
        else "not_signaled"
    )
    return {
        "exact_or_approximate_date": {
            "value": str(entry.get("date") or ""),
            "precision": str(entry.get("date_precision") or ""),
        },
        "event_description": str(entry.get("description") or entry.get("title") or ""),
        "people_involved": [str(item) for item in entry.get("people_involved", []) if str(item).strip()],
        "source_document": {
            "title": str(source_document.get("title") or entry.get("title") or ""),
            "source_ids": [str(item) for item in source_linkage.get("source_ids", []) if str(item).strip()],
            "source_types": [str(item) for item in source_linkage.get("source_types", []) if str(item).strip()],
        },
        "issue_category": _issue_categories(entry),
        "significance_to_case": _significance(entry, case_bundle=case_bundle),
        "supports": {
            "disability_related_disadvantage": str(
                _as_dict(matrix.get("disability_disadvantage")).get("status") or "not_signaled"
            ),
            "retaliation": str(_as_dict(matrix.get("retaliation_after_protected_event")).get("status") or "not_signaled"),
            "eingruppierung": str(_as_dict(matrix.get("eingruppierung_dispute")).get("status") or "not_signaled"),
            "prevention_or_participation_failures": prevention_status,
            "ordinary_managerial_explanation": str(
                _as_dict(matrix.get("ordinary_managerial_explanation")).get("status") or "not_signaled"
            ),
        },
    }


def _neutral_view(entries: list[dict[str, Any]], *, case_bundle: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "short_neutral_chronology": _neutral_view(entries, case_bundle=case_bundle),
        "claimant_favorable_chronology": _claimant_view(entries, case_bundle=case_bundle),
        "defense_favorable_chronology": _defense_view(entries, case_bundle=case_bundle),
        "balanced_timeline_assessment": _balanced_view(entries, case_bundle=case_bundle, date_gaps=date_gaps),
    }
