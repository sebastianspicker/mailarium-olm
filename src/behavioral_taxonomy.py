"""Canonical behavioural taxonomy for workplace-conflict analysis."""

from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

BEHAVIORAL_TAXONOMY_VERSION = "1"

BehavioralTaxonomyCategoryId = Literal[
    "exclusion",
    "selective_non_response",
    "public_criticism",
    "escalation_pressure",
    "blame_shifting",
    "withholding_information",
    "undermining_credibility",
    "unequal_demands",
    "retaliatory_sequence",
    "selective_politeness",
]


class BehavioralTaxonomyEntry(TypedDict):
    """One canonical taxonomy category definition."""

    category_id: BehavioralTaxonomyCategoryId
    label: str
    definition: str
    common_counterexamples: list[str]


BEHAVIORAL_TAXONOMY: list[BehavioralTaxonomyEntry] = [
    {
        "category_id": "exclusion",
        "label": "Exclusion or Isolation",
        "definition": (
            "Repeatedly leaving a person out of relevant communication, decisions, "
            "or visibility without a neutral operational reason."
        ),
        "common_counterexamples": [
            "Single accidental omission later corrected",
            "Legitimate need-to-know limitation with consistent application",
        ],
    },
    {
        "category_id": "selective_non_response",
        "label": "Selective Non-response",
        "definition": (
            "Ignoring or delaying one person's requests or updates in a patterned way "
            "while comparable communication channels remain active."
        ),
        "common_counterexamples": [
            "General inbox backlog affecting everyone equally",
            "One-off missed message without recurrence",
        ],
    },
    {
        "category_id": "public_criticism",
        "label": "Public Criticism",
        "definition": (
            "Correcting, blaming, or criticizing a person in front of unnecessary "
            "recipients or superiors rather than through proportionate private handling."
        ),
        "common_counterexamples": [
            "Operationally necessary broadcast correction affecting a whole team",
            "Neutral status clarification without blame language",
        ],
    },
    {
        "category_id": "escalation_pressure",
        "label": "Escalation Pressure",
        "definition": (
            "Using hierarchy, process escalation, or reputational leverage to pressure "
            "a person beyond the operational need of the issue."
        ),
        "common_counterexamples": [
            "Routine escalation required by policy",
            "Time-critical escalation with documented objective basis",
        ],
    },
    {
        "category_id": "blame_shifting",
        "label": "Blame-shifting",
        "definition": (
            "Framing responsibility away from the actor and onto the target despite "
            "mixed or shared responsibility in the record."
        ),
        "common_counterexamples": [
            "Accurate attribution supported by the record",
            "Good-faith disagreement about responsibility without repetition",
        ],
    },
    {
        "category_id": "withholding_information",
        "label": "Withholding Information",
        "definition": (
            "Keeping relevant information, instructions, or updates from a person in a "
            "way that materially disadvantages them."
        ),
        "common_counterexamples": [
            "Information genuinely unavailable at the time",
            "Restricted information shared consistently under policy constraints",
        ],
    },
    {
        "category_id": "undermining_credibility",
        "label": "Undermining Credibility",
        "definition": (
            "Framing a person as unreliable, confused, or difficult in a recurring way "
            "that reduces their standing beyond the evidence."
        ),
        "common_counterexamples": [
            "Documented performance concern raised proportionately once",
            "Fact-based correction without reputational framing",
        ],
    },
    {
        "category_id": "unequal_demands",
        "label": "Unequal Demands",
        "definition": (
            "Applying stricter standards, deadlines, or procedural burdens to one "
            "person than to relevant comparators."
        ),
        "common_counterexamples": [
            "Different requirements justified by role differences",
            "Temporary exceptional demand applied broadly to everyone",
        ],
    },
    {
        "category_id": "retaliatory_sequence",
        "label": "Retaliatory Sequence",
        "definition": (
            "A change in treatment after a trigger event such as a complaint, "
            "objection, illness disclosure, or escalation to HR."
        ),
        "common_counterexamples": [
            "No meaningful before/after change in treatment",
            "Independent operational changes unrelated to the trigger event",
        ],
    },
    {
        "category_id": "selective_politeness",
        "label": "Selective Politeness or Formality",
        "definition": (
            "Marked contrast in tone, courtesy, or formal respect toward the target "
            "compared with others in similar contexts."
        ),
        "common_counterexamples": [
            "Different tone explained by different audience or formality norms",
            "Isolated curt wording during time pressure without recurrence",
        ],
    },
]

_FOCUS_TO_TAXONOMY_IDS: dict[str, list[BehavioralTaxonomyCategoryId]] = {
    "discrimination": ["unequal_demands", "exclusion"],
    "bullying": ["public_criticism", "undermining_credibility", "escalation_pressure"],
    "mobbing": ["exclusion", "public_criticism", "undermining_credibility", "retaliatory_sequence"],
    "hostility": ["public_criticism", "escalation_pressure", "blame_shifting"],
    "intimidation": ["escalation_pressure"],
    "exclusion": ["exclusion", "withholding_information", "selective_non_response"],
    "unequal_treatment": ["unequal_demands", "selective_politeness"],
    "retaliation": ["retaliatory_sequence", "escalation_pressure", "selective_non_response"],
    "manipulation": ["blame_shifting", "undermining_credibility", "withholding_information"],
    "abuse_of_authority": ["escalation_pressure", "unequal_demands", "public_criticism"],
    "all": [entry["category_id"] for entry in BEHAVIORAL_TAXONOMY],
}


def taxonomy_entries() -> list[BehavioralTaxonomyEntry]:
    """Return the canonical taxonomy entries."""
    return [
        cast(BehavioralTaxonomyEntry, dict(entry)) for entry in BEHAVIORAL_TAXONOMY
    ]


def focus_to_taxonomy_ids(allegation_focus: list[str]) -> list[BehavioralTaxonomyCategoryId]:
    """Map case intake allegation focus values to taxonomy ids without duplicates."""
    if "all" in allegation_focus:
        return [entry["category_id"] for entry in BEHAVIORAL_TAXONOMY]
    mapped: list[BehavioralTaxonomyCategoryId] = []
    for focus in allegation_focus:
        for category_id in _FOCUS_TO_TAXONOMY_IDS.get(str(focus), []):
            if category_id not in mapped:
                mapped.append(category_id)
    return mapped


def behavioral_taxonomy_payload(*, allegation_focus: list[str] | None = None) -> dict[str, Any]:
    """Return the versioned taxonomy payload for analysis surfaces."""
    allegation_focus = allegation_focus or []
    return {
        "version": BEHAVIORAL_TAXONOMY_VERSION,
        "categories": taxonomy_entries(),
        "focus_category_ids": focus_to_taxonomy_ids(allegation_focus),
    }
