"""Executable wave definitions for question-first matter review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mcp_models import EmailCaseAnalysisInput


_UMLAUT_ASCII = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
    }
)


@dataclass(frozen=True)
class WaveDefinition:
    """Stable execution metadata for one question wave."""

    wave_id: str
    label: str
    question_ids: tuple[str, ...]
    issue_terms: tuple[str, ...]
    attachment_terms: tuple[str, ...] = ()
    english_fallback_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class WaveQueryLane:
    """Structured query-lane metadata for wave execution."""

    lane_class: str
    query: str


WAVE_DEFINITIONS: dict[str, WaveDefinition] = {
    "wave_1": WaveDefinition(
        wave_id="wave_1",
        label="Dossier Reconciliation",
        question_ids=("Q10", "Q11", "Q34"),
        issue_terms=("Protokoll", "TOP 7", "PR-Sitzung", "mobiles Arbeiten", "BEM", "Physiotherapie"),
        attachment_terms=("Protokoll", "Meeting Summary", "BEM", "calendar", "invite"),
        english_fallback_terms=("protocol", "mobile work", "BEM", "meeting note"),
    ),
    "wave_2": WaveDefinition(
        wave_id="wave_2",
        label="Null-Result And Silence Evidence",
        question_ids=("Q1", "Q12", "Q24", "Q37"),
        issue_terms=("Bitte um Klärung", "keine Antwort", "Frist", "Rückmeldung", "HR mailbox", "SBV"),
        attachment_terms=("meeting", "invite", "follow-up"),
        english_fallback_terms=("no reply", "clarification", "deadline", "follow-up"),
    ),
    "wave_3": WaveDefinition(
        wave_id="wave_3",
        label="Complaint To Reaction Chains",
        question_ids=("Q13", "Q14", "Q21", "Q22", "Q26", "Q30"),
        issue_terms=("dringend", "Unterstützungsplan", "Stellungnahme", "Antwort", "Besprechung", "Maßnahme"),
        attachment_terms=("Protokoll", "action list", "meeting"),
        english_fallback_terms=("escalation", "response", "implementation", "deadline"),
    ),
    "wave_4": WaveDefinition(
        wave_id="wave_4",
        label="Home Office Differential",
        question_ids=("Q8", "Q32"),
        issue_terms=("Dienstvereinbarung", "mobiles Arbeiten", "20 Prozent", "Kollegen", "Physiotherapie"),
        attachment_terms=("DV", "policy", "calendar", "mobile"),
        english_fallback_terms=("mobile work", "policy", "comparator"),
    ),
    "wave_5": WaveDefinition(
        wave_id="wave_5",
        label="Eingruppierung And Task Withdrawal",
        question_ids=("Q7", "Q15", "Q33", "Q36"),
        issue_terms=("Eingruppierung", "Tätigkeitsdarstellung", "Aufgabenentzug", "Projektbrief", "Rollenklärung"),
        attachment_terms=("Aufgaben", "Projekt", "Tätigkeit", "Bewertung"),
        english_fallback_terms=("task withdrawal", "duties", "role clarification"),
    ),
    "wave_5a": WaveDefinition(
        wave_id="wave_5a",
        label="EG12 Proof-Building",
        question_ids=("Q17", "Q18", "Q19", "Q20"),
        issue_terms=("EG 12", "E12", "Eingruppierung", "tariflich", "Übertragung"),
        attachment_terms=("tarif", "payroll", "EG12", "Arbeitsvorgang"),
        english_fallback_terms=("EG12", "classification", "payroll"),
    ),
    "wave_5b": WaveDefinition(
        wave_id="wave_5b",
        label="Project Brief And Role Ownership",
        question_ids=("Q33",),
        issue_terms=("Projektbrief", "Rollenverantwortung", "Zuständigkeit", "Briefing"),
        attachment_terms=("project", "brief", "task board"),
        english_fallback_terms=("project brief", "ownership", "role evidence"),
    ),
    "wave_6": WaveDefinition(
        wave_id="wave_6",
        label="BEM And Prevention Failures",
        question_ids=("Q5", "Q6", "Q27", "Q28", "Q29"),
        issue_terms=("BEM", "§ 167", "SGB IX", "Prävention", "Empfehlung", "AU"),
        attachment_terms=("BEM", "invite", "medical", "recommendation"),
        english_fallback_terms=("BEM", "section 167", "prevention", "recommendation"),
    ),
    "wave_7": WaveDefinition(
        wave_id="wave_7",
        label="SBV And PR Participation",
        question_ids=("Q3", "Q4", "Q25", "Q38"),
        issue_terms=("SBV", "Personalrat", "Beteiligung", "Anhörung", "Mitbestimmung"),
        attachment_terms=("SBV", "PR", "participation", "record"),
        english_fallback_terms=("SBV", "works council", "participation"),
    ),
    "wave_8": WaveDefinition(
        wave_id="wave_8",
        label="time system And Attendance Control",
        question_ids=("Q9", "Q31"),
        issue_terms=("time system", "Zeiterfassung", "Umbuchung", "Arbeitszeit", "Kontrolle"),
        attachment_terms=("time system", "attendance", "csv", "timesheet"),
        english_fallback_terms=("time system", "attendance", "rebooking"),
    ),
    "wave_9": WaveDefinition(
        wave_id="wave_9",
        label="Coordination And Actor Cluster Analysis",
        question_ids=("Q2", "Q16", "Q23", "Q35", "Q39"),
        issue_terms=("Koordination", "Weiterleitung", "Kalender", "Absage", "HR mailbox", "Vergleichsperson"),
        attachment_terms=("calendar", "invite", "cancellation", "actor map"),
        english_fallback_terms=("coordination", "routing", "calendar", "comparator"),
    ),
    "wave_10": WaveDefinition(
        wave_id="wave_10",
        label="Open Questions Register",
        question_ids=tuple(f"Q{index}" for index in range(1, 40)),
        issue_terms=("offene Fragen", "fehlender Nachweis", "Dokumentenanforderung", "Lücke", "Refresh"),
        attachment_terms=("record", "request", "missing"),
        english_fallback_terms=("open questions", "missing record", "refresh"),
    ),
}


def canonical_wave_id(value: str) -> str:
    """Normalize user-facing wave identifiers to the internal canonical key."""
    compact = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())
    aliases = {
        "1": "wave_1",
        "wave1": "wave_1",
        "2": "wave_2",
        "wave2": "wave_2",
        "3": "wave_3",
        "wave3": "wave_3",
        "4": "wave_4",
        "wave4": "wave_4",
        "5": "wave_5",
        "wave5": "wave_5",
        "5a": "wave_5a",
        "wave5a": "wave_5a",
        "5b": "wave_5b",
        "wave5b": "wave_5b",
        "6": "wave_6",
        "wave6": "wave_6",
        "7": "wave_7",
        "wave7": "wave_7",
        "8": "wave_8",
        "wave8": "wave_8",
        "9": "wave_9",
        "wave9": "wave_9",
        "10": "wave_10",
        "wave10": "wave_10",
    }
    return aliases.get(compact, "")


def list_wave_definitions() -> tuple[WaveDefinition, ...]:
    """Return wave definitions in execution order."""
    return tuple(
        WAVE_DEFINITIONS[key]
        for key in (
            "wave_1",
            "wave_2",
            "wave_3",
            "wave_4",
            "wave_5",
            "wave_5a",
            "wave_5b",
            "wave_6",
            "wave_7",
            "wave_8",
            "wave_9",
            "wave_10",
        )
    )


def get_wave_definition(wave_id: str) -> WaveDefinition:
    """Return the definition for one wave id or alias."""
    normalized = canonical_wave_id(wave_id)
    if not normalized or normalized not in WAVE_DEFINITIONS:
        known = ", ".join(definition.wave_id for definition in list_wave_definitions())
        raise ValueError(f"Unknown wave id: {wave_id}. Use one of: {known}")
    return WAVE_DEFINITIONS[normalized]


def _ascii_variant(text: str) -> str:
    return text.translate(_UMLAUT_ASCII)


def _normalized_unique(values: list[str], *, limit: int | None = None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        compact = " ".join(str(value or "").split()).strip()
        lowered = compact.casefold()
        if not compact or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(compact)
        if limit is not None and len(normalized) >= limit:
            break
    return normalized


def _issue_variants(terms: tuple[str, ...]) -> list[str]:
    variants: list[str] = []
    for term in terms:
        compact = " ".join(str(term or "").split()).strip()
        if not compact:
            continue
        variants.append(compact)
        ascii_variant = _ascii_variant(compact)
        if ascii_variant != compact:
            variants.append(ascii_variant)
    return _normalized_unique(variants, limit=8)


def _english_issue_variants(terms: tuple[str, ...]) -> list[str]:
    return _normalized_unique([str(term).strip() for term in terms if str(term).strip()], limit=6)


def shared_wave_vocabulary(*, limit: int | None = None) -> list[str]:
    """Return a bounded shared retrieval vocabulary derived from wave taxonomy."""
    terms: list[str] = []
    for definition in list_wave_definitions():
        terms.extend(_issue_variants(definition.issue_terms))
        terms.extend(_issue_variants(definition.attachment_terms))
        terms.extend(_english_issue_variants(definition.english_fallback_terms))
    return _normalized_unique(terms, limit=limit)


def _party_identity_terms(party: object) -> list[str]:
    terms: list[str] = []
    name = str(getattr(party, "name", "") or "").strip()
    email = str(getattr(party, "email", "") or "").strip()
    role_hint = str(getattr(party, "role_hint", "") or "").strip()
    if name:
        terms.append(name)
        parts = [item for item in name.replace(",", " ").split() if item.strip()]
        if len(parts) >= 2:
            terms.append(" ".join(parts[-2:]))
            terms.append(parts[-1])
    if email:
        terms.append(email)
        local_part = email.split("@", 1)[0].strip()
        if local_part:
            terms.append(local_part.replace(".", " "))
    if role_hint:
        terms.append(role_hint)
    return terms


def _institutional_actor_terms(actor: object) -> list[str]:
    terms: list[str] = []
    label = str(getattr(actor, "label", "") or "").strip()
    email = str(getattr(actor, "email", "") or "").strip()
    function = str(getattr(actor, "function", "") or "").strip()
    if label:
        terms.append(label)
    if email:
        terms.append(email)
        local_part = email.split("@", 1)[0].strip()
        if local_part:
            terms.append(local_part.replace(".", " ").replace("-", " "))
    if function:
        terms.append(function)
    return terms


def _actor_identity_term_groups(params: EmailCaseAnalysisInput) -> dict[str, list[str]]:
    case_scope = params.case_scope
    role_hints = [
        str(getattr(person, "role_hint", "") or "").strip()
        for person in [
            case_scope.target_person,
            *case_scope.suspected_actors,
            *case_scope.comparator_actors,
            *getattr(case_scope, "context_people", []),
        ]
        if str(getattr(person, "role_hint", "") or "").strip()
    ]
    return {
        "target": _normalized_unique(_party_identity_terms(case_scope.target_person), limit=4),
        "suspected": _normalized_unique(
            [term for actor in case_scope.suspected_actors[:4] for term in _party_identity_terms(actor)],
            limit=6,
        ),
        "comparator": _normalized_unique(
            [term for actor in case_scope.comparator_actors[:4] for term in _party_identity_terms(actor)],
            limit=6,
        ),
        "context_people": _normalized_unique(
            [term for actor in getattr(case_scope, "context_people", [])[:4] for term in _party_identity_terms(actor)],
            limit=6,
        ),
        "institutional": _normalized_unique(
            [term for actor in getattr(case_scope, "institutional_actors", [])[:4] for term in _institutional_actor_terms(actor)],
            limit=6,
        ),
        "role_hints": _normalized_unique(role_hints, limit=4),
    }


def _actor_identity_terms(params: EmailCaseAnalysisInput) -> list[str]:
    groups = _actor_identity_term_groups(params)
    return _normalized_unique(
        [
            *groups["target"],
            *groups["suspected"],
            *groups["comparator"],
            *groups["context_people"],
            *groups["institutional"],
            *groups["role_hints"],
        ],
        limit=10,
    )


def _trigger_terms(params: EmailCaseAnalysisInput) -> list[str]:
    terms: list[str] = []
    for event in list(params.case_scope.trigger_events)[:5]:
        event_bits = [
            str(getattr(event, "date", "") or "").strip(),
            str(getattr(event, "trigger_type", "") or "").replace("_", " ").strip(),
        ]
        terms.append(" ".join(bit for bit in event_bits if bit).strip())
    return _normalized_unique(terms, limit=5)


def _track_terms(params: EmailCaseAnalysisInput) -> list[str]:
    return _normalized_unique(
        [str(item).replace("_", " ").strip() for item in params.case_scope.employment_issue_tracks],
        limit=6,
    )


def _counterevidence_terms(definition: WaveDefinition) -> list[str]:
    label = definition.label.casefold()
    if "silence" in label or "null-result" in label:
        return ["keine Antwort", "keine Rückmeldung", "ohne Antwort", "ohne Reaktion"]
    if "coordination" in label or "actor cluster" in label:
        return ["Absage", "Weiterleitung", "ohne Beteiligung", "ohne Einbindung"]
    if "home office" in label or "mobile" in " ".join(definition.issue_terms).casefold():
        return ["abgelehnt", "widerrufen", "gestrichen", "keine Genehmigung"]
    if "bem" in label or any("bem" in item.casefold() for item in definition.issue_terms):
        return ["nicht umgesetzt", "ohne Maßnahme", "ohne Prävention", "keine Einladung"]
    return ["keine Antwort", "keine Rückmeldung", "abgelehnt", "nicht umgesetzt"]


def derive_wave_query_lane_specs(params: EmailCaseAnalysisInput, wave_id: str) -> list[WaveQueryLane]:
    """Return structured query lanes with explicit lane classes."""
    definition = get_wave_definition(wave_id)
    case_scope = params.case_scope
    target_name = str(case_scope.target_person.name or "").strip()
    target_email = str(case_scope.target_person.email or "").strip()
    target_bits = _normalized_unique([target_name, target_email], limit=2)
    actor_groups = _actor_identity_term_groups(params)
    suspected_terms = actor_groups["suspected"]
    comparator_terms = actor_groups["comparator"]
    context_people_terms = actor_groups["context_people"]
    institutional_terms = actor_groups["institutional"]
    role_hint_terms = actor_groups["role_hints"]
    trigger_terms = _trigger_terms(params)
    track_terms = _track_terms(params)
    issue_terms = _issue_variants(definition.issue_terms)
    attachment_terms = _issue_variants(definition.attachment_terms)
    english_terms = _english_issue_variants(definition.english_fallback_terms)
    counter_terms = _counterevidence_terms(definition)

    lane_specs = [
        WaveQueryLane(
            lane_class="actor_seeded_management",
            query=" ".join(
                [
                    *target_bits,
                    *(suspected_terms or role_hint_terms)[:3],
                    *context_people_terms[:2],
                    *issue_terms[:2],
                    *english_terms[:2],
                ]
            ).strip(),
        ),
        WaveQueryLane(
            lane_class="comparator_actor_anchor",
            query=" ".join(
                [
                    *target_bits[:1],
                    *(comparator_terms or role_hint_terms)[:3],
                    *context_people_terms[:1],
                    *issue_terms[:2],
                    *english_terms[:1],
                ]
            ).strip(),
        ),
        WaveQueryLane(
            lane_class="actor_free_issue_family",
            query=" ".join([*issue_terms[:4], *english_terms[:2], *track_terms[:2]]).strip(),
        ),
        WaveQueryLane(
            lane_class="temporal_event",
            query=" ".join(
                [*target_bits[:1], *trigger_terms[:2], *issue_terms[:2], *english_terms[:1], *track_terms[:2]]
            ).strip(),
        ),
        WaveQueryLane(
            lane_class="attachment_or_record",
            query=" ".join(
                [
                    *target_bits[:1],
                    *attachment_terms[:3],
                    *institutional_terms[:2],
                    *english_terms[:2],
                    *issue_terms[:1],
                    *track_terms[:1],
                ]
            ).strip(),
        ),
        WaveQueryLane(
            lane_class="counterevidence_or_silence",
            query=" ".join([*target_bits[:1], *counter_terms[:3], *issue_terms[:1], *english_terms[:1]]).strip(),
        ),
    ]

    normalized: list[WaveQueryLane] = []
    seen: set[str] = set()
    for spec in lane_specs:
        compact = " ".join(spec.query.split()).strip()
        lowered = compact.casefold()
        if not compact or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(WaveQueryLane(lane_class=spec.lane_class, query=compact[:500]))
    return normalized[:6]


def derive_wave_query_lanes(params: EmailCaseAnalysisInput, wave_id: str) -> list[str]:
    """Return ordered query lanes for one executable wave."""
    specs = derive_wave_query_lane_specs(params, wave_id)
    return [spec.query for spec in specs]
