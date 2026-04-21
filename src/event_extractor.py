"""German-first rule-based event extraction for email ingest."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .language_detector import detect_language_details

EVENT_EXTRACTOR_VERSION = "de_event_rule_v1"
_LOW_SIGNAL_EVENT_CONFIDENCE = "low"

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


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _surface_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _event_key(
    *,
    uid: str,
    event_kind: str,
    source_scope: str,
    surface_scope: str,
    segment_ordinal: int | None,
    char_start: int,
    char_end: int,
    trigger_text: str,
    event_date: str,
) -> str:
    seed = "|".join(
        (
            uid,
            event_kind,
            source_scope,
            surface_scope,
            str(segment_ordinal if segment_ordinal is not None else ""),
            str(char_start),
            str(char_end),
            trigger_text.casefold(),
            event_date,
        )
    )
    return hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()


def _segment_surface_candidates(email: Any) -> list[tuple[str, str, int | None, str]]:
    candidates: list[tuple[str, str, int | None, str]] = []
    for index, segment in enumerate(getattr(email, "segments", None) or []):
        segment_type = str(getattr(segment, "segment_type", "") or "")
        text = _clean_text(getattr(segment, "text", ""))
        if not text:
            continue
        source_scope = {
            "authored_body": "authored_body",
            "quoted_reply": "quoted_body",
            "forwarded_message": "quoted_body",
            "header_block": "forwarded_header",
        }.get(segment_type, "segment_text")
        try:
            ordinal = int(getattr(segment, "ordinal", index))
        except (TypeError, ValueError):
            ordinal = index
        candidates.append((source_scope, "message_segments", ordinal, text))
    return candidates


def _attachment_surface_candidates(email: Any) -> list[tuple[str, str, int | None, str]]:
    candidates: list[tuple[str, str, int | None, str]] = []
    for index, attachment in enumerate(getattr(email, "attachments", None) or []):
        if not isinstance(attachment, dict):
            continue
        text = _clean_text(
            attachment.get("normalized_text") or attachment.get("extracted_text") or attachment.get("text_preview") or ""
        )
        if not text:
            continue
        candidates.append(("attachment_text", "attachments", index, text))
    return candidates


def _is_boilerplate_surface(text: str) -> bool:
    compact = _clean_text(text).casefold()
    if not compact:
        return True
    if len(compact) > 600:
        return False
    marker_count = len(_FOOTER_PATTERN.findall(compact))
    return marker_count >= 2


def _extract_from_candidates(
    *,
    uid: str,
    event_date: str,
    candidates: list[tuple[str, str, int | None, str]],
    seen_event_keys: set[str],
    degrade_confidence: bool,
    skip_boilerplate: bool,
) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for source_scope, surface_scope, segment_ordinal, text in candidates:
        if not text:
            continue
        if skip_boilerplate and _is_boilerplate_surface(text):
            continue
        surface_hash = _surface_hash(text)
        language_details = detect_language_details(text)
        detected_language = str(language_details.get("language") or "unknown")
        confidence = str(language_details.get("confidence") or "low")
        if degrade_confidence and confidence != _LOW_SIGNAL_EVENT_CONFIDENCE:
            confidence = _LOW_SIGNAL_EVENT_CONFIDENCE
        for event_kind, pattern in _EVENT_RULES:
            for match in pattern.finditer(text):
                trigger_text = _clean_text(match.group(0))
                if not trigger_text:
                    continue
                char_start = int(match.start())
                char_end = int(match.end())
                event_key = _event_key(
                    uid=uid,
                    event_kind=event_kind,
                    source_scope=source_scope,
                    surface_scope=surface_scope,
                    segment_ordinal=segment_ordinal,
                    char_start=char_start,
                    char_end=char_end,
                    trigger_text=trigger_text,
                    event_date=event_date,
                )
                if event_key in seen_event_keys:
                    continue
                seen_event_keys.add(event_key)
                provenance = {
                    "source_scope": source_scope,
                    "surface_scope": surface_scope,
                    "segment_ordinal": segment_ordinal,
                    "char_start": char_start,
                    "char_end": char_end,
                    "surface_hash": surface_hash,
                    "quoted_guardrail_fallback": bool(degrade_confidence),
                }
                rows.append(
                    (
                        event_key,
                        uid,
                        event_kind,
                        source_scope,
                        surface_scope,
                        segment_ordinal,
                        char_start,
                        char_end,
                        trigger_text,
                        event_date,
                        surface_hash,
                        detected_language,
                        confidence,
                        EVENT_EXTRACTOR_VERSION,
                        json.dumps(provenance, ensure_ascii=True),
                    )
                )
    return rows


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

    rows.extend(
        _extract_from_candidates(
            uid=uid,
            event_date=event_date,
            candidates=[*primary_segment_candidates, *attachment_candidates],
            seen_event_keys=seen_event_keys,
            degrade_confidence=False,
            skip_boilerplate=True,
        )
    )
    if rows:
        return rows
    rows.extend(
        _extract_from_candidates(
            uid=uid,
            event_date=event_date,
            candidates=quoted_segment_candidates,
            seen_event_keys=seen_event_keys,
            degrade_confidence=True,
            skip_boilerplate=True,
        )
    )
    return rows
