# ruff: noqa: F401
from __future__ import annotations

from src.multi_source_case_bundle import append_chat_log_sources, append_manifest_sources, build_multi_source_case_bundle


def test_build_multi_source_case_bundle_extracts_document_event_dates_and_time_record_ranges() -> None:
    payload = build_multi_source_case_bundle(
        case_bundle={"scope": {"case_label": "case-d"}},
        candidates=[],
        attachment_candidates=[
            {
                "uid": "uid-note-2",
                "sender_actor_id": "actor-1",
                "date": "2026-03-20T11:00:00",
                "snippet": "Meeting summary for 2026-03-05 about the complaint follow-up.",
                "provenance": {"evidence_handle": "attachment:uid-note-2:meeting-summary.txt"},
                "attachment": {
                    "filename": "meeting-summary.txt",
                    "mime_type": "text/plain",
                    "text_available": True,
                    "evidence_strength": "strong_text",
                    "extraction_state": "text_extracted",
                    "text_preview": "Meeting summary for 2026-03-05 about the complaint follow-up.",
                },
            },
            {
                "uid": "uid-time-2",
                "sender_actor_id": "actor-2",
                "date": "2026-03-31T18:00:00",
                "snippet": "Attendance record covering 2026-03-01 to 2026-03-31.",
                "provenance": {"evidence_handle": "attachment:uid-time-2:attendance.xlsx"},
                "attachment": {
                    "filename": "attendance.xlsx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "text_available": True,
                    "evidence_strength": "strong_text",
                    "extraction_state": "text_extracted",
                    "text_preview": "[Sheet: March] Attendance record covering 2026-03-01 to 2026-03-31.",
                },
            },
        ],
        full_map={},
    )

    assert payload is not None
    note_record = next(source for source in payload["sources"] if source["source_type"] == "note_record")
    time_record = next(source for source in payload["sources"] if source["source_type"] == "time_record")
    assert note_record["chronology_anchor"]["date"] == "2026-03-05"
    assert note_record["chronology_anchor"]["date_origin"] == "document_text"
    assert time_record["chronology_anchor"]["date"] == "2026-03-01"
    assert time_record["chronology_anchor"]["date_origin"] == "time_record_range_start"
    assert time_record["chronology_anchor"]["date_range"] == {
        "start": "2026-03-01",
        "end": "2026-03-31",
    }
    assert time_record["spreadsheet_semantics"] == {
        "record_type": "attendance_export",
        "sheet_names": ["March"],
        "sheet_count": 1,
        "explicit_dates": ["2026-03-01", "2026-03-31"],
        "date_range": {"start": "2026-03-01", "end": "2026-03-31"},
        "month_labels": ["march"],
        "date_signal_strength": "range",
        "structure_signal": "sheeted",
    }


def test_append_manifest_sources_extracts_german_document_dates_into_chronology_candidates() -> None:
    bundle = append_manifest_sources(
        {
            "version": "1",
            "summary": {},
            "sources": [],
            "source_links": [],
            "source_type_profiles": [],
            "chronology_anchors": [],
        },
        matter_manifest={
            "manifest_id": "matter-date-1",
            "artifacts": [
                {
                    "source_id": "manifest:doc:eu-date",
                    "source_class": "formal_document",
                    "title": "Besprechungsnotiz",
                    "date": "2026-03-20T11:00:00",
                    "review_status": "parsed",
                    "text": "Besprechung am 05.03.2026 mit Nachtrag 07/03/2026.",
                }
            ],
        },
    )

    assert bundle is not None
    source = next(source for source in bundle["sources"] if source["source_id"] == "manifest:doc:eu-date")
    anchor = source["chronology_anchor"]
    assert anchor["date"] == "2026-03-05"
    assert anchor["date_origin"] == "document_text"
    assert anchor["anchor_confidence"] == "medium"
    assert anchor["date_candidates"][0]["date"] == "2026-03-05"
    assert anchor["date_candidates"][1]["date"] == "2026-03-07"
