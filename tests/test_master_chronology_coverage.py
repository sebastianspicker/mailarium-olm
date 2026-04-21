"""Targeted coverage tests for master_chronology.py (lines 60-89, 143, 162-174, 187, 194, 207, 225)."""

from __future__ import annotations

import json

from src.master_chronology import _adverse_action_entry, _source_event_entry, build_master_chronology

# ── _source_event_entry ──────────────────────────────────────────────────────


def test_source_event_entry_with_dict_provenance() -> None:
    """Lines 68-69: provenance_json as dict is used directly."""
    entry = _source_event_entry(
        source={"uid": "u1", "source_id": "s1", "source_type": "email", "date": "2024-01-10"},
        event_record={
            "event_key": "ek1",
            "event_kind": "exclusion_signal",
            "trigger_text": "was excluded",
            "event_date": "2024-01-10",
            "provenance_json": {"source_scope": "body", "surface_scope": "quoted"},
        },
        case_bundle={"scope": {}},
        citation_ids_by_uid={"u1": ["CIT-001"]},
    )
    assert entry["entry_type"] == "source_event_extracted"
    assert entry["title"] == "Exclusion signal"
    assert entry["description"] == "was excluded"
    assert entry["source_linkage"]["supporting_citation_ids"] == ["CIT-001"]


def test_source_event_entry_with_json_string_provenance() -> None:
    """Lines 70-74: provenance_json as valid JSON string."""
    prov = json.dumps({"source_scope": "body", "surface_scope": "thread"})
    entry = _source_event_entry(
        source={"uid": "u2"},
        event_record={
            "event_kind": "retaliation",
            "trigger_text": "demoted",
            "event_date": "2024-02-01",
            "provenance_json": prov,
        },
        case_bundle={"scope": {}},
        citation_ids_by_uid={},
    )
    assert entry["entry_type"] == "source_event_extracted"
    assert entry["description"] == "demoted"


def test_source_event_entry_with_invalid_json_string_provenance() -> None:
    """Lines 75-76: provenance_json as malformed JSON string falls back to empty."""
    entry = _source_event_entry(
        source={"uid": "u3"},
        event_record={
            "event_kind": "absence",
            "trigger_text": "",
            "event_date": "2024-03-01",
            "provenance_json": "{invalid_json}",
        },
        case_bundle={"scope": {}},
        citation_ids_by_uid={},
    )
    assert entry["entry_type"] == "source_event_extracted"
    # No trigger_text → auto-generated description
    assert "absence" in entry["description"]


def test_source_event_entry_no_trigger_text_generates_description() -> None:
    """Line 88: empty trigger_text falls back to generated description."""
    entry = _source_event_entry(
        source={},
        event_record={"event_kind": "silence_signal", "trigger_text": "", "event_date": "2024-04-01"},
        case_bundle={"scope": {}},
        citation_ids_by_uid={},
    )
    assert "silence signal" in entry["description"]


def test_source_event_entry_empty_uid_no_citations() -> None:
    """Line 86: empty uid skips citation lookup."""
    entry = _source_event_entry(
        source={"uid": ""},
        event_record={"event_kind": "event", "trigger_text": "x", "event_date": "2024-05-01"},
        case_bundle={"scope": {}},
        citation_ids_by_uid={"": ["CIT-X"]},
    )
    assert entry["source_linkage"]["supporting_citation_ids"] == []


def test_source_event_entry_date_falls_back_to_source_date() -> None:
    """Line 65: event_date not set → use source date."""
    entry = _source_event_entry(
        source={"uid": "u4", "date": "2024-06-01"},
        event_record={"event_kind": "event", "trigger_text": "x"},
        case_bundle={"scope": {}},
        citation_ids_by_uid={},
    )
    assert entry["date"] == "2024-06-01"


# ── build_master_chronology — previously uncovered branches ──────────────────


def test_build_master_chronology_with_event_records_in_sources() -> None:
    """Lines 162-174: sources with event_records produce source_event_extracted entries."""
    payload = build_master_chronology(
        case_bundle={"scope": {}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [],
            "sources": [
                {
                    "uid": "u1",
                    "source_id": "s1",
                    "source_type": "email",
                    "date": "2024-03-15",
                    "event_records": [
                        {
                            "event_key": "ev1",
                            "event_kind": "exclusion_signal",
                            "trigger_text": "not invited",
                            "event_date": "2024-03-15",
                        }
                    ],
                }
            ],
        },
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    types = [e["entry_type"] for e in payload["entries"]]
    assert "source_event_extracted" in types


def test_build_master_chronology_deduplicates_event_records() -> None:
    """Lines 167-170: same event_key in multiple sources is only added once."""
    payload = build_master_chronology(
        case_bundle={"scope": {}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [],
            "sources": [
                {
                    "uid": "u1",
                    "event_records": [{"event_key": "dup_key", "event_kind": "absence", "event_date": "2024-01-01"}],
                },
                {
                    "uid": "u2",
                    "event_records": [{"event_key": "dup_key", "event_kind": "absence", "event_date": "2024-01-01"}],
                },
            ],
        },
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    extracted = [e for e in payload["entries"] if e["entry_type"] == "source_event_extracted"]
    assert len(extracted) == 1


def test_build_master_chronology_skips_event_record_without_date() -> None:
    """Line 172-173: event_records without event_date are skipped."""
    payload = build_master_chronology(
        case_bundle={"scope": {}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [],
            "sources": [
                {
                    "uid": "u1",
                    "event_records": [{"event_key": "no_date", "event_kind": "absence", "event_date": ""}],
                }
            ],
        },
        finding_evidence_index={"findings": []},
    )
    # No date → no entry added → payload None or empty
    if payload is not None:
        types = [e["entry_type"] for e in payload["entries"]]
        assert "source_event_extracted" not in types


def test_build_master_chronology_returns_none_for_non_dict_case_bundle() -> None:
    """Line 132: non-dict case_bundle → None."""
    assert (
        build_master_chronology(
            case_bundle=None,
            timeline={"events": []},
            multi_source_case_bundle={"chronology_anchors": [], "sources": []},
            finding_evidence_index={"findings": []},
        )
        is None
    )


def test_build_master_chronology_skips_anchor_with_unknown_source_id() -> None:
    """Lines 144-148: anchor with source_id not in source_lookup is skipped."""
    payload = build_master_chronology(
        case_bundle={"scope": {"alleged_adverse_actions": [{"action_type": "removal", "date": "2024-01-01"}]}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [{"source_id": "MISSING_SRC"}],
            "sources": [],  # source_lookup is empty → miss
        },
        finding_evidence_index={"findings": []},
    )
    # Only adverse action survives; anchor is skipped
    assert payload is not None
    types = [e["entry_type"] for e in payload["entries"]]
    assert all(t != "source_entry" for t in types)


def test_build_master_chronology_skips_non_dict_source_items() -> None:
    """Lines 161-162: non-dict items in sources list are skipped."""
    payload = build_master_chronology(
        case_bundle={"scope": {"alleged_adverse_actions": [{"action_type": "demotion", "date": "2024-02-01"}]}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [],
            "sources": ["not_a_dict", None, 42],
        },
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    types = [e["entry_type"] for e in payload["entries"]]
    assert "source_event_extracted" not in types


def test_build_master_chronology_skips_non_dict_event_records() -> None:
    """Lines 164-165: non-dict items in event_records are skipped."""
    payload = build_master_chronology(
        case_bundle={"scope": {"alleged_adverse_actions": [{"action_type": "demotion", "date": "2024-02-01"}]}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [],
            "sources": [
                {
                    "uid": "u1",
                    "event_records": ["not_a_dict", None],
                }
            ],
        },
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    types = [e["entry_type"] for e in payload["entries"]]
    assert "source_event_extracted" not in types


def test_build_master_chronology_skips_trigger_event_without_date() -> None:
    """Line 187: trigger event without date is skipped."""
    payload = build_master_chronology(
        case_bundle={
            "scope": {
                "trigger_events": [
                    {"trigger_type": "protected_complaint"},  # no date → skipped
                    {"trigger_type": "complaint", "date": "2024-03-01"},  # valid
                ]
            }
        },
        timeline={"events": []},
        multi_source_case_bundle={"chronology_anchors": [], "sources": []},
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    trigger_entries = [e for e in payload["entries"] if e["entry_type"] == "trigger_event"]
    assert len(trigger_entries) == 1


def test_build_master_chronology_skips_timeline_event_without_date() -> None:
    """Lines 225-228: timeline event without date and event already in seen_uids are both skipped."""
    payload = build_master_chronology(
        case_bundle={"scope": {"alleged_adverse_actions": [{"action_type": "termination", "date": "2024-05-01"}]}},
        timeline={
            "events": [
                {"uid": "t1"},  # no date → skipped via line 228 branch
                {"uid": "t2", "date": ""},  # empty date → skipped
            ]
        },
        multi_source_case_bundle={"chronology_anchors": [], "sources": []},
        finding_evidence_index={"findings": []},
    )
    # Only adverse action entry survives
    assert payload is not None
    timeline_entries = [e for e in payload["entries"] if "timeline" in e.get("entry_type", "")]
    assert len(timeline_entries) == 0

    """Line 143: non-dict item in chronology_anchors is skipped."""
    payload = build_master_chronology(
        case_bundle={"scope": {"alleged_adverse_actions": [{"action_type": "removal", "date": "2024-01-01"}]}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": ["not_a_dict", None, 42],
            "sources": [],
        },
        finding_evidence_index={"findings": []},
    )
    # Non-dict anchors must be skipped; only adverse action entry survives
    assert payload is not None
    types = [e["entry_type"] for e in payload["entries"]]
    assert "adverse_action_event" in types


def test_build_master_chronology_skips_invalid_adverse_action() -> None:
    """Line 207: adverse_action without a date is skipped (continue branch)."""
    payload = build_master_chronology(
        case_bundle={
            "scope": {
                "alleged_adverse_actions": [
                    {"action_type": "removal"},  # no date → skipped
                    {"action_type": "demotion", "date": "2024-05-01"},  # valid
                ]
            }
        },
        timeline={"events": []},
        multi_source_case_bundle={"chronology_anchors": [], "sources": []},
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    adverse = [e for e in payload["entries"] if e["entry_type"] == "adverse_action_event"]
    assert len(adverse) == 1
    assert adverse[0]["title"] == "Demotion"


def test_build_master_chronology_uses_timeline_fallback_for_new_uid() -> None:
    """Line 225: timeline events not already in seen_uids produce fallback entries."""
    payload = build_master_chronology(
        case_bundle={"scope": {}},
        timeline={
            "events": [
                {"uid": "timeline_uid_1", "date": "2024-07-01", "description": "meeting cancelled"},
            ]
        },
        multi_source_case_bundle={"chronology_anchors": [], "sources": []},
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    types = [e["entry_type"] for e in payload["entries"]]
    assert any("timeline" in t or "fallback" in t for t in types)


def test_build_master_chronology_deduplicates_trigger_events() -> None:
    """Lines 187, 194: duplicate trigger events (same type/date/notes) are added only once."""
    dup_trigger = {"trigger_type": "protected_complaint", "date": "2024-02-01", "notes": "HR report"}
    payload = build_master_chronology(
        case_bundle={"scope": {"trigger_events": [dup_trigger, dup_trigger]}},
        timeline={"events": []},
        multi_source_case_bundle={"chronology_anchors": [], "sources": []},
        finding_evidence_index={"findings": []},
    )
    assert payload is not None
    trigger_entries = [e for e in payload["entries"] if e["entry_type"] == "trigger_event"]
    assert len(trigger_entries) == 1


# ── _adverse_action_entry (isolated) ─────────────────────────────────────────


def test_adverse_action_entry_structure() -> None:
    entry = _adverse_action_entry({"action_type": "termination", "date": "2025-01-15"})
    assert entry["entry_type"] == "adverse_action_event"
    assert entry["date"] == "2025-01-15"
    assert entry["title"] == "Termination"
    assert entry["source_linkage"]["source_evidence_status"] == "scope_only"
