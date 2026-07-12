"""Public chronology entrypoint with stable helper imports."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .master_chronology_impl import (
    MASTER_CHRONOLOGY_VERSION,
    _as_dict,
    _as_list,
    _chronology_views,
    _citation_ids_by_support_key,
    _citation_ids_by_uid,
    _date_gaps,
    _date_precision,
    _event_support_matrix,
    _source_conflict_registry,
    _source_date_conflicts,
    _source_entry,
    _source_lookup,
    _timeline_fallback_entry,
    _trigger_entry,
)


def _adverse_action_entry(action: dict[str, Any]) -> dict[str, Any]:
    """Return one chronology entry for a supplied adverse-action event."""
    action_type = str(action.get("action_type") or "adverse_action")
    date = str(action.get("date") or "")
    description = f"Supplied alleged {action_type.replace('_', ' ')} event."
    return {
        "date": date,
        "date_precision": _date_precision(date),
        "entry_type": "adverse_action_event",
        "provenance_class": "scope_supplied",
        "title": action_type.replace("_", " ").capitalize(),
        "description": description,
        "source_linkage": {
            "source_ids": [],
            "source_types": [],
            "supporting_uids": [],
            "supporting_citation_ids": [],
            "evidence_handles": [],
            "document_locators": [],
            "source_evidence_status": "scope_only",
        },
    }


def _source_event_entry(
    *,
    source: dict[str, Any],
    event_record: dict[str, Any],
    case_bundle: dict[str, Any],
    citation_ids_by_uid: dict[str, list[str]],
) -> dict[str, Any]:
    """Return one chronology entry for a persisted extracted source event."""
    uid = _text(source, "uid")
    source_id = _text(source, "source_id")
    source_type = _text(source, "source_type")
    event_kind = _text(event_record, "event_kind") or "event"
    event_date = _text(event_record, "event_date") or _text(source, "date")
    provenance_payload = _event_provenance(event_record.get("provenance_json"))
    locator = _event_locator(event_record, provenance_payload)
    citation_ids = list(citation_ids_by_uid.get(uid, [])) if uid else []
    title = event_kind.replace("_", " ").capitalize()
    description = _text(event_record, "trigger_text") or f"Extracted {event_kind.replace('_', ' ')} signal from source text."
    return {
        "date": event_date,
        "date_precision": _date_precision(event_date),
        "entry_type": "source_event_extracted",
        "provenance_class": "source_derived",
        "title": title,
        "description": description,
        "people_involved": [_text(source, "sender_name"), _text(source, "sender_email")],
        "source_document": {"title": _text(source, "title") or title, "source_id": source_id, "source_type": source_type},
        "event_support_matrix": _event_support_matrix(
            case_bundle=case_bundle, entry_type="source_event", title=title, description=description
        ),
        "source_linkage": _event_source_linkage(source, uid, source_id, source_type, citation_ids, locator),
    }


def _text(payload: dict[str, Any], key: str) -> str:
    return str(payload.get(key) or "")


def _event_provenance(raw_provenance: object) -> dict[str, Any]:
    if isinstance(raw_provenance, dict):
        return dict(raw_provenance)
    if isinstance(raw_provenance, str) and raw_provenance.strip():
        try:
            parsed = json.loads(raw_provenance)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _event_locator(event_record: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "event_record",
        "event_key": str(event_record.get("event_key") or ""),
        "source_scope": str(event_record.get("source_scope") or provenance.get("source_scope") or ""),
        "surface_scope": str(event_record.get("surface_scope") or provenance.get("surface_scope") or ""),
        "segment_ordinal": event_record.get("segment_ordinal"),
        "char_start": event_record.get("char_start"),
        "char_end": event_record.get("char_end"),
    }


def _event_source_linkage(
    source: dict[str, Any], uid: str, source_id: str, source_type: str, citation_ids: list[str], locator: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source_ids": [source_id] if source_id else [],
        "source_types": [source_type] if source_type else [],
        "supporting_uids": [uid] if uid else [],
        "supporting_citation_ids": citation_ids,
        "evidence_handles": [str(source.get("source_id") or "")],
        "document_locators": [locator],
        "source_evidence_status": "direct_source_support",
    }


def build_master_chronology(
    *,
    case_bundle: dict[str, Any] | None,
    timeline: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
    finding_evidence_index: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a reusable chronology registry with source linkage and date precision."""
    if not isinstance(case_bundle, dict):
        return None

    source_bundle = _as_dict(multi_source_case_bundle)
    source_lookup = _source_lookup(source_bundle)
    source_links = [link for link in _as_list(source_bundle.get("source_links")) if isinstance(link, dict)]
    citation_ids_by_uid = _citation_ids_by_uid(_as_dict(finding_evidence_index))
    citation_ids_by_support_key = _citation_ids_by_support_key(_as_dict(finding_evidence_index))
    entries = _anchored_entries(source_bundle, source_lookup, source_links, case_bundle, citation_ids_by_support_key)
    entries.extend(_extracted_event_entries(source_bundle, case_bundle, citation_ids_by_uid))
    entries.extend(_trigger_entries(case_bundle))
    entries.extend(_adverse_entries(case_bundle))
    entries.extend(_timeline_entries(timeline, entries, case_bundle, citation_ids_by_uid))

    if not entries:
        return None

    entries.sort(
        key=lambda entry: (
            str(entry.get("date") or ""),
            str(entry.get("entry_type") or ""),
            str(entry.get("title") or ""),
        )
    )
    for index, entry in enumerate(entries, start=1):
        entry["chronology_id"] = f"CHR-{index:03d}"

    summary, primary_entries, scope_supplied_entries, date_gaps = _chronology_summary(entries, source_lookup, source_bundle)
    summary_entries = primary_entries or entries
    return {
        "version": MASTER_CHRONOLOGY_VERSION,
        "entry_count": len(entries),
        "primary_entry_count": len(primary_entries),
        "scope_supplied_entry_count": len(scope_supplied_entries),
        "summary": summary,
        "entries": entries,
        "primary_entries": primary_entries,
        "scope_supplied_entries": scope_supplied_entries,
        "views": _chronology_views(summary_entries, case_bundle=case_bundle, date_gaps=date_gaps),
    }


def _anchored_entries(source_bundle, source_lookup, source_links, case_bundle, citation_ids_by_support_key):
    entries = []
    for anchor in _as_list(source_bundle.get("chronology_anchors")):
        if not isinstance(anchor, dict):
            continue
        source = _as_dict(source_lookup.get(str(anchor.get("source_id") or "")))
        if source:
            entries.append(
                _source_entry(
                    anchor,
                    source,
                    case_bundle=case_bundle,
                    citation_ids_by_support_key=citation_ids_by_support_key,
                    source_lookup=source_lookup,
                    source_links=source_links,
                )
            )
    return entries


def _extracted_event_entries(source_bundle, case_bundle, citation_ids_by_uid):
    entries, seen = [], set()
    for source in _as_list(source_bundle.get("sources")):
        if isinstance(source, dict):
            _append_source_events(entries, seen, source, case_bundle, citation_ids_by_uid)
    return entries


def _append_source_events(entries, seen, source, case_bundle, citation_ids_by_uid):
    for event_record in _as_list(source.get("event_records")):
        if not isinstance(event_record, dict):
            continue
        event_key = str(event_record.get("event_key") or "")
        if event_key and event_key in seen:
            continue
        if event_key:
            seen.add(event_key)
        if str(event_record.get("event_date") or source.get("date") or "").strip():
            entries.append(
                _source_event_entry(
                    source=source, event_record=event_record, case_bundle=case_bundle, citation_ids_by_uid=citation_ids_by_uid
                )
            )


def _trigger_entries(case_bundle):
    entries, seen = [], set()
    for trigger_field in ("trigger_events", "asserted_rights_timeline"):
        for trigger_event in _as_list(_as_dict(case_bundle.get("scope")).get(trigger_field)):
            if not isinstance(trigger_event, dict) or not str(trigger_event.get("date") or "").strip():
                continue
            key = tuple(str(trigger_event.get(field) or "") for field in ("trigger_type", "date", "notes"))
            if key in seen:
                continue
            seen.add(key)
            entry = _trigger_entry(trigger_event)
            entry["event_support_matrix"] = _support_matrix(case_bundle, "trigger_event", entry)
            entries.append(entry)
    return entries


def _adverse_entries(case_bundle):
    entries = []
    for action in _as_list(_as_dict(case_bundle.get("scope")).get("alleged_adverse_actions")):
        if isinstance(action, dict) and str(action.get("date") or "").strip():
            entry = _adverse_action_entry(action)
            entry["event_support_matrix"] = _support_matrix(case_bundle, "adverse_action_event", entry)
            entries.append(entry)
    return entries


def _support_matrix(case_bundle, entry_type, entry):
    return _event_support_matrix(
        case_bundle=case_bundle,
        entry_type=entry_type,
        title=str(entry.get("title") or ""),
        description=str(entry.get("description") or ""),
    )


def _timeline_entries(timeline, entries, case_bundle, citation_ids_by_uid):
    seen_uids = {
        str(uid)
        for entry in entries
        for uid in _as_list(_as_dict(entry.get("source_linkage")).get("supporting_uids"))
        if str(uid).strip()
    }
    output = []
    for event in _as_list(_as_dict(timeline).get("events")):
        if not isinstance(event, dict):
            continue
        uid = str(event.get("uid") or "")
        if str(event.get("date") or "").strip() and not (uid and uid in seen_uids):
            output.append(_timeline_fallback_entry(event, case_bundle=case_bundle, citation_ids_by_uid=citation_ids_by_uid))
    return output


def _chronology_summary(entries, source_lookup, source_bundle):
    date_gaps = _date_gaps(entries)
    sequence_breaks = _source_date_conflicts(entries)
    source_conflict_registry = _source_conflict_registry(
        entries=entries, source_lookup=source_lookup, multi_source_case_bundle=source_bundle, sequence_breaks=sequence_breaks
    )
    entry_type_counts = _field_counts(entries, "entry_type")
    provenance_class_counts = _field_counts(entries, "provenance_class")
    date_precision_counts = _field_counts(entries, "date_precision")
    event_read_status_counts = _event_read_status_counts(entries)
    source_type_counts = _source_type_counts(entries)
    source_evidence_status_counts = _source_evidence_status_counts(entries)
    primary_entries, scope_supplied_entries = _partition_entries(entries)
    summary_entries = primary_entries or entries
    dated_entries = _dated_values(summary_entries)
    combined_dated_entries = _dated_values(entries)

    return (
        {
            "entry_type_counts": _nonempty_counts(entry_type_counts),
            "provenance_class_counts": _nonempty_counts(provenance_class_counts),
            "date_precision_counts": _nonempty_counts(date_precision_counts),
            "event_read_status_counts": _nonempty_counts(event_read_status_counts),
            "source_type_counts": _nonempty_counts(source_type_counts),
            "source_evidence_status_counts": _nonempty_counts(source_evidence_status_counts),
            "source_linked_entry_count": _source_linked_count(entries),
            "date_range": _date_range(dated_entries),
            "combined_date_range": _date_range(combined_dated_entries),
            "date_gap_count": len(date_gaps),
            "largest_gap_days": _largest_gap(date_gaps),
            "date_gaps_and_unexplained_sequences": date_gaps,
            "sequence_breaks_and_contradictions": sequence_breaks,
            "source_conflict_registry": source_conflict_registry,
        },
        primary_entries,
        scope_supplied_entries,
        date_gaps,
    )


def _field_counts(entries, field):
    return Counter(str(entry.get(field) or "") for entry in entries)


def _event_read_status_counts(entries):
    values = []
    for entry in entries:
        for read_id, payload in _as_dict(entry.get("event_support_matrix")).items():
            status = str(_as_dict(payload).get("status") or "") if isinstance(payload, dict) else ""
            if read_id and status:
                values.append(f"{read_id}:{status}")
    return Counter(values)


def _source_type_counts(entries):
    return Counter(
        str(source_type)
        for entry in entries
        for source_type in _as_list(_as_dict(entry.get("source_linkage")).get("source_types"))
        if str(source_type).strip()
    )


def _source_evidence_status(entry):
    return str(_as_dict(entry.get("source_linkage")).get("source_evidence_status") or "")


def _source_evidence_status_counts(entries):
    return Counter(status for entry in entries if (status := _source_evidence_status(entry)))


def _partition_entries(entries):
    primary, scope = [], []
    for entry in entries:
        (scope if _source_evidence_status(entry) == "scope_only" else primary).append(entry)
    return primary, scope


def _dated_values(entries):
    return [date for entry in entries if (date := str(entry.get("date") or "").strip())]


def _nonempty_counts(counts):
    return {key: count for key, count in counts.items() if key}


def _source_linked_count(entries):
    return sum(1 for entry in entries if _as_list(_as_dict(entry.get("source_linkage")).get("source_ids")))


def _date_range(dates):
    return {"first": dates[0] if dates else "", "last": dates[-1] if dates else ""}


def _largest_gap(gaps):
    return max((int(gap.get("gap_days") or 0) for gap in gaps), default=0)
