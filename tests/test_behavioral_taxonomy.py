from __future__ import annotations

from src.behavioral_taxonomy import (
    BEHAVIORAL_TAXONOMY_VERSION,
    behavioral_taxonomy_payload,
    focus_to_taxonomy_ids,
    taxonomy_entries,
)


def test_behavioral_taxonomy_payload_is_versioned_and_complete():
    payload = behavioral_taxonomy_payload(allegation_focus=["retaliation", "exclusion"])

    assert payload["version"] == BEHAVIORAL_TAXONOMY_VERSION
    assert len(payload["categories"]) == 10
    assert payload["categories"][0]["category_id"] == "exclusion"
    assert payload["categories"][0]["common_counterexamples"]
    assert payload["focus_category_ids"] == [
        "retaliatory_sequence",
        "escalation_pressure",
        "selective_non_response",
        "exclusion",
        "withholding_information",
    ]


def test_focus_to_taxonomy_ids_deduplicates_and_all_expands_full_taxonomy():
    mapped = focus_to_taxonomy_ids(["exclusion", "all", "retaliation"])

    assert mapped == [entry["category_id"] for entry in taxonomy_entries()]
