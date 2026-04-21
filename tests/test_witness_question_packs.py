from __future__ import annotations

from src.witness_question_packs import build_witness_question_packs


def test_build_witness_question_packs_renders_decision_and_witness_prep() -> None:
    payload = build_witness_question_packs(
        actor_witness_map={
            "actor_map": {
                "actors": [
                    {
                        "actor_id": "actor-manager",
                        "name": "Morgan Manager",
                        "email": "manager@example.com",
                        "tied_event_ids": ["CHR-001"],
                    },
                    {
                        "actor_id": "actor-witness",
                        "name": "Jamie Witness",
                        "email": "jamie@example.com",
                        "tied_event_ids": ["CHR-002"],
                    },
                ]
            },
            "witness_map": {
                "primary_decision_makers": [
                    {"actor_id": "actor-manager", "name": "Morgan Manager", "email": "manager@example.com"}
                ],
                "potentially_independent_witnesses": [
                    {"actor_id": "actor-witness", "name": "Jamie Witness", "email": "jamie@example.com"}
                ],
                "high_value_record_holders": [
                    {"actor_id": "actor-manager", "name": "Morgan Manager", "email": "manager@example.com"}
                ],
            },
        },
        master_chronology={
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2026-02-10",
                    "title": "Complaint lodged",
                    "source_linkage": {"source_ids": ["email:uid-1"]},
                },
                {
                    "chronology_id": "CHR-002",
                    "date": "2026-02-11",
                    "title": "Follow-up meeting",
                    "source_linkage": {"source_ids": ["calendar:uid-2"]},
                },
            ]
        },
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-1",
                    "short_description": "Complaint email.",
                }
            ]
        },
        document_request_checklist={
            "groups": [
                {"group_id": "calendar_meeting_records", "title": "Calendar Invites", "items": [{"request": "Native invite"}]}
            ]
        },
    )

    assert payload is not None
    assert payload["version"] == "1"
    assert payload["pack_count"] == 3
    first_pack = payload["packs"][0]
    assert first_pack["pack_type"] == "decision_maker"
    assert first_pack["key_tied_events"][0]["chronology_id"] == "CHR-001"
    assert first_pack["documents_to_show_or_confirm"][0]["exhibit_id"] == "EXH-001"
    assert first_pack["suggested_questions"]
