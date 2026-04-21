from __future__ import annotations

from src.matter_workspace import build_matter_workspace


def test_build_matter_workspace_emits_stable_matter_entities_and_registry_refs() -> None:
    payload = build_matter_workspace(
        case_bundle={
            "bundle_id": "case-123",
            "scope": {
                "case_label": "HR-2026-04",
                "analysis_goal": "lawyer_briefing",
                "date_from": "2026-01-01",
                "date_to": "2026-03-31",
                "target_person": {"name": "Alex Example", "email": "alex@example.com", "role_hint": "employee"},
                "suspected_actors": [{"name": "Morgan Manager", "email": "morgan@example.com", "role_hint": "manager"}],
                "trigger_events": [
                    {
                        "trigger_type": "complaint",
                        "date": "2026-02-03",
                        "actor": {"name": "Alex Example", "email": "alex@example.com"},
                    }
                ],
                "employment_issue_frameworks": [
                    {
                        "issue_track": "retaliation_after_protected_event",
                        "title": "Retaliation After Protected or Participation Event",
                        "neutral_question": (
                            "Does the current record support a neutral concern that treatment worsened after a trigger event?"
                        ),
                    }
                ],
                "employment_issue_tag_payloads": [
                    {
                        "tag_id": "retaliation_massregelung",
                        "label": "Retaliation / Maßregelung",
                        "assignment_basis": "operator_supplied",
                    }
                ],
            },
        },
        multi_source_case_bundle={
            "summary": {"source_count": 1, "source_type_counts": {"email": 1}},
            "sources": [{"source_id": "email:uid-1"}],
        },
        matter_evidence_index={
            "version": "1",
            "rows": [{"exhibit_id": "EXH-001"}],
        },
        master_chronology={
            "version": "1",
            "entry_count": 1,
            "entries": [{"chronology_id": "CHR-001"}],
            "summary": {
                "date_range": {"first": "2026-02-03", "last": "2026-02-12"},
                "date_precision_counts": {"day": 1},
            },
        },
    )

    assert payload is not None
    assert payload["version"] == "1"
    assert payload["workspace_id"].startswith("workspace:")
    assert payload["matter"]["bundle_id"] == "case-123"
    assert payload["matter"]["target_person_entity_id"].startswith("person:")
    assert payload["evidence_registry"]["exhibit_ids"] == ["EXH-001"]
    assert payload["chronology_registry"]["entry_ids"] == ["CHR-001"]
    assert payload["registry_refs"] == {
        "case_bundle_ref": "case-123",
        "matter_evidence_index_version": "1",
        "master_chronology_version": "1",
    }

    parties = {party["email"]: party for party in payload["parties"]}
    assert parties["alex@example.com"]["roles_in_matter"] == ["target_person", "trigger_actor"]
    assert parties["morgan@example.com"]["roles_in_matter"] == ["suspected_actor"]
    assert payload["issue_registry"]["employment_issue_tracks"][0]["issue_track"] == "retaliation_after_protected_event"
    assert payload["issue_registry"]["employment_issue_tags"][0]["tag_id"] == "retaliation_massregelung"
