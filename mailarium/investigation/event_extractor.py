"""German-first rule-based event extraction for email ingest."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from mailarium.model.surface_candidates import attachment_surface_candidates as _attachment_surface_candidates
from mailarium.model.surface_candidates import clean_text as _clean_text
from mailarium.model.surface_candidates import segment_surface_candidates as _segment_surface_candidates

from .language_detector import detect_language_details

EVENT_EXTRACTOR_VERSION = "de_event_rule_v1"
_LOW_SIGNAL_EVENT_CONFIDENCE = "low"
_EventRow = tuple[object, ...]
_Candidate = tuple[str, str, int | None, str]
_PreparedCandidate = tuple[str, str, int | None, str, str, str, str]

_FOOTER_PATTERN = re.compile(
    r"(?i)(confidential|vertraulich|disclaimer|haftungsausschluss|do not print|"
    r"diese e-mail|this email|intended recipient|automatisch erstellt)",
)

_EVENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "request",
        re.compile(r"(?i)\b(request|please|bitte|beantrage|ich bitte|ich ersuche|um rueckmeldung|um rückmeldung)\b"),
    ),
    (
        "denial",
        re.compile(r"(?i)\b(denied|cannot approve|not possible|abgelehnt|nicht moeglich|nicht möglich|nicht genehmigt)\b"),
    ),
    (
        "approval",
        re.compile(r"(?i)\b(approved|genehmigt|zugesagt|freigegeben|bewilligt)\b"),
    ),
    (
        "escalation",
        re.compile(r"(?i)\b(escalat|eskalation|compliance|rechtlich|legal team|vorstand|geschaeftsfuehrung|geschäftsführung)\b"),
    ),
    (
        "meeting_change",
        re.compile(r"(?i)\b(meeting|termin|besprechung|verschoben|rescheduled|calendar|einladung|invite)\b"),
    ),
    (
        "deadline_pressure",
        re.compile(r"(?i)\b(heute|bis morgen|deadline|frist|asap|sofort|umgehend|spaetestens|spätestens)\b"),
    ),
    (
        "exclusion_or_omission",
        re.compile(r"(?i)\b(not included|excluded|omit|ausgeschlossen|nicht beteiligt|nicht einbezogen|ohne sbv)\b"),
    ),
    (
        "accommodation_or_participation",
        re.compile(r"(?i)\b(bem|sgb\s*ix|schwerbehindertenvertretung|sbv|personalrat|betriebsrat|wiedereingliederung)\b"),
    ),
    (
        "comparator_treatment",
        re.compile(r"(?i)\b(comparator|vergleichsperson|ungleichbehandlung|gleichbehandlung|agg|peer treatment)\b"),
    ),
)


@dataclass(frozen=True)
class _EventMatch:
    """Immutable identity and persistence representation for one rule match."""

    uid: str
    event_kind: str
    source_scope: str
    surface_scope: str
    segment_ordinal: int | None
    char_start: int
    char_end: int
    trigger_text: str
    event_date: str
    surface_hash: str

    @property
    def event_key(self) -> str:
        """Return the stable event-record key for this exact match."""
        seed = "|".join(
            (
                self.uid,
                self.event_kind,
                self.source_scope,
                self.surface_scope,
                str(self.segment_ordinal if self.segment_ordinal is not None else ""),
                str(self.char_start),
                str(self.char_end),
                self.trigger_text.casefold(),
                self.event_date,
            )
        )
        return hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()

    def provenance_json(self, *, quoted_guardrail_fallback: bool) -> str:
        """Serialize the stable evidence provenance for this exact match."""
        provenance = {
            "source_scope": self.source_scope,
            "surface_scope": self.surface_scope,
            "segment_ordinal": self.segment_ordinal,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "surface_hash": self.surface_hash,
            "quoted_guardrail_fallback": quoted_guardrail_fallback,
        }
        return json.dumps(provenance, ensure_ascii=True)

    def row(
        self,
        *,
        detected_language: str,
        confidence: str,
        quoted_guardrail_fallback: bool,
    ) -> _EventRow:
        """Return the event-record upsert tuple for this exact match."""
        return (
            self.event_key,
            self.uid,
            self.event_kind,
            self.source_scope,
            self.surface_scope,
            self.segment_ordinal,
            self.char_start,
            self.char_end,
            self.trigger_text,
            self.event_date,
            self.surface_hash,
            detected_language,
            confidence,
            EVENT_EXTRACTOR_VERSION,
            self.provenance_json(quoted_guardrail_fallback=quoted_guardrail_fallback),
        )


@dataclass(frozen=True)
class _ExtractionPass:
    """Immutable extraction settings with a deliberately shared mutable dedupe set."""

    uid: str
    event_date: str
    seen_event_keys: set[str]
    degrade_confidence: bool
    skip_boilerplate: bool


def _surface_hash(text: str) -> str:
    """Compute SHA256 hash of text for surface identification."""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _is_boilerplate_surface(text: str) -> bool:
    """Check if a text surface appears to be boilerplate/footer content.

    Args:
        text: The text to check.

    Returns:
        True if the text is short and contains multiple footer-like markers,
        False otherwise.
    """
    compact = _clean_text(text).casefold()
    if not compact:
        return True
    if len(compact) > 600:
        return False
    marker_count = len(_FOOTER_PATTERN.findall(compact))
    return marker_count >= 2


def _extract_from_candidates(
    *,
    extraction_pass: _ExtractionPass,
    candidates: list[_Candidate],
) -> list[_EventRow]:
    """Extract event rows from text surface candidates.

    Args:
        extraction_pass: Stable metadata and shared deduplication state for this pass.
        candidates: List of text surface candidates to search for events.

    Returns:
        A list of event record tuples ready for database upsert.
    """
    rows: list[_EventRow] = []
    for candidate in _prepared_event_candidates(
        candidates=candidates,
        degrade_confidence=extraction_pass.degrade_confidence,
        skip_boilerplate=extraction_pass.skip_boilerplate,
    ):
        rows.extend(
            _event_rows_from_candidate(
                extraction_pass=extraction_pass,
                candidate=candidate,
            )
        )
    return rows


def _prepared_event_candidates(
    *,
    candidates: list[_Candidate],
    degrade_confidence: bool,
    skip_boilerplate: bool,
) -> Iterator[_PreparedCandidate]:
    """Yield eligible candidates with stable surface and language metadata."""
    for source_scope, surface_scope, segment_ordinal, text in candidates:
        if not text:
            continue
        if skip_boilerplate and _is_boilerplate_surface(text):
            continue
        surface_hash = _surface_hash(text)
        language_details = detect_language_details(text)
        detected_language = str(language_details.get("language") or "unknown")
        confidence = _event_confidence(language_details, degrade_confidence)
        yield source_scope, surface_scope, segment_ordinal, text, surface_hash, detected_language, confidence


def _event_rows_from_candidate(
    *,
    extraction_pass: _ExtractionPass,
    candidate: _PreparedCandidate,
) -> list[_EventRow]:
    """Create deduplicated event rows for one prepared text surface."""
    source_scope, surface_scope, segment_ordinal, text, surface_hash, detected_language, confidence = candidate
    rows: list[_EventRow] = []
    for event_kind, pattern in _EVENT_RULES:
        for match in pattern.finditer(text):
            trigger_text = _clean_text(match.group(0))
            if not trigger_text:
                continue
            char_start = int(match.start())
            char_end = int(match.end())
            event_match = _EventMatch(
                uid=extraction_pass.uid,
                event_kind=event_kind,
                source_scope=source_scope,
                surface_scope=surface_scope,
                segment_ordinal=segment_ordinal,
                char_start=char_start,
                char_end=char_end,
                trigger_text=trigger_text,
                event_date=extraction_pass.event_date,
                surface_hash=surface_hash,
            )
            event_key = event_match.event_key
            if event_key in extraction_pass.seen_event_keys:
                continue
            extraction_pass.seen_event_keys.add(event_key)
            rows.append(
                event_match.row(
                    detected_language=detected_language,
                    confidence=confidence,
                    quoted_guardrail_fallback=extraction_pass.degrade_confidence,
                )
            )
    return rows


def _event_confidence(details: dict[str, Any], degrade: bool) -> str:
    """Score event confidence from the number and strength of detected signals."""
    confidence = str(details.get("confidence") or "low")
    return _LOW_SIGNAL_EVENT_CONFIDENCE if degrade and confidence != _LOW_SIGNAL_EVENT_CONFIDENCE else confidence


def extract_event_rows_from_email(email: Any) -> list[tuple[object, ...]]:
    """Return normalized ``event_records`` upsert rows for one email."""
    uid = str(getattr(email, "uid", "") or "")
    if not uid:
        return []
    event_date = str(getattr(email, "date", "") or "")
    rows: list[tuple[object, ...]] = []
    seen_event_keys: set[str] = set()
    segment_candidates = _segment_surface_candidates(email)
    attachment_candidates = _attachment_surface_candidates(email)
    primary_segment_candidates = [
        candidate for candidate in segment_candidates if candidate[0] not in {"quoted_body", "forwarded_header"}
    ]
    quoted_segment_candidates = [
        candidate for candidate in segment_candidates if candidate[0] in {"quoted_body", "forwarded_header"}
    ]
    primary_pass = _ExtractionPass(
        uid=uid,
        event_date=event_date,
        seen_event_keys=seen_event_keys,
        degrade_confidence=False,
        skip_boilerplate=True,
    )

    rows.extend(
        _extract_from_candidates(
            extraction_pass=primary_pass,
            candidates=[*primary_segment_candidates, *attachment_candidates],
        )
    )
    if rows:
        return rows
    quoted_pass = _ExtractionPass(
        uid=uid,
        event_date=event_date,
        seen_event_keys=seen_event_keys,
        degrade_confidence=True,
        skip_boilerplate=True,
    )
    rows.extend(
        _extract_from_candidates(
            extraction_pass=quoted_pass,
            candidates=quoted_segment_candidates,
        )
    )
    return rows
