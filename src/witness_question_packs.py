"""Witness interview prep packs derived from shared legal-support registries."""

from __future__ import annotations

from typing import Any

WITNESS_QUESTION_PACKS_VERSION = "1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _chronology_lookup(master_chronology: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("chronology_id") or ""): entry
        for entry in _as_list(_as_dict(master_chronology).get("entries"))
        if isinstance(entry, dict) and _compact(entry.get("chronology_id"))
    }


def _evidence_lookup(matter_evidence_index: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("exhibit_id") or ""): entry
        for entry in _as_list(_as_dict(matter_evidence_index).get("rows"))
        if isinstance(entry, dict) and _compact(entry.get("exhibit_id"))
    }


def _actor_lookup(actor_map: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
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

    checklist_groups = [row for row in _as_list(_as_dict(document_request_checklist).get("groups")) if isinstance(row, dict)]
    packs: list[dict[str, Any]] = []

    def append_pack(entry: dict[str, Any], pack_type: str) -> None:
        actor_id = _compact(entry.get("actor_id"))
        actor = _as_dict(actor_by_id.get(actor_id))
        actor_name = _first_nonempty(entry.get("name"), actor.get("name"), actor.get("email"))
        actor_email = _first_nonempty(entry.get("email"), actor.get("email"))
        tied_event_ids = [str(item) for item in _as_list(actor.get("tied_event_ids")) if _compact(item)]
        key_events = [
            {
                "chronology_id": chronology_id,
                "date": str(_as_dict(chronology_by_id.get(chronology_id)).get("date") or ""),
                "title": _first_nonempty(
                    _as_dict(chronology_by_id.get(chronology_id)).get("title"),
                    _as_dict(chronology_by_id.get(chronology_id)).get("description"),
                ),
            }
            for chronology_id in tied_event_ids[:3]
            if chronology_id in chronology_by_id
        ]
        likely_knowledge_areas: list[str] = []
        caution_notes: list[str] = []
        if pack_type == "decision_maker":
            likely_knowledge_areas.extend(
                [
                    "Decision path, rationale, and who approved or influenced the step.",
                    "Whether comparator treatment differed under the same policy or decision-maker.",
                ]
            )
            caution_notes.append("Test whether the witness is minimizing discretion or redistributing responsibility.")
        elif pack_type == "independent_witness":
            likely_knowledge_areas.extend(
                [
                    "What the witness directly observed in meetings, messages, or follow-up conduct.",
                    "Whether the witness saw omissions, changed attendance, or inconsistent summaries.",
                ]
            )
            caution_notes.append("Separate firsthand observation from later retellings or team narrative.")
        else:
            likely_knowledge_areas.extend(
                [
                    "Where the underlying records are stored, how they were created, and whether edits or retention rules apply.",
                    "Which native exports or metadata would confirm chronology or participation steps.",
                ]
            )
            caution_notes.append("Pin down record provenance, retention windows, and whether metadata can still be recovered.")

        document_ids: list[str] = []
        for chronology_id in tied_event_ids:
            chronology_entry = _as_dict(chronology_by_id.get(chronology_id))
            for source_id in _as_list(_as_dict(chronology_entry.get("source_linkage")).get("source_ids")):
                source_id = str(source_id)
                for exhibit_id, exhibit in evidence_by_id.items():
                    if str(exhibit.get("source_id") or "") == source_id and exhibit_id not in document_ids:
                        document_ids.append(exhibit_id)
        documents_to_show = [
            {
                "exhibit_id": exhibit_id,
                "summary": _first_nonempty(
                    _as_dict(evidence_by_id.get(exhibit_id)).get("short_description"),
                    _as_dict(evidence_by_id.get(exhibit_id)).get("why_it_matters"),
                ),
            }
            for exhibit_id in document_ids[:3]
            if exhibit_id in evidence_by_id
        ]

        factual_gaps = [
            _first_nonempty(
                _as_dict(_as_list(group.get("items"))[0]).get("request") if _as_list(group.get("items")) else "",
                group.get("title"),
            )
            for group in checklist_groups[:2]
            if _first_nonempty(
                _as_dict(_as_list(group.get("items"))[0]).get("request") if _as_list(group.get("items")) else "",
                group.get("title"),
            )
        ]
        if not key_events:
            factual_gaps.append("No strongly tied chronology events are yet linked to this witness in the current registry.")

        suggested_questions = [
            f"Please describe your role in relation to {actor_name or 'the relevant events'} and what you directly observed.",
            (
                f"What happened around {key_events[0]['date']} and who was involved?"
                if key_events
                else "Which concrete events or communications do you personally recall from this matter?"
            ),
            (
                f"Can you explain the context for {documents_to_show[0]['exhibit_id']} and whether it reflects the full picture?"
                if documents_to_show
                else "Which records or notes would best confirm your account, and where are they kept?"
            ),
        ]
        if pack_type == "record_holder":
            suggested_questions.append(
                "What retention or overwrite risks affect these records, and can native metadata still be exported?"
            )
        else:
            suggested_questions.append(
                "Is there anything important that was omitted from the written record or later summarized differently?"
            )

        packs.append(
            _pack(
                pack_id=f"{pack_type}:{actor_id or len(packs) + 1}",
                actor_id=actor_id,
                actor_name=actor_name,
                actor_email=actor_email,
                pack_type=pack_type,
                likely_knowledge_areas=likely_knowledge_areas,
                key_tied_events=key_events,
                documents_to_show_or_confirm=documents_to_show,
                factual_gaps_to_probe=factual_gaps[:3],
                caution_notes=caution_notes,
                suggested_questions=suggested_questions[:4],
            )
        )

    for entry in _as_list(_as_dict(witness_map).get("primary_decision_makers")):
        if isinstance(entry, dict):
            append_pack(entry, "decision_maker")
    for entry in _as_list(_as_dict(witness_map).get("potentially_independent_witnesses")):
        if isinstance(entry, dict):
            append_pack(entry, "independent_witness")
    for entry in _as_list(_as_dict(witness_map).get("high_value_record_holders")):
        if isinstance(entry, dict):
            append_pack(entry, "record_holder")

    if not packs:
        return None

    return {
        "version": WITNESS_QUESTION_PACKS_VERSION,
        "pack_count": len(packs),
        "summary": {
            "decision_maker_pack_count": sum(1 for item in packs if item.get("pack_type") == "decision_maker"),
            "independent_witness_pack_count": sum(1 for item in packs if item.get("pack_type") == "independent_witness"),
            "record_holder_pack_count": sum(1 for item in packs if item.get("pack_type") == "record_holder"),
        },
        "packs": packs,
    }
