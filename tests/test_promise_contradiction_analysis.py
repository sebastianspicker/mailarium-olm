from __future__ import annotations

from src.promise_contradiction_analysis import build_promise_contradiction_analysis


def test_build_promise_contradiction_analysis_surfaces_promises_omissions_and_contradictions() -> None:
    payload = build_promise_contradiction_analysis(
        case_bundle={"scope": {"case_label": "case-a"}},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "meeting:uid-1:meeting_data",
                    "source_type": "meeting_note",
                    "uid": "uid-1",
                    "actor_id": "actor-manager",
                    "title": "Review meeting",
                    "snippet": "We agreed to include SBV and will send the meeting minutes by Friday.",
                    "date": "2026-03-01",
                    "chronology_anchor": {"date": "2026-03-01"},
                    "source_weighting": {"text_available": True},
                },
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "uid": "uid-1",
                    "actor_id": "actor-manager",
                    "title": "Follow-up",
                    "snippet": "Minutes attached. SBV was not included in this step.",
                    "date": "2026-03-03",
                    "chronology_anchor": {"date": "2026-03-03"},
                    "source_weighting": {"text_available": True},
                },
                {
                    "source_id": "note_record:uid-2:summary.txt",
                    "source_type": "note_record",
                    "uid": "uid-2",
                    "actor_id": "actor-manager",
                    "title": "Internal summary",
                    "snippet": "We will review the grading request and send a written explanation.",
                    "date": "2026-03-04",
                    "chronology_anchor": {"date": "2026-03-04"},
                    "source_weighting": {"text_available": True},
                },
                {
                    "source_id": "email:uid-3",
                    "source_type": "email",
                    "uid": "uid-3",
                    "actor_id": "actor-manager",
                    "title": "Later update",
                    "snippet": "Short status update without any written explanation yet.",
                    "date": "2026-03-06",
                    "chronology_anchor": {"date": "2026-03-06"},
                    "source_weighting": {"text_available": True},
                },
            ]
        },
        master_chronology={
            "summary": {
                "sequence_breaks_and_contradictions": [
                    {
                        "source_id": "note_record:uid-2:summary.txt",
                        "uid": "uid-2",
                        "source_recorded_date": "2026-03-10",
                        "event_date": "2026-03-04",
                        "summary": "Document text suggests an earlier event date than the recorded source date.",
                    }
                ]
            }
        },
    )

    assert payload is not None
    assert payload["version"] == "1"
    assert payload["summary"]["promise_action_row_count"] >= 1
    assert payload["summary"]["omission_row_count"] >= 1
    assert payload["summary"]["contradiction_row_count"] >= 1
    assert payload["promises_vs_actions"][0]["action_alignment"] in {
        "possible_follow_up_match",
        "apparent_contradiction",
    }
    assert payload["omission_rows"][0]["omission_type"] == "later_summary_omits_prior_promise"
    contradiction_kinds = {row["contradiction_kind"] for row in payload["contradiction_table"]}
    assert "promise_vs_later_action" in contradiction_kinds
    assert "source_date_vs_event_date" not in contradiction_kinds
    contradiction_row = next(
        row for row in payload["contradiction_table"] if row["contradiction_kind"] == "promise_vs_later_action"
    )
    assert len(contradiction_row.get("supporting_locators") or []) >= 2
    assert payload["summary"]["locator_backed_contradiction_count"] == payload["summary"]["contradiction_row_count"]


def test_build_promise_contradiction_analysis_pairs_note_records_with_linked_follow_ups() -> None:
    payload = build_promise_contradiction_analysis(
        case_bundle={"scope": {"case_label": "case-b"}},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "note:1",
                    "source_type": "note_record",
                    "uid": "uid-note-1",
                    "actor_id": "actor-manager",
                    "title": "Meeting summary PR follow-up",
                    "snippet": "We will include the Personalrat and send a written summary.",
                    "date": "2026-03-01",
                    "chronology_anchor": {"date": "2026-03-01"},
                    "source_weighting": {"text_available": True},
                },
                {
                    "source_id": "email:2",
                    "source_type": "email",
                    "uid": "uid-email-2",
                    "actor_id": "actor-hr",
                    "title": "Meeting summary PR follow-up",
                    "snippet": "Written summary attached. Personalrat was not included in this step.",
                    "date": "2026-03-03",
                    "chronology_anchor": {"date": "2026-03-03"},
                    "source_weighting": {"text_available": True},
                },
            ],
            "source_links": [
                {
                    "from_source_id": "note:1",
                    "to_source_id": "email:2",
                    "link_type": "follow_up_summary",
                    "relationship": "meeting_note_follow_up",
                }
            ],
        },
        master_chronology={"summary": {}},
    )

    assert payload is not None
    assert payload["summary"]["promise_action_row_count"] >= 1
    contradiction = next(row for row in payload["contradiction_table"] if row["contradiction_kind"] == "promise_vs_later_action")
    assert contradiction["original_source_id"] == "note:1"
    assert contradiction["later_source_id"] == "email:2"


def test_build_promise_contradiction_analysis_ignores_unrelated_same_actor_negation() -> None:
    payload = build_promise_contradiction_analysis(
        case_bundle={"scope": {"case_label": "case-c"}},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "note:promise",
                    "source_type": "note_record",
                    "uid": "uid-note-1",
                    "actor_id": "actor-manager",
                    "title": "Participation follow-up",
                    "snippet": "We will inform the SBV and send a written summary.",
                    "date": "2026-03-01",
                    "chronology_anchor": {"date": "2026-03-01"},
                    "source_weighting": {"text_available": True},
                },
                {
                    "source_id": "email:unrelated",
                    "source_type": "email",
                    "uid": "uid-email-9",
                    "actor_id": "actor-manager",
                    "title": "Participation follow-up",
                    "snippet": "We did not inform IT about the VPN outage.",
                    "date": "2026-03-03",
                    "chronology_anchor": {"date": "2026-03-03"},
                    "source_weighting": {"text_available": True},
                },
            ]
        },
        master_chronology={"summary": {}},
    )

    assert payload is not None
    assert not any(
        row["contradiction_kind"] == "promise_vs_later_action" and row["later_source_id"] == "email:unrelated"
        for row in payload["contradiction_table"]
    )


def test_build_promise_contradiction_analysis_marks_zero_rows_as_insufficient() -> None:
    payload = build_promise_contradiction_analysis(
        case_bundle={"scope": {"case_label": "case-d"}},
        multi_source_case_bundle={"sources": [], "source_links": []},
        master_chronology={"summary": {}},
    )

    assert payload is not None
    assert payload["summary"]["status"] == "insufficient_source_material"
    assert payload["summary"]["insufficiency_reason"]
    assert payload["summary"]["usable_source_count"] == 0


def test_build_promise_contradiction_analysis_ignores_stitched_thread_exports() -> None:
    payload = build_promise_contradiction_analysis(
        case_bundle={"scope": {"case_label": "case-e"}},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "formal_document:thread.html",
                    "source_type": "formal_document",
                    "uid": "uid-thread",
                    "title": "thread.html",
                    "snippet": (
                        "From: a@example.com Subject: Follow-up. We will send the summary. "
                        "From: b@example.com Subject: Reply. We did not send the summary."
                    ),
                    "date": "2026-03-02",
                    "chronology_anchor": {"date": "2026-03-02"},
                }
            ],
            "source_links": [],
        },
        master_chronology={"summary": {}},
    )

    assert payload is not None
    assert payload["summary"]["promise_action_row_count"] == 0
    assert payload["summary"]["contradiction_row_count"] == 0
    assert payload["summary"]["usable_source_count"] == 0


def test_build_promise_contradiction_analysis_orders_timezone_aware_dates_before_filtering() -> None:
    payload = build_promise_contradiction_analysis(
        case_bundle={"scope": {"case_label": "case-f"}},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "note:promise-tz",
                    "source_type": "note_record",
                    "uid": "uid-tz-1",
                    "actor_id": "actor-manager",
                    "title": "Timeline follow-up",
                    "snippet": "We will provide the written summary today.",
                    "date": "2026-03-01T12:00:00+02:00",
                    "chronology_anchor": {"date": "2026-03-01T12:00:00+02:00"},
                    "source_weighting": {"text_available": True},
                },
                {
                    "source_id": "email:followup-tz",
                    "source_type": "email",
                    "uid": "uid-tz-1",
                    "actor_id": "actor-manager",
                    "title": "Timeline follow-up",
                    "snippet": "Provided the written summary as requested.",
                    "date": "2026-03-01T10:30:00Z",
                    "chronology_anchor": {"date": "2026-03-01T10:30:00Z"},
                    "source_weighting": {"text_available": True},
                },
            ],
            "source_links": [],
        },
        master_chronology={"summary": {}},
    )

    assert payload is not None
    assert payload["summary"]["promise_action_row_count"] >= 1
    assert any(row["later_source_id"] == "email:followup-tz" for row in payload["promises_vs_actions"])
