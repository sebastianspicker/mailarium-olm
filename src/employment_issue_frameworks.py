"""Neutral employment-matter issue frameworks for intake and report rendering."""

from __future__ import annotations

from typing import Any

IssueTrack = str

ISSUE_TRACK_DEFINITIONS: dict[IssueTrack, dict[str, Any]] = {
    "disability_disadvantage": {
        "title": "Disability-Related Disadvantage",
        "neutral_question": (
            "Does the current record support a neutral concern that disability- or illness-linked context may have "
            "contributed to disadvantage, exclusion, or unequal treatment?"
        ),
        "required_proof_elements": [
            "Protected or vulnerability context is visible in the record or structured intake.",
            "A disadvantage, exclusion, or unequal-treatment event is identifiable.",
            "A credible link between the context and the disadvantage remains supportable from the current record.",
        ],
        "normal_alternative_explanations": [
            "Operational process differences may explain the treatment gap.",
            "The record may show conflict or weak management rather than disability-linked disadvantage.",
            "Comparator quality may be too weak to support a stronger reading.",
        ],
        "missing_document_checklist": [
            "Accommodation or workload-adjustment requests",
            "Medical recommendation summaries or restrictions actually shared with the employer",
            "Comparator examples from the same process step or decision-maker",
        ],
        "minimum_source_quality_expectations": [
            "Need direct messages or formal records showing the disadvantage event.",
            "Comparator-based support should come from materially similar workflow contexts.",
        ],
    },
    "retaliation_after_protected_event": {
        "title": "Retaliation After Protected or Participation Event",
        "neutral_question": (
            "Does the current record support a neutral concern that treatment worsened after a complaint, objection, "
            "participation act, or protected disclosure?"
        ),
        "required_proof_elements": [
            "A dated trigger event is identified.",
            "A before/after shift in treatment or process handling is visible.",
            "Confounders do not fully explain the shift on the current record.",
        ],
        "normal_alternative_explanations": [
            "The timing change may reflect an unrelated operational development.",
            "The record may show process friction rather than retaliation.",
            "The before/after window may still be too thin for a stronger reading.",
        ],
        "missing_document_checklist": [
            "Complaint, objection, HR-contact, or participation-event record",
            "Messages or decisions close to the trigger date",
            "Neutral context about workflow changes or incidents in the same period",
        ],
        "minimum_source_quality_expectations": [
            "Need a bounded chronology with dated trigger evidence.",
            "Need before/after messages, notes, or decisions from the same actors or process.",
        ],
    },
    "eingruppierung_dispute": {
        "title": "Eingruppierung Dispute",
        "neutral_question": (
            "Does the current record support a neutral concern that task level, role allocation, or classification "
            "handling may be disputed and not yet adequately documented?"
        ),
        "required_proof_elements": [
            "The record identifies a role, task, or classification disagreement.",
            "Current and expected task or grade context is at least minimally described.",
            "The dispute is anchored to messages or documents rather than only a bare allegation.",
        ],
        "normal_alternative_explanations": [
            "The record may show ordinary workload allocation rather than a classification dispute.",
            "Draft or informal task descriptions may not reflect final classification decisions.",
            "The current evidence may be incomplete because decisive formal documents are absent.",
        ],
        "missing_document_checklist": [
            "Job description, task profile, or duty allocation record",
            "Tariff or grade reference used by the employer",
            "Meeting notes, HR correspondence, or decision record about classification",
        ],
        "minimum_source_quality_expectations": [
            "Email alone is often insufficient; formal role or HR documents materially strengthen this track.",
            "Need at least one concrete source tying the dispute to tasks, grade, or role expectations.",
        ],
    },
    "prevention_duty_gap": {
        "title": "Prevention-Duty Gap",
        "neutral_question": (
            "Does the current record support a neutral concern that prevention-oriented follow-up, support, or BEM-like "
            "process steps may not have been adequately pursued?"
        ),
        "required_proof_elements": [
            "A health, disability, or sustained-workability context is visible.",
            "The record suggests prevention-oriented process steps should have been considered.",
            "The current material shows an apparent gap, refusal, or unexplained absence of such steps.",
        ],
        "normal_alternative_explanations": [
            "The decisive prevention steps may exist outside the currently supplied sources.",
            "The employer may have acted, but the current case bundle does not yet contain that documentation.",
            "The record may still be too early in the process to support a stronger gap reading.",
        ],
        "missing_document_checklist": [
            "BEM or prevention-process invitations, notes, or refusals",
            "Health-related process correspondence",
            "Documented support offers, workplace adjustments, or follow-up steps",
        ],
        "minimum_source_quality_expectations": [
            "Need documentary process evidence, not only interpersonal conflict messages.",
            "Formal HR or occupational-process records materially strengthen this track.",
        ],
    },
    "participation_duty_gap": {
        "title": "Participation-Duty Gap",
        "neutral_question": (
            "Does the current record support a neutral concern that required participation or consultation of SBV, PR, "
            "or comparable bodies may be missing or bypassed?"
        ),
        "required_proof_elements": [
            "A participation-relevant matter is identified.",
            "The record indicates which participation body or representative should be involved.",
            "The current material suggests the participation step is missing, bypassed, or not yet evidenced.",
        ],
        "normal_alternative_explanations": [
            "The participation step may have occurred outside the currently supplied sources.",
            "The matter may not yet have reached the stage where participation was required.",
            "The current record may show poor documentation rather than a true participation failure.",
        ],
        "missing_document_checklist": [
            "SBV, Personalrat, or other participation correspondence",
            "Meeting invitations, consultation records, or confirmations",
            "Decision records showing whether participation was considered or waived",
        ],
        "minimum_source_quality_expectations": [
            "Need participation-related correspondence or formal process records.",
            "Email patterns alone usually cannot establish the full participation picture.",
        ],
    },
}

_KEYWORDS_BY_TRACK: dict[IssueTrack, tuple[str, ...]] = {
    "eingruppierung_dispute": ("eingruppierung", "entgeltgruppe", "vergütungsgruppe", "tarif", "td "),
    "prevention_duty_gap": ("bem", "prävention", "praevention", "sgb ix", "167", "arbeitsfähigkeit", "workability"),
    "participation_duty_gap": (
        "sbv",
        "schwerbehindertenvertretung",
        "personalrat",
        "betriebsrat",
        "mitbestimmung",
        "participation",
    ),
}


def issue_track_definition(issue_track: IssueTrack) -> dict[str, Any]:
    """Return the normalized definition for one issue track."""
    return dict(ISSUE_TRACK_DEFINITIONS[issue_track])


def issue_track_titles(issue_tracks: list[str]) -> list[str]:
    """Return titles for selected issue tracks."""
    return [
        str(ISSUE_TRACK_DEFINITIONS[issue_track]["title"])
        for issue_track in issue_tracks
        if issue_track in ISSUE_TRACK_DEFINITIONS
    ]


def _context_text(case_scope: Any) -> str:
    """Return normalized context notes as a single-line lowercase string."""
    return " ".join(str(case_scope.context_notes or "").lower().split())


def _has_protected_context(case_scope: Any) -> bool:
    org_context = getattr(case_scope, "org_context", None)
    if org_context is None:
        return False
    for context in getattr(org_context, "vulnerability_contexts", []):
        if str(getattr(context, "context_type", "") or "") in {"disability", "illness"}:
            return True
    return False


def _track_needs(case_scope: Any, issue_track: IssueTrack) -> list[dict[str, str]]:
    """Return structured missing-input guidance for one selected issue track."""
    context_text = _context_text(case_scope)
    if issue_track == "disability_disadvantage":
        return _disability_needs(case_scope)
    if issue_track == "retaliation_after_protected_event":
        return _retaliation_needs(case_scope)
    if issue_track == "prevention_duty_gap":
        return _prevention_needs(case_scope, context_text)
    if issue_track in {"eingruppierung_dispute", "participation_duty_gap"}:
        return _context_needs(issue_track, context_text)
    return []


def _need(field: str, reason: str, recommendation: str) -> dict[str, str]:
    return {"field": field, "reason": reason, "recommendation": recommendation}


def _disability_needs(case_scope: Any) -> list[dict[str, str]]:
    needs = []
    if not _has_protected_context(case_scope):
        needs.append(
            _need(
                "org_context.vulnerability_contexts",
                "Protected or vulnerability context is not yet visible in structured intake.",
                "Add illness or disability context only when it is already documented and relevant.",
            )
        )
    if not getattr(case_scope, "comparator_actors", []):
        needs.append(
            _need(
                "comparator_actors",
                "Comparator support is missing for a disadvantage or unequal-treatment issue track.",
                "Add one or more comparable actors from the same workflow or decision context.",
            )
        )
    return needs


def _retaliation_needs(case_scope: Any) -> list[dict[str, str]]:
    if getattr(case_scope, "trigger_events", []):
        return []
    return [
        _need(
            "trigger_events",
            "The protected or participation trigger event is not yet anchored to a date.",
            "Add dated complaint, objection, disclosure, or participation events.",
        )
    ]


def _prevention_needs(case_scope: Any, context_text: str) -> list[dict[str, str]]:
    needs = []
    if not _has_protected_context(case_scope):
        needs.append(
            _need(
                "org_context.vulnerability_contexts",
                "The health or disability context that would trigger prevention review is not yet visible.",
                "Add documented health, disability, or workability context when already known.",
            )
        )
    needs.extend(_context_needs("prevention_duty_gap", context_text))
    return needs


def _context_needs(issue_track: IssueTrack, context_text: str) -> list[dict[str, str]]:
    if context_text and any(keyword in context_text for keyword in _KEYWORDS_BY_TRACK[issue_track]):
        return []
    messages = {
        "eingruppierung_dispute": (
            "The intake does not yet describe the classification or task-allocation dispute concretely.",
            "Add neutral context about grade, task profile, or disputed role allocation.",
        ),
        "prevention_duty_gap": (
            "The intake does not yet identify a prevention, BEM, or follow-up process question.",
            "Add neutral notes about the prevention or BEM process concern.",
        ),
        "participation_duty_gap": (
            "The intake does not yet identify which participation body should have been involved.",
            "Add neutral notes naming SBV, Personalrat, or the relevant participation path.",
        ),
    }
    reason, recommendation = messages[issue_track]
    return [_need("context_notes", reason, recommendation)]


def build_issue_track_intake_payload(case_scope: Any) -> list[dict[str, Any]]:
    """Return selected issue-track frameworks plus intake readiness markers."""
    payloads: list[dict[str, Any]] = []
    for issue_track in getattr(case_scope, "employment_issue_tracks", []):
        if issue_track not in ISSUE_TRACK_DEFINITIONS:
            continue
        definition = issue_track_definition(issue_track)
        missing_inputs = _track_needs(case_scope, issue_track)
        payloads.append(
            {
                "issue_track": issue_track,
                **definition,
                "intake_status": "ready_for_issue_spotting" if not missing_inputs else "alleged_but_under_documented",
                "missing_inputs": missing_inputs,
            }
        )
    return payloads
