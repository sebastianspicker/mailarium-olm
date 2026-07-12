"""Witness interview prep packs derived from shared legal-support registries."""
# pylint: disable=too-many-arguments,too-many-locals

from __future__ import annotations

from typing import Any

from ._utils import _as_dict, _as_list, _compact, _first_nonempty

WITNESS_QUESTION_PACKS_VERSION = "1"


def _chronology_lookup(master_chronology: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Build a lookup dict of chronology entries keyed by chronology_id."""
    return {
        str(entry.get("chronology_id") or ""): entry
        for entry in _as_list(_as_dict(master_chronology).get("entries"))
        if isinstance(entry, dict) and _compact(entry.get("chronology_id"))
    }


def _evidence_lookup(matter_evidence_index: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Build a lookup dict of evidence entries keyed by exhibit_id."""
    return {
        str(entry.get("exhibit_id") or ""): entry
        for entry in _as_list(_as_dict(matter_evidence_index).get("rows"))
        if isinstance(entry, dict) and _compact(entry.get("exhibit_id"))
    }


def _actor_lookup(actor_map: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Build a lookup dict of actor entries keyed by actor_id."""
    return {
        str(entry.get("actor_id") or ""): entry
        for entry in _as_list(_as_dict(actor_map).get("actors"))
        if isinstance(entry, dict) and _compact(entry.get("actor_id"))
    }


def _pack(
    *,
    pack_id: str,
    actor_id: str,
    actor_name: str,
    actor_email: str,
    pack_type: str,
    likely_knowledge_areas: list[str],
    key_tied_events: list[dict[str, Any]],
    documents_to_show_or_confirm: list[dict[str, Any]],
    factual_gaps_to_probe: list[str],
    caution_notes: list[str],
    suggested_questions: list[str],
) -> dict[str, Any]:
    """Construct a witness question pack dictionary from the given components."""
    return {
        "pack_id": pack_id,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "actor_email": actor_email,
        "pack_type": pack_type,
        "likely_knowledge_areas": [item for item in likely_knowledge_areas if _compact(item)],
        "key_tied_events": key_tied_events,
        "documents_to_show_or_confirm": documents_to_show_or_confirm,
        "factual_gaps_to_probe": [item for item in factual_gaps_to_probe if _compact(item)],
        "caution_notes": [item for item in caution_notes if _compact(item)],
        "suggested_questions": [item for item in suggested_questions if _compact(item)],
        "non_leading_style": True,
    }


def build_witness_question_packs(
    *,
    actor_witness_map: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
    matter_evidence_index: dict[str, Any] | None,
    document_request_checklist: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return practical witness interview prep packs from shared registries."""
    actor_map = _as_dict(actor_witness_map).get("actor_map")
    witness_map = _as_dict(actor_witness_map).get("witness_map")
    actor_by_id = _actor_lookup(actor_map)
    chronology_by_id = _chronology_lookup(master_chronology)
    evidence_by_id = _evidence_lookup(matter_evidence_index)
    if not actor_by_id and not witness_map:
        return None
    groups = _dict_rows(_as_dict(document_request_checklist).get("groups"))
    packs: list[dict[str, Any]] = []
    context = (actor_by_id, chronology_by_id, evidence_by_id, groups)
    _append_witness_rows(packs, _as_dict(witness_map).get("primary_decision_makers"), "decision_maker", context)
    _append_witness_rows(packs, _as_dict(witness_map).get("potentially_independent_witnesses"), "independent_witness", context)
    _append_witness_rows(packs, _as_dict(witness_map).get("high_value_record_holders"), "record_holder", context)
    if not packs:
        return None
    return {
        "version": WITNESS_QUESTION_PACKS_VERSION,
        "pack_count": len(packs),
        "summary": {
            "decision_maker_pack_count": _pack_count(packs, "decision_maker"),
            "independent_witness_pack_count": _pack_count(packs, "independent_witness"),
            "record_holder_pack_count": _pack_count(packs, "record_holder"),
        },
        "packs": packs,
    }


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [row for row in _as_list(value) if isinstance(row, dict)]


def _append_witness_rows(packs, rows, pack_type, context) -> None:
    for entry in _dict_rows(rows):
        _append_pack(packs, entry, pack_type, *context)


def _append_pack(packs, entry, pack_type, actor_by_id, chronology_by_id, evidence_by_id, checklist_groups) -> None:
    actor_id = _compact(entry.get("actor_id"))
    actor = _as_dict(actor_by_id.get(actor_id))
    actor_name = _first_nonempty(entry.get("name"), actor.get("name"), actor.get("email"))
    actor_email = _first_nonempty(entry.get("email"), actor.get("email"))
    tied_event_ids = [str(item) for item in _as_list(actor.get("tied_event_ids")) if _compact(item)]
    key_events = _key_events(tied_event_ids, chronology_by_id)
    knowledge, cautions = _knowledge_and_cautions(pack_type)
    document_ids = _document_ids(tied_event_ids, chronology_by_id, evidence_by_id)
    documents = _documents_to_show(document_ids, evidence_by_id)
    gaps = _factual_gaps(checklist_groups, key_events)
    questions = _suggested_questions(pack_type, actor_name, key_events, documents)
    packs.append(
        _pack(
            pack_id=f"{pack_type}:{actor_id or len(packs) + 1}",
            actor_id=actor_id,
            actor_name=actor_name,
            actor_email=actor_email,
            pack_type=pack_type,
            likely_knowledge_areas=knowledge,
            key_tied_events=key_events,
            documents_to_show_or_confirm=documents,
            factual_gaps_to_probe=gaps[:3],
            caution_notes=cautions,
            suggested_questions=questions[:4],
        )
    )


def _key_events(ids, chronology_by_id):
    events = []
    for chronology_id in ids[:3]:
        if chronology_id not in chronology_by_id:
            continue
        row = _as_dict(chronology_by_id.get(chronology_id))
        events.append(
            {
                "chronology_id": chronology_id,
                "date": str(row.get("date") or ""),
                "title": _first_nonempty(row.get("title"), row.get("description")),
            }
        )
    return events


def _knowledge_and_cautions(pack_type):
    if pack_type == "decision_maker":
        return [
            "Decision path, rationale, and who approved or influenced the step.",
            "Whether comparator treatment differed under the same policy or decision-maker.",
        ], ["Test whether the witness is minimizing discretion or redistributing responsibility."]
    if pack_type == "independent_witness":
        return [
            "What the witness directly observed in meetings, messages, or follow-up conduct.",
            "Whether the witness saw omissions, changed attendance, or inconsistent summaries.",
        ], ["Separate firsthand observation from later retellings or team narrative."]
    return [
        "Where the underlying records are stored, how they were created, and whether edits or retention rules apply.",
        "Which native exports or metadata would confirm chronology or participation steps.",
    ], ["Pin down record provenance, retention windows, and whether metadata can still be recovered."]


def _document_ids(tied_event_ids, chronology_by_id, evidence_by_id):
    document_ids = []
    for chronology_id in tied_event_ids:
        entry = _as_dict(chronology_by_id.get(chronology_id))
        for source_id in _as_list(_as_dict(entry.get("source_linkage")).get("source_ids")):
            for exhibit_id, exhibit in evidence_by_id.items():
                if str(exhibit.get("source_id") or "") == str(source_id) and exhibit_id not in document_ids:
                    document_ids.append(exhibit_id)
    return document_ids


def _documents_to_show(document_ids, evidence_by_id):
    rows = []
    for exhibit_id in document_ids[:3]:
        if exhibit_id in evidence_by_id:
            evidence = _as_dict(evidence_by_id.get(exhibit_id))
            rows.append(
                {
                    "exhibit_id": exhibit_id,
                    "summary": _first_nonempty(evidence.get("short_description"), evidence.get("why_it_matters")),
                }
            )
    return rows


def _factual_gaps(groups, key_events):
    gaps = []
    for group in groups[:2]:
        items = _as_list(group.get("items"))
        request = _as_dict(items[0]).get("request") if items else ""
        text = _first_nonempty(request, group.get("title"))
        if text:
            gaps.append(text)
    if not key_events:
        gaps.append("No strongly tied chronology events are yet linked to this witness in the current registry.")
    return gaps


def _suggested_questions(pack_type, actor_name, key_events, documents):
    questions = [
        f"Please describe your role in relation to {actor_name or 'the relevant events'} and what you directly observed.",
        f"What happened around {key_events[0]['date']} and who was involved?"
        if key_events
        else "Which concrete events or communications do you personally recall from this matter?",
        f"Can you explain the context for {documents[0]['exhibit_id']} and whether it reflects the full picture?"
        if documents
        else "Which records or notes would best confirm your account, and where are they kept?",
    ]
    if pack_type == "record_holder":
        questions.append("What retention or overwrite risks affect these records, and can native metadata still be exported?")
    else:
        questions.append("Is there anything important that was omitted from the written record or later summarized differently?")
    return questions


def _pack_count(packs, pack_type):
    return sum(1 for item in packs if item.get("pack_type") == pack_type)
