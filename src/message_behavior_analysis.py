"""Per-message behavioural tagging helpers for behavioural analysis."""

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
    return [str(signal["signal_id"]) for signal in rhetoric.get("signals", [])]


def _relevant_wording(
    *,
    rhetoric: MessageRhetoricAnalysis,
    behavior_candidates: list[BehaviorCandidate],
) -> list[RelevantWording]:
    items: list[RelevantWording] = []
    seen: set[tuple[str, str, str]] = set()
    for signal in rhetoric.get("signals", []):
        if not isinstance(signal, dict):
            continue
        signal_id = str(signal.get("signal_id") or "")
        for evidence in signal.get("evidence", []) or []:
            if not isinstance(evidence, dict):
                continue
            text = str(evidence.get("matched_text") or evidence.get("excerpt") or "").strip()
            source_scope = str(evidence.get("source_text_scope") or "authored_text")
            key = (text, source_scope, f"signal:{signal_id}")
            if not text or key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "text": text,
                    "source_scope": source_scope,  # type: ignore[typeddict-item]
                    "basis_id": f"signal:{signal_id}",
                }
            )
    for candidate in behavior_candidates:
        behavior_id = str(candidate.get("behavior_id") or "")
        for behavior_evidence in candidate.get("evidence", []) or []:
            if not isinstance(behavior_evidence, dict):
                continue
            text = str(behavior_evidence.get("matched_text") or behavior_evidence.get("excerpt") or "").strip()
            source_scope = str(behavior_evidence.get("source_scope") or "authored_text")
            key = (text, source_scope, f"behavior:{behavior_id}")
            if not text or key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "text": text,
                    "source_scope": source_scope,  # type: ignore[typeddict-item]
                    "basis_id": f"behavior:{behavior_id}",
                }
            )
    return items[:6]


def _process_signals(
    *,
    signal_ids: list[str],
    behavior_candidates: list[BehaviorCandidate],
    omission_target_linked: bool,
    target_label: str,
) -> list[ProcessSignal]:
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
    applied: list[CommunicationClass] = []
    behavior_ids = {str(candidate.get("behavior_id") or "") for candidate in behavior_candidates}

    if behavior_ids & {"exclusion", "withholding"} or omission_target_linked:
        applied.append("exclusionary")
    if behavior_ids & {"selective_non_response"}:
        applied.append("retaliatory")
    if behavior_ids & {"deadline_pressure", "selective_accountability", "escalation"}:
        applied.append("controlling")
    if behavior_ids & {"blame_shifting"} or {"strategic_ambiguity", "passive_aggressive_deflection"} & set(signal_ids):
        applied.append("defensive")
    if {"dismissiveness", "patronizing_wording", "ridicule"} & set(signal_ids) or behavior_ids & {
        "public_correction",
        "undermining",
    }:
        applied.append("dismissive")
    if behavior_ids & {"escalation", "deadline_pressure", "public_correction", "blame_shifting"} or {
        "implicit_accusation",
        "institutional_pressure_framing",
        "procedural_intimidation",
    } & set(signal_ids):
        applied.append("tense")

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
    visible_recipient_emails = [str(email).strip().lower() for email in (visible_recipient_emails or []) if email]
    target_email = case_target_email.strip().lower()
    target_label = target_email or case_target_name or "case target"
    lowered_text = str(text or "").casefold()
    signal_ids = _signal_ids(rhetoric)
    behavior_candidates: list[BehaviorCandidate] = []
    consumed_signal_ids: set[str] = set()
    counter_indicators: list[str] = []

    if "institutional_pressure_framing" in signal_ids:
        derived_from = ["institutional_pressure_framing"]
        if "procedural_intimidation" in signal_ids:
            derived_from.append("procedural_intimidation")
        if "status_marking" in signal_ids:
            derived_from.append("status_marking")
        behavior_candidates.append(
            _candidate(
                behavior_id="escalation",
                label="Escalation",
                confidence="medium",
                taxonomy_ids=["escalation_pressure"],
                rationale=(
                    "Escalation or formal-process wording suggests a behaviour-level pressure move rather than wording alone."
                ),
                evidence=_signal_evidence(rhetoric, signal_id="institutional_pressure_framing"),
                derived_from_signal_ids=derived_from,
                neutral_alternatives=["Routine escalation may be required by policy or time pressure."],
            )
        )
        consumed_signal_ids.update(derived_from)
    elif {"procedural_intimidation", "status_marking"} & set(signal_ids):
        derived_from = [signal_id for signal_id in ("procedural_intimidation", "status_marking") if signal_id in signal_ids]
        behavior_candidates.append(
            _candidate(
                behavior_id="escalation",
                label="Escalation",
                confidence="low",
                taxonomy_ids=["escalation_pressure"],
                rationale=(
                    "Procedural pressure or hierarchy-marking without a clear substantive basis can still support a "
                    "low-confidence escalation behaviour candidate."
                ),
                evidence=_signal_evidence(rhetoric, signal_id=derived_from[0]),
                derived_from_signal_ids=derived_from,
                neutral_alternatives=["Formal role or documentation language may be routine in the current workflow."],
            )
        )
        consumed_signal_ids.update(derived_from)

    deadline_evidence = _match_evidence(text, pattern=_DEADLINE_RE, source_scope=text_scope)
    if deadline_evidence:
        behavior_candidates.append(
            _candidate(
                behavior_id="deadline_pressure",
                label="Deadline Pressure",
                confidence="medium",
                taxonomy_ids=["escalation_pressure", "unequal_demands"],
                rationale="Time-pressure wording suggests an action-demanding behavioural cue beyond tone alone.",
                evidence=deadline_evidence,
                derived_from_signal_ids=[],
                neutral_alternatives=["The deadline may be operationally justified or genuinely urgent."],
            )
        )

    if recipient_count > 1 and (
        "implicit_accusation" in signal_ids
        or "competence_framing" in signal_ids
        or "ridicule" in signal_ids
        or "patronizing_wording" in signal_ids
    ):
        derived_from = [
            signal_id
            for signal_id in ("implicit_accusation", "competence_framing", "ridicule", "patronizing_wording")
            if signal_id in signal_ids
        ]
        evidence = (
            _signal_evidence(rhetoric, signal_id=derived_from[0])
            if derived_from
            else _metadata_evidence(
                excerpt=f"Message has {recipient_count} visible recipients.",
                matched_text=f"recipient_count={recipient_count}",
            )
        )
        behavior_candidates.append(
            _candidate(
                behavior_id="public_correction",
                label="Public Correction",
                confidence="medium",
                taxonomy_ids=["public_criticism"],
                rationale=(
                    "Corrective, accusatory, or patronizing wording sent to multiple visible recipients can indicate "
                    "a disproportionate public-correction behaviour."
                ),
                evidence=evidence,
                derived_from_signal_ids=derived_from,
                neutral_alternatives=["A wider recipient list may be operationally necessary for shared work tracking."],
            )
        )
        consumed_signal_ids.update(derived_from)
    elif recipient_count <= 1:
        counter_indicators.append("No multi-recipient visibility for public-correction inference.")

    if {"competence_framing", "ridicule", "patronizing_wording"} & set(signal_ids):
        derived_from = [
            signal_id for signal_id in ("competence_framing", "ridicule", "patronizing_wording") if signal_id in signal_ids
        ]
        if "dismissiveness" in signal_ids:
            derived_from.append("dismissiveness")
        behavior_candidates.append(
            _candidate(
                behavior_id="undermining",
                label="Undermining",
                confidence="medium",
                taxonomy_ids=["undermining_credibility"],
                rationale=(
                    "Credibility-, capability-, or patronizing framing can indicate a degrading or credibility-"
                    "undermining behaviour rather than tone alone."
                ),
                evidence=_signal_evidence(rhetoric, signal_id=derived_from[0]),
                derived_from_signal_ids=derived_from,
                neutral_alternatives=[
                    "The wording may reflect a one-off correction or performance concern "
                    "rather than a broader behavioural pattern."
                ],
            )
        )
        consumed_signal_ids.update(derived_from)

    blame_shifting_evidence = _match_evidence(text, pattern=_BLAME_SHIFTING_RE, source_scope=text_scope)
    if blame_shifting_evidence or {"implicit_accusation", "strategic_ambiguity"} <= set(signal_ids):
        derived_from = [
            signal_id
            for signal_id in ("implicit_accusation", "strategic_ambiguity", "selective_accountability")
            if signal_id in signal_ids
        ]
        behavior_candidates.append(
            _candidate(
                behavior_id="blame_shifting",
                label="Blame-shifting",
                confidence="low" if blame_shifting_evidence else "medium",
                taxonomy_ids=["blame_shifting"],
                rationale=(
                    "Responsibility-framing that shifts failure or causation onto one person can indicate a "
                    "narrative-framing or blame-shifting behaviour candidate."
                ),
                evidence=blame_shifting_evidence or _signal_evidence(rhetoric, signal_id=derived_from[0]),
                derived_from_signal_ids=derived_from,
                neutral_alternatives=[
                    "The record may reflect accurate attribution of responsibility rather than unfair narrative framing."
                ],
            )
        )
        consumed_signal_ids.update(derived_from)

    selective_accountability_evidence = _match_evidence(
        text,
        pattern=_SELECTIVE_ACCOUNTABILITY_RE,
        source_scope=text_scope,
    )
    if selective_accountability_evidence:
        behavior_candidates.append(
            _candidate(
                behavior_id="selective_accountability",
                label="Selective Accountability",
                confidence="medium",
                taxonomy_ids=["unequal_demands", "blame_shifting"],
                rationale=(
                    "Language assigning sole or exceptional responsibility suggests "
                    "a selective-accountability behaviour candidate."
                ),
                evidence=selective_accountability_evidence,
                derived_from_signal_ids=[],
                neutral_alternatives=["The actor may genuinely own the task in that specific workflow."],
            )
        )

    target_named = bool(case_target_name and case_target_name.casefold() in lowered_text)
    target_excluded = bool(target_email and visible_recipient_emails and target_email not in visible_recipient_emails)
    target_referenced = bool(target_named or (target_email and target_email in lowered_text))
    omission_target_linked = bool(text_scope == "authored_text" and target_excluded and target_referenced)
    if omission_target_linked:
        behavior_candidates.append(
            _candidate(
                behavior_id="exclusion",
                label="Exclusion",
                confidence="low",
                taxonomy_ids=["exclusion"],
                rationale=(
                    "The case target is referenced in the message context but is absent from visible recipients, "
                    "which can support an exclusion hypothesis."
                ),
                evidence=_metadata_evidence(
                    excerpt=(
                        f"Target {target_email or case_target_name} absent from visible recipients {visible_recipient_emails}."
                    ),
                    matched_text=target_email or case_target_name,
                ),
                derived_from_signal_ids=[],
                neutral_alternatives=["The message may concern the target without requiring them as a recipient."],
            )
        )
        if _DECISION_UPDATE_RE.search(text or ""):
            behavior_candidates.append(
                _candidate(
                    behavior_id="withholding",
                    label="Withholding Information",
                    confidence="low",
                    taxonomy_ids=["withholding_information", "exclusion"],
                    rationale=(
                        "Decision- or update-framing combined with target absence can "
                        "suggest a withholding-information behaviour candidate."
                    ),
                    evidence=_metadata_evidence(
                        excerpt=(
                            f"Decision/update wording present while target {target_email or case_target_name} "
                            f"is absent from visible recipients {visible_recipient_emails}."
                        ),
                        matched_text=target_email or case_target_name,
                    ),
                    derived_from_signal_ids=[],
                    neutral_alternatives=[
                        "The update may be preparatory and later communicated to the target through another channel."
                    ],
                )
            )
    elif text_scope == "authored_text" and target_email:
        counter_indicators.append(
            "Case target appears in visible recipients, so omission-based exclusion checks stayed negative."
        )
    elif text_scope == "authored_text" and not target_email:
        counter_indicators.append("No case target email available for omission-aware checks.")

    wording_only_signal_ids = [signal_id for signal_id in signal_ids if signal_id not in consumed_signal_ids]
    if wording_only_signal_ids:
        counter_indicators.append(
            "Some rhetorical cues remained wording-only because message-level behavioural support was insufficient."
        )

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
        {
            "text_scope": text_scope,
            "behavior_candidate_count": len(behavior_candidates),
            "behavior_candidates": behavior_candidates,
            "wording_only_signal_ids": wording_only_signal_ids,
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
        },
        text_scope=text_scope,
    )
