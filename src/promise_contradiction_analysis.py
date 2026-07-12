"""Promise-versus-action, omission, and contradiction analysis for mixed-source records."""
# pylint: disable=too-many-locals

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from ._utils import _as_dict, _as_list, _compact

PROMISE_CONTRADICTION_ANALYSIS_VERSION = "1"
_PROMISE_SOURCE_TYPES = {"meeting_note", "note_record", "email", "formal_document", "participation_record"}
_SUMMARY_SOURCE_TYPES = {"meeting_note", "note_record", "email", "formal_document", "participation_record"}
_PROMISE_CUES = (
    "will",
    "would",
    "shall",
    "agreed to",
    "agree to",
    "promised to",
    "promise to",
    "follow up",
    "next step",
    "will send",
    "will provide",
    "will share",
    "will review",
    "will schedule",
    "will invite",
    "will include",
    "wird",
    "werden",
    "zugesagt",
    "vereinbart",
    "nachreichen",
    "prüfen",
    "pruefen",
    "einladen",
    "beteiligen",
    "informieren",
)
_NEGATION_CUES = ("no", "not", "without", "never", "did not", "didn't", "kein", "keine", "ohne", "nicht")
_ACTION_TAGS: dict[str, tuple[str, ...]] = {
    "provide_documents": ("provide", "send", "share", "submit", "nachreichen", "senden", "teilen", "provide the", "send the"),
    "schedule_or_meet": ("schedule", "meeting", "invite", "calendar", "termin", "einladen", "besprechung"),
    "review_or_decide": ("review", "decide", "approval", "approve", "prüfen", "entscheidung", "freigabe"),
    "participation_or_consultation": (
        "consult",
        "participation",
        "sbv",
        "personalrat",
        "betriebsrat",
        "beteilig",
        "consultation",
    ),
    "include_or_inform": ("include", "inform", "copy", "cc", "einbeziehen", "informieren"),
}
_ALPHA_TOKEN_RE = re.compile(r"[^\W\d_]+")
_TOPIC_STOPWORDS = {
    "and",
    "the",
    "that",
    "this",
    "with",
    "about",
    "from",
    "into",
    "will",
    "would",
    "shall",
    "agreed",
    "agree",
    "promised",
    "promise",
    "follow",
    "next",
    "step",
    "send",
    "provide",
    "share",
    "review",
    "schedule",
    "invite",
    "include",
    "wird",
    "werden",
    "zugesagt",
    "vereinbart",
    "nachreichen",
    "prüfen",
    "pruefen",
    "einladen",
    "beteiligen",
    "informieren",
    "inform",
    "written",
    "summary",
    "und",
    "der",
    "die",
    "das",
    "einer",
    "einem",
    "einen",
}


def _source_text(source: dict[str, Any]) -> str:
    """Extract text content from a source dict for analysis.

    Combines title, snippet, and text_preview from documentary_support.
    """
    documentary = _as_dict(source.get("documentary_support"))
    return " ".join(
        part
        for part in (
            _compact(source.get("title")),
            _compact(source.get("snippet")),
            _compact(documentary.get("text_preview")),
        )
        if part
    )


def _content_text(source: dict[str, Any]) -> str:
    """Extract content text from a source dict (snippet and text_preview only).

    Unlike _source_text, this excludes the title.
    """
    documentary = _as_dict(source.get("documentary_support"))
    return " ".join(
        part
        for part in (
            _compact(source.get("snippet")),
            _compact(documentary.get("text_preview")),
        )
        if part
    )


def _source_date(source: dict[str, Any]) -> str:
    """Extract the date from a source dict.

    Checks chronology_anchor first, then falls back to source date.
    """
    chronology_anchor = _as_dict(source.get("chronology_anchor"))
    return str(chronology_anchor.get("date") or source.get("date") or "")


def _source_locator_payload(source: dict[str, Any]) -> dict[str, Any]:
    """Build a locator payload for a source.

    Tries document_locator first, then provenance.document_locator,
    then constructs one from evidence_handle or source_id.
    """
    locator = _as_dict(source.get("document_locator"))
    if locator:
        return locator
    provenance = _as_dict(source.get("provenance"))
    if _as_dict(provenance.get("document_locator")):
        return _as_dict(provenance.get("document_locator"))
    evidence_handle = str(provenance.get("evidence_handle") or source.get("source_id") or "")
    if not evidence_handle:
        return {}
    return {
        "kind": "source_reference",
        "evidence_handle": evidence_handle,
        "source_id": str(source.get("source_id") or ""),
        "uid": str(source.get("uid") or ""),
    }


def _parse_ordering_datetime(value: str) -> datetime | None:
    """Parse a date or datetime string into a timezone-aware datetime.

    Handles ISO date format (YYYY-MM-DD) and ISO datetime format.
    Returns None if parsing fails.
    """
    raw = _compact(value)
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            parsed_date = date.fromisoformat(raw)
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_stitched_thread_export(source: dict[str, Any]) -> bool:
    """Check if a source is a stitched thread export.

    Identifies formal_document sources that appear to be stitched email threads
    based on source_id, title, or content containing multiple email headers.
    """
    if str(source.get("source_type") or "") != "formal_document":
        return False
    source_id = _compact(source.get("source_id")).lower()
    title = _compact(source.get("title")).lower()
    if "thread" in source_id or "thread" in title:
        return True
    text = _source_text(source).lower()
    return text.count("from:") >= 2 or text.count("subject:") >= 2


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences.

    Normalizes line breaks to spaces, then splits on sentence-ending punctuation
    followed by whitespace. Strips trailing punctuation from each sentence.
    """
    if not text:
        return []
    normalized = re.sub(r"[\r\n]+", ". ", text)
    parts = re.split(r"(?<=[.!?;])\s+", normalized)
    return [part.strip(" .;") for part in parts if _compact(part)]


def _contains_bounded_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    """Return whether text contains a phrase at regex-compatible word boundaries."""
    normalized = text.casefold()
    for phrase in phrases:
        start = 0
        while (index := normalized.find(phrase, start)) >= 0:
            end = index + len(phrase)
            before_is_word = index > 0 and (normalized[index - 1].isalnum() or normalized[index - 1] == "_")
            after_is_word = end < len(normalized) and (normalized[end].isalnum() or normalized[end] == "_")
            if not before_is_word and not after_is_word:
                return True
            start = index + 1
    return False


def _title_tokens(value: Any) -> set[str]:
    """Extract title tokens from a value.

    Finds all alphabetic tokens of length 4+ and returns them as lowercase strings.
    """
    return {match.group(0).lower() for match in _ALPHA_TOKEN_RE.finditer(_compact(value)) if len(match.group(0)) >= 4}


def _action_tags(text: str) -> list[str]:
    """Extract action tags from text.

    Matches text against predefined action tag keywords and returns matching tags.
    """
    lowered = _compact(text).lower()
    return [action_tag for action_tag, keywords in _ACTION_TAGS.items() if any(keyword in lowered for keyword in keywords)]


def _topic_tokens(text: str) -> set[str]:
    """Extract topic tokens from text.

    Finds all alphabetic tokens of length 3+ that are not stopwords.
    """
    return {
        match.group(0).lower()
        for match in _ALPHA_TOKEN_RE.finditer(_compact(text))
        if len(match.group(0)) >= 3 and match.group(0).lower() not in _TOPIC_STOPWORDS
    }


def _promise_candidates(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract promise candidates from a source.

    Identifies sentences containing promise cues and action tags,
    returning structured promise candidate records.
    Skips stitched thread exports.
    """
    if str(source.get("source_type") or "") not in _PROMISE_SOURCE_TYPES:
        return []
    if _is_stitched_thread_export(source):
        return []
    text = _source_text(source)
    rows: list[dict[str, Any]] = []
    for sentence in _split_sentences(text):
        if not _contains_bounded_phrase(sentence, _PROMISE_CUES):
            continue
        tags = _action_tags(sentence)
        if not tags:
            continue
        rows.append(
            {
                "statement": sentence,
                "action_tags": tags,
                "source_id": str(source.get("source_id") or ""),
                "uid": str(source.get("uid") or ""),
                "actor_id": str(source.get("actor_id") or ""),
                "date": _source_date(source),
                "source_type": str(source.get("source_type") or ""),
                "title": str(source.get("title") or ""),
            }
        )
    return rows


def _related_sources(
    promise: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    source_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find sources related to a promise.

    Identifies related sources based on:
    - Shared UID
    - Explicit source links
    - Shared title tokens (2+ matches)
    - Same actor ID

    Only returns sources dated at or after the promise date.
    Adds _relation_basis and _relation_strength to each related source.
    """
    promise_source_id = str(promise.get("source_id") or "")
    promise_uid = str(promise.get("uid") or "")
    promise_actor_id = str(promise.get("actor_id") or "")
    promise_date = str(promise.get("date") or "")
    promise_date_key = _parse_ordering_datetime(promise_date)
    promise_title_tokens = _title_tokens(promise.get("title"))
    linked_source_ids = _linked_source_ids(promise_source_id, source_links)
    related: list[dict[str, Any]] = []
    for source in sources:
        relation = _related_source(
            source, promise_source_id, promise_uid, promise_actor_id, promise_date_key, promise_title_tokens, linked_source_ids
        )
        if relation:
            related.append(relation)
    return related


def _linked_source_ids(promise_source_id: str, links: list[dict[str, Any]]) -> set[str]:
    linked: set[str] = set()
    for link in links:
        from_id = str(link.get("from_source_id") or "")
        to_id = str(link.get("to_source_id") or "")
        if from_id == promise_source_id and to_id:
            linked.add(to_id)
        if to_id == promise_source_id and from_id:
            linked.add(from_id)
    return linked


def _related_source(source, promise_source_id, promise_uid, promise_actor_id, promise_date_key, promise_title_tokens, linked_ids):
    if str(source.get("source_id") or "") == promise_source_id:
        return None
    if str(source.get("source_type") or "") not in {*_SUMMARY_SOURCE_TYPES, "time_record"}:
        return None
    source_date_key = _parse_ordering_datetime(_source_date(source))
    if promise_date_key is not None and source_date_key is not None and source_date_key < promise_date_key:
        return None
    basis, strength = _relation_basis(source, promise_uid, promise_actor_id, promise_title_tokens, linked_ids)
    return {**source, "_relation_basis": basis, "_relation_strength": strength} if basis else None


def _relation_basis(source, promise_uid, promise_actor_id, promise_title_tokens, linked_ids):
    if promise_uid and str(source.get("uid") or "") == promise_uid:
        return "shared_uid", 3
    if str(source.get("source_id") or "") in linked_ids:
        return "explicit_source_link", 3
    if promise_title_tokens and len(promise_title_tokens & _title_tokens(source.get("title"))) >= 2:
        return "shared_title_tokens", 2
    if promise_actor_id and str(source.get("actor_id") or "") == promise_actor_id:
        return "same_actor_id", 1
    return "", 0


def _matching_action_source(promise: dict[str, Any], related_sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the best matching action source for a promise.

    Looks for related sources with overlapping action tags and either:
    - Topic overlap with the promise statement
    - Explicit source link or shared UID relation
    - Relation strength >= 3

    Returns the first matching source with topic_overlap added, or None.
    """
    action_tags = set(_as_list(promise.get("action_tags")))
    promise_topics = _topic_tokens(str(promise.get("statement") or ""))
    for source in related_sources:
        text = _content_text(source)
        tags = set(_action_tags(text))
        relation_basis = str(source.get("_relation_basis") or "")
        relation_strength = int(source.get("_relation_strength") or 0)
        topic_overlap = sorted(promise_topics & _topic_tokens(text))
        if action_tags & tags and (
            topic_overlap or relation_basis in {"explicit_source_link", "shared_uid"} or relation_strength >= 3
        ):
            source = dict(source)
            source["_topic_overlap"] = topic_overlap
            return source
    return None


def _significance_for_tags(action_tags: list[str]) -> str:
    """Determine the likely significance of a set of action tags.

    Returns a human-readable significance string based on the action tag categories.
    """
    tag_set = set(action_tags)
    if "participation_or_consultation" in tag_set:
        return "May matter for participation, consultation, or prevention-step review."
    if "review_or_decide" in tag_set:
        return "May matter for decision-flow, approval responsibility, or gatekeeper analysis."
    if "include_or_inform" in tag_set:
        return "May matter for whether promised inclusion or notice actually occurred."
    if "schedule_or_meet" in tag_set:
        return "May matter for chronology credibility and whether promised meetings or follow-up steps happened."
    return "May matter for whether promised follow-up or document production actually occurred."


def build_promise_contradiction_analysis(
    *,
    case_bundle: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return source-linked promise, omission, and contradiction analysis."""
    if not isinstance(case_bundle, dict):
        return None

    sources = _dict_rows(_as_dict(multi_source_case_bundle).get("sources"))
    source_links = _dict_rows(_as_dict(multi_source_case_bundle).get("source_links"))
    promises = [candidate for source in sources for candidate in _promise_candidates(source)]
    promise_action_rows: list[dict[str, Any]] = []
    omission_rows: list[dict[str, Any]] = []
    contradiction_rows: list[dict[str, Any]] = []

    _append_promise_rows(promises, sources, source_links, promise_action_rows, omission_rows, contradiction_rows)

    chronology_contradictions = _dict_rows(
        _as_dict(_as_dict(master_chronology).get("summary")).get("sequence_breaks_and_contradictions")
    )
    _append_chronology_contradictions(contradiction_rows, chronology_contradictions)

    contradiction_rows = [row for row in contradiction_rows if _has_locator_pair(row)]
    for rows in (contradiction_rows, omission_rows, promise_action_rows):
        rows.sort(key=_row_id)
    usable_sources = _usable_promise_sources(sources)
    summary_status, insufficiency_reason = _promise_summary_status(
        promise_action_rows, omission_rows, contradiction_rows, usable_sources
    )
    return {
        "version": PROMISE_CONTRADICTION_ANALYSIS_VERSION,
        "summary": {
            "promise_action_row_count": len(promise_action_rows),
            "omission_row_count": len(omission_rows),
            "contradiction_row_count": len(contradiction_rows),
            "status": summary_status,
            "insufficiency_reason": insufficiency_reason,
            "usable_source_count": len(usable_sources),
            "locator_backed_contradiction_count": sum(1 for row in contradiction_rows if _has_locator_pair(row)),
        },
        "promises_vs_actions": promise_action_rows,
        "omission_rows": omission_rows,
        "contradiction_table": contradiction_rows,
    }


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _has_locator_pair(row: dict[str, Any]) -> bool:
    return len([item for item in _as_list(row.get("supporting_locators")) if isinstance(item, dict) and item]) >= 2


def _row_id(row: dict[str, Any]) -> str:
    return str(row.get("row_id") or "")


def _append_promise_rows(promises, sources, source_links, action_rows, omission_rows, contradiction_rows):
    for index, promise in enumerate(promises, start=1):
        related = _related_sources(promise, sources, source_links=source_links)
        matched = _matching_action_source(promise, related)
        if matched is not None:
            action_row, contradiction_row = _matched_promise_rows(index, promise, matched)
            action_rows.append(action_row)
            if contradiction_row:
                contradiction_rows.append(contradiction_row)
        elif related:
            omission_rows.append(_omission_row(index, promise, related))


def _matched_promise_rows(index, promise, matched):
    later_text = _source_text(matched)
    relation_support = bool(_as_list(matched.get("_topic_overlap"))) or _text(matched, "_relation_basis") in {
        "explicit_source_link",
        "shared_uid",
    }
    contradiction = _contains_bounded_phrase(later_text, _NEGATION_CUES) and relation_support
    original_locator, later_locator = _source_locator_payload(promise), _source_locator_payload(matched)
    shared = {
        "original_statement_or_promise": _text(promise, "statement"),
        "later_action": later_text,
        "original_source_id": _text(promise, "source_id"),
        "later_source_id": _text(matched, "source_id"),
        "likely_significance": _significance_for_tags(list(_as_list(promise.get("action_tags")))),
        "supporting_uids": _nonempty_values((promise.get("uid"), matched.get("uid"))),
    }
    action = {
        **shared,
        "row_id": f"promise_action:{index}",
        "confidence_level": _promise_confidence(promise, matched),
        "action_alignment": "apparent_contradiction" if contradiction else "possible_follow_up_match",
        "supporting_locators": _nonempty_locators((original_locator, later_locator)),
    }
    if not contradiction:
        return action, None
    contradiction_row = {
        **shared,
        "row_id": f"contradiction:promise_action:{index}",
        "confidence_level": "medium",
        "contradiction_kind": "promise_vs_later_action",
        "source_locator_pair": {"original": original_locator, "later": later_locator},
        "supporting_locators": _nonempty_locators((original_locator, later_locator)),
    }
    return action, contradiction_row


def _promise_confidence(promise, matched):
    return (
        "high"
        if str(promise.get("source_type") or "") in {"meeting_note", "note_record"} and bool(matched.get("source_weighting"))
        else "medium"
    )


def _omission_row(index, promise, related):
    sources = related[:3]
    locators = [_source_locator_payload(promise), *[_source_locator_payload(source) for source in sources]]
    return {
        "row_id": f"omission:{index}",
        "original_statement_or_promise": _text(promise, "statement"),
        "later_summary_context": (
            "Later related summaries or follow-up records were found, but this promise/action topic was not clearly repeated."
        ),
        "original_source_id": _text(promise, "source_id"),
        "later_source_ids": [source_id for source in related[:4] if (source_id := _text(source, "source_id"))],
        "likely_significance": (
            "May matter if a later summary or follow-up omits a promised step that should have remained visible."
        ),
        "confidence_level": "low",
        "omission_type": "later_summary_omits_prior_promise",
        "supporting_uids": _nonempty_values([promise.get("uid"), *[source.get("uid") for source in sources]]),
        "supporting_locators": _nonempty_locators(locators),
    }


def _append_chronology_contradictions(rows, items):
    for index, item in enumerate(items, start=1):
        original = _as_dict(item.get("source_locator"))
        later = _as_dict(item.get("event_locator"))
        uid = str(item.get("uid") or "")
        rows.append(
            {
                "row_id": f"contradiction:chronology:{index}",
                "original_statement_or_promise": (
                    f"Recorded source date {item.get('source_recorded_date') or ''} "
                    f"differs from extracted event date {item.get('event_date') or ''}."
                ).strip(),
                "later_action": str(item.get("summary") or ""),
                "original_source_id": str(item.get("source_id") or ""),
                "later_source_id": "",
                "likely_significance": "May matter for chronology reliability or later contradiction review.",
                "confidence_level": "medium",
                "contradiction_kind": "source_date_vs_event_date",
                "supporting_uids": [uid] if uid else [],
                "source_locator_pair": {"original": original, "later": {}},
                "supporting_locators": [locator for locator in (original, later) if locator],
            }
        )


def _usable_promise_sources(sources):
    return [
        source
        for source in sources
        if str(source.get("source_type") or "") in _PROMISE_SOURCE_TYPES and not _is_stitched_thread_export(source)
    ]


def _promise_summary_status(action_rows, omission_rows, contradiction_rows, usable_sources):
    if action_rows or omission_rows or contradiction_rows:
        return "supported", ""
    if not usable_sources:
        return (
            "insufficient_source_material",
            "No usable meeting-note, note-record, or comparable follow-up source pair survived "
            "the current record well enough for promise/contradiction analysis.",
        )
    return (
        "insufficient_source_material",
        "No source-linked promise, omission, or contradiction pair was confirmed on the current record.",
    )


def _text(payload: dict[str, Any], key: str) -> str:
    return str(payload.get(key) or "")


def _nonempty_values(values) -> list[str]:
    return [str(value) for value in values if _compact(value)]


def _nonempty_locators(values) -> list[dict[str, Any]]:
    return [value for value in values if value]
