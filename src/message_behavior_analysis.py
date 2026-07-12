"""Per-message behavioural tagging helpers for behavioural analysis."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import re
from typing import Literal, cast

from .language_rhetoric import MessageRhetoricAnalysis
from .message_behavior_evidence import _candidate, _match_evidence, _metadata_evidence, _signal_evidence
from .message_behavior_models import (
    BehaviorCandidate,
    BehaviorConfidence,
    CommunicationClass,
    CommunicationClassification,
    MessageBehaviorAnalysis,
    ProcessSignal,
    RelevantWording,
    class_rank,
    normalize_message_behavior_analysis,
    ordered_unique,
)
from .message_behavior_reply_pairing import _tone_summary
from .message_behavior_reply_pairing import inject_reply_pairing_findings as _inject_reply_pairing_findings


def inject_reply_pairing_findings(
    analysis: MessageBehaviorAnalysis,
    *,
    reply_pairing: dict[str, object] | None,
) -> MessageBehaviorAnalysis:
    """Inject reply-pairing findings into a message behavior analysis.

    Args:
        analysis: The existing message behavior analysis to augment.
        reply_pairing: Reply pairing metadata containing response status, actor emails,
            and activity UIDs. Used to detect selective non-response patterns.

    Returns:
        The analysis enriched with reply-pairing findings, including additional
        behavior candidates (e.g., selective_non_response), process signals,
        classification updates, and relevant wording.

    """
    return _inject_reply_pairing_findings(analysis, reply_pairing=reply_pairing)


_DEADLINE_RE = re.compile(
    r"\b(?:today|by end of day|by eod|immediately|without delay|as soon as possible|asap|by tomorrow|"
    r"heute|noch heute|bis heute|bis morgen|bis ende des tages|spätestens|spaetestens|"
    r"umgehend|unverzüglich|unverzueglich|zeitnah|frist(?:gerecht)?)\b",
    re.IGNORECASE,
)
_SELECTIVE_ACCOUNTABILITY_RE = re.compile(
    r"\b(?:you alone|only you|solely your responsibility|you must ensure|your responsibility|"
    r"nur sie|sie allein|allein ihre verantwortung|ausschließlich ihre verantwortung|"
    r"ausschliesslich ihre verantwortung|sie müssen sicherstellen|sie muessen sicherstellen|"
    r"in ihrer verantwortung)\b",
    re.IGNORECASE,
)
_DECISION_UPDATE_RE = re.compile(
    r"\b(?:we decided|we will proceed|approved|decision has been made|update follows|"
    r"wir haben entschieden|es wurde entschieden|wir werden fortfahren|beschlossen|"
    r"freigegeben|die entscheidung steht|update folgt|wir informieren später|wir informieren spaeter)\b",
    re.IGNORECASE,
)
_BLAME_SHIFTING_RE = re.compile(
    r"\b(?:due to your (?:delay|failure|omission)|because of you|"
    r"your delay caused|your omission caused|"
    r"aufgrund ihrer? (?:verzoegerung|verzögerung|versaeumnis|versäumnis)|"
    r"durch ihre? (?:verzoegerung|verzögerung|unterlassung)|"
    r"wegen ihrer? (?:verzoegerung|verzögerung|unterlassung))\b",
    re.IGNORECASE,
)


def _signal_ids(rhetoric: MessageRhetoricAnalysis) -> list[str]:
    """Extract signal IDs from a rhetoric analysis.

    Args:
        rhetoric: The message rhetoric analysis containing signals.

    Returns:
        A list of string signal IDs extracted from the rhetoric's signals.

    """
    return [str(signal["signal_id"]) for signal in rhetoric.get("signals", [])]


def _relevant_wording(
    *,
    rhetoric: MessageRhetoricAnalysis,
    behavior_candidates: list[BehaviorCandidate],
) -> list[RelevantWording]:
    """Extract relevant wording snippets from rhetoric signals and behavior evidence.

    Args:
        rhetoric: The message rhetoric analysis containing signals with evidence.
        behavior_candidates: List of behavior candidates with their evidence.

    Returns:
        A list of RelevantWording items (text, source_scope, basis_id) deduplicated
        and limited to 6 entries, extracted from both signal and behavior evidence.

    """
    signal_items = _wording_from_rows(
        rhetoric.get("signals", []), id_key="signal_id", basis_prefix="signal", scope_key="source_text_scope"
    )
    behavior_items = _wording_from_rows(
        behavior_candidates, id_key="behavior_id", basis_prefix="behavior", scope_key="source_scope"
    )
    unique: dict[tuple[str, str, str], RelevantWording] = {}
    for item in [*signal_items, *behavior_items]:
        unique.setdefault((item["text"], item["source_scope"], item["basis_id"]), item)
    return list(unique.values())[:6]


def _wording_from_rows(rows, *, id_key, basis_prefix, scope_key):
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        basis_id = f"{basis_prefix}:{row.get(id_key) or ''}"
        for evidence in row.get("evidence", []) or []:
            if not isinstance(evidence, dict):
                continue
            text = str(evidence.get("matched_text") or evidence.get("excerpt") or "").strip()
            if text:
                items.append(
                    {"text": text, "source_scope": str(evidence.get(scope_key) or "authored_text"), "basis_id": basis_id}
                )
    return items


def _process_signals(
    *,
    signal_ids: list[str],
    behavior_candidates: list[BehaviorCandidate],
    omission_target_linked: bool,
    target_label: str,
) -> list[ProcessSignal]:
    """Generate process signals from detected signal IDs and behavior candidates.

    Args:
        signal_ids: List of detected rhetorical signal identifiers.
        behavior_candidates: List of behavior candidates with their IDs.
        omission_target_linked: Whether the case target is referenced but omitted.
        target_label: Label for the case target (used in signal summaries).

    Returns:
        A list of ProcessSignal items describing institutional pressure, procedural
        intimidation, deadline pressure, target absence, decision updates, and
        selective non-response patterns.

    """
    items: list[ProcessSignal] = []
    if "institutional_pressure_framing" in signal_ids:
        items.append(
            {
                "signal": "institutional_pressure_framing",
                "summary": "Formal-process or record-making wording appears in the authored text.",
            }
        )
    if "procedural_intimidation" in signal_ids:
        items.append(
            {
                "signal": "procedural_intimidation",
                "summary": "Rule or documentation language may function as pressure rather than neutral coordination.",
            }
        )
    behavior_ids = {str(candidate.get("behavior_id") or "") for candidate in behavior_candidates}
    if "deadline_pressure" in behavior_ids:
        items.append({"signal": "deadline_pressure", "summary": "The message uses explicit timing pressure or urgency wording."})
    if omission_target_linked:
        items.append(
            {
                "signal": "target_absent_from_visible_recipients",
                "summary": f"{target_label or 'Case target'} is absent from the visible recipient set.",
            }
        )
    if "withholding" in behavior_ids:
        items.append(
            {
                "signal": "decision_update_with_target_absent",
                "summary": "Decision/update wording appears while the case target is omitted from visible recipients.",
            }
        )
    if "selective_non_response" in behavior_ids:
        items.append(
            {
                "signal": "selective_non_response_inference",
                "summary": "Reply-pairing metadata supports a non-response concern in the current evidence slice.",
            }
        )
    return items


def _communication_classification(
    *,
    signal_ids: list[str],
    behavior_candidates: list[BehaviorCandidate],
    omission_target_linked: bool,
) -> CommunicationClassification:
    """Derive a communication classification from signals and behavior candidates.

    Args:
        signal_ids: List of detected rhetorical signal identifiers.
        behavior_candidates: List of behavior candidates with their IDs.
        omission_target_linked: Whether the case target is referenced but omitted.

    Returns:
        A CommunicationClassification with primary_class, applied_classes,
        confidence, and rationale. Applied classes are derived from behavior IDs
        and signal IDs, with higher ranks indicating more severe classifications.

    """
    behavior_ids = {str(candidate.get("behavior_id") or "") for candidate in behavior_candidates}
    signal_set = set(signal_ids)
    applied = _applied_classes(behavior_ids, signal_set, omission_target_linked)

    if not applied:
        applied = ["neutral"]

    primary = max(applied, key=class_rank)
    confidence: BehaviorConfidence
    if primary == "neutral":
        confidence = "low"
    elif len(applied) >= 2 or len(behavior_ids) >= 2:
        confidence = "high"
    else:
        confidence = "medium"
    return {
        "primary_class": primary,
        "applied_classes": [cast(CommunicationClass, label) for label in ordered_unique(applied)],
        "confidence": confidence,
        "rationale": (
            f"Applied classes follow the current message-level rhetoric, behaviour, and omission signals: {', '.join(applied)}."
        ),
    }


def _applied_classes(behavior_ids, signal_set, omission_target_linked):
    rules = (
        ("exclusionary", bool(behavior_ids & {"exclusion", "withholding"}) or omission_target_linked),
        ("retaliatory", bool(behavior_ids & {"selective_non_response"})),
        ("controlling", bool(behavior_ids & {"deadline_pressure", "selective_accountability", "escalation"})),
        (
            "defensive",
            bool(behavior_ids & {"blame_shifting"} or {"strategic_ambiguity", "passive_aggressive_deflection"} & signal_set),
        ),
        (
            "dismissive",
            bool(
                {"dismissiveness", "patronizing_wording", "ridicule"} & signal_set
                or behavior_ids & {"public_correction", "undermining"}
            ),
        ),
        (
            "tense",
            bool(
                behavior_ids & {"escalation", "deadline_pressure", "public_correction", "blame_shifting"}
                or {"implicit_accusation", "institutional_pressure_framing", "procedural_intimidation"} & signal_set
            ),
        ),
    )
    return [cast(CommunicationClass, label) for label, enabled in rules if enabled]


def _append_optional(items, item):
    if item is not None:
        items.append(item)


def _escalation_behavior(rhetoric, signal_ids):
    signal_set = set(signal_ids)
    if "institutional_pressure_framing" in signal_set:
        derived = [
            item for item in ("institutional_pressure_framing", "procedural_intimidation", "status_marking") if item in signal_set
        ]
        return [
            _candidate(
                behavior_id="escalation",
                label="Escalation",
                confidence="medium",
                taxonomy_ids=["escalation_pressure"],
                rationale=(
                    "Escalation or formal-process wording suggests a behaviour-level pressure move rather than wording alone."
                ),
                evidence=_signal_evidence(rhetoric, signal_id="institutional_pressure_framing"),
                derived_from_signal_ids=derived,
                neutral_alternatives=["Routine escalation may be required by policy or time pressure."],
            )
        ], set(derived)
    derived = [item for item in ("procedural_intimidation", "status_marking") if item in signal_set]
    if not derived:
        return [], set()
    return [
        _candidate(
            behavior_id="escalation",
            label="Escalation",
            confidence="low",
            taxonomy_ids=["escalation_pressure"],
            rationale=(
                "Procedural pressure or hierarchy-marking without a clear substantive basis can still support a "
                "low-confidence escalation behaviour candidate."
            ),
            evidence=_signal_evidence(rhetoric, signal_id=derived[0]),
            derived_from_signal_ids=derived,
            neutral_alternatives=["Formal role or documentation language may be routine in the current workflow."],
        )
    ], set(derived)


def _deadline_behavior(text, text_scope):
    evidence = _match_evidence(text, pattern=_DEADLINE_RE, source_scope=text_scope)
    if not evidence:
        return None
    return _candidate(
        behavior_id="deadline_pressure",
        label="Deadline Pressure",
        confidence="medium",
        taxonomy_ids=["escalation_pressure", "unequal_demands"],
        rationale="Time-pressure wording suggests an action-demanding behavioural cue beyond tone alone.",
        evidence=evidence,
        derived_from_signal_ids=[],
        neutral_alternatives=["The deadline may be operationally justified or genuinely urgent."],
    )


def _public_correction_behavior(rhetoric, signal_ids, recipient_count):
    public_ids = ("implicit_accusation", "competence_framing", "ridicule", "patronizing_wording")
    derived = [item for item in public_ids if item in signal_ids]
    if recipient_count <= 1:
        return None, [], "No multi-recipient visibility for public-correction inference."
    if not derived:
        return None, [], ""
    return (
        _candidate(
            behavior_id="public_correction",
            label="Public Correction",
            confidence="medium",
            taxonomy_ids=["public_criticism"],
            rationale=(
                "Corrective, accusatory, or patronizing wording sent to multiple visible recipients can indicate "
                "a disproportionate public-correction behaviour."
            ),
            evidence=_signal_evidence(rhetoric, signal_id=derived[0]),
            derived_from_signal_ids=derived,
            neutral_alternatives=["A wider recipient list may be operationally necessary for shared work tracking."],
        ),
        derived,
        "",
    )


def _undermining_behavior(rhetoric, signal_ids):
    derived = [item for item in ("competence_framing", "ridicule", "patronizing_wording") if item in signal_ids]
    if not derived:
        return None, []
    if "dismissiveness" in signal_ids:
        derived.append("dismissiveness")
    return _candidate(
        behavior_id="undermining",
        label="Undermining",
        confidence="medium",
        taxonomy_ids=["undermining_credibility"],
        rationale=(
            "Credibility-, capability-, or patronizing framing can indicate a degrading or credibility-"
            "undermining behaviour rather than tone alone."
        ),
        evidence=_signal_evidence(rhetoric, signal_id=derived[0]),
        derived_from_signal_ids=derived,
        neutral_alternatives=[
            "The wording may reflect a one-off correction or performance concern rather than a broader behavioural pattern."
        ],
    ), derived


def _blame_behavior(text, text_scope, rhetoric, signal_ids):
    evidence = _match_evidence(text, pattern=_BLAME_SHIFTING_RE, source_scope=text_scope)
    derived = [item for item in ("implicit_accusation", "strategic_ambiguity", "selective_accountability") if item in signal_ids]
    if not evidence and not {"implicit_accusation", "strategic_ambiguity"} <= set(signal_ids):
        return None, []
    return _candidate(
        behavior_id="blame_shifting",
        label="Blame-shifting",
        confidence="low" if evidence else "medium",
        taxonomy_ids=["blame_shifting"],
        rationale=(
            "Responsibility-framing that shifts failure or causation onto one person can indicate a "
            "narrative-framing or blame-shifting behaviour candidate."
        ),
        evidence=evidence or _signal_evidence(rhetoric, signal_id=derived[0]),
        derived_from_signal_ids=derived,
        neutral_alternatives=[
            "The record may reflect accurate attribution of responsibility rather than unfair narrative framing."
        ],
    ), derived


def _selective_accountability_behavior(text, text_scope):
    evidence = _match_evidence(text, pattern=_SELECTIVE_ACCOUNTABILITY_RE, source_scope=text_scope)
    if not evidence:
        return None
    return _candidate(
        behavior_id="selective_accountability",
        label="Selective Accountability",
        confidence="medium",
        taxonomy_ids=["unequal_demands", "blame_shifting"],
        rationale=(
            "Language assigning sole or exceptional responsibility suggests a selective-accountability behaviour candidate."
        ),
        evidence=evidence,
        derived_from_signal_ids=[],
        neutral_alternatives=["The actor may genuinely own the task in that specific workflow."],
    )


def _omission_behaviors(text, target, visible_recipients):
    evidence = _metadata_evidence(
        excerpt=f"Target {target} absent from visible recipients {visible_recipients}.", matched_text=target
    )
    items = [
        _candidate(
            behavior_id="exclusion",
            label="Exclusion",
            confidence="low",
            taxonomy_ids=["exclusion"],
            rationale=(
                "The case target is referenced in the message context but is absent from visible recipients, "
                "which can support an exclusion hypothesis."
            ),
            evidence=evidence,
            derived_from_signal_ids=[],
            neutral_alternatives=["The message may concern the target without requiring them as a recipient."],
        )
    ]
    if _DECISION_UPDATE_RE.search(text or ""):
        items.append(
            _candidate(
                behavior_id="withholding",
                label="Withholding Information",
                confidence="low",
                taxonomy_ids=["withholding_information", "exclusion"],
                rationale=(
                    "Decision- or update-framing combined with target absence can suggest a withholding-information "
                    "behaviour candidate."
                ),
                evidence=_metadata_evidence(
                    excerpt=(
                        f"Decision/update wording present while target {target} is absent from visible recipients "
                        f"{visible_recipients}."
                    ),
                    matched_text=target,
                ),
                derived_from_signal_ids=[],
                neutral_alternatives=[
                    "The update may be preparatory and later communicated to the target through another channel."
                ],
            )
        )
    return items


def analyze_message_behavior(
    text: str,
    *,
    text_scope: Literal["authored_text", "quoted_text"],
    rhetoric: MessageRhetoricAnalysis,
    recipient_count: int = 0,
    visible_recipient_emails: list[str] | None = None,
    case_target_email: str = "",
    case_target_name: str = "",
) -> MessageBehaviorAnalysis:
    """Analyze a message for behavioral patterns and communication classification.

    Args:
        text: The message text to analyze.
        text_scope: Whether the text is authored or quoted.
        rhetoric: Pre-computed rhetoric analysis of the message.
        recipient_count: Number of visible recipients.
        visible_recipient_emails: List of visible recipient email addresses.
        case_target_email: Email address of the case target.
        case_target_name: Name of the case target.

    Returns:
        A complete MessageBehaviorAnalysis with behavior candidates, signals,
        classification, and supporting evidence.

    """
    visible_recipient_emails = _normalized_emails(visible_recipient_emails)
    target_email = case_target_email.strip().lower()
    target_label = target_email or case_target_name or "case target"
    lowered_text = str(text or "").casefold()
    signal_ids = _signal_ids(rhetoric)
    behavior_candidates, consumed_signal_ids, counter_indicators = _collect_behavior_candidates(
        text, text_scope, rhetoric, signal_ids, recipient_count
    )

    omission_target_linked = _omission_target_linked(
        text_scope, target_email, case_target_name, lowered_text, visible_recipient_emails
    )
    omission_candidates, omission_counter = _omission_results(
        omission_target_linked, text_scope, target_email, case_target_name, text, visible_recipient_emails
    )
    behavior_candidates.extend(omission_candidates)
    counter_indicators.extend(omission_counter)
    wording_only_signal_ids, wording_counter = _wording_status(signal_ids, consumed_signal_ids)
    counter_indicators.extend(wording_counter)

    included_actors = ordered_unique(visible_recipient_emails)
    excluded_actors = [target_email] if omission_target_linked else []
    relevant_wording = _relevant_wording(rhetoric=rhetoric, behavior_candidates=behavior_candidates)
    process_signals = _process_signals(
        signal_ids=signal_ids,
        behavior_candidates=behavior_candidates,
        omission_target_linked=omission_target_linked,
        target_label=target_label,
    )
    classification = _communication_classification(
        signal_ids=signal_ids,
        behavior_candidates=behavior_candidates,
        omission_target_linked=omission_target_linked,
    )
    return normalize_message_behavior_analysis(
        _analysis_payload(
            text_scope,
            behavior_candidates,
            wording_only_signal_ids,
            counter_indicators,
            classification,
            signal_ids,
            relevant_wording,
            process_signals,
            included_actors,
            excluded_actors,
        ),
        text_scope=text_scope,
    )


def _collect_behavior_candidates(text, text_scope, rhetoric, signal_ids, recipient_count):
    candidates, consumed = _escalation_behavior(rhetoric, signal_ids)
    _append_optional(candidates, _deadline_behavior(text, text_scope))
    public_candidate, public_consumed, public_counter = _public_correction_behavior(rhetoric, signal_ids, recipient_count)
    _append_optional(candidates, public_candidate)
    consumed.update(public_consumed)
    candidate, more_consumed = _undermining_behavior(rhetoric, signal_ids)
    _append_optional(candidates, candidate)
    consumed.update(more_consumed)
    candidate, more_consumed = _blame_behavior(text, text_scope, rhetoric, signal_ids)
    _append_optional(candidates, candidate)
    consumed.update(more_consumed)
    _append_optional(candidates, _selective_accountability_behavior(text, text_scope))
    return candidates, consumed, [public_counter] if public_counter else []


def _omission_results(linked, text_scope, target_email, target_name, text, visible_emails):
    if linked:
        return _omission_behaviors(text, target_email or target_name, visible_emails), []
    if text_scope != "authored_text":
        return [], []
    message = (
        "Case target appears in visible recipients, so omission-based exclusion checks stayed negative."
        if target_email
        else "No case target email available for omission-aware checks."
    )
    return [], [message]


def _wording_status(signal_ids, consumed):
    wording_ids = [signal_id for signal_id in signal_ids if signal_id not in consumed]
    counters = (
        ["Some rhetorical cues remained wording-only because message-level behavioural support was insufficient."]
        if wording_ids
        else []
    )
    return wording_ids, counters


def _normalized_emails(emails):
    return [str(email).strip().lower() for email in (emails or []) if email]


def _omission_target_linked(text_scope, target_email, target_name, lowered_text, visible_emails):
    target_named = bool(target_name and target_name.casefold() in lowered_text)
    target_excluded = bool(target_email and visible_emails and target_email not in visible_emails)
    target_referenced = bool(target_named or (target_email and target_email in lowered_text))
    return bool(text_scope == "authored_text" and target_excluded and target_referenced)


def _analysis_payload(
    text_scope,
    behavior_candidates,
    wording_ids,
    counter_indicators,
    classification,
    signal_ids,
    relevant_wording,
    process_signals,
    included_actors,
    excluded_actors,
):
    return {
        "text_scope": text_scope,
        "behavior_candidate_count": len(behavior_candidates),
        "behavior_candidates": behavior_candidates,
        "wording_only_signal_ids": wording_ids,
        "counter_indicators": counter_indicators,
        "tone_summary": _tone_summary(
            classification=classification,
            behavior_candidates=behavior_candidates,
            signal_ids=signal_ids,
        ),
        "relevant_wording": relevant_wording,
        "omissions_or_process_signals": process_signals,
        "included_actors": included_actors,
        "excluded_actors": excluded_actors,
        "communication_classification": classification,
    }
