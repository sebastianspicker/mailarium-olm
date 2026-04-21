"""Canonical behavioural taxonomy for workplace-conflict analysis."""

from __future__ import annotations

from collections.abc import Sequence
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

EmploymentIssueTagId = Literal[
    "eingruppierung",
    "agg_disability_disadvantage",
    "retaliation_massregelung",
    "mobile_work_home_office",
    "sbv_participation",
    "pr_participation",
    "prevention_bem_sgb_ix_167",
    "medical_recommendations_ignored",
    "task_withdrawal_td_fixation",
    "worktime_control_surveillance",
    "witness_relevance",
    "comparator_evidence",
]


class BehavioralTaxonomyEntry(TypedDict):
    """One canonical taxonomy category definition."""

    category_id: BehavioralTaxonomyCategoryId
    label: str
    definition: str
    common_counterexamples: list[str]


class EmploymentIssueTagEntry(TypedDict):
    """One canonical employment-matter issue tag definition."""

    tag_id: EmploymentIssueTagId
    label: str
    definition: str


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
            "Framing responsibility away from the actor and onto the target despite mixed or shared responsibility in the record."
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
            "Keeping relevant information, instructions, or updates from a person in a way that materially disadvantages them."
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
            "Applying stricter standards, deadlines, or procedural burdens to one person than to relevant comparators."
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
            "A change in treatment after a trigger event such as a complaint, objection, illness disclosure, or escalation to HR."
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
            "Marked contrast in tone, courtesy, or formal respect toward the target compared with others in similar contexts."
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

EMPLOYMENT_ISSUE_TAGS: list[EmploymentIssueTagEntry] = [
    {
        "tag_id": "eingruppierung",
        "label": "Eingruppierung",
        "definition": "Classification, grading, task-level, or tariff-group dispute evidence.",
    },
    {
        "tag_id": "agg_disability_disadvantage",
        "label": "AGG / Disability Disadvantage",
        "definition": "Disability- or illness-linked disadvantage or unequal-treatment evidence.",
    },
    {
        "tag_id": "retaliation_massregelung",
        "label": "Retaliation / Maßregelung",
        "definition": "Before/after retaliation or adverse-treatment sequencing evidence.",
    },
    {
        "tag_id": "mobile_work_home_office",
        "label": "Mobile Work / Home Office",
        "definition": "Remote-work, home-office, or attendance-control issue evidence.",
    },
    {
        "tag_id": "sbv_participation",
        "label": "SBV Participation",
        "definition": "Schwerbehindertenvertretung participation or consultation evidence.",
    },
    {
        "tag_id": "pr_participation",
        "label": "PR Participation",
        "definition": "Personalrat or comparable participation-path evidence.",
    },
    {
        "tag_id": "prevention_bem_sgb_ix_167",
        "label": "Section 167 / BEM / Prevention",
        "definition": "Prevention, BEM, or section-167 SGB IX process evidence.",
    },
    {
        "tag_id": "medical_recommendations_ignored",
        "label": "Medical Recommendations Ignored",
        "definition": "Evidence that documented medical recommendations or restrictions may have been disregarded.",
    },
    {
        "tag_id": "task_withdrawal_td_fixation",
        "label": "Task Withdrawal / TD Fixation",
        "definition": "Evidence about task withdrawal, fixation on duty descriptions, or narrowed task allocation.",
    },
    {
        "tag_id": "worktime_control_surveillance",
        "label": "Worktime Control / Surveillance",
        "definition": "Evidence around worktime monitoring, attendance control, or surveillance-like oversight.",
    },
    {
        "tag_id": "witness_relevance",
        "label": "Witness Relevance",
        "definition": "Evidence identifying likely witnesses, witness relevance, or witness-linked corroboration paths.",
    },
    {
        "tag_id": "comparator_evidence",
        "label": "Comparator Evidence",
        "definition": "Evidence that materially supports or weakens comparator-based unequal-treatment review.",
    },
]

_TRACK_TO_ISSUE_TAGS: dict[str, list[EmploymentIssueTagId]] = {
    "disability_disadvantage": ["agg_disability_disadvantage"],
    "retaliation_after_protected_event": ["retaliation_massregelung"],
    "eingruppierung_dispute": ["eingruppierung"],
    "prevention_duty_gap": ["prevention_bem_sgb_ix_167"],
}

_FOCUS_TO_ISSUE_TAGS: dict[str, list[EmploymentIssueTagId]] = {
    "retaliation": ["retaliation_massregelung"],
    "discrimination": ["agg_disability_disadvantage", "comparator_evidence"],
    "unequal_treatment": ["comparator_evidence"],
}

_ISSUE_TAG_KEYWORDS: dict[EmploymentIssueTagId, tuple[str, ...]] = {
    "eingruppierung": ("eingruppierung", "entgeltgruppe", "vergütungsgruppe", "tarif", "td "),
    "agg_disability_disadvantage": ("behinderung", "disability", "illness", "krank", "erkrank"),
    "retaliation_massregelung": ("maßregel", "massregel", "retaliat", "complaint", "beschwerde"),
    "mobile_work_home_office": ("home office", "homeoffice", "mobile work", "remote work", "hybrid"),
    "sbv_participation": ("sbv", "schwerbehindertenvertretung"),
    "pr_participation": ("personalrat", "betriebsrat", "mitbestimmung"),
    "prevention_bem_sgb_ix_167": ("bem", "prävention", "praevention", "sgb ix", "167"),
    "medical_recommendations_ignored": ("medical recommendation", "ärzt", "arzt", "betriebsarzt", "restriction"),
    "task_withdrawal_td_fixation": ("task withdrawal", "aufgabenentzug", "td-fix", "td fixation", "duty description"),
    "worktime_control_surveillance": ("arbeitszeit", "zeiterfassung", "surveillance", "überwachung", "monitoring"),
    "witness_relevance": ("zeuge", "zeugen", "witness"),
    "comparator_evidence": ("comparator", "vergleich", "vergleichsperson"),
}


def taxonomy_entries() -> list[BehavioralTaxonomyEntry]:
    """Return the canonical taxonomy entries."""
    return [cast(BehavioralTaxonomyEntry, dict(entry)) for entry in BEHAVIORAL_TAXONOMY]


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


def employment_issue_tag_entries() -> list[EmploymentIssueTagEntry]:
    """Return canonical employment issue tag definitions."""
    return [cast(EmploymentIssueTagEntry, dict(entry)) for entry in EMPLOYMENT_ISSUE_TAGS]


def normalize_issue_tag_ids(issue_tag_ids: Sequence[str]) -> list[EmploymentIssueTagId]:
    """Normalize selected employment issue tag ids without duplicates."""
    normalized: list[EmploymentIssueTagId] = []
    for item in issue_tag_ids:
        tag_id = cast(EmploymentIssueTagId, str(item))
        if tag_id not in {entry["tag_id"] for entry in EMPLOYMENT_ISSUE_TAGS}:
            continue
        if tag_id not in normalized:
            normalized.append(tag_id)
    return normalized


def issue_track_to_tag_ids(issue_track: str, *, context_text: str = "") -> list[EmploymentIssueTagId]:
    """Map one employment issue track to issue tags."""
    mapped = list(_TRACK_TO_ISSUE_TAGS.get(issue_track, []))
    normalized_context = " ".join(context_text.lower().split())
    if issue_track == "participation_duty_gap":
        if any(keyword in normalized_context for keyword in _ISSUE_TAG_KEYWORDS["sbv_participation"]):
            mapped.append("sbv_participation")
        if any(keyword in normalized_context for keyword in _ISSUE_TAG_KEYWORDS["pr_participation"]):
            mapped.append("pr_participation")
    return normalize_issue_tag_ids(mapped)


def focus_to_issue_tag_ids(allegation_focus: list[str]) -> list[EmploymentIssueTagId]:
    """Map allegation focus values to issue tags without duplicates."""
    mapped: list[EmploymentIssueTagId] = []
    for focus in allegation_focus:
        for tag_id in _FOCUS_TO_ISSUE_TAGS.get(str(focus), []):
            if tag_id not in mapped:
                mapped.append(tag_id)
    return mapped


def text_to_issue_tag_ids(text: str) -> list[EmploymentIssueTagId]:
    """Return issue tags directly visible in free text."""
    normalized_text = " ".join(str(text or "").lower().split())
    mapped: list[EmploymentIssueTagId] = []
    for tag_id, keywords in _ISSUE_TAG_KEYWORDS.items():
        if any(keyword in normalized_text for keyword in keywords):
            mapped.append(tag_id)
    return normalize_issue_tag_ids([str(tag_id) for tag_id in mapped])
