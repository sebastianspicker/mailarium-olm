"""Public chronology entrypoint with stable helper imports."""

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
    uid = str(source.get("uid") or "")
    source_id = str(source.get("source_id") or "")
    source_type = str(source.get("source_type") or "")
    event_kind = str(event_record.get("event_kind") or "event")
    trigger_text = str(event_record.get("trigger_text") or "")
    event_date = str(event_record.get("event_date") or source.get("date") or "")
    provenance_payload: dict[str, Any] = {}
    raw_provenance = event_record.get("provenance_json")
    if isinstance(raw_provenance, dict):
        provenance_payload = dict(raw_provenance)
    elif isinstance(raw_provenance, str) and raw_provenance.strip():
        try:
            parsed = json.loads(raw_provenance)
            if isinstance(parsed, dict):
                provenance_payload = parsed
        except json.JSONDecodeError:
            provenance_payload = {}
    locator = {
        "kind": "event_record",
        "event_key": str(event_record.get("event_key") or ""),
        "source_scope": str(event_record.get("source_scope") or provenance_payload.get("source_scope") or ""),
        "surface_scope": str(event_record.get("surface_scope") or provenance_payload.get("surface_scope") or ""),
        "segment_ordinal": event_record.get("segment_ordinal"),
        "char_start": event_record.get("char_start"),
        "char_end": event_record.get("char_end"),
    }
    citation_ids = list(citation_ids_by_uid.get(uid, [])) if uid else []
    title = event_kind.replace("_", " ").capitalize()
    description = trigger_text or f"Extracted {event_kind.replace('_', ' ')} signal from source text."
    return {
        "date": event_date,
        "date_precision": _date_precision(event_date),
        "entry_type": "source_event_extracted",
        "provenance_class": "source_derived",
        "title": title,
        "description": description,
        "people_involved": [
            str(source.get("sender_name") or ""),
            str(source.get("sender_email") or ""),
        ],
        "source_document": {
            "title": str(source.get("title") or title),
            "source_id": source_id,
            "source_type": source_type,
        },
        "event_support_matrix": _event_support_matrix(
            case_bundle=case_bundle,
            entry_type="source_event",
            title=title,
            description=description,
        ),
        "source_linkage": {
            "source_ids": [source_id] if source_id else [],
            "source_types": [source_type] if source_type else [],
            "supporting_uids": [uid] if uid else [],
            "supporting_citation_ids": citation_ids,
            "evidence_handles": [str(source.get("source_id") or "")],
            "document_locators": [locator],
            "source_evidence_status": "direct_source_support",
        },
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
    entries: list[dict[str, Any]] = []

    for anchor in _as_list(source_bundle.get("chronology_anchors")):
        if not isinstance(anchor, dict):
            continue
        source_id = str(anchor.get("source_id") or "")
        source = _as_dict(source_lookup.get(source_id))
        if not source:
            continue
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

    seen_extracted_event_keys: set[str] = set()
    for source in _as_list(source_bundle.get("sources")):
        if not isinstance(source, dict):
            continue
        for event_record in _as_list(source.get("event_records")):
            if not isinstance(event_record, dict):
                continue
            event_key = str(event_record.get("event_key") or "")
            if event_key and event_key in seen_extracted_event_keys:
                continue
            if event_key:
                seen_extracted_event_keys.add(event_key)
            event_date = str(event_record.get("event_date") or source.get("date") or "").strip()
            if not event_date:
                continue
            entries.append(
                _source_event_entry(
                    source=source,
                    event_record=event_record,
                    case_bundle=case_bundle,
                    citation_ids_by_uid=citation_ids_by_uid,
                )
            )

    seen_trigger_keys: set[tuple[str, str, str]] = set()
    for trigger_field in ("trigger_events", "asserted_rights_timeline"):
        for trigger_event in _as_list(_as_dict(case_bundle.get("scope")).get(trigger_field)):
            if not isinstance(trigger_event, dict) or not str(trigger_event.get("date") or "").strip():
                continue
            trigger_key = (
                str(trigger_event.get("trigger_type") or ""),
                str(trigger_event.get("date") or ""),
                str(trigger_event.get("notes") or ""),
            )
            if trigger_key in seen_trigger_keys:
                continue
            seen_trigger_keys.add(trigger_key)
            trigger_entry = _trigger_entry(trigger_event)
            trigger_entry["event_support_matrix"] = _event_support_matrix(
                case_bundle=case_bundle,
                entry_type="trigger_event",
                title=str(trigger_entry.get("title") or ""),
                description=str(trigger_entry.get("description") or ""),
            )
            entries.append(trigger_entry)

    for adverse_action in _as_list(_as_dict(case_bundle.get("scope")).get("alleged_adverse_actions")):
        if not isinstance(adverse_action, dict) or not str(adverse_action.get("date") or "").strip():
            continue
        action_entry = _adverse_action_entry(adverse_action)
        action_entry["event_support_matrix"] = _event_support_matrix(
            case_bundle=case_bundle,
            entry_type="adverse_action_event",
            title=str(action_entry.get("title") or ""),
            description=str(action_entry.get("description") or ""),
        )
        entries.append(action_entry)

    seen_uids = {
        str(uid)
        for entry in entries
        for uid in _as_list(_as_dict(entry.get("source_linkage")).get("supporting_uids"))
        if str(uid).strip()
    }
    for event in _as_list(_as_dict(timeline).get("events")):
        if not isinstance(event, dict):
            continue
        uid = str(event.get("uid") or "")
        if not str(event.get("date") or "").strip() or (uid and uid in seen_uids):
            continue
        entries.append(_timeline_fallback_entry(event, case_bundle=case_bundle, citation_ids_by_uid=citation_ids_by_uid))

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

    date_gaps = _date_gaps(entries)
    sequence_breaks = _source_date_conflicts(entries)
    source_conflict_registry = _source_conflict_registry(
        entries=entries,
        source_lookup=source_lookup,
        multi_source_case_bundle=source_bundle,
        sequence_breaks=sequence_breaks,
    )
    entry_type_counts = Counter(str(entry.get("entry_type") or "") for entry in entries)
    provenance_class_counts = Counter(str(entry.get("provenance_class") or "") for entry in entries)
    date_precision_counts = Counter(str(entry.get("date_precision") or "") for entry in entries)
    event_read_status_counts = Counter(
        f"{read_id}:{_as_dict(read_payload).get('status') or ''}"
        for entry in entries
        for read_id, read_payload in _as_dict(entry.get("event_support_matrix")).items()
        if read_id and isinstance(read_payload, dict) and str(_as_dict(read_payload).get("status") or "")
    )
    source_type_counts = Counter(
        str(source_type)
        for entry in entries
        for source_type in _as_list(_as_dict(entry.get("source_linkage")).get("source_types"))
        if str(source_type).strip()
    )
    source_evidence_status_counts = Counter(
        str(_as_dict(entry.get("source_linkage")).get("source_evidence_status") or "")
        for entry in entries
        if str(_as_dict(entry.get("source_linkage")).get("source_evidence_status") or "")
    )
    primary_entries = [
        entry
        for entry in entries
        if str(_as_dict(entry.get("source_linkage")).get("source_evidence_status") or "") != "scope_only"
    ]
    scope_supplied_entries = [
        entry
        for entry in entries
        if str(_as_dict(entry.get("source_linkage")).get("source_evidence_status") or "") == "scope_only"
    ]
    summary_entries = primary_entries or entries
    dated_entries = [str(entry.get("date") or "") for entry in summary_entries if str(entry.get("date") or "").strip()]
    combined_dated_entries = [str(entry.get("date") or "") for entry in entries if str(entry.get("date") or "").strip()]

    return {
        "version": MASTER_CHRONOLOGY_VERSION,
        "entry_count": len(entries),
        "primary_entry_count": len(primary_entries),
        "scope_supplied_entry_count": len(scope_supplied_entries),
        "summary": {
            "entry_type_counts": {key: count for key, count in entry_type_counts.items() if key},
            "provenance_class_counts": {key: count for key, count in provenance_class_counts.items() if key},
            "date_precision_counts": {key: count for key, count in date_precision_counts.items() if key},
            "event_read_status_counts": {key: count for key, count in event_read_status_counts.items() if key},
            "source_type_counts": {key: count for key, count in source_type_counts.items() if key},
            "source_evidence_status_counts": {key: count for key, count in source_evidence_status_counts.items() if key},
            "source_linked_entry_count": sum(
                1 for entry in entries if _as_list(_as_dict(entry.get("source_linkage")).get("source_ids"))
            ),
            "date_range": {
                "first": dated_entries[0] if dated_entries else "",
                "last": dated_entries[-1] if dated_entries else "",
            },
            "combined_date_range": {
                "first": combined_dated_entries[0] if combined_dated_entries else "",
                "last": combined_dated_entries[-1] if combined_dated_entries else "",
            },
            "date_gap_count": len(date_gaps),
            "largest_gap_days": max((int(gap.get("gap_days") or 0) for gap in date_gaps), default=0),
            "date_gaps_and_unexplained_sequences": date_gaps,
            "sequence_breaks_and_contradictions": sequence_breaks,
            "source_conflict_registry": source_conflict_registry,
        },
        "entries": entries,
        "primary_entries": primary_entries,
        "scope_supplied_entries": scope_supplied_entries,
        "views": _chronology_views(summary_entries, case_bundle=case_bundle, date_gaps=date_gaps),
    }
